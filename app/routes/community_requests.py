import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.database import get_db
from app.models import CommunityRequestCreateIn
from app.models_sql import CommunityRequest, CommunityRequestMember, User
from app.serializers import serialize_community_request
from app.services.products import ALLOWED_PRODUCT_TYPES
from app.utils import now_utc

router = APIRouter(prefix="/community-requests", tags=["Community Requests"])

def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def clean_display_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def require_buyer(user: User, action: str):
    if user.role != "Buyer":
        raise HTTPException(status_code=403, detail=f"Only buyers can {action} community requests.")


def validate_request_body(body: CommunityRequestCreateIn):
    product_type = normalize_text(body.product_type)
    brand = clean_display_text(body.brand)
    model = clean_display_text(body.model)

    if product_type not in ALLOWED_PRODUCT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid product type.")
    if not brand or not model:
        raise HTTPException(status_code=400, detail="brand and model are required.")
    if body.budget_min is not None and body.budget_min < 0:
        raise HTTPException(status_code=400, detail="budget_min cannot be negative.")
    if body.budget_max is not None and body.budget_max < 0:
        raise HTTPException(status_code=400, detail="budget_max cannot be negative.")
    if body.budget_min is not None and body.budget_max is not None and body.budget_max < body.budget_min:
        raise HTTPException(status_code=400, detail="Budget max cannot be less than budget min.")

    return product_type, brand, model


def active_member(db: Session, request_id: str, buyer_id: str):
    return (
        db.query(CommunityRequestMember)
        .filter(
            CommunityRequestMember.request_id == request_id,
            CommunityRequestMember.buyer_id == buyer_id,
            CommunityRequestMember.is_active.is_(True),
        )
        .first()
    )


def member_any(db: Session, request_id: str, buyer_id: str):
    return (
        db.query(CommunityRequestMember)
        .filter(
            CommunityRequestMember.request_id == request_id,
            CommunityRequestMember.buyer_id == buyer_id,
        )
        .first()
    )


def is_joined(db: Session, request_id: str, user: User) -> bool:
    return bool(user and user.role == "Buyer" and active_member(db, request_id, user.user_id))


def recalc_interested_count(db: Session, community_request: CommunityRequest):
    community_request.interested_count = (
        db.query(CommunityRequestMember)
        .filter(
            CommunityRequestMember.request_id == community_request.request_id,
            CommunityRequestMember.is_active.is_(True),
        )
        .count()
    )


def request_or_404(db: Session, request_id: str) -> CommunityRequest:
    community_request = db.query(CommunityRequest).filter(CommunityRequest.request_id == request_id).first()
    if not community_request:
        raise HTTPException(status_code=404, detail="Community request not found.")
    return community_request


