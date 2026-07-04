import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret-key")
JWT_ALGO = "HS256"
JWT_EXPIRES_DAYS = int(os.environ.get("JWT_EXPIRES_DAYS", "7"))
AUCTION_DURATION_SECONDS = int(os.environ.get("AUCTION_DURATION_SECONDS", "120"))
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
MAX_REQUEST_SIZE_MB = int(os.environ.get("MAX_REQUEST_SIZE_MB", "50"))
MAX_REQUEST_SIZE_BYTES = MAX_REQUEST_SIZE_MB * 1024 * 1024

APP_ENV = os.environ.get("APP_ENV", "development").lower()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin@123")
ADMIN_MOBILE_NUMBER = os.environ.get("ADMIN_MOBILE_NUMBER", "9123456789")
OLD_ADMIN_EMAIL = "admin@vehiclebid.com"

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_CURRENCY = os.environ.get("RAZORPAY_CURRENCY", "INR")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.hostinger.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "true").lower() in ("1", "true", "yes")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "DealsKB Support")
