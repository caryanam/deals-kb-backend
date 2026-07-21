from __future__ import annotations

from decimal import Decimal
from typing import Any


SELLER_LISTING_FEES = {
    "car": Decimal("1.00"),
    "bike": Decimal("1.00"),
    "mobile": Decimal("1.00"),
    "laptop": Decimal("1.00"),
}

BUYER_PASS_AMOUNT = Decimal("1.00")
DEALER_PLAN_AMOUNT = Decimal("1.00")

PAYMENT_PLANS: list[dict[str, Any]] = [
    {
        "plan_id": "buyer_mobile_day",
        "plan_name": "Mobile Buyer Pass",
        "payment_type": "BUYER_PASS",
        "role": "Buyer",
        "product_type": "mobile",
        "amount": BUYER_PASS_AMOUNT,
        "duration_days": 1,
    },
    {
        "plan_id": "buyer_laptop_day",
        "plan_name": "Laptop Buyer Pass",
        "payment_type": "BUYER_PASS",
        "role": "Buyer",
        "product_type": "laptop",
        "amount": BUYER_PASS_AMOUNT,
        "duration_days": 1,
    },
    {
        "plan_id": "buyer_bike_day",
        "plan_name": "Bike Buyer Pass",
        "payment_type": "BUYER_PASS",
        "role": "Buyer",
        "product_type": "bike",
        "amount": BUYER_PASS_AMOUNT,
        "duration_days": 1,
    },
    {
        "plan_id": "buyer_car_day",
        "plan_name": "Car Buyer Pass",
        "payment_type": "BUYER_PASS",
        "role": "Buyer",
        "product_type": "car",
        "amount": BUYER_PASS_AMOUNT,
        "duration_days": 1,
    },
    {
        "plan_id": "dealer_monthly",
        "plan_name": "Dealer Monthly Plan",
        "payment_type": "DEALER_PLAN",
        "role": "Dealer",
        "product_type": "mobile,laptop,bike",
        "amount": DEALER_PLAN_AMOUNT,
        "duration_days": 30,
    },
    {
        "plan_id": "dealer_car_monthly",
        "plan_name": "Dealer Car Monthly Plan",
        "payment_type": "DEALER_PLAN",
        "role": "Dealer",
        "product_type": "car",
        "amount": DEALER_PLAN_AMOUNT,
        "duration_days": 30,
    },
]


def money_string(amount: Decimal) -> str:
    return f"{Decimal(amount).quantize(Decimal('0.01')):.2f}"


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    payload = dict(plan)
    payload["amount"] = money_string(plan["amount"])
    payload["currency"] = "INR"
    return payload


def list_public_plans() -> list[dict[str, Any]]:
    plans = [public_plan(plan) for plan in PAYMENT_PLANS]
    for product_type, amount in SELLER_LISTING_FEES.items():
        plans.append(
            {
                "plan_id": f"seller_{product_type}_listing",
                "plan_name": f"{product_type.title()} Listing Fee",
                "payment_type": "SELLER_LISTING",
                "role": "Seller",
                "product_type": product_type,
                "amount": money_string(amount),
                "currency": "INR",
                "duration_days": 0,
            }
        )
    return plans


def get_plan(plan_id: str | None, payment_type: str | None = None) -> dict[str, Any] | None:
    normalized_plan_id = (plan_id or "").strip()
    normalized_type = (payment_type or "").strip().upper()
    for plan in PAYMENT_PLANS:
        if plan["plan_id"] == normalized_plan_id and (not normalized_type or plan["payment_type"] == normalized_type):
            return plan
    return None
