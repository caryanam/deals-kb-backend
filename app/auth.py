from datetime import timedelta
from typing import List, Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    normalize_role,
    pwd_context,
    role_aliases,
    verify_access_token,
    verify_password,
)
from app.database import get_db
from app.dependencies.auth import get_current_user as auth_required
from app.dependencies.auth import require_roles
from app.models_sql import User, UserSession
from app.utils import now_utc


def create_jwt(user_id: str, role: str, email: str | None = None) -> str:
    data = {
        "sub": user_id,
        "email": email,
        "role": normalize_role(role),
        "purpose": "access",
    }
    return create_access_token(
        data,
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def get_user_from_token(token: str, db: Session) -> Optional[User]:
    if not token:
        return None

    user_id = None
    try:
        payload = verify_access_token(token)
        purpose = payload.get("purpose")
        if purpose and purpose != "access":
            return None
        user_id = payload.get("sub")
    except HTTPException:
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if not session:
            session = db.query(UserSession).filter(UserSession.session_id == token).first()
        if not session:
            return None
        if session.expires_at and session.expires_at < now_utc().replace(tzinfo=None):
            return None
        user_id = session.user_id

    if not user_id:
        return None
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or getattr(user, "is_deleted", False) or getattr(user, "is_active", True) is False:
        return None
    return user


def role_required(roles: List[str]):
    return require_roles(*roles)


def is_seller_like(user: User) -> bool:
    return bool(user and role_aliases(user.role).intersection({"SELLER", "DEALER"}))
