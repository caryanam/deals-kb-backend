import base64
import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.auth import auth_required, get_user_from_token, is_seller_like, role_required
from app.config import CASHFREE_ENV
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
logger = logging.getLogger("dealskb")

MULTIPART_PHOTO_KEYS = ("photos", "photos[]", "images", "images[]")
MULTIPART_VIDEO_KEYS = ("video", "video_file")
MULTIPART_SCALAR_KEYS = {
    "title",
    "product_type",
    "category",
    "brand",
    "model",
    "condition",
    "description",
    "product_price",
    "price",
    "expected_price",
    "expectedPrice",
    "specifications",
    "specs",
    "documents",
}
MULTIPART_DOCUMENT_KEYS = {
    "aadhaar_card",
    "pan_card",
    "rc_copy",
    "insurance_copy",
    "invoice_copy",
    "bill_copy",
}


from app.config import UPLOAD_DIR

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB

ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_VIDEO_MIME = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/webm"}
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB

ALLOWED_DOC_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_DOC_MIME = {"application/pdf", "image/jpeg", "image/png"}
MAX_DOC_SIZE = 20 * 1024 * 1024  # 20 MB


def parse_json_field(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON field in multipart request") from exc


async def save_and_validate_file(
    upload: UploadFile,
    max_size: int,
    allowed_exts: set[str],
    allowed_mimes: set[str]
) -> str:
    filename = upload.filename or "file"
    ext = Path(filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' is not allowed. Supported: {', '.join(allowed_exts)}"
        )

    mime = upload.content_type
    if mime not in allowed_mimes:
        raise HTTPException(
            status_code=400,
            detail=f"MIME type '{mime}' is not allowed. Supported: {', '.join(allowed_mimes)}"
        )

    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / unique_filename

    size = 0
    try:
        with open(file_path, "wb") as buffer:
            while chunk := await upload.read(16384):  # 16KB chunks
                size += len(chunk)
                if size > max_size:
                    buffer.close()
                    if file_path.exists():
                        file_path.unlink()
                    max_mb = max_size / (1024 * 1024)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File '{filename}' exceeds max size of {max_mb:.0f} MB"
                    )
                buffer.write(chunk)
    except Exception as exc:
        if file_path.exists():
            file_path.unlink()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(exc)}") from exc

    return f"/uploads/{unique_filename}"


async def handle_file_value(
    value,
    max_size: int,
    allowed_exts: set[str],
    allowed_mimes: set[str]
) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, UploadFile) and value.filename:
        return await save_and_validate_file(value, max_size, allowed_exts, allowed_mimes)
    if isinstance(value, str):
        val_str = value.strip()
        if val_str.startswith("http") or val_str.startswith("/uploads/"):
            return val_str
        if val_str.startswith("data:"):
            try:
                header, base64_data = val_str.split(",", 1)
                mime = header.split(";", 1)[0].split(":", 1)[1]
                if mime not in allowed_mimes:
                    raise HTTPException(status_code=400, detail=f"MIME type '{mime}' is not allowed")
                
                ext = None
                if mime == "image/jpeg":
                    ext = ".jpg"
                elif mime == "image/png":
                    ext = ".png"
                elif mime == "image/webp":
                    ext = ".webp"
                elif mime == "video/mp4":
                    ext = ".mp4"
                elif mime == "application/pdf":
                    ext = ".pdf"
                else:
                    ext = ".bin"
                
                if ext not in allowed_exts:
                    raise HTTPException(status_code=400, detail=f"Inferred extension '{ext}' is not allowed")

                file_content = base64.b64decode(base64_data)
                if len(file_content) > max_size:
                    max_mb = max_size / (1024 * 1024)
                    raise HTTPException(status_code=413, detail=f"Base64 file exceeds max size of {max_mb:.0f} MB")
                
                unique_filename = f"{uuid.uuid4().hex}{ext}"
                file_path = UPLOAD_DIR / unique_filename
                with open(file_path, "wb") as f:
                    f.write(file_content)
                return f"/uploads/{unique_filename}"
            except Exception as exc:
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(status_code=400, detail="Invalid Base64 file data") from exc
    return None


