import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.database import get_db
from app.models import ReportCreate
from app.models_sql import Product, Report, User
from app.serializers import serialize_report
from app.services.notifications import notify_admins
from app.utils import now_utc

router = APIRouter(prefix="/reports", tags=["reports"])

REPORT_TYPES = {
    "suspicious_auction",
    "fake_listing",
    "fake_bid",
    "shill_bidding",
    "wrong_product_details",
    "fake_documents",
    "abusive_user",
    "payment_contact_fraud",
    "chat_abuse",
    "fraud_attempt",
    "spam",
    "seller_buyer_dispute",
    "other",
}

PRODUCT_REPORT_TYPES = {
    "suspicious_auction",
    "fake_listing",
    "fake_bid",
    "shill_bidding",
    "wrong_product_details",
    "fake_documents",
}

ACTIVE_REPORT_STATUSES = {"pending", "under_review"}


def validate_report_payload(body: ReportCreate):
    if body.report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid report type")
    if not body.reason or len(body.reason.strip()) < 10:
        raise HTTPException(status_code=400, detail="Reason must be at least 10 characters")
    if body.report_type in PRODUCT_REPORT_TYPES and not body.product_id:
        raise HTTPException(status_code=400, detail="product_id is required for this report type")


@router.post("")
def create_report(
    body: ReportCreate,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    if user.role not in ("Buyer", "Seller", "Dealer", "Admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    validate_report_payload(body)

    product = None
    if body.product_id:
        product = db.query(Product).filter(Product.product_id == body.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

    duplicate = (
        db.query(Report)
        .filter(
            Report.reporter_id == user.user_id,
            Report.product_id == body.product_id,
            Report.report_type == body.report_type,
            Report.status.in_(list(ACTIVE_REPORT_STATUSES)),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="You have already submitted this report and it is under review")

    report = Report(
        report_id=f"rep_{uuid.uuid4().hex[:12]}",
        product_id=body.product_id,
        reporter_id=user.user_id,
        reporter_name=user.name or "",
        reporter_role=user.role,
        reported_user_id=body.reported_user_id,
        report_type=body.report_type,
        reason=body.reason.strip(),
        evidence=body.evidence or [],
        status="pending",
    )
    db.add(report)

    if product:
        product.report_count = (product.report_count or 0) + 1
        if product.report_count >= 3:
            product.is_flagged = True
            notify_admins(
                db,
                title="Product flagged",
                message="Product has been flagged due to multiple reports.",
                notif_type="product_flagged",
                product_id=product.product_id,
            )

    notify_admins(
        db,
        title="New report submitted",
        message="New report submitted for product/auction.",
        notif_type="report_submitted",
        product_id=body.product_id,
    )
    db.commit()
    db.refresh(report)
    return {"message": "Report submitted successfully", "report": serialize_report(report)}


@router.get("/my")
def my_reports(
    status: Optional[str] = None,
    report_type: Optional[str] = None,
    product_id: Optional[str] = None,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
):
    query = db.query(Report).filter(Report.reporter_id == user.user_id)
    if status:
        query = query.filter(Report.status == status)
    if report_type:
        if report_type not in REPORT_TYPES:
            raise HTTPException(status_code=400, detail="Invalid report type")
        query = query.filter(Report.report_type == report_type)
    if product_id:
        query = query.filter(Report.product_id == product_id)
    reports = query.order_by(Report.created_at.desc()).limit(500).all()
    return [serialize_report(report) for report in reports]
