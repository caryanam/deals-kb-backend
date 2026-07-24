import json
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile
from starlette.datastructures import FormData, UploadFile as StarletteUploadFile
from sqlalchemy.orm import Session

from app.auth import auth_required, get_user_from_token, is_seller_like, role_required
from app.database import get_db
from app.models import BidIn, ProductEditIn, ProductIn, ProductUpdate
from app.models_sql import Bid, Product, User
from app.serializers import serialize_bid, serialize_product
from app.services.media_assets import store_upload_in_db
from app.services.products import (
    broadcast_new_bid,
    maybe_end_auction,
    starting_bid_floor,
    start_product_auction,
    validate_product_payload,
)
from app.services.notifications import create_notification, notify_admins
from app.services.community_matching_service import match_community_requests_for_product
from app.utils import now_utc

router = APIRouter(prefix="/products", tags=["products"])


BID_INCREMENTS = {
    "mobile": 50,
    "laptop": 100,
    "bike": 500,
    "car": 1000,
}


def _parse_json_dict(value: Any, field_name: str) -> dict:
    if value in (None, "", b""):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON for {field_name}") from exc
        if isinstance(parsed, dict):
            return parsed
    raise HTTPException(status_code=400, detail=f"Invalid value for {field_name}")


PRODUCT_CORE_FIELDS = {
    "title",
    "product_type",
    "category",
    "brand",
    "model",
    "condition",
    "description",
    "expected_price",
    "photos",
    "video",
    "specifications",
    "documents",
    "rc_copy",
    "insurance_copy",
    "aadhaar_card",
    "pan_card",
    "front_view_image",
    "back_view_image",
    "side_view_image",
    "location_latitude",
    "location_longitude",
    "location_address",
    "location_full_address",
}

DOCUMENT_UPLOAD_FIELDS = (
    "rc_copy",
    "insurance_copy",
    "aadhaar_card",
    "pan_card",
    "front_view_image",
    "back_view_image",
    "side_view_image",
)


def _build_specifications_from_form(form: FormData) -> dict:
    specifications = _parse_json_dict(form.get("specifications"), "specifications")
    for key, value in form.multi_items():
        if key in PRODUCT_CORE_FIELDS:
            continue
        if isinstance(value, (UploadFile, StarletteUploadFile)):
            continue
        normalized = str(value or "").strip()
        if not normalized:
            continue
        specifications[key] = normalized
    return specifications


def _build_product_payload_from_json(data: dict) -> dict:
    payload = dict(data)
    if not payload.get("product_type") and payload.get("category"):
        payload["product_type"] = payload.get("category")

    specifications = payload.get("specifications")
    if not isinstance(specifications, dict):
        specifications = {}

    for key, value in list(payload.items()):
        if key in PRODUCT_CORE_FIELDS:
            continue
        if value in (None, ""):
            continue
        specifications[key] = value

    payload["specifications"] = specifications
    payload["documents"] = payload.get("documents") or {}
    for field_name in DOCUMENT_UPLOAD_FIELDS:
        if payload.get(field_name):
            payload["documents"][field_name] = payload[field_name]
    payload["photos"] = payload.get("photos") or []
    return payload


