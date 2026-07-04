import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth import auth_required, get_user_from_token, is_seller_like, role_required
from app.database import get_db
from app.models import BidIn, ProductEditIn, ProductIn, ProductUpdate
from app.models_sql import Bid, Product, User
from app.serializers import serialize_bid, serialize_product
from app.services.products import (
    broadcast_new_bid,
    maybe_end_auction,
    start_product_auction,
    validate_product_payload,
)
from app.services.notifications import create_notification, notify_admins
from app.services.payment_plans import BUYER_PASS_PLAN_BY_PRODUCT_TYPE, PAYMENT_PLANS, active_plan_until
from app.services.community_matching_service import match_community_requests_for_product
from app.utils import now_utc

router = APIRouter(prefix="/products", tags=["products"])


@router.post("")
def create_product(
    body: ProductIn,
    user: User = Depends(role_required(["Seller", "Dealer", "Admin"])),
    db: Session = Depends(get_db),
):
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Blocked users cannot create listings.")
    validate_product_payload(body)
    product = Product(
        product_id=f"prod_{uuid.uuid4().hex[:12]}",
        seller_id=user.user_id,
        seller_name=user.name or "",
        title=body.title,
        product_type=body.product_type.lower().strip(),
        brand=body.brand,
        model=body.model,
        product_condition=body.condition,
        description=body.description,
        product_price=body.product_price,
        expected_price=body.expected_price,
        photos=body.photos,
        video=body.video,
        specifications=body.specifications,
        documents=body.documents,
        status="pending",
        bid_count=0,
    )
    db.add(product)
    create_notification(
        db,
        user_id=user.user_id,
        title="Product submitted",
        message=f"Your listing '{body.title}' was submitted for verification.",
        notif_type="product_submitted",
        product_id=product.product_id,
    )
    notify_admins(db, "New product listing submitted", f"{user.name} submitted '{body.title}'.", "product_submitted", product.product_id)
    db.commit()
    db.refresh(product)
    return serialize_product(product)


