from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: Optional[EmailStr] = None
    password: str
    name: str
    role: str
    mobile_number: Optional[str] = None


class LoginIn(BaseModel):
    mobile_number: Optional[str] = None
    email: Optional[EmailStr] = None
    password: str


class GoogleSessionIn(BaseModel):
    session_token: str
    role: Optional[str] = "Buyer"


class RegistrationOtpIn(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    name: str
    role: str
    mobile_number: Optional[str] = None


class VerifyRegistrationOtpIn(BaseModel):
    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None
    password: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    otp: str


class ForgotPasswordOtpIn(BaseModel):
    identifier: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None


class VerifyForgotPasswordOtpIn(BaseModel):
    identifier: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None
    otp: str


class ResetPasswordIn(BaseModel):
    identifier: Optional[str] = None
    email: Optional[EmailStr] = None
    reset_token: str
    new_password: str


class NewsletterSubscribeIn(BaseModel):
    email: EmailStr


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None


class ProductIn(BaseModel):
    title: str
    product_type: str
    brand: str
    model: str
    condition: str
    description: str
    product_price: float
    expected_price: float
    photos: List[str] = Field(default_factory=list)
    video: Optional[str] = None
    specifications: Dict = Field(default_factory=dict)
    documents: Dict = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    status: Optional[str] = None
    reject_reason: Optional[str] = None


class ProductEditIn(BaseModel):
    title: Optional[str] = None
    product_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    condition: Optional[str] = None
    description: Optional[str] = None
    product_price: Optional[float] = None
    expected_price: Optional[float] = None
    photos: Optional[List[str]] = None
    video: Optional[str] = None
    specifications: Optional[Dict] = None
    documents: Optional[Dict] = None


class BidIn(BaseModel):
    amount: float


class ChatMessageIn(BaseModel):
    message: str


class ChatRequestCreateIn(BaseModel):
    product_id: str


class ChatRequestRespondIn(BaseModel):
    action: str


class ReportCreate(BaseModel):
    product_id: Optional[str] = None
    reported_user_id: Optional[str] = None
    report_type: str
    reason: str
    evidence: Optional[List[str]] = Field(default_factory=list)


class ReportStatusUpdate(BaseModel):
    status: str
    admin_note: Optional[str] = None


class ReportActionRequest(BaseModel):
    action: str
    admin_note: Optional[str] = None


class CommunityRequestCreateIn(BaseModel):
    product_type: str
    brand: str
    model: str
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    condition_preference: Optional[str] = None
    description: Optional[str] = None


class CommunityRequestStatusUpdate(BaseModel):
    status: str


class PaymentOrderCreate(BaseModel):
    plan_id: str


class PaymentVerifyIn(BaseModel):
    cashfree_order_id: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None


class PaymentFailIn(BaseModel):
    order_id: Optional[str] = None
    cashfree_order_id: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    reason: Optional[str] = None
