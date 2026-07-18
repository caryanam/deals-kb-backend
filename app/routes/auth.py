import uuid
import random
import re
import logging
import threading
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import auth_required, create_jwt, pwd_context
from app.config import APP_ENV
from app.core.security import create_access_token, verify_access_token
from app.database import get_db
from app.models import (
    ForgotPasswordOtpIn,
    GoogleSessionIn,
    LoginIn,
    DeleteAccountConfirmIn,
    DeleteAccountVerifyIn,
    RegisterIn,
    RegistrationOtpIn,
    ResetPasswordIn,
    VerifyForgotPasswordOtpIn,
    VerifyRegistrationOtpIn,
)
from app.models_sql import Buyer, Dealer, MobileVerificationOTP, RegistrationOTP, Seller, User, UserSession
from app.serializers import serialize_user
from app.services.email import send_otp_email
from app.services.notifications import notify_admins
from app.services.otp_cache import (
    RegistrationOtpCacheEntry,
    delete_registration_otp,
    get_registration_otp,
    set_registration_otp,
)
from app.services.users import next_role_user_id, sync_role_profile
from app.utils import now_utc

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("dealskb")
REGISTRATION_ROLES = ("Buyer", "Seller", "Dealer")
INVALID_DELETE_CREDENTIALS = {
    "success": False,
    "message": "Invalid email/mobile number or password.",
}


def new_password_matches_current(new_password: str, current_hash: str | None) -> bool:
    if not current_hash:
        return False

    candidates = {new_password, new_password.strip()}
    for candidate in candidates:
        if not candidate:
            continue
        try:
            if pwd_context.verify(candidate, current_hash):
                return True
        except Exception:
            logger.exception("Unable to verify current password while resetting password")
            raise HTTPException(status_code=500, detail="Unable to verify current password. Please try again.")
    return False


def normalize_mobile(mobile_number: str | None) -> str | None:
    return mobile_number.strip() if mobile_number else None


def validate_full_name_backend(name: str | None) -> str | None:
    if not name:
        return "Full Name is required."
    trimmed = name.strip()
    if len(trimmed) < 2:
        return "Full name must contain at least 2 characters."
    
    # Allow letters, spaces, apostrophes, hyphens, and periods.
    # Reject digits-only or spaces-only names.
    if not re.fullmatch(r"[a-zA-Z\s'\-\.]+", trimmed):
        return "Full name must contain only letters, spaces, apostrophes, hyphens, or periods."
    return None


def validate_password_strength_backend(password: str | None) -> str | None:
    if not password:
        return "Password is required."
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if " " in password:
        return "Password must not contain spaces."
    # Require at least one uppercase, lowercase, digit, and special char
    pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#^()_\-+=])[^\s]{8,}$"
    if not re.match(pattern, password):
        return "Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character."
    return None


def validate_indian_mobile(mobile_number: str | None):
    if mobile_number and not re.fullmatch(r"[6-9]\d{9}", mobile_number):
        raise HTTPException(status_code=400, detail="mobile_number must be a valid 10-digit Indian mobile number")


def resolve_user_by_identifier(
    db: Session,
    identifier: str | None = None,
    email: str | None = None,
    mobile_number: str | None = None,
) -> User:
    raw_identifier = (identifier or email or mobile_number or "").strip()
    if not raw_identifier:
        raise HTTPException(status_code=400, detail="Enter mobile or email")

    if "@" in raw_identifier:
        user = db.query(User).filter(User.email == raw_identifier.lower()).first()
    else:
        mobile = normalize_mobile(raw_identifier)
        validate_indian_mobile(mobile)
        user = db.query(User).filter(User.mobile_number == mobile).first()

    if not user:
        raise HTTPException(status_code=404, detail="Account does not exist.")
    if getattr(user, "is_deleted", False) or getattr(user, "is_active", True) is False:
        raise HTTPException(status_code=404, detail="Account does not exist.")
    if user.auth_provider != "email":
        raise HTTPException(status_code=400, detail="Password reset is available only for password accounts.")
    return user


def create_deletion_confirmation_token(user: User) -> str:
    return create_access_token(
        {
            "sub": user.user_id,
            "email": user.email,
            "role": user.role,
            "purpose": "account_deletion",
        },
        expires_delta=timedelta(minutes=5),
    )


