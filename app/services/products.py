import asyncio
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import AUCTION_DURATION_SECONDS
from app.database import SessionLocal
from app.models import ProductIn
from app.models_sql import Product
from app.realtime import manager
from app.serializers import serialize_bid
from app.services.notifications import create_notification, notify_admins
from app.utils import iso, now_utc

ALLOWED_PRODUCT_TYPES = {"car", "bike", "laptop", "mobile"}

REQUIRED_DOCUMENTS = {
    "car": {"rc_copy", "insurance_copy"},
    "bike": {"rc_copy", "insurance_copy"},
    "laptop": {"aadhaar_card", "pan_card"},
    "mobile": {"aadhaar_card", "pan_card"},
}

REQUIRED_SPECIFICATIONS = {
    "car": {"ownership", "accidental"},
    "bike": {"ownership", "accidental"},
    "laptop": {"ram", "storage"},
    "mobile": {"ram", "storage"},
}


def validate_product_payload(body: ProductIn):
    product_type = body.product_type.lower().strip()
    if product_type not in ALLOWED_PRODUCT_TYPES:
        raise HTTPException(status_code=400, detail="product_type must be car, bike, laptop, or mobile")
    if body.product_price <= 0:
        raise HTTPException(status_code=400, detail="product_price must be greater than 0")
    if body.expected_price <= 0:
        raise HTTPException(status_code=400, detail="expected_price must be greater than 0")
    if len(body.photos) > 8:
        raise HTTPException(status_code=400, detail="Maximum 8 photos allowed")
    if not body.video:
        raise HTTPException(status_code=400, detail="Video walkthrough is required")

    missing_specs = sorted(REQUIRED_SPECIFICATIONS[product_type] - set(body.specifications.keys()))
    if missing_specs:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required specifications for {product_type}: {', '.join(missing_specs)}",
        )

    missing_docs = sorted(REQUIRED_DOCUMENTS[product_type] - set(body.documents.keys()))
    if missing_docs:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required documents for {product_type}: {', '.join(missing_docs)}",
        )


def auction_time_left(product: Product) -> int:
    if not product.auction_end:
        return 0
    return max(0, int((product.auction_end - now_utc().replace(tzinfo=None)).total_seconds()))


def auction_snapshot(product: Product) -> dict:
    return {
        "product_id": product.product_id,
        "status": product.status,
        "auction_start": iso(product.auction_start),
        "auction_end": iso(product.auction_end),
        "server_time": iso(now_utc().replace(tzinfo=None)),
        "time_left": auction_time_left(product),
        "current_bid": float(product.current_bid) if product.current_bid is not None else None,
        "highest_bidder_id": product.highest_bidder_id,
        "highest_bidder_name": product.highest_bidder_name,
        "winner_id": product.winner_id,
        "winner_name": product.winner_name,
        "bid_count": product.bid_count or 0,
    }


def maybe_end_auction(db: Session, product_id: str):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product or product.status != "live":
        return

    end_time = product.auction_end
    if not end_time or end_time > now_utc().replace(tzinfo=None):
        return

    product.status = "ended"
    product.winner_id = product.highest_bidder_id
    product.winner_name = product.highest_bidder_name

    if product.highest_bidder_id:
        create_notification(
            db,
            user_id=product.highest_bidder_id,
            title="You won the auction!",
            message="Congratulations! You won the auction. Seller contact details are now available.",
            notif_type="auction_won",
            product_id=product_id,
        )

    seller_message = (
        f"{product.highest_bidder_name} won the bid for {product.title}. Your contact details have been shared with them."
        if product.highest_bidder_id
        else f"{product.title} ended without bids"
    )
    create_notification(
        db,
        user_id=product.seller_id,
        title="Auction ended",
        message=seller_message,
        notif_type="auction_ended",
        product_id=product_id,
    )
    notify_admins(db, "Auction ended", f"Auction ended for {product.title}.", "auction_ended", product_id)
    db.commit()
    db.refresh(product)

    event = {
        "type": "auction_ended",
        "final_amount": float(product.current_bid) if product.current_bid is not None else None,
        **auction_snapshot(product),
    }
    event["time_left"] = 0
    return event


async def auction_timer(product_id: str, end_time: datetime):
    while True:
        time_left = max(0, int((end_time - now_utc().replace(tzinfo=None)).total_seconds()))
        await manager.broadcast(product_id, {
            "type": "timer_tick",
            "product_id": product_id,
            "auction_end": iso(end_time),
            "server_time": iso(now_utc().replace(tzinfo=None)),
            "time_left": time_left,
        })
        if time_left <= 0:
            break
        await asyncio.sleep(1)

    db = SessionLocal()
    try:
        event = maybe_end_auction(db, product_id)
    finally:
        db.close()

    if event:
        await manager.broadcast(product_id, event)


async def start_product_auction(db: Session, product: Product):
    start_time = now_utc().replace(tzinfo=None)
    end_time = start_time + timedelta(seconds=AUCTION_DURATION_SECONDS)
    product.status = "live"
    product.auction_start = start_time
    product.auction_end = end_time
    db.commit()
    db.refresh(product)

    create_notification(db, product.seller_id, "Auction started", f"Auction started for {product.title}.", "auction_started", product.product_id)
    notify_admins(db, "Auction started", f"Auction started for {product.title}.", "auction_started", product.product_id)
    db.commit()

    asyncio.create_task(auction_timer(product.product_id, end_time))
    await manager.broadcast(product.product_id, {
        "type": "auction_started",
        **auction_snapshot(product),
    })


async def broadcast_new_bid(product: Product, bid, user, amount: float):
    await manager.broadcast(product.product_id, {
        "type": "new_bid",
        "bid": serialize_bid(bid),
        **auction_snapshot(product),
    })