def query_requests(
    db: Session,
    product_type: Optional[str] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    query = db.query(CommunityRequest)
    if status:
        query = query.filter(CommunityRequest.status == normalize_text(status))
    else:
        query = query.filter(CommunityRequest.status == "active")
    if product_type:
        query = query.filter(CommunityRequest.product_type == normalize_text(product_type))
    if brand:
        query = query.filter(CommunityRequest.brand == clean_display_text(brand))
    if model:
        query = query.filter(CommunityRequest.model == clean_display_text(model))
    if search:
        pattern = f"%{clean_display_text(search)}%"
        query = query.filter(
            or_(
                CommunityRequest.brand.ilike(pattern),
                CommunityRequest.model.ilike(pattern),
                CommunityRequest.description.ilike(pattern),
            )
        )
    return query.order_by(CommunityRequest.created_at.desc())


@router.post("")
def create_community_request(
    body: CommunityRequestCreateIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    require_buyer(user, "create")
    product_type, brand, model = validate_request_body(body)

    community_request = CommunityRequest(
        request_id=f"cr_{uuid.uuid4().hex[:12]}",
        created_by_user_id=user.user_id,
        created_by_name=user.name or "Buyer",
        product_type=product_type,
        brand=brand,
        model=model,
        budget_min=body.budget_min,
        budget_max=body.budget_max,
        condition_preference=clean_display_text(body.condition_preference),
        description=clean_display_text(body.description),
        interested_count=1,
        status="active",
        created_at=now_utc().replace(tzinfo=None),
        updated_at=now_utc().replace(tzinfo=None),
    )
    db.add(community_request)
    db.flush()
    db.add(
        CommunityRequestMember(
            request_id=community_request.request_id,
            buyer_id=user.user_id,
            buyer_name=user.name or "Buyer",
            is_active=True,
            joined_at=now_utc().replace(tzinfo=None),
            updated_at=now_utc().replace(tzinfo=None),
        )
    )
    db.commit()
    db.refresh(community_request)
    return {
        "message": "Community request posted successfully",
        "request": serialize_community_request(
            community_request,
            is_joined_by_me=True,
            is_created_by_me=True,
        ),
    }


@router.get("")
def list_community_requests(
    product_type: Optional[str] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    if user.role not in ("Buyer", "Admin"):
        raise HTTPException(status_code=403, detail="Only buyers or admins can view community requests.")
    requests = query_requests(db, product_type, brand, model, status, search).limit(500).all()
    return [
        serialize_community_request(
            item,
            is_joined_by_me=is_joined(db, item.request_id, user),
            is_created_by_me=user.user_id == item.created_by_user_id,
        )
        for item in requests
    ]


@router.get("/my")
def my_community_requests(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    require_buyer(user, "view own")
    created = (
        db.query(CommunityRequest)
        .filter(CommunityRequest.created_by_user_id == user.user_id)
        .order_by(CommunityRequest.created_at.desc())
        .all()
    )
    joined_ids = [
        row.request_id
        for row in db.query(CommunityRequestMember)
        .filter(CommunityRequestMember.buyer_id == user.user_id, CommunityRequestMember.is_active.is_(True))
        .all()
    ]
    joined = []
    if joined_ids:
        joined = (
            db.query(CommunityRequest)
            .filter(CommunityRequest.request_id.in_(joined_ids), CommunityRequest.created_by_user_id != user.user_id)
            .order_by(CommunityRequest.created_at.desc())
            .all()
        )
    return {
        "created": [
            serialize_community_request(item, is_joined_by_me=is_joined(db, item.request_id, user), is_created_by_me=True)
            for item in created
        ],
        "joined": [
            serialize_community_request(item, is_joined_by_me=True, is_created_by_me=False)
            for item in joined
        ],
    }


@router.get("/{request_id}")
def get_community_request(request_id: str, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    if user.role not in ("Buyer", "Admin"):
        raise HTTPException(status_code=403, detail="Only buyers or admins can view community requests.")
    community_request = request_or_404(db, request_id)
    return serialize_community_request(
        community_request,
        is_joined_by_me=is_joined(db, request_id, user),
        is_created_by_me=user.user_id == community_request.created_by_user_id,
        admin=user.role == "Admin",
    )


@router.post("/{request_id}/join")
def join_community_request(request_id: str, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    require_buyer(user, "join")
    community_request = request_or_404(db, request_id)
    if community_request.status != "active":
        raise HTTPException(status_code=400, detail="Only active community requests can be joined.")
    if community_request.created_by_user_id == user.user_id:
        raise HTTPException(status_code=400, detail="The creator of the request cannot join/leave it.")

    existing = member_any(db, request_id, user.user_id)
    if existing and existing.is_active:
        raise HTTPException(status_code=409, detail="You have already joined this community request.")
    if existing:
        existing.is_active = True
        existing.buyer_name = user.name or existing.buyer_name
        existing.updated_at = now_utc().replace(tzinfo=None)
    else:
        db.add(
            CommunityRequestMember(
                request_id=request_id,
                buyer_id=user.user_id,
                buyer_name=user.name or "Buyer",
                is_active=True,
                joined_at=now_utc().replace(tzinfo=None),
                updated_at=now_utc().replace(tzinfo=None),
            )
        )
    db.flush()
    recalc_interested_count(db, community_request)
    community_request.updated_at = now_utc().replace(tzinfo=None)
    db.commit()
    db.refresh(community_request)
    return {
        "message": "Interest added successfully. We'll notify you when a matching product is approved.",
        "request_id": request_id,
        "is_joined_by_me": True,
        "interested_count": community_request.interested_count,
    }


@router.delete("/{request_id}/leave")
def leave_community_request(request_id: str, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    require_buyer(user, "leave")
    community_request = request_or_404(db, request_id)
    if community_request.created_by_user_id == user.user_id:
        raise HTTPException(status_code=400, detail="The creator of the request cannot remove their interest. You can delete the request instead.")
        
    member = active_member(db, request_id, user.user_id)
    if not member:
        raise HTTPException(status_code=404, detail="Joined community request not found.")
    member.is_active = False
    member.updated_at = now_utc().replace(tzinfo=None)
    db.flush()
    recalc_interested_count(db, community_request)
    community_request.interested_count = max(0, community_request.interested_count or 0)
    community_request.updated_at = now_utc().replace(tzinfo=None)
    db.commit()
    db.refresh(community_request)
    return {
        "message": "Interest removed successfully",
        "request_id": request_id,
        "is_joined_by_me": False,
        "interested_count": community_request.interested_count,
    }


@router.delete("/{request_id}")
def delete_community_request(request_id: str, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    require_buyer(user, "delete")
    community_request = request_or_404(db, request_id)
    if community_request.created_by_user_id != user.user_id:
        raise HTTPException(status_code=403, detail="You can only delete requests created by you.")
    
    db.query(CommunityRequestMember).filter(CommunityRequestMember.request_id == request_id).delete()
    db.delete(community_request)
    db.commit()
    return {"message": "Community request deleted successfully."}
