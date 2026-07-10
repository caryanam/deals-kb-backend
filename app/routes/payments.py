import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.config import (
    CASHFREE_API_VERSION,
    CASHFREE_APP_ID,
    CASHFREE_BASE_URL,
    CASHFREE_ENV,
    CASHFREE_SECRET_KEY,
)
from app.database import get_db
from app.models import PaymentFailIn, PaymentOrderCreate, PaymentVerifyIn
from app.models_sql import PaymentTransaction, User
from app.serializers import serialize_payment
from app.services.payment_plans import PAYMENT_PLANS, plans_for_user, user_plan_status
from app.utils import now_utc

router = APIRouter(prefix="/payments", tags=["payments"])


def _cashfree_credentials():
    return CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_ENV, CASHFREE_BASE_URL, CASHFREE_API_VERSION


def _require_cashfree_config():
    app_id, secret_key, *_ = _cashfree_credentials()
    if not app_id or not secret_key:
        raise HTTPException(status_code=500, detail="Cashfree credentials are not configured")


def _log_cashfree_config():
    app_id, secret_key, mode, base_url, api_version = _cashfree_credentials()
    print("CASHFREE_APP_ID:", app_id, flush=True)
    print("CASHFREE_ENV:", mode, flush=True)
    print("CASHFREE_BASE_URL:", base_url, flush=True)
    print("CASHFREE_API_VERSION:", api_version, flush=True)
    print("CASHFREE_SECRET_KEY loaded:", bool(secret_key), flush=True)
    print("CASHFREE_SECRET_KEY length:", len(secret_key or ""), flush=True)


def _cashfree_headers():
    app_id, secret_key, _, _, api_version = _cashfree_credentials()
    return {
        "Content-Type": "application/json",
        "x-client-id": app_id,
        "x-client-secret": secret_key,
        "x-api-version": api_version,
    }


def _amount_rupees(amount_paise: int) -> float:
    return round(amount_paise / 100, 2)


def _normalize_phone(mobile_number: str | None) -> str:
    digits = "".join(ch for ch in str(mobile_number or "") if ch.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return "9999999999"


def _is_cashfree_paid(order: dict) -> bool:
    return str(order.get("order_status") or "").upper() == "PAID"


async def create_cashfree_order(*, amount_paise: int, currency: str, user: User, order_tags: dict | None = None) -> dict:
    _require_cashfree_config()
    _log_cashfree_config()
    _, _, _, base_url, _ = _cashfree_credentials()

    order_id = f"cf_{uuid.uuid4().hex[:22]}"
    payload = {
        "order_id": order_id,
        "order_currency": currency,
        "order_amount": _amount_rupees(amount_paise),
        "customer_details": {
            "customer_id": user.user_id,
            "customer_name": user.name or "DealsKB User",
            "customer_email": user.email or "support@dealskb.com",
            "customer_phone": _normalize_phone(user.mobile_number),
        },
        "order_note": f"DealsKB payment for {order_tags.get('plan_id') if order_tags else 'platform service'}",
    }
    if order_tags:
        payload["order_tags"] = order_tags

    print("Cashfree order create payload:", payload, flush=True)

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{base_url}/orders",
            json=payload,
            headers=_cashfree_headers(),
        )

    print("Cashfree order create status:", response.status_code, flush=True)
    print("Cashfree order create response:", response.text, flush=True)
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Cashfree order creation failed: {response.text}")

    return response.json()


async def fetch_cashfree_order(order_id: str) -> dict:
    _require_cashfree_config()
    _, _, _, base_url, _ = _cashfree_credentials()

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{base_url}/orders/{order_id}",
            headers=_cashfree_headers(),
        )

    print("Cashfree get order status:", response.status_code, flush=True)
    print("Cashfree get order response:", response.text, flush=True)
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Cashfree order verification failed: {response.text}")

    return response.json()


def _find_payment_by_any_order_id(db: Session, user_id: str, body: PaymentFailIn):
    order_id = body.cashfree_order_id or body.order_id
    if not order_id:
        raise HTTPException(status_code=400, detail="order_id is required")

    payment = db.query(PaymentTransaction).filter(
        PaymentTransaction.user_id == user_id,
    ).filter(
        PaymentTransaction.cashfree_order_id == order_id
    ).first()
    return order_id, payment


