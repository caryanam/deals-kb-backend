from decimal import Decimal
import hashlib
from urllib.parse import urlparse

from app.utils import iso


def value(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def money(amount):
    if isinstance(amount, Decimal):
        return float(amount)
    return amount


def serialize_user(user) -> dict:
    return {
        "user_id": value(user, "user_id"),
        "email": value(user, "email"),
        "name": value(user, "name", ""),
        "role": value(user, "role"),
        "auth_provider": value(user, "auth_provider", "email"),
        "mobile_number": value(user, "mobile_number"),
        "buyer_access_until": iso(value(user, "buyer_access_until")),
        "created_at": iso(value(user, "created_at")) or "",
    }



def _public_base_url() -> str:
    """Always read BACKEND_URL fresh from config so the correct value is used
    regardless of module import order or late .env loading."""
    from app.config import BACKEND_URL  # noqa: PLC0415 – intentional lazy import
    return BACKEND_URL.rstrip("/")


def build_public_media_url(path: str) -> str:
    """Return a fully-qualified production-safe media URL.

    Rules (in priority order):
    1. Empty / None  → return as-is.
    2. Corrupted UploadFile(...) string → return "".
    3. Already starts with the correct public base → return unchanged.
    4. Any http(s) URL whose path begins with /uploads/ → rewrite host to public base.
    5. Starts with /uploads/ → prepend public base.
    6. Bare filename (no slashes, has a dot) → prepend public base + /uploads/.
    7. Anything else → return as-is.
    """
    if not path:
        return path

    normalized = str(path).strip()

    if normalized.startswith("UploadFile("):
        return ""

    base = _public_base_url()

    # Already correct public URL – return unchanged.
    if normalized.startswith(base):
        return normalized

    # Absolute URL (any host) pointing at an /uploads/ path → rewrite host.
    if normalized.startswith("http://") or normalized.startswith("https://"):
        parsed = urlparse(normalized)
        if parsed.path.startswith("/uploads/"):
            return f"{base}{parsed.path}"
        return normalized

    # Relative /uploads/... path → prepend public base.
    if normalized.startswith("/uploads/"):
        return f"{base}{normalized}"

    # Bare filename (e.g. "abc123.jpg") → serve from /uploads/.
    if "/" not in normalized and "\\" not in normalized and "." in normalized:
        return f"{base}/uploads/{normalized}"

    return path


# Alias kept for backwards compatibility with any call-sites that use the old name.
format_file_url = build_public_media_url


PRIVATE_PRODUCT_DOCUMENT_FIELDS = {"aadhaar_card", "pan_card"}
PRODUCT_IMAGE_DOCUMENT_FIELDS = {"front_view_image", "back_view_image", "side_view_image"}
VEHICLE_PRODUCT_TYPES = {"car", "bike"}
_MEDIA_CONTENT_HASH_CACHE: dict[str, str | None] = {}


def _vehicle_image_urls(documents: dict) -> dict:
    return {
        "front_view_image": documents.get("front_view_image"),
        "back_view_image": documents.get("back_view_image"),
        "side_view_image": documents.get("side_view_image"),
    }


def _media_ref(path: str | None) -> str | None:
    if not path:
        return None
    normalized = str(path).strip()
    if not normalized:
        return None
    parsed = urlparse(normalized)
    media_path = parsed.path if parsed.scheme else normalized
    if "/uploads/" not in media_path and not media_path.startswith("uploads/"):
        return None
    return media_path.replace("\\", "/").rstrip("/").split("/")[-1] or None


def _media_content_hash(path: str | None) -> str | None:
    ref = _media_ref(path)
    if not ref:
        return None
    if ref in _MEDIA_CONTENT_HASH_CACHE:
        return _MEDIA_CONTENT_HASH_CACHE[ref]

    try:
        from app.database import SessionLocal  # noqa: PLC0415
        from app.models_sql import MediaAsset  # noqa: PLC0415

        db = SessionLocal()
        try:
            asset = db.query(MediaAsset).filter(MediaAsset.asset_id == ref).first()
            if not asset:
                asset = db.query(MediaAsset).filter(MediaAsset.storage_key == ref).first()
            if not asset:
                asset = db.query(MediaAsset).filter(MediaAsset.filename == ref).first()
            digest = hashlib.sha256(asset.content).hexdigest() if asset and asset.content is not None else None
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - best-effort display cleanup only
        digest = None

    _MEDIA_CONTENT_HASH_CACHE[ref] = digest
    return digest


def serialize_product(product, include_private_documents: bool = True) -> dict:
    location_data = None
    try:
        from app.database import SessionLocal
        from app.models_sql import ProductLocation
        db = SessionLocal()
        try:
            loc = db.query(ProductLocation).filter(ProductLocation.product_id == value(product, "product_id")).first()
            if loc:
                location_data = {
                    "latitude": float(loc.latitude),
                    "longitude": float(loc.longitude),
                    "address": loc.address,
                    "full_address": loc.full_address
                }
        finally:
            db.close()
    except Exception as e:
        print(f"Error fetching product location for serialization: {e}")

    photos_raw = value(product, "photos", []) or []
    photos = [format_file_url(p) for p in photos_raw]
    video = format_file_url(value(product, "video"))
    
    docs_raw = value(product, "documents", {}) or {}
    documents = {
        k: format_file_url(v)
        for k, v in docs_raw.items()
        if k not in PRODUCT_IMAGE_DOCUMENT_FIELDS
        and (include_private_documents or k not in PRIVATE_PRODUCT_DOCUMENT_FIELDS)
    }
    vehicle_images = _vehicle_image_urls({k: format_file_url(v) for k, v in docs_raw.items()})
    product_type = value(product, "product_type")
    side_view_image = vehicle_images["side_view_image"]

    if product_type in VEHICLE_PRODUCT_TYPES and side_view_image:
        side_hash = _media_content_hash(side_view_image)
        photos = [
            side_view_image,
            *[
                photo
                for photo in photos
                if photo != side_view_image
                and (not side_hash or _media_content_hash(photo) != side_hash)
            ],
        ]

    photos = list(dict.fromkeys(photo for photo in photos if photo))
    cover_image = side_view_image if product_type in VEHICLE_PRODUCT_TYPES and side_view_image else (photos[0] if photos else None)

    return {
        "product_id": value(product, "product_id"),
        "seller_id": value(product, "seller_id"),
        "seller_name": value(product, "seller_name", ""),
        "title": value(product, "title"),
        "product_type": product_type,
        "brand": value(product, "brand"),
        "model": value(product, "model"),
        "condition": value(product, "product_condition", value(product, "condition")),
        "description": value(product, "description"),
        "expected_price": money(value(product, "expected_price")),
        "product_price": money(value(product, "product_price")),
        "currency": "INR",
        "photos": photos,
        "cover_image": cover_image,
        "front_view_image": vehicle_images["front_view_image"],
        "back_view_image": vehicle_images["back_view_image"],
        "side_view_image": side_view_image,
        "video": video,
        "specifications": value(product, "specifications", {}) or {},
        "documents": documents,
        "status": value(product, "status"),
        "reject_reason": value(product, "reject_reason"),
        "auction_start": iso(value(product, "auction_start")),
        "auction_end": iso(value(product, "auction_end")),
        "current_bid": money(value(product, "current_bid")),
        "highest_bidder_id": value(product, "highest_bidder_id"),
        "highest_bidder_name": value(product, "highest_bidder_name"),
        "bid_count": value(product, "bid_count", 0) or 0,
        "winner_id": value(product, "winner_id"),
        "winner_name": value(product, "winner_name"),
        "is_flagged": bool(value(product, "is_flagged", False)),
        "report_count": value(product, "report_count", 0) or 0,
        "is_cancelled": bool(value(product, "is_cancelled", False)),
        "cancel_reason": value(product, "cancel_reason"),
        "cancelled_at": iso(value(product, "cancelled_at")),
        "created_at": iso(value(product, "created_at")),
        "submitted_at": iso(value(product, "submitted_at", value(product, "created_at"))),
        "updated_at": iso(value(product, "updated_at")),
        "approved_at": iso(value(product, "approved_at")),
        "rejected_at": iso(value(product, "rejected_at")),
        "parent_product_id": value(product, "parent_product_id"),
        "is_relisted": bool(value(product, "is_relisted", False)),
        "relist_count": value(product, "relist_count", 0) or 0,
        "relist_payment_status": value(product, "relist_payment_status"),
        "relist_payment_order_id": value(product, "relist_payment_order_id"),
        "relist_payment_id": value(product, "relist_payment_id"),
        "location": location_data,
    }


def serialize_bid(bid) -> dict:
    return {
        "bid_id": value(bid, "bid_id"),
        "product_id": value(bid, "product_id"),
        "bidder_id": value(bid, "bidder_id"),
        "bidder_name": value(bid, "bidder_name"),
        "amount": money(value(bid, "amount")),
        "currency": "INR",
        "created_at": iso(value(bid, "created_at")),
    }


def serialize_notification(notification) -> dict:
    return {
        "notif_id": value(notification, "notif_id"),
        "user_id": value(notification, "user_id"),
        "role": value(notification, "role"),
        "product_id": value(notification, "product_id"),
        "title": value(notification, "title"),
        "body": value(notification, "message"),
        "message": value(notification, "message"),
        "type": value(notification, "type"),
        "read": bool(value(notification, "is_read", False)),
        "is_read": bool(value(notification, "is_read", False)),
        "is_cleared": bool(value(notification, "is_cleared", False)),
        "created_at": iso(value(notification, "created_at")),
        "read_at": iso(value(notification, "read_at")),
        "cleared_at": iso(value(notification, "cleared_at")),
    }


def serialize_chat_message(message) -> dict:
    return {
        "message_id": value(message, "message_id"),
        "conversation_id": value(message, "conversation_id"),
        "sender_id": value(message, "sender_id"),
        "receiver_id": value(message, "receiver_id"),
        "message": value(message, "message"),
        "is_read": bool(value(message, "is_read", False)),
        "created_at": iso(value(message, "created_at")),
    }


def serialize_chat_conversation(conversation, product=None, buyer=None, seller=None, last_message=None) -> dict:
    payload = {
        "conversation_id": value(conversation, "conversation_id"),
        "request_id": value(conversation, "request_id"),
        "product_id": value(conversation, "product_id"),
        "buyer_id": value(conversation, "buyer_id"),
        "seller_id": value(conversation, "seller_id"),
        "created_at": iso(value(conversation, "created_at")),
        "updated_at": iso(value(conversation, "updated_at")),
        "last_message": serialize_chat_message(last_message) if last_message else None,
    }
    if product:
        payload["product"] = {
            "product_id": value(product, "product_id"),
            "title": value(product, "title"),
            "status": value(product, "status"),
            "winner_id": value(product, "winner_id"),
        }
    if buyer:
        payload["buyer"] = {
            "user_id": value(buyer, "user_id"),
            "name": value(buyer, "name", ""),
        }
    if seller:
        payload["seller"] = {
            "user_id": value(seller, "user_id"),
            "name": value(seller, "name", ""),
        }
    return payload


def serialize_chat_request(chat_request, conversation=None) -> dict:
    payload = {
        "request_id": value(chat_request, "request_id"),
        "product_id": value(chat_request, "product_id"),
        "listing_name": value(chat_request, "listing_name"),
        "buyer_id": value(chat_request, "buyer_id"),
        "buyer_name": value(chat_request, "buyer_name"),
        "seller_id": value(chat_request, "seller_id"),
        "seller_name": value(chat_request, "seller_name"),
        "winning_bid_amount": money(value(chat_request, "winning_bid_amount")),
        "status": value(chat_request, "status"),
        "buyer_message": value(chat_request, "buyer_message"),
        "seller_response_message": value(chat_request, "seller_response_message"),
        "created_at": iso(value(chat_request, "created_at")),
        "updated_at": iso(value(chat_request, "updated_at")),
        "responded_at": iso(value(chat_request, "responded_at")),
    }
    if conversation:
        payload["conversation_id"] = value(conversation, "conversation_id")
        payload["conversation"] = serialize_chat_conversation(conversation)
    return payload


def serialize_community_request(community_request, is_joined_by_me=False, is_created_by_me=False, admin=False) -> dict:
    payload = {
        "request_id": value(community_request, "request_id"),
        "product_type": value(community_request, "product_type"),
        "brand": value(community_request, "brand"),
        "model": value(community_request, "model"),
        "budget_min": money(value(community_request, "budget_min")),
        "budget_max": money(value(community_request, "budget_max")),
        "condition_preference": value(community_request, "condition_preference"),
        "description": value(community_request, "description"),
        "interested_count": value(community_request, "interested_count", 0) or 0,
        "status": value(community_request, "status"),
        "created_by_name": value(community_request, "created_by_name"),
        "is_joined_by_me": bool(is_joined_by_me),
        "is_created_by_me": bool(is_created_by_me),
        "created_at": iso(value(community_request, "created_at")),
        "updated_at": iso(value(community_request, "updated_at")),
    }
    if admin:
        payload["created_by_user_id"] = value(community_request, "created_by_user_id")
    return payload


def serialize_report(report) -> dict:
    return {
        "report_id": value(report, "report_id"),
        "product_id": value(report, "product_id"),
        "reporter_id": value(report, "reporter_id"),
        "reporter_name": value(report, "reporter_name"),
        "reporter_role": value(report, "reporter_role"),
        "reported_user_id": value(report, "reported_user_id"),
        "report_type": value(report, "report_type"),
        "reason": value(report, "reason"),
        "evidence": value(report, "evidence", []) or [],
        "status": value(report, "status"),
        "admin_note": value(report, "admin_note"),
        "action_taken": value(report, "action_taken"),
        "created_at": iso(value(report, "created_at")),
        "updated_at": iso(value(report, "updated_at")),
    }


def serialize_payment(payment) -> dict:
    return {
        "payment_id": value(payment, "payment_id"),
        "order_id": value(payment, "order_id"),
        "user_id": value(payment, "user_id"),
        "user_role": value(payment, "user_role"),
        "plan_id": value(payment, "plan_id"),
        "plan_name": value(payment, "plan_name"),
        "listing_id": value(payment, "listing_id"),
        "subscription_plan_id": value(payment, "subscription_plan_id"),
        "payment_type": value(payment, "payment_type"),
        "amount": str(value(payment, "amount")) if value(payment, "amount") is not None else None,
        "currency": value(payment, "currency"),
        "payment_gateway": value(payment, "payment_gateway"),
        "gateway_tracking_id": value(payment, "gateway_tracking_id"),
        "bank_reference_number": value(payment, "bank_reference_number"),
        "order_status": value(payment, "order_status"),
        "payment_mode": value(payment, "payment_mode"),
        "failure_message": value(payment, "failure_message"),
        "status_code": value(payment, "status_code"),
        "status_message": value(payment, "status_message"),
        "status": value(payment, "status"),
        "receipt": value(payment, "receipt"),
        "notes": value(payment, "notes", {}) or {},
        "initiated_at": iso(value(payment, "initiated_at")),
        "completed_at": iso(value(payment, "completed_at")),
        "created_at": iso(value(payment, "initiated_at") or value(payment, "created_at")),
        "paid_at": iso(value(payment, "paid_at")),
        "updated_at": iso(value(payment, "updated_at")),
    }


def serialize_admin_user(user, product_count=0) -> dict:
    return {
        "user_id": value(user, "user_id"),
        "name": value(user, "name", ""),
        "email": value(user, "email"),
        "mobile_number": value(user, "mobile_number"),
        "role": value(user, "role"),
        "created_at": iso(value(user, "created_at")) or "",
        "product_count": product_count,
    }
