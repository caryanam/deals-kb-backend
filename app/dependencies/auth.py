from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.security import normalize_role, role_aliases, verify_access_token
from app.database import get_db
from app.models_sql import User, UserSession
from app.utils import now_utc


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = None
    try:
        payload = verify_access_token(token)
        user_id = payload.get("sub")
    except HTTPException:
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if not session:
            session = db.query(UserSession).filter(UserSession.session_id == token).first()
        if not session:
            raise
        if session.expires_at and session.expires_at < now_utc().replace(tzinfo=None):
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        user_id = session.user_id

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def require_roles(*allowed_roles: str):
    allowed = {normalize_role(role) for role in allowed_roles}

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        current_roles = role_aliases(current_user.role)
        if not current_roles.intersection(allowed):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this resource.",
            )
        return current_user

    return role_checker