def _parse_float_value(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid value for {field_name}") from exc


def _get_bid_increment(product_type: str | None) -> int:
    normalized = (product_type or "").strip().lower()
    return BID_INCREMENTS.get(normalized, 100)


def _read_upload_list(form: FormData, key: str, db: Session, owner_user_id: str | None = None, owner_role: str | None = None) -> List[str]:
    items = form.getlist(key)
    urls: List[str] = []
    for item in items:
        if isinstance(item, (UploadFile, StarletteUploadFile)):
            if item.filename:
                urls.append(store_upload_in_db(db, item, owner_user_id=owner_user_id, owner_role=owner_role))
        elif item:
            urls.append(str(item).strip())
    return urls


def _read_optional_upload(form: FormData, key: str, db: Session, owner_user_id: str | None = None, owner_role: str | None = None) -> Optional[str]:
    value = form.get(key)
    if isinstance(value, (UploadFile, StarletteUploadFile)):
        if value.filename:
            return store_upload_in_db(db, value, owner_user_id=owner_user_id, owner_role=owner_role)
        return None
    if value:
        return str(value).strip()
    return None


def _build_documents_from_form(form: FormData, db: Session, owner_user_id: str | None = None, owner_role: str | None = None) -> dict:
    documents = _parse_json_dict(form.get("documents"), "documents")
    for field_name in DOCUMENT_UPLOAD_FIELDS:
        file_url = _read_optional_upload(form, field_name, db, owner_user_id=owner_user_id, owner_role=owner_role)
        if file_url:
            documents[field_name] = file_url
    return documents


def _merge_existing_listing_files(existing_product: Product, body: ProductIn) -> ProductIn:
    """Relist/edit submissions can omit files that are already present."""
    existing_documents = existing_product.documents or {}
    merged_documents = dict(existing_documents)
    merged_documents.update(body.documents or {})

    photos = body.photos or []
    if not photos and existing_product.photos:
        photos = list(existing_product.photos or [])

    video = body.video or existing_product.video

    return ProductIn(
        title=body.title,
        product_type=body.product_type,
        brand=body.brand,
        model=body.model,
        condition=body.condition,
        description=body.description,
        expected_price=body.expected_price,
        product_price=body.product_price,
        photos=photos,
        video=video,
        specifications=body.specifications,
        documents=merged_documents,
    )


async def _parse_product_create_request(request: Request, db: Session, owner_user_id: str | None = None, owner_role: str | None = None) -> ProductIn:
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" not in content_type:
        return ProductIn(**_build_product_payload_from_json(await request.json()))

    form = await request.form()
    expected = _parse_float_value(form.get("expected_price"), "expected_price")
    prod_price_raw = form.get("product_price")
    product_price = _parse_float_value(prod_price_raw, "product_price") if prod_price_raw else expected

    return ProductIn(
        title=str(form.get("title") or "").strip(),
        product_type=str(form.get("product_type") or form.get("category") or "").strip(),
        brand=str(form.get("brand") or "").strip(),
        model=str(form.get("model") or "").strip(),
        condition=str(form.get("condition") or "").strip(),
        description=str(form.get("description") or "").strip(),
        expected_price=expected,
        product_price=product_price,
        photos=_read_upload_list(form, "photos", db, owner_user_id=owner_user_id, owner_role=owner_role),
        video=_read_optional_upload(form, "video", db, owner_user_id=owner_user_id, owner_role=owner_role),
        specifications=_build_specifications_from_form(form),
        documents=_build_documents_from_form(form, db, owner_user_id=owner_user_id, owner_role=owner_role),
        location_latitude=float(form.get("location_latitude")) if form.get("location_latitude") else None,
        location_longitude=float(form.get("location_longitude")) if form.get("location_longitude") else None,
        location_address=str(form.get("location_address") or "").strip() if form.get("location_address") else None,
        location_full_address=str(form.get("location_full_address") or "").strip() if form.get("location_full_address") else None,
    )


async def _parse_product_edit_request(request: Request, db: Session, owner_user_id: str | None = None, owner_role: str | None = None) -> dict:
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" not in content_type:
        payload = ProductEditIn(**_build_product_payload_from_json(await request.json()))
        return payload.model_dump(exclude_unset=True)

    form = await request.form()
    photos = _read_upload_list(form, "photos", db, owner_user_id=owner_user_id, owner_role=owner_role)
    video = _read_optional_upload(form, "video", db, owner_user_id=owner_user_id, owner_role=owner_role)
    documents = _build_documents_from_form(form, db, owner_user_id=owner_user_id, owner_role=owner_role)
    specifications = _build_specifications_from_form(form)
    payload = {
        "title": str(form.get("title") or "").strip(),
        "product_type": str(form.get("product_type") or form.get("category") or "").strip(),
        "brand": str(form.get("brand") or "").strip(),
        "model": str(form.get("model") or "").strip(),
        "condition": str(form.get("condition") or "").strip(),
        "description": str(form.get("description") or "").strip(),
    }
    if form.get("location_latitude") is not None:
        payload["location_latitude"] = float(form.get("location_latitude"))
    if form.get("location_longitude") is not None:
        payload["location_longitude"] = float(form.get("location_longitude"))
    if form.get("location_address") is not None:
        payload["location_address"] = str(form.get("location_address") or "").strip()
    if form.get("location_full_address") is not None:
        payload["location_full_address"] = str(form.get("location_full_address") or "").strip()
    if specifications or form.get("specifications") is not None:
        payload["specifications"] = specifications
    if photos:
        payload["photos"] = photos
    if video:
        payload["video"] = video
    if documents or form.get("documents") is not None:
        payload["documents"] = documents
    if form.get("expected_price") is not None:
        payload["expected_price"] = _parse_float_value(form.get("expected_price"), "expected_price")
    if form.get("product_price") is not None:
        payload["product_price"] = _parse_float_value(form.get("product_price"), "product_price")
    return {key: value for key, value in payload.items() if value not in (None, "")}


@router.post("")
async def create_product(
    request: Request,
    user: User = Depends(role_required(["Seller", "Dealer", "Admin"])),
    db: Session = Depends(get_db),
):
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Blocked users cannot create listings.")
    body = await _parse_product_create_request(request, db, owner_user_id=user.user_id, owner_role=user.role)
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
        product_price=body.product_price if body.product_price is not None else body.expected_price,
        expected_price=body.expected_price,
        photos=body.photos,
        video=body.video,
        specifications=body.specifications,
        documents=body.documents,
        status="pending",
        bid_count=0,
    )
    db.add(product)
    if body.location_latitude is not None and body.location_longitude is not None:
        from app.models_sql import ProductLocation
        product_loc = ProductLocation(
            location_id=f"loc_{uuid.uuid4().hex[:12]}",
            product_id=product.product_id,
            latitude=body.location_latitude,
            longitude=body.location_longitude,
            address=body.location_address or "",
            full_address=body.location_full_address
        )
        db.add(product_loc)
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

    is_admin = False
    current_user = None
    if authorization and authorization.startswith("Bearer "):
        current_user = get_user_from_token(authorization.replace("Bearer ", "").strip(), db)
        if current_user and current_user.role == "Admin":
            is_admin = True

    if mine:
        if not current_user:
            if authorization and authorization.startswith("Bearer "):
                current_user = get_user_from_token(authorization.replace("Bearer ", "").strip(), db)
            if not current_user:
                raise HTTPException(status_code=401, detail="Invalid token")
        query = query.filter(Product.seller_id == current_user.user_id)
    else:
        if not is_admin:
            query = query.filter(Product.status.in_(["approved", "live", "ended"]))

    if status_filter:
        if status_filter == "live_or_upcoming":
            query = query.filter(Product.status.in_(["approved", "live"]))
        else:
            if not is_admin and not mine and status_filter in ["pending", "rejected", "cancelled"]:
                query = query.filter(Product.status == "never-match-this-status")
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
    include_private_documents = bool(is_admin or mine)
    return [serialize_product(item, include_private_documents=include_private_documents) for item in items]


