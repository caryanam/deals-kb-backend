import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.config import CCAVENUE_ACCESS_CODE, CCAVENUE_CURRENCY, CCAVENUE_MERCHANT_ID, FRONTEND_PAYMENT_RESULT_URL
from app.database import get_db
from app.models import CCAvenuePaymentCreateIn, PaymentFailIn, PaymentOrderCreate, PaymentVerifyIn
from app.models_sql import PaymentTransaction, Product, User
from app.serializers import serialize_payment
from app.services import ccavenue_service
from app.services.payment_plans import SELLER_LISTING_FEES, get_plan, list_public_plans, public_plan
from app.utils import iso, now_utc

router = APIRouter(prefix="/payments", tags=["payments"])

PAYMENTS_DISABLED_MESSAGE = "Legacy payment endpoints are disabled. Use /payments/ccavenue/create."
TERMINAL_STATUSES = {"SUCCESS", "FAILED", "ABORTED", "INVALID"}


def _clip(value: Any, length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:length] if text else None


def _result_redirect(order_id: str | None, status: str) -> RedirectResponse:
    params = {"status": status}
    if order_id:
        params["order_id"] = order_id
    return RedirectResponse(f"{FRONTEND_PAYMENT_RESULT_URL}?{urlencode(params)}", status_code=303)


