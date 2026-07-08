import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)


class Settings:
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET", "change-this-secret-key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM") or os.getenv("JWT_ALGO", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
        or str(int(os.getenv("JWT_EXPIRES_DAYS", "7")) * 24 * 60)
    )

    DEFAULT_ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "https://dealskb.com",
        "https://www.dealskb.com",
        "https://dealskb.com"

    ]

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", "")
        if not raw or raw.strip() == "*":
            return self.DEFAULT_ALLOWED_ORIGINS
        configured = [origin.strip() for origin in raw.split(",") if origin.strip()]
        return configured or self.DEFAULT_ALLOWED_ORIGINS


settings = Settings()