@router.get("")
def list_products(
    status_filter: Optional[str] = None,
    product_type: Optional[str] = None,
    seller_id: Optional[str] = None,
    winner_id: Optional[str] = None,
    mine: Optional[bool] = False,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    query = db.query(Product)

    if mine:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Auth required for mine=true")
        user = get_user_from_token(authorization.replace("Bearer ", "").strip(), db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        query = query.filter(Product.seller_id == user.user_id)

    if status_filter:
        if status_filter == "live_or_upcoming":
            query = query.filter(Product.status.in_(["approved", "live"]))
        else:
            query = query.filter(Product.status == status_filter)

    if product_type and product_type != "all":
        query = query.filter(Product.product_type == product_type.lower().strip())
    if seller_id:
        query = query.filter(Product.seller_id == seller_id)
    if winner_id:
        query = query.filter(Product.winner_id == winner_id)

    items = query.order_by(Product.created_at.desc()).limit(500).all()
    for item in items:
        if item.status == "live":
            maybe_end_auction(db, item.product_id)

    items = query.order_by(Product.created_at.desc()).limit(500).all()
    return [serialize_product(item) for item in items]


@router.get("/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.status == "live":
        maybe_end_auction(db, product_id)
        db.refresh(product)

    return serialize_product(product)


@router.patch("/{product_id}")
def edit_product(
    product_id: str,
    body: ProductEditIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Blocked users cannot edit listings.")
    if user.role != "Admin" and (not is_seller_like(user) or user.user_id != product.seller_id):
        raise HTTPException(status_code=403, detail="Only seller, dealer, or admin can edit product")
    if user.role != "Admin" and product.status not in ("pending", "rejected"):
        raise HTTPException(status_code=400, detail="Seller or dealer can edit only pending or rejected listings")

    data = body.model_dump(exclude_unset=True)
    if "product_price" in data and data["product_price"] is not None and data["product_price"] <= 0:
        raise HTTPException(status_code=400, detail="product_price must be greater than 0")
    if "expected_price" in data and data["expected_price"] is not None and data["expected_price"] <= 0:
        raise HTTPException(status_code=400, detail="expected_price must be greater than 0")
    if "photos" in data and data["photos"] is not None:
        if len(data["photos"]) == 0:
            raise HTTPException(status_code=400, detail="At least one photo is required")
        if len(data["photos"]) > 8:
            raise HTTPException(status_code=400, detail="Maximum 8 photos allowed")

    for field in ("title", "brand", "model", "description", "product_price", "expected_price", "photos", "video", "specifications", "documents"):
        if field in data:
            setattr(product, field, data[field])
    if "condition" in data:
        product.product_condition = data["condition"]
    if "product_type" in data and data["product_type"] is not None:
        product.product_type = data["product_type"].lower().strip()

    # Validate the complete product after applying edits.
    validate_product_payload(ProductIn(
        title=product.title,
        product_type=product.product_type,
        brand=product.brand,
        model=product.model,
        condition=product.product_condition,
        description=product.description or "",
        product_price=float(product.product_price),
        expected_price=float(product.expected_price),
        photos=product.photos or [],
        video=product.video,
        specifications=product.specifications or {},
        documents=product.documents or {},
    ))

    if product.status == "rejected" and user.role != "Admin":
        product.status = "pending"
        product.reject_reason = None
        product.rejected_at = None

    product.updated_at = now_utc().replace(tzinfo=None)
    db.commit()
    db.refresh(product)
    return {"message": "Product updated successfully", "product": serialize_product(product)}


@router.get("/{product_id}/seller-contact")
def get_seller_contact(
    product_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status != "ended":
        raise HTTPException(status_code=400, detail="Seller contact is available only after auction ends")
    if user.role != "Admin" and product.winner_id != user.user_id:
        raise HTTPException(status_code=403, detail="Seller contact is available only to the winning buyer")

    seller = db.query(User).filter(User.user_id == product.seller_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")

    return {
        "product_id": product.product_id,
        "product_title": product.title,
        "seller": {
            "seller_id": seller.user_id,
            "name": seller.name or "",
            "email": seller.email,
            "mobile_number": seller.mobile_number,
        },
    }


@router.get("/{product_id}/winner-contact")
def get_winner_contact(
    product_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if user.role != "Admin" and (not is_seller_like(user) or product.seller_id != user.user_id):
        raise HTTPException(status_code=403, detail="Winner contact is available only to the seller or dealer")
    if product.status != "ended":
        raise HTTPException(status_code=400, detail="Winner contact is available only after auction ends")
    if not product.winner_id:
        raise HTTPException(status_code=404, detail="Winner not found")

    winner = db.query(User).filter(User.user_id == product.winner_id).first()
    if not winner:
        raise HTTPException(status_code=404, detail="Winner not found")

    return {
        "product_id": product.product_id,
        "winner": {
            "user_id": winner.user_id,
            "name": winner.name or "",
            "email": winner.email,
            "mobile_number": winner.mobile_number,
        },
    }


@router.patch("/{product_id}/review")
def review_product(
    product_id: str,
    body: ProductUpdate,
    user: User = Depends(role_required(["Admin"])),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending products can be reviewed")
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be approved or rejected")

    product.status = body.status
    product.updated_at = now_utc().replace(tzinfo=None)
    if body.status == "rejected":
        product.reject_reason = body.reject_reason or "Not specified"
        product.rejected_at = now_utc().replace(tzinfo=None)
        notif_type = "listing_rejected"
        title = "Listing Rejected"
        message = f"Your listing '{product.title}' was rejected. Reason: {product.reject_reason}"
    else:
        product.approved_at = now_utc().replace(tzinfo=None)
        notif_type = "listing_approved"
        title = "Listing Approved"
        message = f"Your listing '{product.title}' has been approved."

    create_notification(
        db,
        user_id=product.seller_id,
        title=title,
        message=message,
        notif_type=notif_type,
        product_id=product_id,
    )
    if body.status == "approved":
        match_community_requests_for_product(db, product)
    db.commit()
    db.refresh(product)
    return {"message": f"Product {body.status} successfully", "product": serialize_product(product)}


@router.post("/{product_id}/start-auction")
async def start_auction(
    product_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Blocked users cannot start auctions.")
    if user.role != "Admin" and (not is_seller_like(user) or user.user_id != product.seller_id):
        raise HTTPException(status_code=403, detail="Only seller, dealer, or admin can start auction")
    if product.status != "approved":
        raise HTTPException(status_code=400, detail="Auction can only start for approved listings")

    await start_product_auction(db, product)
    return serialize_product(product)


@router.post("/{product_id}/bid")
async def place_bid(
    product_id: str,
    body: BidIn,
    user: User = Depends(role_required(["Buyer", "Admin"])),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status != "live":
        raise HTTPException(status_code=400, detail="Auction is not live")

    if product.auction_end and product.auction_end <= now_utc().replace(tzinfo=None):
        maybe_end_auction(db, product_id)
        raise HTTPException(status_code=400, detail="Auction has ended")

    if user.user_id == product.seller_id:
        raise HTTPException(status_code=400, detail="Seller cannot bid on own listing")
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Blocked users cannot place bids.")
    if user.role == "Buyer":
        required_plan_id = BUYER_PASS_PLAN_BY_PRODUCT_TYPE.get(product.product_type)
        if required_plan_id and not active_plan_until(db, user.user_id, required_plan_id):
            plan = PAYMENT_PLANS[required_plan_id]
            raise HTTPException(
                status_code=402,
                detail={
                    "message": "Please activate a bidding pass for this category.",
                    "required_plan": plan,
                    "product_type": product.product_type,
                },
            )

    current_bid = float(product.current_bid or 0)
    expected_price = float(product.expected_price)
    min_bid = max(current_bid + 100, expected_price) if current_bid == 0 else current_bid + 100
    if body.amount < min_bid:
        raise HTTPException(status_code=400, detail=f"Bid must be at least INR {min_bid}")

    previous_bidder_id = product.highest_bidder_id
    bid = Bid(
        bid_id=uuid.uuid4().hex,
        product_id=product_id,
        bidder_id=user.user_id,
        bidder_name=user.name or "",
        amount=body.amount,
    )
    db.add(bid)
    product.current_bid = body.amount
    product.highest_bidder_id = user.user_id
    product.highest_bidder_name = user.name or ""
    product.bid_count = (product.bid_count or 0) + 1
    create_notification(db, user.user_id, "Bid placed", f"Your bid of INR {body.amount} was placed for {product.title}.", "bid_placed", product_id)
    create_notification(db, product.seller_id, "New winning bid", f"{user.name} placed a bid of INR {body.amount} on {product.title}.", "winning_bid", product_id)
    if previous_bidder_id and previous_bidder_id != user.user_id:
        create_notification(db, previous_bidder_id, "You were outbid", f"You were outbid on {product.title}.", "outbid", product_id)
    db.commit()
    db.refresh(bid)
    db.refresh(product)

    await broadcast_new_bid(product, bid, user, body.amount)
    return serialize_bid(bid)


@router.get("/{product_id}/bids")
def get_bids(product_id: str, db: Session = Depends(get_db)):
    bids = (
        db.query(Bid)
        .filter(Bid.product_id == product_id)
        .order_by(Bid.created_at.desc())
        .limit(200)
        .all()
    )
    return [serialize_bid(bid) for bid in bids]