def _load_payable_item(db: Session, user: User, body: CCAvenuePaymentCreateIn) -> tuple[Decimal, dict[str, Any]]:
    payment_type = (body.payment_type or "").strip().upper()
    user_role = (user.role or "").strip()
    if not body.listing_id:
        if payment_type == "SELLER_LISTING":
            raise HTTPException(status_code=400, detail="listing_id is required for SELLER_LISTING")
    if payment_type == "BUYER_PASS":
        plan = get_plan(body.plan_id or body.subscription_plan_id, payment_type)
        if not plan:
            raise HTTPException(status_code=400, detail="A valid buyer plan_id is required")
        if user_role not in {"Buyer", "Admin"}:
            raise HTTPException(status_code=403, detail="Buyer pass payments are available only to buyers")
        return plan["amount"], {"name": plan["plan_name"], "plan": plan}
    if payment_type == "DEALER_PLAN":
        plan = get_plan(body.plan_id or body.subscription_plan_id, payment_type)
        if not plan:
            raise HTTPException(status_code=400, detail="A valid dealer plan_id is required")
        if user_role not in {"Dealer", "Admin"}:
            raise HTTPException(status_code=403, detail="Dealer plan payments are available only to dealers")
        return plan["amount"], {"name": plan["plan_name"], "plan": plan}
    if payment_type != "SELLER_LISTING":
        raise HTTPException(status_code=400, detail="Unsupported payment_type")

    product = (
        db.query(Product)
        .filter(Product.product_id == body.listing_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Listing not found")
    if user_role not in {"Seller", "Dealer", "Admin"}:
        raise HTTPException(status_code=403, detail="Listing payments are available only to sellers and dealers")
    if user_role != "Admin" and product.seller_id != user.user_id:
        raise HTTPException(status_code=403, detail="You can pay only for your own listing")

    amount = SELLER_LISTING_FEES.get((product.product_type or "").lower())
    if amount is None:
        raise HTTPException(status_code=400, detail="No listing fee configured for this product type")
    return amount, {"product": product, "name": product.title}


def _apply_success_activation(payment: PaymentTransaction, db: Session) -> None:
    if payment.activated_at:
        return
    activated_at = now_utc().replace(tzinfo=None)
    if payment.payment_type == "SELLER_LISTING" and payment.listing_id:
        product = db.query(Product).filter(Product.product_id == payment.listing_id).first()
        if product:
            product.relist_payment_status = "paid"
            product.relist_payment_order_id = payment.order_id
            product.relist_payment_id = payment.gateway_tracking_id or payment.order_id
            notes = dict(payment.notes or {})
            notes["activated_listing_id"] = product.product_id
            payment.notes = notes
    elif payment.payment_type in {"BUYER_PASS", "DEALER_PLAN"}:
        notes = dict(payment.notes or {})
        duration_days = int(notes.get("duration_days") or 0)
        if duration_days > 0:
            active_until = activated_at + timedelta(days=duration_days)
            notes["active_until"] = iso(active_until)
            if payment.payment_type == "BUYER_PASS":
                user = db.query(User).filter(User.user_id == payment.user_id).first()
                if user:
                    start = user.buyer_access_until if user.buyer_access_until and user.buyer_access_until > activated_at else activated_at
                    user.buyer_access_until = start + timedelta(days=duration_days)
                    notes["buyer_access_until"] = iso(user.buyer_access_until)
        payment.notes = notes
    payment.activated_at = activated_at


def _payment_status_payload(payment: PaymentTransaction) -> dict:
    return {
        "order_id": payment.order_id,
        "status": payment.status,
        "amount": f"{Decimal(payment.amount):.2f}",
        "currency": payment.currency,
        "payment_type": payment.payment_type,
        "tracking_id": payment.gateway_tracking_id,
        "completed_at": iso(payment.completed_at),
    }


def _validated_decimal(value: str | None) -> Decimal | None:
    try:
        return Decimal(str(value or "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


@router.get("/config")
def payment_config(user: User = Depends(auth_required)):
    configured = bool(CCAVENUE_MERCHANT_ID and CCAVENUE_ACCESS_CODE)
    return {
        "enabled": configured,
        "gateway": "ccavenue" if configured else None,
        "mode": "ccavenue" if configured else "disabled",
        "currency": CCAVENUE_CURRENCY,
        "supported_payment_types": ["SELLER_LISTING", "BUYER_PASS", "DEALER_PLAN"],
    }


@router.post("/ccavenue/create")
def create_ccavenue_payment(
    body: CCAvenuePaymentCreateIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    try:
        ccavenue_service.require_configured()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    amount, item = _load_payable_item(db, user, body)
    order_id = ccavenue_service.generate_order_id()
    payment_type = body.payment_type.strip().upper()
    plan = item.get("plan")
    plan_id = body.plan_id or body.subscription_plan_id
    if payment_type == "SELLER_LISTING":
        plan_id = plan_id or "seller_listing"
    notes = {}
    if plan:
        notes = {
            "plan": public_plan(plan),
            "duration_days": plan.get("duration_days"),
            "product_type": plan.get("product_type"),
        }
    else:
        notes = {"product_type": getattr(item.get("product"), "product_type", None)}

    payment = PaymentTransaction(
        payment_id=order_id,
        order_id=order_id,
        user_id=user.user_id,
        user_role=user.role,
        plan_id=plan_id,
        plan_name=plan["plan_name"] if plan else payment_type,
        subscription_plan_id=body.subscription_plan_id or body.plan_id,
        listing_id=body.listing_id,
        payment_type=payment_type,
        amount=amount,
        currency=CCAVENUE_CURRENCY,
        payment_gateway="ccavenue",
        status="PENDING",
        order_status="PENDING",
        receipt=order_id,
        initiated_at=now_utc().replace(tzinfo=None),
        notes=notes,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    plain_request = ccavenue_service.build_payment_request(payment, user, item)
    enc_request = ccavenue_service.encrypt_request(plain_request)
    return {
        "order_id": order_id,
        "gateway_url": ccavenue_service.gateway_url(),
        "enc_request": enc_request,
        "access_code": CCAVENUE_ACCESS_CODE,
    }


def _process_ccavenue_response(db: Session, enc_resp: str | None, cancel: bool = False) -> tuple[str | None, str]:
    if not enc_resp:
        return None, "failed"

    decrypted = ccavenue_service.decrypt_response(enc_resp)
    response = ccavenue_service.parse_decrypted_response(decrypted)
    order_id = response.get("order_id")
    if not order_id:
        return None, "failed"

    payment = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.order_id == order_id)
        .with_for_update()
        .first()
    )
    if not payment:
        return order_id, "failed"

    mapped_status = "ABORTED" if cancel else ccavenue_service.map_order_status(response.get("order_status"))
    response_amount = _validated_decimal(response.get("amount"))
    stored_amount = Decimal(payment.amount).quantize(Decimal("0.01"))
    valid = True
    if response.get("merchant_id") != CCAVENUE_MERCHANT_ID:
        valid = False
    if response_amount is None or response_amount != stored_amount:
        valid = False
    if response.get("currency") != payment.currency:
        valid = False
    if not valid:
        mapped_status = "INVALID"

    if payment.status == "SUCCESS" and mapped_status != "SUCCESS":
        return payment.order_id, "success"

    if payment.status not in TERMINAL_STATUSES or payment.status == "AWAITED":
        payment.status = mapped_status
        payment.order_status = _clip(response.get("order_status") or mapped_status, 50)
        payment.gateway_tracking_id = _clip(response.get("tracking_id"), 100)
        payment.bank_reference_number = _clip(response.get("bank_ref_no"), 100)
        payment.payment_mode = _clip(response.get("payment_mode"), 100)
        payment.failure_message = _clip(response.get("failure_message") or response.get("status_message"), 500)
        payment.status_code = _clip(response.get("status_code"), 50)
        payment.status_message = _clip(response.get("status_message"), 500)
        payment.raw_response_json = {
            key: value
            for key, value in response.items()
            if key.lower() not in {"card_name", "card_number", "vault", "token"}
        }
        payment.completed_at = now_utc().replace(tzinfo=None) if mapped_status in TERMINAL_STATUSES else None
        if mapped_status == "SUCCESS":
            payment.paid_at = payment.completed_at
            _apply_success_activation(payment, db)
        db.commit()

    return payment.order_id, "success" if payment.status == "SUCCESS" else "failed"


@router.post("/ccavenue/callback")
def ccavenue_callback(encResp: str = Form(None), db: Session = Depends(get_db)):
    try:
        order_id, result = _process_ccavenue_response(db, encResp, cancel=False)
    except Exception:
        db.rollback()
        return _result_redirect(None, "failed")
    return _result_redirect(order_id, result)


@router.post("/ccavenue/cancel")
def ccavenue_cancel(encResp: str = Form(None), db: Session = Depends(get_db)):
    try:
        order_id, _ = _process_ccavenue_response(db, encResp, cancel=True)
    except Exception:
        db.rollback()
        order_id = None
    return _result_redirect(order_id, "failed")


@router.get("/{order_id}/status")
def payment_status(order_id: str, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    payment = db.query(PaymentTransaction).filter(PaymentTransaction.order_id == order_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if user.role != "Admin" and payment.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="You cannot view this payment")
    return _payment_status_payload(payment)


@router.get("/plans")
def list_payment_plans(user: User = Depends(auth_required)):
    return list_public_plans()


@router.get("/plans/my")
def list_my_payment_plans(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    now = now_utc()
    payments = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.user_id == user.user_id,
            PaymentTransaction.status == "SUCCESS",
            PaymentTransaction.payment_type.in_(["BUYER_PASS", "DEALER_PLAN"]),
        )
        .order_by(PaymentTransaction.created_at.desc())
        .all()
    )
    plans = []
    for payment in payments:
        notes = payment.notes or {}
        plan = notes.get("plan") if isinstance(notes, dict) else {}
        active_until = notes.get("active_until") if isinstance(notes, dict) else None
        active = False
        if active_until:
            try:
                from datetime import datetime  # noqa: PLC0415

                active = datetime.fromisoformat(active_until).replace(tzinfo=now.tzinfo) > now
            except ValueError:
                active = False
        plans.append(
            {
                **(plan if isinstance(plan, dict) else {}),
                "payment_id": payment.payment_id,
                "order_id": payment.order_id,
                "plan_id": payment.plan_id,
                "plan_name": payment.plan_name,
                "payment_type": payment.payment_type,
                "active": active,
                "active_until": active_until,
                "paid_at": iso(payment.paid_at),
            }
        )
    return plans


@router.post("/create-order")
async def create_payment_order(body: PaymentOrderCreate, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail=PAYMENTS_DISABLED_MESSAGE)


@router.post("/create-plan-order")
async def create_plan_payment_order(body: PaymentOrderCreate, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail=PAYMENTS_DISABLED_MESSAGE)


@router.post("/verify")
async def verify_payment(body: PaymentVerifyIn, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail=PAYMENTS_DISABLED_MESSAGE)


@router.post("/verify-plan-payment")
async def verify_plan_payment(body: PaymentVerifyIn, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail=PAYMENTS_DISABLED_MESSAGE)


@router.post("/mark-failed")
def mark_payment_failed(body: PaymentFailIn, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail=PAYMENTS_DISABLED_MESSAGE)


@router.get("/my")
def my_payments(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    payments = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.user_id == user.user_id)
        .order_by(PaymentTransaction.created_at.desc())
        .limit(200)
        .all()
    )
    return [serialize_payment(payment) for payment in payments]
