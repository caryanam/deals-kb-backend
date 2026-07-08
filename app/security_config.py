from datetime import timedelta

from app.core.config import settings


JWT_SECRET_KEY = settings.JWT_SECRET_KEY
JWT_ALGORITHM = settings.JWT_ALGORITHM
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
JWT_ACCESS_TOKEN_EXPIRE_DELTA = timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)


def get_security_config() -> dict:
    return {
        "jwt_algorithm": JWT_ALGORITHM,
        "jwt_access_token_expire_minutes": JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        "jwt_secret_key_loaded": bool(JWT_SECRET_KEY),
    }
