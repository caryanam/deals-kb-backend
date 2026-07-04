import re

from sqlalchemy.orm import Session

from app.models_sql import CommunityRequest, CommunityRequestMember, Notification, Product
from app.services.notifications import create_notification


def normalize_match_value(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def match_community_requests_for_product(db: Session, product: Product) -> int:
    product_type = normalize_match_value(product.product_type)
    brand = normalize_match_value(product.brand)
    model = normalize_match_value(product.model)
    if not product_type or not brand or not model:
        return 0

    matched_count = 0
    requests = db.query(CommunityRequest).filter(CommunityRequest.status == "active").all()
    for request in requests:
        if (
            normalize_match_value(request.product_type) != product_type
            or normalize_match_value(request.brand) != brand
            or normalize_match_value(request.model) != model
        ):
            continue

        members = (
            db.query(CommunityRequestMember)
            .filter(
                CommunityRequestMember.request_id == request.request_id,
                CommunityRequestMember.is_active.is_(True),
            )
            .all()
        )
        message = (
            f'Good news! A product matching your community request "{request.brand} {request.model}" '
            "has been approved and will be live soon."
        )
        for member in members:
            duplicate = (
                db.query(Notification)
                .filter(
                    Notification.user_id == member.buyer_id,
                    Notification.product_id == product.product_id,
                    Notification.type == "community_request_match",
                    Notification.message == message,
                )
                .first()
            )
            if duplicate:
                continue
            create_notification(
                db,
                user_id=member.buyer_id,
                title="Matching Product Available",
                message=message,
                notif_type="community_request_match",
                product_id=product.product_id,
                role="Buyer",
            )
            matched_count += 1
    return matched_count
