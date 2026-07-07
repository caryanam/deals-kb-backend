from datetime import timedelta
from typing import Any

import jwt
from fastapi import HTTPException
from passlib.context import CryptContext

from app.core.config import settings
from app.utils import now_utc

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def normalize_role(role: str | None) -> str:
    value = (role or "").strip().upper()
    if value == "USER":
        return "BUYER"
    return value


def role_aliases(role: str | None) -> set[str]:
    normalized = normalize_role(role)
    aliases = {normalized} if normalized else set()
    if normalized == "BUYER":
        aliases.add("USER")
    return aliases


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    expire = now_utc() + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload.update({"exp": expire, "iat": now_utc()})
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