@router.get("/config")
def payment_config(user: User = Depends(auth_required)):
    app_id, _, mode, _, _ = _cashfree_credentials()
    return {
        "gateway": "cashfree",
        "app_id": app_id,
        "mode": mode,
        "currency": "INR",
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
    order = await create_cashfree_order(
        amount_paise=plan["amount"],
        currency=plan.get("currency") or "INR",
        user=user,
        order_tags={
            "user_id": user.user_id,
            "role": user.role,
            "plan_id": plan["plan_id"],
        },
    )

    payment = PaymentTransaction(
        payment_id=f"paytxn_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        user_role=user.role,
        plan_id=plan["plan_id"],
        plan_name=plan["name"],
        amount=plan["amount"],
        currency=order.get("order_currency") or plan.get("currency") or "INR",
        payment_gateway="cashfree",
        cashfree_order_id=order["order_id"],
        cashfree_payment_session_id=order.get("payment_session_id"),
        cashfree_order_status=order.get("order_status"),
        status="created",
        receipt=receipt,
        notes={
            "plan_id": plan["plan_id"],
            "product_type": plan.get("product_type"),
            "product_types": plan.get("product_types"),
        },
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    print(
        "DB payment created:",
        {"payment_id": payment.payment_id, "cashfree_order_id": payment.cashfree_order_id, "status": payment.status},
        flush=True,
    )

    return {
        "gateway": "cashfree",
        "cashfree_mode": CASHFREE_ENV,
        "order_id": order["order_id"],
        "orderId": order["order_id"],
        "payment_session_id": order.get("payment_session_id"),
        "paymentSessionId": order.get("payment_session_id"),
        "amount": payment.amount,
        "currency": payment.currency,
        "order_status": order.get("order_status"),
        "orderStatus": order.get("order_status"),
        "payment": serialize_payment(payment),
    }


@router.post("/create-plan-order")
async def create_plan_payment_order(
    body: PaymentOrderCreate,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    return await create_payment_order(body, user, db)


@router.post("/verify")
async def verify_payment(
    body: PaymentVerifyIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    cashfree_order_id = body.cashfree_order_id
    if not cashfree_order_id:
        raise HTTPException(status_code=400, detail="cashfree_order_id is required")

    print("Cashfree verify request:", {"cashfree_order_id": cashfree_order_id}, flush=True)
    payment = db.query(PaymentTransaction).filter(
        PaymentTransaction.cashfree_order_id == cashfree_order_id,
        PaymentTransaction.user_id == user.user_id,
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment order not found")
    if payment.status == "paid":
        return {"message": "Payment already verified", "payment": serialize_payment(payment)}

    order = await fetch_cashfree_order(cashfree_order_id)
    payment.cashfree_order_status = order.get("order_status")
    payment.updated_at = now_utc().replace(tzinfo=None)

    print("Cashfree order status:", payment.cashfree_order_status, flush=True)

    if not _is_cashfree_paid(order):
        db.commit()
        raise HTTPException(status_code=400, detail=f"Payment not completed. Current status: {payment.cashfree_order_status}")

    payment.status = "paid"
    payment.paid_at = now_utc().replace(tzinfo=None)
    db.commit()
    db.refresh(payment)
    print(
        "DB payment update result:",
        {"payment_id": payment.payment_id, "status": payment.status, "paid_at": str(payment.paid_at)},
        flush=True,
    )
    return {"message": "Payment verified successfully", "payment": serialize_payment(payment)}


@router.post("/verify-plan-payment")
async def verify_plan_payment(
    body: PaymentVerifyIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    return await verify_payment(body, user, db)


@router.post("/mark-failed")
def mark_payment_failed(
    body: PaymentFailIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    order_id, payment = _find_payment_by_any_order_id(db, user.user_id, body)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment order not found")
    if payment.status == "paid":
        return {"message": "Payment already paid", "payment": serialize_payment(payment)}

    payment.status = "failed"
    payment.updated_at = now_utc().replace(tzinfo=None)
    if payment.cashfree_order_id == order_id:
        payment.cashfree_order_status = "FAILED"
    notes = payment.notes or {}
    notes["failure_reason"] = body.reason or "Payment cancelled or failed"
    payment.notes = notes
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
