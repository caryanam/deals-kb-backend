from sqlalchemy import Boolean, Column, DateTime, DECIMAL, Enum, Integer, JSON, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(Text)
    name = Column(String(255), nullable=False)
    role = Column(Enum("Buyer", "Seller", "Dealer", "Admin"), nullable=False)
    mobile_number = Column(String(20), index=True)
    auth_provider = Column(String(50), default="email")
    is_blocked = Column(Boolean, default=False, index=True)
    blocked_reason = Column(Text)
    blocked_at = Column(DateTime)
    buyer_access_until = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    token = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime)


class RegistrationOTP(Base):
    __tablename__ = "registration_otps"

    id = Column(Integer, primary_key=True, index=True)
    otp_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    mobile_number = Column(String(20), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    role = Column(Enum("Buyer", "Seller", "Dealer"), nullable=False)
    password_hash = Column(Text, nullable=False)
    otp = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"

    id = Column(Integer, primary_key=True, index=True)
    reset_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    mobile_number = Column(String(20), nullable=False, index=True)
    otp = Column(String(6), nullable=False)
    reset_token = Column(String(100), unique=True, index=True)
    is_verified = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class MobileVerificationOTP(Base):
    __tablename__ = "mobile_verification_otps"

    id = Column(Integer, primary_key=True, index=True)
    verification_id = Column(String(100), unique=True, nullable=False, index=True)
    purpose = Column(Enum("registration", "forgot_password"), nullable=False, index=True)
    mobile_number = Column(String(20), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    name = Column(String(255))
    role = Column(Enum("Buyer", "Seller", "Dealer"), nullable=True)
    password_hash = Column(Text)
    user_id = Column(String(100), index=True)
    otp = Column(String(6), nullable=False)
    reset_token = Column(String(100), unique=True, index=True)
    is_verified = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Buyer(Base):
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    name = Column(String(255), nullable=False)
    mobile_number = Column(String(20), index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Seller(Base):
    __tablename__ = "sellers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    name = Column(String(255), nullable=False)
    mobile_number = Column(String(20), index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Dealer(Base):
    __tablename__ = "dealers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    name = Column(String(255), nullable=False)
    mobile_number = Column(String(20), index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(100), unique=True, nullable=False, index=True)
    seller_id = Column(String(100), nullable=False, index=True)
    seller_name = Column(String(255))
    title = Column(String(255), nullable=False)
    product_type = Column(Enum("car", "bike", "laptop", "mobile"), nullable=False, index=True)
    brand = Column(String(255), nullable=False)
    model = Column(String(255), nullable=False)
    product_condition = Column(String(100), nullable=False)
    description = Column(Text)
    product_price = Column(DECIMAL(12, 2), nullable=False)
    expected_price = Column(DECIMAL(12, 2), nullable=False)
    photos = Column(JSON)
    video = Column(Text().with_variant(LONGTEXT, "mysql"))
    specifications = Column(JSON)
    documents = Column(JSON)
    status = Column(Enum("pending", "approved", "rejected", "live", "ended", "cancelled"), default="pending", index=True)
    reject_reason = Column(Text)
    auction_start = Column(DateTime)
    auction_end = Column(DateTime)
    current_bid = Column(DECIMAL(12, 2))
    highest_bidder_id = Column(String(100))
    highest_bidder_name = Column(String(255))
    bid_count = Column(Integer, default=0)
    winner_id = Column(String(100))
    winner_name = Column(String(255))
    is_flagged = Column(Boolean, default=False, index=True)
    report_count = Column(Integer, default=0)
    is_cancelled = Column(Boolean, default=False, index=True)
    cancel_reason = Column(Text)
    cancelled_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    submitted_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    approved_at = Column(DateTime)
    rejected_at = Column(DateTime)
    parent_product_id = Column(String(100), nullable=True)
    is_relisted = Column(Boolean, default=False)
    relist_count = Column(Integer, default=0)
    relist_payment_status = Column(String(50), nullable=True)
    relist_payment_order_id = Column(String(100), nullable=True)
    relist_payment_id = Column(String(100), nullable=True)


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    bid_id = Column(String(100), unique=True, nullable=False, index=True)
    product_id = Column(String(100), nullable=False, index=True)
    bidder_id = Column(String(100), nullable=False, index=True)
    bidder_name = Column(String(255), nullable=False)
    amount = Column(DECIMAL(12, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    notif_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    role = Column(String(50), index=True)
    product_id = Column(String(100))
    title = Column(String(255))
    message = Column(Text, nullable=False)
    type = Column(String(100), index=True)
    is_read = Column(Boolean, default=False)
    is_cleared = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    read_at = Column(DateTime)
    cleared_at = Column(DateTime)


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(100), unique=True, nullable=False, index=True)
    request_id = Column(String(100), unique=True, nullable=True, index=True)
    product_id = Column(String(100), nullable=False, index=True)
    buyer_id = Column(String(100), nullable=False, index=True)
    seller_id = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatRequest(Base):
    __tablename__ = "chat_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(100), unique=True, nullable=False, index=True)
    product_id = Column(String(100), nullable=False, index=True)
    listing_name = Column(String(255), nullable=False)
    buyer_id = Column(String(100), nullable=False, index=True)
    buyer_name = Column(String(255), nullable=False)
    seller_id = Column(String(100), nullable=False, index=True)
    seller_name = Column(String(255), nullable=False)
    winning_bid_amount = Column(DECIMAL(12, 2), nullable=False)
    status = Column(Enum("PENDING", "ACCEPTED", "REJECTED"), default="PENDING", nullable=False, index=True)
    buyer_message = Column(Text, nullable=False)
    seller_response_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    responded_at = Column(DateTime)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(100), unique=True, nullable=False, index=True)
    conversation_id = Column(String(100), nullable=False, index=True)
    sender_id = Column(String(100), nullable=False, index=True)
    receiver_id = Column(String(100), nullable=False, index=True)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


class CommunityRequest(Base):
    __tablename__ = "community_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(100), unique=True, nullable=False, index=True)
    created_by_user_id = Column(String(100), nullable=False, index=True)
    created_by_name = Column(String(255), nullable=False)
    product_type = Column(Enum("car", "bike", "mobile", "laptop"), nullable=False, index=True)
    brand = Column(String(255), nullable=False, index=True)
    model = Column(String(255), nullable=False, index=True)
    budget_min = Column(DECIMAL(12, 2))
    budget_max = Column(DECIMAL(12, 2))
    condition_preference = Column(String(100))
    description = Column(Text)
    interested_count = Column(Integer, default=0)
    status = Column(Enum("active", "matched", "closed", "disabled"), default="active", nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CommunityRequestMember(Base):
    __tablename__ = "community_request_members"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(100), nullable=False, index=True)
    buyer_id = Column(String(100), nullable=False, index=True)
    buyer_name = Column(String(255), nullable=False)
    linked_interest_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    joined_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String(100), unique=True, nullable=False, index=True)
    product_id = Column(String(100), nullable=True, index=True)
    reporter_id = Column(String(100), nullable=False, index=True)
    reporter_name = Column(String(255))
    reporter_role = Column(String(50))
    reported_user_id = Column(String(100), nullable=True, index=True)
    report_type = Column(String(100), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    evidence = Column(JSON)
    status = Column(Enum("pending", "under_review", "resolved", "rejected", "action_taken"), default="pending", index=True)
    admin_note = Column(Text)
    action_taken = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    user_role = Column(String(50), nullable=False, index=True)
    plan_id = Column(String(100), nullable=False, index=True)
    plan_name = Column(String(255), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(10), nullable=False, default="INR")
    razorpay_order_id = Column(String(100), unique=True, nullable=False, index=True)
    razorpay_payment_id = Column(String(100), index=True)
    razorpay_signature = Column(Text)
    status = Column(Enum("created", "paid", "failed"), default="created", index=True)
    receipt = Column(String(100), unique=True, nullable=False, index=True)
    notes = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    paid_at = Column(DateTime)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