def delete_user_account(db: Session, user: User):
    original_email = user.email
    original_mobile = user.mobile_number

    db.query(UserSession).filter(UserSession.user_id == user.user_id).delete(synchronize_session=False)
    db.query(MobileVerificationOTP).filter(
        or_(
            MobileVerificationOTP.user_id == user.user_id,
            MobileVerificationOTP.email == original_email,
            MobileVerificationOTP.mobile_number == original_mobile,
        )
    ).delete(synchronize_session=False)
    db.query(RegistrationOTP).filter(
        or_(
            RegistrationOTP.email == original_email,
            RegistrationOTP.mobile_number == original_mobile,
        )
    ).delete(synchronize_session=False)
    db.query(Buyer).filter(Buyer.user_id == user.user_id).delete(synchronize_session=False)
    db.query(Seller).filter(Seller.user_id == user.user_id).delete(synchronize_session=False)
    db.query(Dealer).filter(Dealer.user_id == user.user_id).delete(synchronize_session=False)
    db.delete(user)


def generate_otp() -> str:
    return f"{random.randint(100000, 999999)}"


def send_forgot_password_otp_email_background(email: str, otp: str):
    try:
        send_otp_email(email, otp, "forgot_password")
        logger.info("Forgot password OTP email sent to %s", email)
    except Exception:
        logger.exception("Failed to send forgot password OTP email to %s", email)


def create_user(db: Session, email: str | None, password_hash: str, name: str, role: str, mobile_number: str | None):
    user = User(
        user_id=next_role_user_id(db, role),
        email=email.lower() if email else None,
        name=name,
        role=role,
        mobile_number=mobile_number,
        password_hash=password_hash,
        auth_provider="email",
    )
    db.add(user)
    sync_role_profile(db, user)
    notify_admins(
        db,
        title=f"New {role} registered",
        message=f"{name} registered as {role}.",
        notif_type=f"new_{role.lower()}_registered",
    )
    return user


