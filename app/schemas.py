from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Money = Decimal


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password is too long in UTF-8 bytes")
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("password must contain letters and numbers")
        return value


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(ORMModel):
    id: int
    username: str
    email: str
    full_name: str | None = None
    phone: str | None = None
    email_verified_at: datetime | None = None
    phone_verified_at: datetime | None = None
    is_verified: bool = False
    is_seller: bool
    is_admin: bool
    rating: Decimal
    total_sales: int
    balance: Decimal
    balance_frozen: Decimal
    withdrawable_balance: Decimal = Decimal("0")
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    icon: str | None = Field(default=None, max_length=50)


class ProductCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, max_length=50)
    price: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    old_price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    fulfillment_type: Literal["automatic", "manual"] = "automatic"
    delivery_time: str | None = Field(default=None, max_length=50)
    stock_quantity: int = Field(default=1, ge=0, le=100000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    digital_items: list[str] = Field(default_factory=list, max_length=1000)

    @field_validator("digital_items")
    @classmethod
    def validate_items(cls, items: list[str]) -> list[str]:
        cleaned = [x.strip() for x in items if x and x.strip()]
        if any(len(x) > 10000 for x in cleaned):
            raise ValueError("digital item is too long")
        return cleaned


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, max_length=50)
    price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    old_price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    delivery_time: str | None = Field(default=None, max_length=50)
    stock_quantity: int | None = Field(default=None, ge=0, le=100000)
    tags: list[str] | None = None
    status: Literal["active", "paused"] | None = None


class ProductResponse(ORMModel):
    id: int
    seller_id: int
    title: str
    description: str | None = None
    category: str | None = None
    price: Decimal
    old_price: Decimal | None = None
    stock_quantity: int
    fulfillment_type: str
    status: str
    views_count: int
    favorites_count: int
    is_verified: bool
    delivery_time: str | None = None
    tags: list[str] | None = None
    created_at: datetime


class InventoryAdd(BaseModel):
    items: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("items")
    @classmethod
    def clean_items(cls, items: list[str]) -> list[str]:
        cleaned = [x.strip() for x in items if x and x.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty item is required")
        return cleaned


class OrderCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=100)


class OrderResponse(ORMModel):
    id: int
    buyer_id: int
    seller_id: int
    product_id: int
    quantity: int
    total_price: Decimal
    commission: Decimal
    seller_earnings: Decimal
    status: str
    product_title_snapshot: str | None = None
    product_category_snapshot: str | None = None
    delivery_info: str | None = None
    created_at: datetime
    paid_at: datetime | None = None
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    auto_complete_at: datetime | None = None


class OrderRoomMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class OrderMessageResponse(ORMModel):
    id: int
    order_id: int
    sender_id: int
    message: str | None = None
    attachment_url: str | None = None
    attachment_name: str | None = None
    attachment_mime: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class OrderEventResponse(ORMModel):
    id: int
    order_id: int
    actor_id: int | None = None
    event_type: str
    text: str
    payload: dict | None = None
    created_at: datetime


class DepositCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    platform: Literal["web", "android"] = "web"


class DepositResponse(ORMModel):
    id: int
    user_id: int
    provider: str
    provider_payment_id: str | None = None
    amount: Decimal
    currency: str
    status: str
    confirmation_url: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    succeeded_at: datetime | None = None
    canceled_at: datetime | None = None


class WithdrawalRequestCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    wallet_type: Literal["sbp", "manual", "card", "crypto", "other"] = "sbp"
    wallet_address: str = Field(min_length=3, max_length=255)
    bank_id: str | None = Field(default=None, min_length=3, max_length=32)


class WithdrawalResponse(BaseModel):
    id: int
    user_id: int
    amount: Decimal
    wallet_type: str
    wallet_address: str
    bank_id: str | None = None
    provider: str = "manual"
    provider_payout_id: str | None = None
    failure_reason: str | None = None
    status: str
    created_at: datetime
    processed_at: datetime | None = None


class ChatMessageCreate(BaseModel):
    receiver_id: int = Field(gt=0)
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageResponse(ORMModel):
    id: int
    sender_id: int
    receiver_id: int
    message: str
    is_read: bool
    created_at: datetime


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None


class ReviewCreate(BaseModel):
    order_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=3000)


class ReviewResponse(ORMModel):
    id: int
    reviewer_id: int
    target_user_id: int
    order_id: int
    rating: int
    comment: str | None = None
    created_at: datetime


class DisputeCreate(BaseModel):
    order_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=100)
    description: str | None = Field(default=None, max_length=5000)


class DisputeResolve(BaseModel):
    resolution: Literal["buyer", "seller", "split"]


class DisputeResponse(ORMModel):
    id: int
    order_id: int
    initiator_id: int
    reason: str
    description: str | None = None
    status: str
    resolution: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


# ===== ACCOUNT SECURITY / VERIFICATION =====
class VerificationRequest(BaseModel):
    channel: Literal["email", "phone"]


class VerificationConfirm(BaseModel):
    channel: Literal["email", "phone"]
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password is too long in UTF-8 bytes")
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("password must contain letters and numbers")
        return value


class PasswordResetRequest(BaseModel):
    # New clients use identifier+channel. `email` is kept for backward compatibility
    # with older web/Android builds.
    identifier: str | None = Field(default=None, min_length=3, max_length=255)
    channel: Literal["email", "phone"] | None = None
    email: EmailStr | None = None

    def resolved_identifier(self) -> str:
        return (self.identifier or (str(self.email) if self.email else "")).strip()


class PasswordResetConfirm(BaseModel):
    identifier: str | None = Field(default=None, min_length=3, max_length=255)
    channel: Literal["email", "phone"] | None = None
    email: EmailStr | None = None
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=72)

    def resolved_identifier(self) -> str:
        return (self.identifier or (str(self.email) if self.email else "")).strip()

    @field_validator("new_password")
    @classmethod
    def reset_password_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password is too long in UTF-8 bytes")
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("password must contain letters and numbers")
        return value


# ===== SUPPORT =====
class SupportTicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    category: Literal["general", "payment", "order", "seller", "technical", "complaint", "account"] = "general"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    order_id: int | None = Field(default=None, gt=0)
    message: str = Field(min_length=3, max_length=10000)


class SupportReplyCreate(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class SupportStatusUpdate(BaseModel):
    status: Literal["open", "awaiting_user", "awaiting_support", "closed"]


class SupportMessageResponse(ORMModel):
    id: int
    ticket_id: int
    author_id: int
    message: str
    is_staff: bool
    created_at: datetime


class SupportTicketResponse(ORMModel):
    id: int
    user_id: int
    subject: str
    category: str
    priority: str
    status: str
    order_id: int | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None


# ===== NOTIFICATIONS =====
class NotificationResponse(ORMModel):
    id: int
    type: str
    title: str
    body: str | None = None
    link: str | None = None
    is_read: bool
    created_at: datetime
