import os
from pathlib import Path

from dotenv import load_dotenv
from app.config import CORS_ORIGINS

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)


class Settings:
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET", "change-this-secret-key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM") or os.getenv("JWT_ALGO", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
        or str(int(os.getenv("JWT_EXPIRES_DAYS", "7")) * 24 * 60)
    )

    DEFAULT_ALLOWED_ORIGINS = CORS_ORIGINS if CORS_ORIGINS and CORS_ORIGINS != ["*"] else [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", "")
        if not raw or raw.strip() == "*":
            return self.DEFAULT_ALLOWED_ORIGINS
        configured = [origin.strip() for origin in raw.split(",") if origin.strip()]
        return configured or self.DEFAULT_ALLOWED_ORIGINS

    CCAVENUE_MERCHANT_ID: str = os.getenv("CCAVENUE_MERCHANT_ID", "").strip()
    CCAVENUE_ACCESS_CODE: str = os.getenv("CCAVENUE_ACCESS_CODE", "").strip()
    CCAVENUE_WORKING_KEY: str = os.getenv("CCAVENUE_WORKING_KEY", "").strip()
    CCAVENUE_ENVIRONMENT: str = os.getenv("CCAVENUE_ENVIRONMENT", "test").strip().lower()
    CCAVENUE_CURRENCY: str = os.getenv("CCAVENUE_CURRENCY", "INR").strip().upper()
    CCAVENUE_LANGUAGE: str = os.getenv("CCAVENUE_LANGUAGE", "EN").strip().upper()
    CCAVENUE_TEST_URL: str = os.getenv("CCAVENUE_TEST_URL", "").strip() or "https://test.ccavenue.com/transaction/transaction.do?command=initiateTransaction"
    CCAVENUE_PRODUCTION_URL: str = os.getenv("CCAVENUE_PRODUCTION_URL", "").strip() or "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction"
    FRONTEND_PAYMENT_RESULT_URL: str = os.getenv(
        "FRONTEND_PAYMENT_RESULT_URL",
        "https://dealskb.com/payment-result",
    ).strip()


settings = Settings()
