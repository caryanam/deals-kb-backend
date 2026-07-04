from datetime import timedelta
from typing import List, Optional

import jwt
from fastapi import Depends, Header, HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import JWT_ALGO, JWT_EXPIRES_DAYS, JWT_SECRET
from app.database import get_db
from app.models_sql import User, UserSession
from app.utils import now_utc

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_jwt(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": now_utc() + timedelta(days=JWT_EXPIRES_DAYS),
        "iat": now_utc(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def get_user_from_token(token: str, db: Session) -> Optional[User]:
    if not token:
        return None

    user_id = None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if not session:
            session = db.query(UserSession).filter(UserSession.session_id == token).first()
        if not session:
            return None
        if session.expires_at and session.expires_at < now_utc().replace(tzinfo=None):
            return None
        user_id = session.user_id

    if not user_id:
        return None
    return db.query(User).filter(User.user_id == user_id).first()


def auth_required(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.replace("Bearer ", "").strip()
    user = get_user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def role_required(roles: List[str]):
    def checker(user: User = Depends(auth_required)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def is_seller_like(user: User) -> bool:
    return bool(user and user.role in ("Seller", "Dealer"))