def active_user_query(db: Session):
    return db.query(User).filter(User.is_deleted.is_(False), User.is_active.is_(True))


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    raise HTTPException(status_code=400, detail="Use email OTP registration flow")
    if body.role not in REGISTRATION_ROLES:
        raise HTTPException(status_code=400, detail="Role must be Buyer, Seller, or Dealer")
    if not body.email:
        raise HTTPException(status_code=400, detail="Email is required")
    mobile_number = normalize_mobile(body.mobile_number)
    validate_indian_mobile(mobile_number)

    if body.email and active_user_query(db).filter(User.email == body.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if mobile_number and active_user_query(db).filter(User.mobile_number == mobile_number).first():
        raise HTTPException(status_code=400, detail="Mobile number already registered")

    user = create_user(db, body.email, pwd_context.hash(body.password), body.name, body.role, mobile_number)
    db.commit()
    db.refresh(user)

    return {"access_token": create_jwt(user.user_id, user.role, user.email), "token_type": "bearer", "user": serialize_user(user)}


@router.post("/send-registration-otp")
def send_registration_otp(body: RegistrationOtpIn, db: Session = Depends(get_db)):
    if body.role not in REGISTRATION_ROLES:
        raise HTTPException(status_code=400, detail="Role must be Buyer, Seller, or Dealer")
    name_error = validate_full_name_backend(body.name)
    if name_error:
        raise HTTPException(status_code=400, detail=name_error)
    email = body.email.lower() if body.email else None
    if not email:
        raise HTTPException(status_code=400, detail="Email is required to send OTP")
    if email and active_user_query(db).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    now = now_utc().replace(tzinfo=None)
    latest_otp = db.query(RegistrationOTP).filter(
        RegistrationOTP.email == email,
    ).order_by(RegistrationOTP.created_at.desc()).first()
    if latest_otp and latest_otp.created_at:
        elapsed_seconds = (now - latest_otp.created_at).total_seconds()
        if 0 <= elapsed_seconds < 30:
            wait_seconds = max(1, int(30 - elapsed_seconds))
            raise HTTPException(status_code=429, detail=f"Please wait {wait_seconds} seconds before resending OTP")

    otp = generate_otp()
    if APP_ENV != "production":
        print(f"\n=== REGISTRATION OTP for {email}: {otp} ===\n", flush=True)
        logger.warning("Registration OTP for %s is %s", email, otp)
    try:
        send_otp_email(email, otp, "registration")
        logger.info("Registration OTP email sent to %s", email)
    except Exception as exc:
        logger.exception("Failed to send registration OTP email to %s", email)
        raise HTTPException(status_code=502, detail=f"Failed to send OTP email: {exc}") from exc
    db.query(RegistrationOTP).filter(
        RegistrationOTP.email == email,
    ).delete()
    delete_registration_otp(email=email)
    db.add(RegistrationOTP(
        otp_id=f"rotp_{uuid.uuid4().hex[:12]}",
        email=email,
        mobile_number=None,
        name=body.name,
        role=body.role,
        password_hash="",
        otp=otp,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    ))
    set_registration_otp(RegistrationOtpCacheEntry(
        email=email,
        mobile_number=None,
        name=body.name,
        role=body.role,
        password_hash=None,
        otp=otp,
        expires_at=now + timedelta(minutes=5),
    ))
    db.commit()

    response = {"message": "OTP sent successfully to email"}
    if APP_ENV != "production":
        response["dev_otp"] = otp
    return response


@router.post("/check-registration-otp")
def check_registration_otp(body: VerifyRegistrationOtpIn, db: Session = Depends(get_db)):
    email = body.email.lower() if body.email else None
    if not email:
        raise HTTPException(status_code=400, detail="Email is required to verify OTP")
    now = now_utc().replace(tzinfo=None)
    otp_record = get_registration_otp(
        otp=body.otp.strip(),
        email=email,
        now=now,
    )
    if not otp_record:
        db_otp = db.query(RegistrationOTP).filter(
            RegistrationOTP.email == email,
            RegistrationOTP.otp == body.otp.strip(),
        ).order_by(RegistrationOTP.created_at.desc()).first()
        if db_otp and db_otp.expires_at >= now:
            otp_record = RegistrationOtpCacheEntry(
                email=db_otp.email,
                mobile_number=db_otp.mobile_number or None,
                name=db_otp.name,
                role=db_otp.role,
                password_hash=db_otp.password_hash,
                otp=db_otp.otp,
                expires_at=db_otp.expires_at,
            )
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    if active_user_query(db).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    return {"message": "Email OTP verified successfully"}


@router.post("/verify-registration-otp")
def verify_registration_otp(body: VerifyRegistrationOtpIn, db: Session = Depends(get_db)):
    mobile_number = normalize_mobile(body.mobile_number)
    email = body.email.lower() if body.email else None
    if not email:
        raise HTTPException(status_code=400, detail="Email is required to verify OTP")
    
    name_error = validate_full_name_backend(body.name)
    if name_error:
        raise HTTPException(status_code=400, detail=name_error)
        
    if not body.role or body.role not in REGISTRATION_ROLES:
        raise HTTPException(status_code=400, detail="Role must be Buyer, Seller, or Dealer")
        
    password_error = validate_password_strength_backend(body.password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)
        
    validate_indian_mobile(mobile_number)
    now = now_utc().replace(tzinfo=None)
    otp_record = get_registration_otp(
        mobile_number,
        otp=body.otp.strip(),
        email=email,
        now=now,
    )
    if not otp_record:
        query = db.query(RegistrationOTP).filter(
            RegistrationOTP.email == email,
            RegistrationOTP.otp == body.otp.strip(),
        )
        if mobile_number:
            query = query.filter(or_(RegistrationOTP.mobile_number == mobile_number, RegistrationOTP.mobile_number.is_(None)))
        db_otp = query.order_by(RegistrationOTP.created_at.desc()).first()
        if db_otp and db_otp.expires_at >= now:
            otp_record = RegistrationOtpCacheEntry(
                email=db_otp.email,
                mobile_number=db_otp.mobile_number or None,
                name=db_otp.name,
                role=db_otp.role,
                password_hash=db_otp.password_hash,
                otp=db_otp.otp,
                expires_at=db_otp.expires_at,
            )
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    if otp_record.email and active_user_query(db).filter(User.email == otp_record.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if mobile_number and active_user_query(db).filter(User.mobile_number == mobile_number).first():
        raise HTTPException(status_code=400, detail="Mobile number already registered")

    user = create_user(
        db,
        email=email,
        password_hash=pwd_context.hash(body.password),
        name=body.name.strip(),
        role=body.role,
        mobile_number=mobile_number,
    )
    delete_registration_otp(mobile_number, email=email)
    db.query(RegistrationOTP).filter(
        RegistrationOTP.email == email,
    ).delete()
    db.commit()
    db.refresh(user)
    return {"access_token": create_jwt(user.user_id, user.role, user.email), "token_type": "bearer", "user": serialize_user(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = None
    password = (body.password or "").strip()
    if body.mobile_number:
        mobile_number = normalize_mobile(body.mobile_number)
        validate_indian_mobile(mobile_number)
        user = db.query(User).filter(User.mobile_number == mobile_number).first()
    elif body.email:
        user = db.query(User).filter(User.email == body.email.lower()).first()
    else:
        raise HTTPException(status_code=400, detail="Email or mobile_number is required")
    if not user or user.auth_provider != "email":
        raise HTTPException(status_code=400, detail="Invalid email/mobile number or password")
    if not password or not pwd_context.verify(password, user.password_hash or ""):
        raise HTTPException(status_code=400, detail="Invalid email/mobile number or password")
    if getattr(user, "is_deleted", False) or getattr(user, "is_active", True) is False:
        raise HTTPException(status_code=403, detail="This account has been deleted or disabled.")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Your account has been blocked. Please contact support.")

    return {"access_token": create_jwt(user.user_id, user.role, user.email), "token_type": "bearer", "user": serialize_user(user)}


@router.post("/delete-account/verify")
def verify_account_for_deletion(body: DeleteAccountVerifyIn, db: Session = Depends(get_db)):
    identifier = (body.identifier or "").strip()
    password = (body.password or "").strip()
    if not identifier or not password:
        return JSONResponse(status_code=401, content=INVALID_DELETE_CREDENTIALS)

    if "@" in identifier:
        user = db.query(User).filter(User.email == identifier.lower()).first()
    else:
        lookup_mobile = normalize_mobile(identifier)
        user = db.query(User).filter(User.mobile_number == lookup_mobile).first()
    if (
        not user
        or getattr(user, "is_deleted", False)
        or getattr(user, "is_active", True) is False
        or user.auth_provider != "email"
        or not pwd_context.verify(password, user.password_hash or "")
    ):
        return JSONResponse(status_code=401, content=INVALID_DELETE_CREDENTIALS)

    if user.role == "Admin":
        return JSONResponse(status_code=403, content={"success": False, "message": "Admin accounts cannot be deleted."})

    return {
        "success": True,
        "message": "Account verified. Please confirm account deletion.",
        "confirmationToken": create_deletion_confirmation_token(user),
        "expiresInSeconds": 300,
    }


@router.delete("/delete-account/confirm")
def confirm_account_deletion(body: DeleteAccountConfirmIn, db: Session = Depends(get_db)):
    if body.confirmation != "DELETE":
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Account deletion confirmation has expired. Please verify again."},
        )

    try:
        payload = verify_access_token((body.confirmationToken or "").strip())
    except HTTPException:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Account deletion confirmation has expired. Please verify again."},
        )

    if payload.get("purpose") != "account_deletion":
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Account deletion confirmation has expired. Please verify again."},
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or getattr(user, "is_deleted", False):
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Account does not exist or has already been deleted."},
        )
    if user.role == "Admin":
        return JSONResponse(status_code=403, content={"success": False, "message": "Admin accounts cannot be deleted."})

    try:
        delete_user_account(db, user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"success": True, "message": "Your account has been deleted successfully."}


@router.post("/forgot-password/send-otp")
def forgot_password_send_otp(
    body: ForgotPasswordOtpIn,
    db: Session = Depends(get_db),
):
    user = resolve_user_by_identifier(db, body.identifier, body.email, body.mobile_number)
    mobile_number = normalize_mobile(user.mobile_number)

    db.query(MobileVerificationOTP).filter(
        MobileVerificationOTP.user_id == user.user_id,
        MobileVerificationOTP.purpose == "forgot_password",
        MobileVerificationOTP.expires_at < now_utc().replace(tzinfo=None),
    ).delete()
    otp = generate_otp()
    if APP_ENV != "production":
        print(f"\n=== FORGOT PASSWORD OTP for {mobile_number} / {user.email}: {otp} ===\n", flush=True)
        logger.warning("Forgot password OTP for %s / %s is %s", mobile_number, user.email, otp)
    reset = MobileVerificationOTP(
        verification_id=f"motp_{uuid.uuid4().hex[:12]}",
        purpose="forgot_password",
        user_id=user.user_id,
        email=user.email,
        mobile_number=mobile_number,
        otp=otp,
        expires_at=now_utc().replace(tzinfo=None) + timedelta(minutes=5),
    )
    db.add(reset)
    db.commit()
    threading.Thread(
        target=send_forgot_password_otp_email_background,
        args=(user.email, otp),
        daemon=True,
    ).start()

    response = {"message": "OTP sent successfully to email"}
    if APP_ENV != "production":
        response["dev_otp"] = otp
    return response


@router.post("/forgot-password/verify-otp")
def forgot_password_verify_otp(body: VerifyForgotPasswordOtpIn, db: Session = Depends(get_db)):
    user = resolve_user_by_identifier(db, body.identifier, body.email, body.mobile_number)
    now = now_utc().replace(tzinfo=None)
    reset = db.query(MobileVerificationOTP).filter(
        MobileVerificationOTP.user_id == user.user_id,
        MobileVerificationOTP.purpose == "forgot_password",
        MobileVerificationOTP.otp == body.otp.strip(),
        MobileVerificationOTP.expires_at >= now,
    ).order_by(MobileVerificationOTP.created_at.desc()).first()
    if not reset:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    reset.is_verified = True
    reset.reset_token = f"reset_{uuid.uuid4().hex}"
    reset.expires_at = now_utc().replace(tzinfo=None) + timedelta(minutes=10)
    db.commit()
    return {"message": "OTP verified successfully", "reset_token": reset.reset_token}


@router.post("/forgot-password/reset")
def forgot_password_reset(body: ResetPasswordIn, db: Session = Depends(get_db)):
    user = resolve_user_by_identifier(db, body.identifier, body.email)
    reset = db.query(MobileVerificationOTP).filter(
        MobileVerificationOTP.user_id == user.user_id,
        MobileVerificationOTP.reset_token == body.reset_token,
        MobileVerificationOTP.is_verified.is_(True),
        MobileVerificationOTP.purpose == "forgot_password",
    ).first()
    if not reset:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    if reset.expires_at < now_utc().replace(tzinfo=None):
        db.delete(reset)
        db.commit()
        raise HTTPException(status_code=400, detail="Reset token expired")

    new_password = (body.new_password or "").strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    if new_password_matches_current(new_password, user.password_hash):
        logger.info("Rejected password reset because new password matches current password for user_id=%s", user.user_id)
        raise HTTPException(status_code=400, detail="New password cannot be the same as your current password")

    user.password_hash = pwd_context.hash(new_password)
    db.query(MobileVerificationOTP).filter(
        MobileVerificationOTP.user_id == user.user_id,
        MobileVerificationOTP.purpose == "forgot_password",
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "Password reset successfully"}


@router.post("/google/session")
async def google_session(body: GoogleSessionIn, db: Session = Depends(get_db)):
    async with httpx.AsyncClient(timeout=15) as http:
        response = await http.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": body.session_token},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google session")
        data = response.json()

    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=400, detail="No email returned from Google")

    name = data.get("name") or email.split("@")[0]
    session_token = data.get("session_token") or body.session_token

    user = db.query(User).filter(User.email == email).first()
    if not user:
        role = body.role if body.role in REGISTRATION_ROLES else "Buyer"
        user = User(
            user_id=next_role_user_id(db, role),
            email=email,
            name=name,
            role=role,
            auth_provider="google",
        )
        db.add(user)
        sync_role_profile(db, user)
        db.commit()
        db.refresh(user)
    else:
        sync_role_profile(db, user)

    session = db.query(UserSession).filter(UserSession.session_id == session_token).first()
    if not session:
        session = UserSession(session_id=session_token, token=session_token, user_id=user.user_id)
        db.add(session)
    session.user_id = user.user_id
    session.token = session_token
    session.expires_at = now_utc().replace(tzinfo=None) + timedelta(days=7)
    db.commit()

    return {"access_token": session_token, "user": serialize_user(user)}


@router.get("/me")
def me(user: User = Depends(auth_required)):
    return serialize_user(user)


@router.post("/logout")
def logout(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if session:
            db.delete(session)
            db.commit()
    return {"ok": True}
