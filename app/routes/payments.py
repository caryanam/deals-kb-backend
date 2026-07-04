import hashlib
import hmac
import uuid

import httpx
from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.config import RAZORPAY_CURRENCY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, ROOT_DIR
from app.database import get_db
from app.models import PaymentFailIn, PaymentOrderCreate, PaymentVerifyIn
from app.models_sql import PaymentTransaction, User
from app.serializers import serialize_payment
from app.services.payment_plans import PAYMENT_PLANS, plans_for_user, user_plan_status
from app.utils import now_utc

router = APIRouter(prefix="/payments", tags=["payments"])

def _razorpay_credentials():
    env_values = dotenv_values(ROOT_DIR / ".env")
    key_id = env_values.get("RAZORPAY_KEY_ID") or RAZORPAY_KEY_ID
    key_secret = env_values.get("RAZORPAY_KEY_SECRET") or RAZORPAY_KEY_SECRET
    currency = env_values.get("RAZORPAY_CURRENCY") or RAZORPAY_CURRENCY
    return key_id, key_secret, currency


def _require_razorpay_config():
    key_id, key_secret, _ = _razorpay_credentials()
    if not key_id or not key_secret:
        raise HTTPException(status_code=500, detail="Razorpay credentials are not configured")


def _log_razorpay_config():
    key_id, key_secret, _ = _razorpay_credentials()
    print("RAZORPAY_KEY_ID:", key_id, flush=True)
    print("RAZORPAY_KEY_SECRET loaded:", bool(key_secret), flush=True)
    print("RAZORPAY_KEY_SECRET length:", len(key_secret or ""), flush=True)


def _verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    _, key_secret, _ = _razorpay_credentials()
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(key_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.get("/config")
def payment_config(user: User = Depends(auth_required)):
    key_id, _, currency = _razorpay_credentials()
    return {
        "key_id": key_id,
        "currency": currency,
    }


@router.get("/plans")
def list_payment_plans(user: User = Depends(auth_required)):
    return plans_for_user(user)


@router.get("/plans/my")
def list_my_payment_plans(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    return user_plan_status(db, user)


@router.post("/create-order")
async def create_payment_order(
    body: PaymentOrderCreate,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    _require_razorpay_config()
    _log_razorpay_config()
    key_id, key_secret, currency = _razorpay_credentials()
    if user.role not in ("Buyer", "Seller", "Dealer"):
        raise HTTPException(status_code=403, detail="Payments are available only for buyer, seller, or dealer accounts")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Blocked users cannot make payments")

    plan = PAYMENT_PLANS.get(body.plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid payment plan")
    if user.role not in plan.get("roles", [plan["role"]]):
        raise HTTPException(status_code=403, detail="This payment plan is not available for your role")

    receipt = f"rcpt_{uuid.uuid4().hex[:28]}"
    payload = {
        "amount": plan["amount"],
        "currency": plan.get("currency") or currency,
        "receipt": receipt,
        "notes": {
            "user_id": user.user_id,
            "role": user.role,
            "plan_id": plan["plan_id"],
        },
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.razorpay.com/v1/orders",
            json=payload,
            auth=(key_id, key_secret),
        )

    if response.status_code >= 400:
        print("Razorpay status:", response.status_code, flush=True)
        print("Razorpay response:", response.text, flush=True)
        raise HTTPException(
            status_code=400,
            detail=f"Razorpay order creation failed: {response.text}",
        )

    order = response.json()
    payment = PaymentTransaction(
        payment_id=f"paytxn_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        user_role=user.role,
        plan_id=plan["plan_id"],
        plan_name=plan["name"],
        amount=plan["amount"],
        currency=payload["currency"],
        razorpay_order_id=order["id"],
        status="created",
        receipt=receipt,
        notes=payload["notes"],
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return {
        "key_id": key_id,
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "order": order,
        "payment": serialize_payment(payment),
        "prefill": {
            "name": user.name or "",
            "email": user.email,
            "contact": user.mobile_number,
        },
    }


@router.post("/create-plan-order")
async def create_plan_payment_order(
    body: PaymentOrderCreate,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    return await create_payment_order(body, user, db)


@router.post("/verify")
def verify_payment(
    body: PaymentVerifyIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    _require_razorpay_config()
    payment = db.query(PaymentTransaction).filter(
        PaymentTransaction.razorpay_order_id == body.razorpay_order_id,
        PaymentTransaction.user_id == user.user_id,
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment order not found")
    if payment.status == "paid":
        return {"message": "Payment already verified", "payment": serialize_payment(payment)}

    if not _verify_signature(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature):
        payment.status = "failed"
        payment.updated_at = now_utc().replace(tzinfo=None)
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    payment.razorpay_payment_id = body.razorpay_payment_id
    payment.razorpay_signature = body.razorpay_signature
    payment.status = "paid"
    payment.paid_at = now_utc().replace(tzinfo=None)
    payment.updated_at = now_utc().replace(tzinfo=None)
    db.commit()
    db.refresh(payment)
    return {"message": "Payment verified successfully", "payment": serialize_payment(payment)}


@router.post("/verify-plan-payment")
def verify_plan_payment(
    body: PaymentVerifyIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    return verify_payment(body, user, db)


@router.post("/mark-failed")
def mark_payment_failed(
    body: PaymentFailIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    payment = db.query(PaymentTransaction).filter(
        PaymentTransaction.razorpay_order_id == body.razorpay_order_id,
        PaymentTransaction.user_id == user.user_id,
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment order not found")
    if payment.status == "paid":
        return {"message": "Payment already paid", "payment": serialize_payment(payment)}

    payment.status = "failed"
    notes = payment.notes or {}
    notes["failure_reason"] = body.reason or "Payment cancelled or failed"
    payment.notes = notes
    payment.updated_at = now_utc().replace(tzinfo=None)
    db.commit()
    db.refresh(payment)
    return {"message": "Payment marked as failed", "payment": serialize_payment(payment)}


@router.get("/my")
def my_payments(
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    payments = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.user_id == user.user_id)
        .order_by(PaymentTransaction.created_at.desc())
        .limit(200)
        .all()
    )
    return [serialize_payment(payment) for payment in payments]
