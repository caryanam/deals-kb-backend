from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import auth_required
from app.database import get_db
from app.models_sql import Notification, User
from app.serializers import serialize_notification
from app.utils import now_utc

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    items = (
        db.query(Notification)
        .filter(Notification.user_id == user.user_id, Notification.is_cleared.is_(False))
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return [serialize_notification(item) for item in items]


@router.post("/{notif_id}/read")
def mark_read(notif_id: str, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    item = (
        db.query(Notification)
        .filter(Notification.notif_id == notif_id, Notification.user_id == user.user_id)
        .first()
    )
    if item:
        item.is_read = True
        item.read_at = now_utc().replace(tzinfo=None)
        db.commit()
    return {"ok": True}


@router.post("/{notif_id}/unread")
def mark_unread(notif_id: str, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    item = (
        db.query(Notification)
        .filter(Notification.notif_id == notif_id, Notification.user_id == user.user_id)
        .first()
    )
    if item:
        item.is_read = False
        item.read_at = None
        db.commit()
    return {"ok": True}


@router.delete("/clear")
def clear_all(user: User = Depends(auth_required), db: Session = Depends(get_db)):
    now = now_utc().replace(tzinfo=None)
    db.query(Notification).filter(Notification.user_id == user.user_id).update({
        "is_cleared": True,
        "cleared_at": now,
    })
    db.commit()
    return {"ok": True}


@router.delete("/{notif_id}")
def clear_notification(notif_id: str, user: User = Depends(auth_required), db: Session = Depends(get_db)):
    item = (
        db.query(Notification)
        .filter(Notification.notif_id == notif_id, Notification.user_id == user.user_id)
        .first()
    )
    if item:
        item.is_cleared = True
        item.cleared_at = now_utc().replace(tzinfo=None)
        db.commit()
    return {"ok": True}
