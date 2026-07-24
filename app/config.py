import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

JWT_SECRET = os.environ.get("JWT_SECRET_KEY") or os.environ.get("JWT_SECRET", "change-this-secret-key")
JWT_ALGO = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_DAYS = int(os.environ.get("JWT_EXPIRES_DAYS", "7"))
AUCTION_DURATION_SECONDS = int(os.environ.get("AUCTION_DURATION_SECONDS", "1800"))
CORS_ORIGINS = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "*").split(",") if origin.strip()]
MAX_REQUEST_SIZE_MB = int(os.environ.get("MAX_REQUEST_SIZE_MB", "100"))
MAX_REQUEST_SIZE_BYTES = MAX_REQUEST_SIZE_MB * 1024 * 1024

PORT = os.environ.get("PORT", "8000")
APP_ENV = os.environ.get("APP_ENV", "development").lower()
BACKEND_URL = os.environ.get("BACKEND_URL", f"http://localhost:{PORT}").rstrip("/")
API_BASE_URL = os.environ.get("API_BASE_URL", f"{BACKEND_URL}/api/").rstrip("/") + "/"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin@123")
ADMIN_MOBILE_NUMBER = os.environ.get("ADMIN_MOBILE_NUMBER", "9123456789")
OLD_ADMIN_EMAIL = "admin@vehiclebid.com"

CCAVENUE_MERCHANT_ID = os.environ.get("CCAVENUE_MERCHANT_ID", "").strip()
CCAVENUE_ACCESS_CODE = os.environ.get("CCAVENUE_ACCESS_CODE", "").strip()
CCAVENUE_WORKING_KEY = os.environ.get("CCAVENUE_WORKING_KEY", "").strip()
CCAVENUE_ENVIRONMENT = os.environ.get("CCAVENUE_ENVIRONMENT", "test").strip().lower()
CCAVENUE_CURRENCY = os.environ.get("CCAVENUE_CURRENCY", "INR").strip().upper()
CCAVENUE_LANGUAGE = os.environ.get("CCAVENUE_LANGUAGE", "EN").strip().upper()
CCAVENUE_TEST_URL = os.environ.get("CCAVENUE_TEST_URL", "").strip() or "https://test.ccavenue.com/transaction/transaction.do?command=initiateTransaction"
CCAVENUE_PRODUCTION_URL = os.environ.get("CCAVENUE_PRODUCTION_URL", "").strip() or "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction"
CCAVENUE_REDIRECT_URL = os.environ.get(
    "CCAVENUE_REDIRECT_URL",
    f"{API_BASE_URL.rstrip('/')}/payments/ccavenue/callback",
).strip()
CCAVENUE_CANCEL_URL = os.environ.get(
    "CCAVENUE_CANCEL_URL",
    f"{API_BASE_URL.rstrip('/')}/payments/ccavenue/cancel",
).strip()
FRONTEND_PAYMENT_RESULT_URL = os.environ.get(
    "FRONTEND_PAYMENT_RESULT_URL",
    "https://dealskb.com/payment-result" if APP_ENV == "production" else "http://localhost:5173/payment-result",
).strip()

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.hostinger.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "DealsKB Support")
SMTP_TIMEOUT_SECONDS = int(os.environ.get("SMTP_TIMEOUT_SECONDS", "8"))
