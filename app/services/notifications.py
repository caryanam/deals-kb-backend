import uuid

from sqlalchemy.orm import Session

from app.models_sql import Notification, User
from app.utils import now_utc


def create_notification(
    db: Session,
    user_id: str,
    title: str,
    message: str,
    notif_type: str,
    product_id: str | None = None,
    role: str | None = None,
):
    if role is None:
        user = db.query(User).filter(User.user_id == user_id).first()
        role = user.role if user else None

    notification = Notification(
        notif_id=f"notif_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        role=role,
        product_id=product_id,
        title=title,
        message=message,
        type=notif_type,
        is_read=False,
        is_cleared=False,
        created_at=now_utc().replace(tzinfo=None),
    )
    db.add(notification)
    return notification


def notify_admins(db: Session, title: str, message: str, notif_type: str, product_id: str | None = None):
    admins = db.query(User).filter(User.role == "Admin").all()
    for admin in admins:
        create_notification(
            db,
            user_id=admin.user_id,
            title=title,
            message=message,
            notif_type=notif_type,
            product_id=product_id,
            role="Admin",
        )