@router.get("/public")
def list_public_products(
    status_filter: Optional[str] = None,
    product_type: Optional[str] = None,
    seller_id: Optional[str] = None,
    winner_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return list_products(
        status_filter=status_filter,
        product_type=product_type,
        seller_id=seller_id,
        winner_id=winner_id,
        mine=False,
        authorization=None,
        db=db,
    )


def serialize_public_auction_product(product: Product) -> dict:
    payload = serialize_product(product, include_private_documents=False)
    for field in ("seller_id", "expected_price", "documents", "highest_bidder_id", "winner_id"):
        payload.pop(field, None)
    return payload


def serialize_public_auction_bid(bid: Bid) -> dict:
    payload = serialize_bid(bid)
    payload.pop("bidder_id", None)
    return payload


@router.get("/public/{product_id}")
def get_public_auction_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.status == "live":
        maybe_end_auction(db, product_id)
        db.refresh(product)

    if product.status not in ("approved", "live", "ended", "cancelled"):
        raise HTTPException(status_code=404, detail="Product not found")

    return serialize_public_auction_product(product)


@router.get("/public/{product_id}/bids")
def get_public_auction_bids(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product or product.status not in ("approved", "live", "ended", "cancelled"):
        raise HTTPException(status_code=404, detail="Product not found")

    if product.status == "live":
        maybe_end_auction(db, product_id)

    bids = (
        db.query(Bid)
        .filter(Bid.product_id == product_id)
        .order_by(Bid.created_at.desc())
        .limit(200)
        .all()
    )
    return [serialize_public_auction_bid(bid) for bid in bids]


@router.get("/{product_id}")
def get_product(
    product_id: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.status == "live":
        maybe_end_auction(db, product_id)
        db.refresh(product)

    include_private_documents = False
    if authorization and authorization.startswith("Bearer "):
        current_user = get_user_from_token(authorization.replace("Bearer ", "").strip(), db)
        include_private_documents = bool(
            current_user
            and (
                current_user.role == "Admin"
                or current_user.user_id == product.seller_id
            )
        )

    return serialize_product(product, include_private_documents=include_private_documents)


@router.patch("/{product_id}")
@router.put("/{product_id}")
async def edit_product(
    product_id: str,
    request: Request,
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

    data = await _parse_product_edit_request(request, db, owner_user_id=user.user_id, owner_role=user.role)
    if "expected_price" in data and data["expected_price"] is not None and data["expected_price"] <= 0:
        raise HTTPException(status_code=400, detail="expected_price must be greater than 0")
    if "photos" in data and data["photos"] is not None:
        if len(data["photos"]) == 0:
            raise HTTPException(status_code=400, detail="At least one photo is required")
        if len(data["photos"]) > 8:
            raise HTTPException(status_code=400, detail="Maximum 8 photos allowed")

    if "documents" in data:
        merged_documents = dict(product.documents or {})
        merged_documents.update(data["documents"] or {})
        product.documents = merged_documents

    for field in ("title", "brand", "model", "description", "expected_price", "photos", "video", "specifications"):
        if field in data:
            setattr(product, field, data[field])
    if "expected_price" in data and data["expected_price"] is not None:
        if "product_price" not in data:
            product.product_price = data["expected_price"]
    if "product_price" in data and data["product_price"] is not None:
        product.product_price = data["product_price"]
    if "condition" in data:
        product.product_condition = data["condition"]
    if "product_type" in data and data["product_type"] is not None:
        product.product_type = data["product_type"].lower().strip()

    # Fetch current location for validation if exists
    from app.models_sql import ProductLocation
    product_loc = db.query(ProductLocation).filter(ProductLocation.product_id == product.product_id).first()

    # Validate the complete product after applying edits.
    validate_product_payload(ProductIn(
        title=product.title,
        product_type=product.product_type,
        brand=product.brand,
        model=product.model,
        condition=product.product_condition,
        description=product.description or "",
        expected_price=float(product.expected_price),
        product_price=float(product.product_price) if product.product_price is not None else float(product.expected_price),
        photos=product.photos or [],
        video=product.video,
        specifications=product.specifications or {},
        documents=product.documents or {},
        location_latitude=float(product_loc.latitude) if product_loc else None,
        location_longitude=float(product_loc.longitude) if product_loc else None,
        location_address=product_loc.address if product_loc else None,
        location_full_address=product_loc.full_address if product_loc else None,
    ))

    if product.status == "rejected" and user.role != "Admin":
        product.status = "pending"
        product.reject_reason = None
        product.rejected_at = None

    location_fields = ("location_latitude", "location_longitude", "location_address", "location_full_address")
    has_location_update = any(f in data for f in location_fields)
    if has_location_update:
        lat = data.get("location_latitude")
        lng = data.get("location_longitude")
        addr = data.get("location_address")
        full_addr = data.get("location_full_address")
        
        if product_loc:
            if lat is not None:
                product_loc.latitude = lat
            if lng is not None:
                product_loc.longitude = lng
            if addr is not None:
                product_loc.address = addr
            if full_addr is not None:
                product_loc.full_address = full_addr
        elif lat is not None and lng is not None:
            product_loc = ProductLocation(
                location_id=f"loc_{uuid.uuid4().hex[:12]}",
                product_id=product.product_id,
                latitude=lat,
                longitude=lng,
                address=addr or "",
                full_address=full_addr
            )
            db.add(product_loc)

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
        now = now_utc().replace(tzinfo=None)
        active_pass = False
        from app.models_sql import PaymentTransaction  # noqa: PLC0415
        
        transactions = (
            db.query(PaymentTransaction)
            .filter(
                PaymentTransaction.user_id == user.user_id,
                PaymentTransaction.status == "SUCCESS",
                PaymentTransaction.payment_type == "BUYER_PASS",
            )
            .all()
        )
        for tx in transactions:
            notes = tx.notes or {}
            if not isinstance(notes, dict):
                continue
            tx_product_type = notes.get("product_type")
            if tx_product_type == product.product_type:
                active_until_str = notes.get("active_until")
                if active_until_str:
                    try:
                        from datetime import datetime  # noqa: PLC0415
                        active_until = datetime.fromisoformat(active_until_str)
                        if active_until > now:
                            active_pass = True
                            break
                    except (ValueError, TypeError):
                        pass
        
        if not active_pass:
            raise HTTPException(
                status_code=402,
                detail=f"You need an active bidding pass for the {product.product_type} category to place a bid."
            )

    current_bid = float(product.current_bid or 0)
    expected_price = float(product.expected_price)
    bid_increment = _get_bid_increment(product.product_type)
    min_bid = max(current_bid + bid_increment, starting_bid_floor(expected_price)) if current_bid == 0 else current_bid + bid_increment
    if body.amount < min_bid:
        raise HTTPException(status_code=400, detail=f"Bid must be at least INR {min_bid}")

    previous_bidder_id = product.highest_bidder_id
    bid = Bid(
        bid_id=uuid.uuid4().hex,
        product_id=product_id,
        bidder_id=user.user_id,
        bidder_name=user.name or "",
        amount=body.amount,
        created_at=now_utc().replace(tzinfo=None),
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


from pydantic import BaseModel

class RelistFailIn(BaseModel):
    razorpayOrderId: str
    reason: str


@router.get("/{product_id}/relist-data")
def get_relist_data(
    product_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Listing not found")
    if product.seller_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this listing")
    
    is_unsold = (product.status == "ended" and not product.winner_id)
    if not is_unsold:
        raise HTTPException(status_code=400, detail="This listing is not eligible for relisting")
        
    return serialize_product(product)


@router.post("/{product_id}/relist/create-order")
async def create_relist_order(
    product_id: str,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Listing not found")
    if product.seller_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this listing")

    product.relist_payment_status = "bypassed"
    db.commit()

    return {
        "status": "bypassed",
        "payment_required": False,
        "message": "Relisting does not require payment right now.",
    }


@router.post("/{product_id}/relist/submit")
async def submit_relist(
    product_id: str,
    request: Request,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Original listing not found")
    if product.seller_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this listing")
        
    body = await _parse_product_create_request(request, db, owner_user_id=user.user_id, owner_role=user.role)
    body = _merge_existing_listing_files(product, body)
    validate_product_payload(body)

    product.relist_payment_status = "bypassed"

    # Relisting should update the same listing record rather than creating a new one.
    # Reset the previous auction state so the product goes back through admin approval cleanly.
    product.seller_name = user.name or ""
    product.title = body.title
    product.product_type = body.product_type.lower().strip()
    product.brand = body.brand
    product.model = body.model
    product.product_condition = body.condition
    product.description = body.description
    product.product_price = body.product_price if body.product_price is not None else body.expected_price
    product.expected_price = body.expected_price
    product.photos = body.photos
    product.video = body.video
    product.specifications = body.specifications
    product.documents = body.documents
    product.status = "pending"
    product.reject_reason = None
    product.auction_start = None
    product.auction_end = None
    product.current_bid = None
    product.highest_bidder_id = None
    product.highest_bidder_name = None
    product.bid_count = 0
    product.winner_id = None
    product.winner_name = None
    product.is_cancelled = False
    product.cancel_reason = None
    product.cancelled_at = None
    product.approved_at = None
    product.rejected_at = None
    product.submitted_at = now_utc().replace(tzinfo=None)
    product.parent_product_id = product.parent_product_id or product.product_id
    product.is_relisted = True
    product.relist_count = (product.relist_count or 0) + 1

    db.query(Bid).filter(Bid.product_id == product.product_id).delete(synchronize_session=False)
    
    create_notification(
        db,
        user_id=user.user_id,
        title="Product Relisted",
        message=f"Your listing '{body.title}' has been relisted and submitted for verification.",
        notif_type="product_submitted",
        product_id=product.product_id,
    )
    notify_admins(
        db,
        "Relisted listing submitted",
        f"{user.name} resubmitted '{body.title}' for approval.",
        "product_submitted",
        product.product_id,
    )
    
    db.commit()
    db.refresh(product)
    
    return {
        "message": "Relisted listing submitted for admin approval",
        "listingId": product.product_id,
        "newListingId": product.product_id,
        "status": "pending"
    }


@router.post("/{product_id}/relist/payment-failed")
def relist_payment_failed(
    product_id: str,
    body: RelistFailIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Listing not found")
    if product.seller_id != user.user_id:
        raise HTTPException(status_code=403, detail="You do not own this listing")

    product.relist_payment_status = "bypassed"
    db.commit()
    return {"message": "Relisting does not require payment right now."}
