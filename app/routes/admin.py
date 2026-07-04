from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import role_required
from app.database import get_db
from app.models import CommunityRequestStatusUpdate, ReportActionRequest, ReportStatusUpdate
from app.models_sql import Bid, CommunityRequest, Product, Report, User
from app.realtime import manager
from app.serializers import serialize_admin_user, serialize_bid, serialize_product, serialize_report, serialize_user
from app.services.notifications import create_notification
from app.services.products import ALLOWED_PRODUCT_TYPES
from app.utils import now_utc

router = APIRouter(prefix="/admin", tags=["admin"])

REPORT_STATUSES = {"pending", "under_review", "resolved", "rejected", "action_taken"}
REPORT_ACTIONS = {"resolve", "reject", "warn_user", "block_user", "cancel_auction", "mark_product_flagged"}
COMMUNITY_STATUSES = {"active", "matched", "closed", "disabled"}


def _clean_filter(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _serialize_admin_community_request(item: CommunityRequest):
    return {
        "request_id": item.request_id,
        "product_type": item.product_type,
        "brand": item.brand,
        "model": item.model,
        "budget_min": float(item.budget_min) if item.budget_min is not None else None,
        "budget_max": float(item.budget_max) if item.budget_max is not None else None,
        "condition_preference": item.condition_preference,
        "description": item.description,
        "interested_count": item.interested_count or 0,
        "status": item.status,
        "created_by_name": item.created_by_name,
        "created_by_user_id": item.created_by_user_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/users")
def admin_users(user: User = Depends(role_required(["Admin"])), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.role.in_(["Buyer", "Seller", "Dealer"])).order_by(User.created_at.desc()).limit(1000).all()
    result = []
    for user_doc in users:
        if user_doc.role in ("Seller", "Dealer"):
            product_count = db.query(Product).filter(Product.seller_id == user_doc.user_id).count()
        else:
            product_count = db.query(Product).filter(Product.winner_id == user_doc.user_id).count()
        result.append(serialize_admin_user(user_doc, product_count=product_count))
    return result


@router.get("/community-requests")
def admin_community_requests(
    product_type: Optional[str] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    user: User = Depends(role_required(["Admin"])),
    db: Session = Depends(get_db),
):
    query = db.query(CommunityRequest)
    if product_type:
        query = query.filter(CommunityRequest.product_type == _clean_filter(product_type).lower())
    if brand:
        query = query.filter(CommunityRequest.brand == _clean_filter(brand))
    if model:
        query = query.filter(CommunityRequest.model == _clean_filter(model))
    if status:
        query = query.filter(CommunityRequest.status == _clean_filter(status).lower())
    if search:
        pattern = f"%{_clean_filter(search)}%"
        query = query.filter(
            (CommunityRequest.brand.ilike(pattern))
            | (CommunityRequest.model.ilike(pattern))
            | (CommunityRequest.description.ilike(pattern))
        )
    requests = query.order_by(CommunityRequest.created_at.desc()).limit(1000).all()
    return [_serialize_admin_community_request(item) for item in requests]


@router.patch("/community-requests/{request_id}/status")
def admin_update_community_request_status(
    request_id: str,
    body: CommunityRequestStatusUpdate,
    user: User = Depends(role_required(["Admin"])),
    db: Session = Depends(get_db),
):
    status = _clean_filter(body.status).lower()
    if status not in COMMUNITY_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid community request status.")
    community_request = db.query(CommunityRequest).filter(CommunityRequest.request_id == request_id).first()
    if not community_request:
        raise HTTPException(status_code=404, detail="Community request not found.")
    community_request.status = status
    community_request.updated_at = now_utc().replace(tzinfo=None)
    db.commit()
    return {
        "message": "Community request status updated successfully",
        "request_id": request_id,
        "status": status,
    }


@router.get("/users/{user_id}")
def admin_user_details(user_id: str, user: User = Depends(role_required(["Admin"])), db: Session = Depends(get_db)):
    user_doc = db.query(User).filter(User.user_id == user_id, User.role.in_(["Buyer", "Seller", "Dealer"])).first()
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    products = (
        db.query(Product)
        .filter(Product.seller_id == user_id)
        .order_by(Product.created_at.desc())
        .all()
    )
    if user_doc.role == "Buyer":
        products = (
            db.query(Product)
            .filter(Product.winner_id == user_id)
            .order_by(Product.created_at.desc())
            .all()
        )

    return {
        "user": {
            "user_id": user_doc.user_id,
            "name": user_doc.name,
            "email": user_doc.email,
            "mobile_number": user_doc.mobile_number,
            "role": user_doc.role,
            "created_at": serialize_admin_user(user_doc)["created_at"],
        },
        "products": [
            {
                "product_id": product.product_id,
                "title": product.title,
                "product_type": product.product_type,
                "status": product.status,
                "created_at": serialize_product(product)["created_at"],
                "updated_at": serialize_product(product)["updated_at"],
            }
            for product in products
        ],
    }


@router.get("/products/history")
def admin_product_history(
    status: Optional[str] = None,
    product_type: Optional[str] = None,
    user: User = Depends(role_required(["Admin"])),
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(Product.status.in_(["approved", "rejected", "cancelled"]))
    if status:
        query = query.filter(Product.status == status)
    if product_type and product_type != "all":
        query = query.filter(Product.product_type == product_type.lower().strip())
    products = query.order_by(Product.updated_at.desc()).limit(500).all()
    return [serialize_product(product) for product in products]


@router.get("/reports")
def admin_reports(
    status: Optional[str] = None,
    product_id: Optional[str] = None,
    report_type: Optional[str] = None,
    reporter_id: Optional[str] = None,
    reported_user_id: Optional[str] = None,
    user: User = Depends(role_required(["Admin"])),
    db: Session = Depends(get_db),
):
    query = db.query(Report)
    if status:
        query = query.filter(Report.status == status)
    if product_id:
        query = query.filter(Report.product_id == product_id)
    if report_type:
        query = query.filter(Report.report_type == report_type)
    if reporter_id:
        query = query.filter(Report.reporter_id == reporter_id)
    if reported_user_id:
        query = query.filter(Report.reported_user_id == reported_user_id)
    reports = query.order_by(Report.created_at.desc()).limit(1000).all()
    return [serialize_report(report) for report in reports]


@router.get("/reports/{report_id}")
def admin_report_details(
    report_id: str,
    user: User = Depends(role_required(["Admin"])),
    db: Session = Depends(get_db),
):
    report = db.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    reporter = db.query(User).filter(User.user_id == report.reporter_id).first()
    reported_user = None
    if report.reported_user_id:
        reported_user = db.query(User).filter(User.user_id == report.reported_user_id).first()

    product = None
    bid_history = []
    if report.product_id:
        product = db.query(Product).filter(Product.product_id == report.product_id).first()
        bid_history = (
            db.query(Bid)
            .filter(Bid.product_id == report.product_id)
            .order_by(Bid.created_at.desc())
            .limit(200)
            .all()
        )

    return {
        "report": serialize_report(report),
        "reporter": serialize_user(reporter) if reporter else None,
        "reported_user": serialize_user(reported_user) if reported_user else None,
        "product": serialize_product(product) if product else None,
        "bid_history": [serialize_bid(bid) for bid in bid_history],
    }


@router.patch("/reports/{report_id}/status")
def admin_update_report_status(
    report_id: str,
    body: ReportStatusUpdate,
    user: User = Depends(role_required(["Admin"])),
    db: Session = Depends(get_db),
):
    if body.status not in REPORT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid report status")
    report = db.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.status = body.status
    if body.admin_note is not None:
        report.admin_note = body.admin_note
    report.updated_at = now_utc().replace(tzinfo=None)

    messages = {
        "under_review": "Your report is now under review.",
        "resolved": "Your report has been resolved.",
        "rejected": "Your report was reviewed and rejected.",
        "action_taken": "Action has been taken on your report.",
        "pending": "Your report status has been updated.",
    }
    create_notification(
        db,
        user_id=report.reporter_id,
        title="Report status updated",
        message=messages[body.status],
        notif_type="report_status_updated",
        product_id=report.product_id,
    )
    db.commit()
    db.refresh(report)
    return {"message": "Report status updated successfully", "report": serialize_report(report)}


@router.post("/reports/{report_id}/action")
async def admin_report_action(
    report_id: str,
    body: ReportActionRequest,
    user: User = Depends(role_required(["Admin"])),
    db: Session = Depends(get_db),
):
    if body.action not in REPORT_ACTIONS:
        raise HTTPException(status_code=400, detail="Invalid report action")
    report = db.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    admin_note = body.admin_note or report.admin_note or ""
    product = db.query(Product).filter(Product.product_id == report.product_id).first() if report.product_id else None
    reported_user = db.query(User).filter(User.user_id == report.reported_user_id).first() if report.reported_user_id else None

    if body.action == "resolve":
        report.status = "resolved"
        create_notification(db, report.reporter_id, "Report resolved", "Your report has been resolved.", "report_resolved", report.product_id)
    elif body.action == "reject":
        report.status = "rejected"
        create_notification(db, report.reporter_id, "Report rejected", "Your report was reviewed and rejected.", "report_rejected", report.product_id)
    elif body.action == "warn_user":
        if not reported_user:
            raise HTTPException(status_code=400, detail="reported_user_id is required for warn_user")
        report.status = "action_taken"
        create_notification(
            db,
            reported_user.user_id,
            "Admin warning",
            "Admin has issued a warning regarding your activity.",
            "admin_warning",
            report.product_id,
        )
    elif body.action == "block_user":
        if not reported_user:
            raise HTTPException(status_code=400, detail="reported_user_id is required for block_user")
        reported_user.is_blocked = True
        reported_user.blocked_reason = admin_note
        reported_user.blocked_at = now_utc().replace(tzinfo=None)
        report.status = "action_taken"
        create_notification(
            db,
            reported_user.user_id,
            "Account blocked",
            "Your account has been blocked. Please contact support.",
            "account_blocked",
            report.product_id,
        )
    elif body.action == "cancel_auction":
        if not product:
            raise HTTPException(status_code=400, detail="product_id is required for cancel_auction")
        product.is_cancelled = True
        product.is_flagged = True
        product.cancel_reason = admin_note
        product.cancelled_at = now_utc().replace(tzinfo=None)
        if product.status in ("live", "approved"):
            product.status = "cancelled"
        report.status = "action_taken"
        create_notification(
            db,
            product.seller_id,
            "Auction cancelled",
            "Your auction was cancelled by admin due to suspicious activity.",
            "auction_cancelled",
            product.product_id,
        )
        if product.highest_bidder_id:
            create_notification(
                db,
                product.highest_bidder_id,
                "Auction cancelled",
                "Auction was cancelled by admin due to suspicious activity.",
                "auction_cancelled",
                product.product_id,
            )
        create_notification(db, report.reporter_id, "Action taken", "Action has been taken on your report.", "report_action_taken", report.product_id)
        await manager.broadcast(product.product_id, {
            "type": "auction_cancelled",
            "product_id": product.product_id,
            "reason": admin_note or "Suspicious activity detected.",
        })
    elif body.action == "mark_product_flagged":
        if not product:
            raise HTTPException(status_code=400, detail="product_id is required for mark_product_flagged")
        product.is_flagged = True
        report.status = "action_taken"
        create_notification(db, report.reporter_id, "Action taken", "Action has been taken on your report.", "report_action_taken", report.product_id)

    report.admin_note = admin_note
    report.action_taken = body.action
    report.updated_at = now_utc().replace(tzinfo=None)
    db.commit()
    db.refresh(report)
    return {"message": "Action applied successfully", "report": serialize_report(report)}


@router.get("/analytics")
def admin_analytics(user: User = Depends(role_required(["Admin"])), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_buyers = db.query(User).filter(User.role == "Buyer").count()
    total_sellers = db.query(User).filter(User.role == "Seller").count()
    total_dealers = db.query(User).filter(User.role == "Dealer").count()
    total_products = db.query(Product).count()
    pending = db.query(Product).filter(Product.status == "pending").count()
    approved = db.query(Product).filter(Product.status == "approved").count()
    rejected = db.query(Product).filter(Product.status == "rejected").count()
    live = db.query(Product).filter(Product.status == "live").count()
    ended = db.query(Product).filter(Product.status == "ended").count()
    pending_reports = db.query(Report).filter(Report.status == "pending").count()
    under_review_reports = db.query(Report).filter(Report.status == "under_review").count()
    resolved_reports = db.query(Report).filter(Report.status == "resolved").count()
    flagged_products = db.query(Product).filter(Product.is_flagged.is_(True)).count()
    cancelled_auctions = db.query(Product).filter(Product.is_cancelled.is_(True)).count()
    total_bids = db.query(Bid).count()
    gmv = (
        db.query(func.coalesce(func.sum(Product.current_bid), 0))
        .filter(Product.status == "ended", Product.current_bid.isnot(None))
        .scalar()
    )

    products_by_type = {}
    for product_type in sorted(ALLOWED_PRODUCT_TYPES):
        products_by_type[product_type] = db.query(Product).filter(Product.product_type == product_type).count()

    total_community_requests = db.query(CommunityRequest).count()
    active_community_requests = db.query(CommunityRequest).filter(CommunityRequest.status == "active").count()
    top_requested_products = (
        db.query(
            CommunityRequest.product_type,
            CommunityRequest.brand,
            CommunityRequest.model,
            func.coalesce(func.sum(CommunityRequest.interested_count), 0).label("interested_count"),
        )
        .group_by(CommunityRequest.product_type, CommunityRequest.brand, CommunityRequest.model)
        .order_by(func.coalesce(func.sum(CommunityRequest.interested_count), 0).desc())
        .limit(10)
        .all()
    )

    return {
        "total_users": total_users,
        "total_buyers": total_buyers,
        "total_sellers": total_sellers,
        "total_dealers": total_dealers,
        "total_products": total_products,
        "total_listings": total_products,
        "pending_listings": pending,
        "approved_listings": approved,
        "rejected_listings": rejected,
        "live_auctions": live,
        "ended_auctions": ended,
        "pending_reports": pending_reports,
        "under_review_reports": under_review_reports,
        "resolved_reports": resolved_reports,
        "flagged_products": flagged_products,
        "cancelled_auctions": cancelled_auctions,
        "total_bids": total_bids,
        "gmv": float(gmv or 0),
        "currency": "INR",
        "products_by_type": products_by_type,
        "total_community_requests": total_community_requests,
        "active_community_requests": active_community_requests,
        "top_requested_products": [
            {
                "product_type": row.product_type,
                "brand": row.brand,
                "model": row.model,
                "interested_count": int(row.interested_count or 0),
            }
            for row in top_requested_products
        ],
    }
