from datetime import timedelta

from sqlalchemy.orm import Session

from app.models_sql import PaymentTransaction, User
from app.utils import now_utc


THREE_MONTH_ACCESS_HOURS = 24 * 90
MONTHLY_ACCESS_HOURS = 24 * 30

PAYMENT_PLANS = {
    "buyer_mobile_24h": {
        "plan_id": "buyer_mobile_24h",
        "name": "Mobile Bidding Pass",
        "role": "Buyer",
        "amount": 100,
        "currency": "INR",
        "description": "Unlimited mobile bidding for 24 hours (incl. 18% GST).",
        "product_type": "mobile",
        "access_hours": 24,
        "duration_label": "24 hours",
    },
    "buyer_laptop_24h": {
        "plan_id": "buyer_laptop_24h",
        "name": "Laptop Bidding Pass",
        "role": "Buyer",
        "amount": 100,
        "currency": "INR",
        "description": "Unlimited laptop bidding for 24 hours (incl. 18% GST).",
        "product_type": "laptop",
        "access_hours": 24,
        "duration_label": "24 hours",
    },
    "buyer_car_24h": {
        "plan_id": "buyer_car_24h",
        "name": "Car Bidding Pass",
        "role": "Buyer",
        "amount": 100,
        "currency": "INR",
        "description": "Unlimited car bidding for 24 hours (incl. 18% GST).",
        "product_type": "car",
        "access_hours": 24,
        "duration_label": "24 hours",
    },
    "buyer_bike_24h": {
        "plan_id": "buyer_bike_24h",
        "name": "Bike Bidding Pass",
        "role": "Buyer",
        "amount": 100,
        "currency": "INR",
        "description": "Unlimited bike bidding for 24 hours (incl. 18% GST).",
        "product_type": "bike",
        "access_hours": 24,
        "duration_label": "24 hours",
    },
    "seller_listing_car": {
        "plan_id": "seller_listing_car",
        "name": "Seller Listing - Car",
        "role": "Seller",
        "roles": ["Seller", "Dealer"],
        "amount": 100,
        "currency": "INR",
        "description": "Submit a car listing fee (incl. 18% GST)",
        "product_type": "car",
    },
    "seller_listing_mobile": {
        "plan_id": "seller_listing_mobile",
        "name": "Seller Listing - Mobile",
        "role": "Seller",
        "roles": ["Seller", "Dealer"],
        "amount": 100,
        "currency": "INR",
        "description": "Submit a mobile listing fee (incl. 18% GST)",
        "product_type": "mobile",
    },
    "seller_listing_bike": {
        "plan_id": "seller_listing_bike",
        "name": "Seller Listing - Bike",
        "role": "Seller",
        "roles": ["Seller", "Dealer"],
        "amount": 100,
        "currency": "INR",
        "description": "Submit a bike listing fee (incl. 18% GST)",
        "product_type": "bike",
    },
    "seller_listing_laptop": {
        "plan_id": "seller_listing_laptop",
        "name": "Seller Listing - Laptop",
        "role": "Seller",
        "roles": ["Seller", "Dealer"],
        "amount": 100,
        "currency": "INR",
        "description": "Submit a laptop listing fee (incl. 18% GST)",
        "product_type": "laptop",
    },
    "dealer_monthly": {
        "plan_id": "dealer_monthly",
        "name": "Dealer Monthly Plan - Mobile, Laptop & Bike",
        "role": "Dealer",
        "amount": 100,
        "currency": "INR",
        "description": "Monthly dealer plan for mobile, laptop, and bike listings (incl. 18% GST).",
        "product_types": ["mobile", "laptop", "bike"],
        "access_hours": MONTHLY_ACCESS_HOURS,
        "duration_label": "monthly",
    },
    "dealer_car_monthly": {
        "plan_id": "dealer_car_monthly",
        "name": "Dealer Monthly Plan - Car",
        "role": "Dealer",
        "amount": 100,
        "currency": "INR",
        "description": "Monthly dealer plan for car listings (incl. 18% GST).",
        "product_types": ["car"],
        "access_hours": MONTHLY_ACCESS_HOURS,
        "duration_label": "monthly",
    },
}

BUYER_PASS_PLAN_BY_PRODUCT_TYPE = {
    "mobile": "buyer_mobile_24h",
    "laptop": "buyer_laptop_24h",
    "car": "buyer_car_24h",
    "bike": "buyer_bike_24h",
}


def plans_for_user(user: User):
    return [
        plan
        for plan in PAYMENT_PLANS.values()
        if user.role == "Admin" or user.role in plan.get("roles", [plan["role"]])
    ]


def active_plan_until(db: Session, user_id: str, plan_id: str):
    plan = PAYMENT_PLANS.get(plan_id)
    if not plan or not plan.get("access_hours"):
        return None
    payment = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.user_id == user_id,
            PaymentTransaction.plan_id == plan_id,
            PaymentTransaction.status == "paid",
            PaymentTransaction.paid_at.isnot(None),
        )
        .order_by(PaymentTransaction.paid_at.desc())
        .first()
    )
    if not payment:
        return None
    expires_at = payment.paid_at + timedelta(hours=plan["access_hours"])
    if expires_at <= now_utc().replace(tzinfo=None):
        return None
    return expires_at


def user_plan_status(db: Session, user: User):
    statuses = []
    for plan in plans_for_user(user):
        expires_at = active_plan_until(db, user.user_id, plan["plan_id"])
        payload = dict(plan)
        payload["active"] = bool(expires_at)
        payload["expires_at"] = expires_at.isoformat() if expires_at else None
        statuses.append(payload)
    return statuses