async def parse_product_request(request: Request) -> ProductIn:
    content_type = (request.headers.get("content-type") or "").lower()
    content_length = request.headers.get("content-length", "-")
    logger.info("create_product request content_type=%s content_length=%s", content_type, content_length)

    if "multipart/form-data" not in content_type:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
        
        if isinstance(payload.get("photos"), list):
            processed_photos = []
            for p in payload["photos"]:
                saved = await handle_file_value(p, MAX_IMAGE_SIZE, ALLOWED_IMAGE_EXT, ALLOWED_IMAGE_MIME)
                if saved:
                    processed_photos.append(saved)
            payload["photos"] = processed_photos
            
        if payload.get("video"):
            saved = await handle_file_value(payload["video"], MAX_VIDEO_SIZE, ALLOWED_VIDEO_EXT, ALLOWED_VIDEO_MIME)
            if saved:
                payload["video"] = saved
                
        if isinstance(payload.get("documents"), dict):
            processed_docs = {}
            for k, v in payload["documents"].items():
                saved = await handle_file_value(v, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
                if saved:
                    processed_docs[k] = saved
            payload["documents"] = processed_docs

        try:
            return ProductIn.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

    form = await request.form()

    photos = []
    for key in MULTIPART_PHOTO_KEYS:
        for item in form.getlist(key):
            saved = await handle_file_value(item, MAX_IMAGE_SIZE, ALLOWED_IMAGE_EXT, ALLOWED_IMAGE_MIME)
            if saved:
                photos.append(saved)

    video = None
    for key in MULTIPART_VIDEO_KEYS:
        value = form.get(key)
        saved = await handle_file_value(value, MAX_VIDEO_SIZE, ALLOWED_VIDEO_EXT, ALLOWED_VIDEO_MIME)
        if saved:
            video = saved
            break

    specifications = parse_json_field(form.get("specifications") or form.get("specs"), {})
    documents = parse_json_field(form.get("documents"), {})

    for key, value in form.multi_items():
        if key in MULTIPART_SCALAR_KEYS or key in MULTIPART_PHOTO_KEYS or key in MULTIPART_VIDEO_KEYS or key in MULTIPART_DOCUMENT_KEYS:
            continue
        saved = await handle_file_value(value, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
        if saved:
            documents[key] = saved

    for key in MULTIPART_DOCUMENT_KEYS:
        value = form.get(key)
        saved = await handle_file_value(value, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
        if saved:
            documents[key] = saved

    payload = {
        "title": (form.get("title") or "").strip(),
        "product_type": (form.get("product_type") or form.get("category") or "").strip(),
        "brand": (form.get("brand") or "").strip(),
        "model": (form.get("model") or "").strip(),
        "condition": (form.get("condition") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "product_price": form.get("product_price") or form.get("price"),
        "expected_price": form.get("expected_price") or form.get("expectedPrice"),
        "photos": photos,
        "video": video,
        "specifications": specifications,
        "documents": documents,
    }
    try:
        return ProductIn.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


@router.post("")
async def create_product(
    request: Request,
    user: User = Depends(role_required(["Seller", "Dealer", "Admin"])),
    db: Session = Depends(get_db),
):
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="Blocked users cannot create listings.")
    body = await parse_product_request(request)
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
    return [serialize_product(item) for item in items]


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
    payload = serialize_product(product)
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
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.status == "live":
        maybe_end_auction(db, product_id)
        db.refresh(product)

    return serialize_product(product)


async def parse_product_edit_request(request: Request) -> ProductEditIn:
    content_type = (request.headers.get("content-type") or "").lower()
    content_length = request.headers.get("content-length", "-")
    logger.info("edit_product request content_type=%s content_length=%s", content_type, content_length)

    if "multipart/form-data" not in content_type:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
        
        if isinstance(payload.get("photos"), list):
            processed_photos = []
            for p in payload["photos"]:
                saved = await handle_file_value(p, MAX_IMAGE_SIZE, ALLOWED_IMAGE_EXT, ALLOWED_IMAGE_MIME)
                if saved:
                    processed_photos.append(saved)
            payload["photos"] = processed_photos
            
        if payload.get("video"):
            saved = await handle_file_value(payload["video"], MAX_VIDEO_SIZE, ALLOWED_VIDEO_EXT, ALLOWED_VIDEO_MIME)
            if saved:
                payload["video"] = saved
                
        if isinstance(payload.get("documents"), dict):
            processed_docs = {}
            for k, v in payload["documents"].items():
                saved = await handle_file_value(v, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
                if saved:
                    processed_docs[k] = saved
            payload["documents"] = processed_docs

        try:
            return ProductEditIn.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

    form = await request.form()

    # Process photos:
    photos = None
    has_photos = False
    for key in MULTIPART_PHOTO_KEYS:
        if form.getlist(key):
            has_photos = True
            break
    if has_photos:
        photos = []
        for key in MULTIPART_PHOTO_KEYS:
            for item in form.getlist(key):
                saved = await handle_file_value(item, MAX_IMAGE_SIZE, ALLOWED_IMAGE_EXT, ALLOWED_IMAGE_MIME)
                if saved:
                    photos.append(saved)

    # Process video:
    video = None
    has_video = False
    for key in MULTIPART_VIDEO_KEYS:
        if form.get(key) is not None:
            has_video = True
            break
    if has_video:
        for key in MULTIPART_VIDEO_KEYS:
            value = form.get(key)
            saved = await handle_file_value(value, MAX_VIDEO_SIZE, ALLOWED_VIDEO_EXT, ALLOWED_VIDEO_MIME)
            if saved:
                video = saved
                break

    specifications = None
    if form.get("specifications") or form.get("specs"):
        specifications = parse_json_field(form.get("specifications") or form.get("specs"), {})
        
    documents = None
    has_documents = False
    for key in MULTIPART_DOCUMENT_KEYS:
        if form.get(key) is not None:
            has_documents = True
            break
    if form.get("documents"):
        has_documents = True

    if has_documents:
        documents = parse_json_field(form.get("documents"), {})
        for key, value in form.multi_items():
            if key in MULTIPART_SCALAR_KEYS or key in MULTIPART_PHOTO_KEYS or key in MULTIPART_VIDEO_KEYS or key in MULTIPART_DOCUMENT_KEYS:
                continue
            saved = await handle_file_value(value, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
            if saved:
                documents[key] = saved

        for key in MULTIPART_DOCUMENT_KEYS:
            value = form.get(key)
            saved = await handle_file_value(value, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
            if saved:
                documents[key] = saved

    payload = {}
    for key in MULTIPART_SCALAR_KEYS:
        val = form.get(key)
        if val is not None:
            payload[key] = val.strip()

    if photos is not None:
        payload["photos"] = photos
    if video is not None:
        payload["video"] = video
    if specifications is not None:
        payload["specifications"] = specifications
    if documents is not None:
        payload["documents"] = documents

    try:
        return ProductEditIn.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


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

    body = await parse_product_edit_request(request)
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


from pydantic import BaseModel

class RelistSubmitIn(BaseModel):
    category: str
    title: str
    brand: str
    model: str
    condition: str
    description: str
    product_price: float
    expected_price: float
    photos: List[str]
    video: Optional[str] = None
    specifications: dict
    documents: dict
    cashfreeOrderId: str

class RelistFailIn(BaseModel):
    cashfreeOrderId: str
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
        
    from app.routes.payments import create_cashfree_order

    amount = 100
    order = await create_cashfree_order(
        amount_paise=amount,
        currency="INR",
        user=user,
        order_tags={
            "user_id": user.user_id,
            "product_id": product_id,
            "purpose": "relist",
        },
    )

    product.relist_payment_order_id = order["order_id"]
    product.relist_payment_status = "created"
    db.commit()

    return {
        "gateway": "cashfree",
        "cashfree_mode": CASHFREE_ENV,
        "orderId": order["order_id"],
        "paymentSessionId": order.get("payment_session_id"),
        "amount": amount,
        "currency": order.get("order_currency") or "INR",
        "orderStatus": order.get("order_status"),
    }


async def parse_relist_submit_request(request: Request) -> RelistSubmitIn:
    content_type = (request.headers.get("content-type") or "").lower()
    content_length = request.headers.get("content-length", "-")
    logger.info("relist_submit request content_type=%s content_length=%s", content_type, content_length)

    if "multipart/form-data" not in content_type:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
        
        if isinstance(payload.get("photos"), list):
            processed_photos = []
            for p in payload["photos"]:
                saved = await handle_file_value(p, MAX_IMAGE_SIZE, ALLOWED_IMAGE_EXT, ALLOWED_IMAGE_MIME)
                if saved:
                    processed_photos.append(saved)
            payload["photos"] = processed_photos
            
        if payload.get("video"):
            saved = await handle_file_value(payload["video"], MAX_VIDEO_SIZE, ALLOWED_VIDEO_EXT, ALLOWED_VIDEO_MIME)
            if saved:
                payload["video"] = saved
                
        if isinstance(payload.get("documents"), dict):
            processed_docs = {}
            for k, v in payload["documents"].items():
                saved = await handle_file_value(v, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
                if saved:
                    processed_docs[k] = saved
            payload["documents"] = processed_docs

        try:
            return RelistSubmitIn.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

    form = await request.form()

    photos = []
    for key in MULTIPART_PHOTO_KEYS:
        for item in form.getlist(key):
            saved = await handle_file_value(item, MAX_IMAGE_SIZE, ALLOWED_IMAGE_EXT, ALLOWED_IMAGE_MIME)
            if saved:
                photos.append(saved)

    video = None
    for key in MULTIPART_VIDEO_KEYS:
        value = form.get(key)
        saved = await handle_file_value(value, MAX_VIDEO_SIZE, ALLOWED_VIDEO_EXT, ALLOWED_VIDEO_MIME)
        if saved:
            video = saved
            break

    specifications = parse_json_field(form.get("specifications") or form.get("specs"), {})
    documents = parse_json_field(form.get("documents"), {})

    for key, value in form.multi_items():
        if key in MULTIPART_SCALAR_KEYS or key in MULTIPART_PHOTO_KEYS or key in MULTIPART_VIDEO_KEYS or key in MULTIPART_DOCUMENT_KEYS:
            continue
        saved = await handle_file_value(value, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
        if saved:
            documents[key] = saved

    for key in MULTIPART_DOCUMENT_KEYS:
        value = form.get(key)
        saved = await handle_file_value(value, MAX_DOC_SIZE, ALLOWED_DOC_EXT, ALLOWED_DOC_MIME)
        if saved:
            documents[key] = saved

    payload = {
        "title": (form.get("title") or "").strip(),
        "category": (form.get("category") or form.get("product_type") or "").strip(),
        "brand": (form.get("brand") or "").strip(),
        "model": (form.get("model") or "").strip(),
        "condition": (form.get("condition") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "product_price": form.get("product_price") or form.get("price"),
        "expected_price": form.get("expected_price") or form.get("expectedPrice"),
        "photos": photos,
        "video": video,
        "specifications": specifications,
        "documents": documents,
        "cashfreeOrderId": (form.get("cashfreeOrderId") or form.get("cashfree_order_id") or "").strip(),
    }
    try:
        return RelistSubmitIn.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


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
        
    body = await parse_relist_submit_request(request)
        
    from app.routes.payments import fetch_cashfree_order
    from app.models_sql import PaymentTransaction

    order = await fetch_cashfree_order(body.cashfreeOrderId)
    if str(order.get("order_status") or "").upper() != "PAID":
        raise HTTPException(status_code=400, detail=f"Payment not completed. Current status: {order.get('order_status')}")

    product.relist_payment_status = "paid"
    product.relist_payment_id = body.cashfreeOrderId
    product.relist_payment_order_id = body.cashfreeOrderId
    
    new_product = Product(
        product_id=f"prod_{uuid.uuid4().hex[:12]}",
        seller_id=user.user_id,
        seller_name=user.name or "",
        title=body.title,
        product_type=body.category.lower().strip(),
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
        parent_product_id=product_id,
        is_relisted=True,
        relist_count=(product.relist_count or 0) + 1,
        bid_count=0
    )
    db.add(new_product)
    
    new_tx = PaymentTransaction(
        payment_id=f"paytxn_{uuid.uuid4().hex[:12]}",
        user_id=user.user_id,
        user_role=user.role,
        plan_id=f"relist_{body.category.lower()}",
        plan_name=f"Relist fee - {body.category}",
        amount=100,
        currency="INR",
        payment_gateway="cashfree",
        cashfree_order_id=body.cashfreeOrderId,
        cashfree_payment_session_id=order.get("payment_session_id"),
        cashfree_order_status=order.get("order_status"),
        status="paid",
        receipt=f"rcpt_relist_{uuid.uuid4().hex[:20]}",
        notes={"old_product_id": product_id, "new_product_id": new_product.product_id}
    )
    db.add(new_tx)
    
    create_notification(
        db,
        user_id=user.user_id,
        title="Product Relisted",
        message=f"Your listing '{body.title}' has been relisted and submitted for verification.",
        notif_type="product_submitted",
        product_id=new_product.product_id,
    )
    notify_admins(
        db,
        "New relisted product submitted",
        f"{user.name} relisted '{body.title}'.",
        "product_submitted",
        new_product.product_id,
    )
    
    db.commit()
    db.refresh(new_product)
    
    return {
        "message": "Relisted listing submitted for admin approval",
        "newListingId": new_product.product_id,
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
        
    product.relist_payment_status = "failed"
    product.relist_payment_order_id = body.cashfreeOrderId
    db.commit()
    return {"message": "Relist payment failed status recorded"}
