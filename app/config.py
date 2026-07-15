import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

JWT_SECRET = os.environ.get("JWT_SECRET_KEY") or os.environ.get("JWT_SECRET", "change-this-secret-key")
JWT_ALGO = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_DAYS = int(os.environ.get("JWT_EXPIRES_DAYS", "7"))
AUCTION_DURATION_SECONDS = int(os.environ.get("AUCTION_DURATION_SECONDS", "120"))
CORS_ORIGINS = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "*").split(",") if origin.strip()]
MAX_REQUEST_SIZE_MB = int(os.environ.get("MAX_REQUEST_SIZE_MB", "100"))
MAX_REQUEST_SIZE_BYTES = MAX_REQUEST_SIZE_MB * 1024 * 1024

PORT = os.environ.get("PORT", "8000")
APP_ENV = os.environ.get("APP_ENV", "development").lower()
BACKEND_URL = os.environ.get("BACKEND_URL")
API_BASE_URL = os.environ.get("API_BASE_URL", f"{BACKEND_URL}/api/").rstrip("/") + "/"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin@123")
ADMIN_MOBILE_NUMBER = os.environ.get("ADMIN_MOBILE_NUMBER", "9123456789")
OLD_ADMIN_EMAIL = "admin@vehiclebid.com"

CASHFREE_APP_ID = os.environ.get("CASHFREE_APP_ID", "")
CASHFREE_SECRET_KEY = os.environ.get("CASHFREE_SECRET_KEY", "")
CASHFREE_ENV = os.environ.get("CASHFREE_ENV", "sandbox").lower()
CASHFREE_API_VERSION = os.environ.get("CASHFREE_API_VERSION", "2025-01-01")
CASHFREE_BASE_URL = os.environ.get(
    "CASHFREE_BASE_URL",
    "https://sandbox.cashfree.com/pg" if CASHFREE_ENV != "production" else "https://api.cashfree.com/pg",
)

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.hostinger.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "DealsKB Support")
SMTP_TIMEOUT_SECONDS = int(os.environ.get("SMTP_TIMEOUT_SECONDS", "8"))
