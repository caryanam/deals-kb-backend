from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.database import get_db
from app.models import PaymentFailIn, PaymentOrderCreate, PaymentVerifyIn
from app.models_sql import PaymentTransaction, User
from app.serializers import serialize_payment
from app.utils import now_utc

router = APIRouter(prefix="/payments", tags=["payments"])

PAYMENTS_DISABLED_MESSAGE = "Payments and bidding passes are temporarily disabled."


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
    return {
        "enabled": False,
        "gateway": None,
        "mode": "disabled",
        "currency": "INR",
        "message": PAYMENTS_DISABLED_MESSAGE,
    }


@router.get("/plans")
def list_payment_plans(user: User = Depends(auth_required)):
    return []


@router.get("/plans/my")
def list_my_payment_plans(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    return []


@router.post("/create-order")
async def create_payment_order(
    body: PaymentOrderCreate,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail=PAYMENTS_DISABLED_MESSAGE)


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
    raise HTTPException(status_code=410, detail=PAYMENTS_DISABLED_MESSAGE)


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
    raise HTTPException(status_code=410, detail=PAYMENTS_DISABLED_MESSAGE)


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
