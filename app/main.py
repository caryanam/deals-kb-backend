import logging
import time

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import models_sql
from app.auth import pwd_context
from app.config import ADMIN_EMAIL, ADMIN_MOBILE_NUMBER, ADMIN_PASSWORD, MAX_REQUEST_SIZE_BYTES, MAX_REQUEST_SIZE_MB, OLD_ADMIN_EMAIL
from app.database import Base, SessionLocal, engine, ensure_database_exists
from app.middleware.cors import configure_cors
from app.models_sql import User
from app.routes import admin, auth, chat_requests, chats, community_requests, newsletter, notifications, payments, plans, products, reports, users, ws
from app.services.users import sync_role_profile

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("dealskb")

app = FastAPI(title="DealsKB Multi-Product AutoBid Backend", version="2.0.0")
api = APIRouter(prefix="/api")


@app.middleware("http")
async def request_size_limit(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    method = request.method
    origin = request.headers.get("origin", "-")
    content_type = request.headers.get("content-type", "-")
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_REQUEST_SIZE_BYTES:
        logger.warning(
            "%s %s origin=%s content_type=%s status=413 duration_ms=0",
            method,
            path,
            origin,
            content_type,
        )
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body too large. Maximum allowed size is {MAX_REQUEST_SIZE_MB} MB"},
        )
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "%s %s origin=%s content_type=%s failed",
            method,
            path,
            origin,
            content_type,
        )
        raise
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "%s %s origin=%s content_type=%s status=%s duration_ms=%s",
        method,
        path,
        origin,
        content_type,
        response.status_code,
        duration_ms,
    )
    return response


@api.get("/")
def root():
    return {"app": "DealsKB Multi-Product AutoBid Backend", "status": "ok"}


@api.get("/health")
def health():
    return {"status": "ok"}


api.include_router(auth.router)
api.include_router(products.router)
api.include_router(reports.router)
api.include_router(payments.router)
api.include_router(plans.router)
api.include_router(users.router)
api.include_router(newsletter.router)
api.include_router(notifications.router)
api.include_router(community_requests.router)
api.include_router(chat_requests.router)
api.include_router(chats.router)
api.include_router(admin.router)
api.include_router(ws.router)


@app.on_event("startup")
def startup():
    ensure_database_exists()
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "mysql":
        with engine.begin() as connection:
            for ddl in [
                "ALTER TABLE products ADD COLUMN submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP",
                "ALTER TABLE products ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
                "ALTER TABLE products ADD COLUMN approved_at DATETIME NULL",
                "ALTER TABLE products ADD COLUMN rejected_at DATETIME NULL",
                "ALTER TABLE products ADD COLUMN is_flagged BOOL DEFAULT FALSE",
                "ALTER TABLE products ADD COLUMN report_count INT DEFAULT 0",
                "ALTER TABLE products ADD COLUMN is_cancelled BOOL DEFAULT FALSE",
                "ALTER TABLE products ADD COLUMN cancel_reason TEXT NULL",
                "ALTER TABLE products ADD COLUMN cancelled_at DATETIME NULL",
                "ALTER TABLE products ADD COLUMN product_price DECIMAL(12, 2) NOT NULL DEFAULT 0",
                "ALTER TABLE products ADD COLUMN parent_product_id VARCHAR(100) NULL",
                "ALTER TABLE products ADD COLUMN is_relisted BOOL DEFAULT FALSE",
                "ALTER TABLE products ADD COLUMN relist_count INT DEFAULT 0",
                "ALTER TABLE products ADD COLUMN relist_payment_status VARCHAR(50) NULL",
                "ALTER TABLE products ADD COLUMN relist_payment_order_id VARCHAR(100) NULL",
                "ALTER TABLE products ADD COLUMN relist_payment_id VARCHAR(100) NULL",
                "ALTER TABLE users MODIFY email VARCHAR(255) NULL",
                "ALTER TABLE users MODIFY role ENUM('Buyer','Seller','Dealer','Admin') NOT NULL",
                "ALTER TABLE users ADD COLUMN is_blocked BOOL DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN blocked_reason TEXT NULL",
                "ALTER TABLE users ADD COLUMN blocked_at DATETIME NULL",
                "ALTER TABLE users ADD COLUMN buyer_access_until DATETIME NULL",
                "ALTER TABLE buyers MODIFY email VARCHAR(255) NULL",
                "ALTER TABLE sellers MODIFY email VARCHAR(255) NULL",
                "ALTER TABLE dealers MODIFY email VARCHAR(255) NULL",
                "ALTER TABLE registration_otps MODIFY email VARCHAR(255) NULL",
                "ALTER TABLE registration_otps MODIFY role ENUM('Buyer','Seller','Dealer') NOT NULL",
                "ALTER TABLE mobile_verification_otps MODIFY role ENUM('Buyer','Seller','Dealer') NULL",
                "ALTER TABLE notifications ADD COLUMN role VARCHAR(50) NULL",
                "ALTER TABLE notifications ADD COLUMN type VARCHAR(100) NULL",
                "ALTER TABLE notifications ADD COLUMN is_cleared BOOL DEFAULT FALSE",
                "ALTER TABLE notifications ADD COLUMN read_at DATETIME NULL",
                "ALTER TABLE notifications ADD COLUMN cleared_at DATETIME NULL",
                "ALTER TABLE chat_conversations ADD COLUMN request_id VARCHAR(100) NULL",
                "ALTER TABLE payment_transactions ADD COLUMN payment_gateway VARCHAR(30) DEFAULT 'cashfree'",
                "ALTER TABLE payment_transactions MODIFY razorpay_order_id VARCHAR(100) NULL",
                "ALTER TABLE payment_transactions ADD COLUMN cashfree_order_id VARCHAR(100) NULL",
                "ALTER TABLE payment_transactions ADD COLUMN cashfree_payment_session_id TEXT NULL",
                "ALTER TABLE payment_transactions ADD COLUMN cashfree_order_status VARCHAR(30) NULL",
            ]:
                try:
                    connection.execute(text(ddl))
                except SQLAlchemyError:
                    pass
            for ddl in [
                "CREATE UNIQUE INDEX ix_chat_conversations_request_id ON chat_conversations (request_id)",
                "CREATE UNIQUE INDEX ix_payment_transactions_cashfree_order_id ON payment_transactions (cashfree_order_id)",
            ]:
                try:
                    connection.execute(text(ddl))
                except SQLAlchemyError:
                    pass
            connection.execute(text("ALTER TABLE products MODIFY video LONGTEXT NULL"))
            try:
                connection.execute(text("ALTER TABLE products MODIFY status ENUM('pending','approved','rejected','live','ended','cancelled') DEFAULT 'pending'"))
            except SQLAlchemyError:
                pass

    db = SessionLocal()
    try:
        existing_admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        old_admin = db.query(User).filter(User.email == OLD_ADMIN_EMAIL).first()
        fixed_admin = db.query(User).filter(User.user_id == "user_admin000001").first()
        if not existing_admin and fixed_admin:
            existing_admin = fixed_admin
        if not existing_admin and old_admin:
            existing_admin = old_admin
        if not existing_admin:
            admin = User(
                user_id="user_admin000001",
                email=ADMIN_EMAIL,
                name="Admin",
                role="Admin",
                mobile_number=ADMIN_MOBILE_NUMBER,
                password_hash=pwd_context.hash(ADMIN_PASSWORD),
                auth_provider="email",
            )
            db.add(admin)
            db.commit()
            logger.info("Seeded admin user: %s", ADMIN_EMAIL)
        elif (
            existing_admin.email != ADMIN_EMAIL
            or existing_admin.mobile_number != ADMIN_MOBILE_NUMBER
            or existing_admin.role != "Admin"
        ):
            existing_admin.email = ADMIN_EMAIL
            existing_admin.mobile_number = ADMIN_MOBILE_NUMBER
            existing_admin.password_hash = pwd_context.hash(ADMIN_PASSWORD)
            existing_admin.name = "Admin"
            existing_admin.role = "Admin"
            existing_admin.auth_provider = "email"
            db.commit()

        users_to_sync = db.query(User).filter(User.role.in_(["Buyer", "Seller", "Dealer"])).all()
        for user in users_to_sync:
            sync_role_profile(db, user)
        db.commit()
    finally:
        db.close()


configure_cors(app)

app.include_router(api)
