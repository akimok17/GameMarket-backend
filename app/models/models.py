from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, JSON
)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ARRAY

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100))
    phone = Column(String(30), unique=True, index=True)
    email_verified_at = Column(DateTime(timezone=True))
    phone_verified_at = Column(DateTime(timezone=True))
    is_seller = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    rating = Column(Numeric(3, 2), default=0, nullable=False)
    total_sales = Column(Integer, default=0, nullable=False)
    balance = Column(Numeric(14, 2), default=0, nullable=False)
    balance_frozen = Column(Numeric(14, 2), default=0, nullable=False)
    withdrawable_balance = Column(Numeric(14, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_active = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True))
    token_version = Column(Integer, default=0, nullable=False)

    @property
    def is_verified(self) -> bool:
        return bool(self.email_verified_at or self.phone_verified_at)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    icon = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    category = Column(String(50), index=True)
    price = Column(Numeric(14, 2), nullable=False)
    old_price = Column(Numeric(14, 2))
    stock_quantity = Column(Integer, default=0, nullable=False)
    fulfillment_type = Column(String(20), default="automatic", nullable=False)
    status = Column(String(20), default="active", nullable=False, index=True)
    views_count = Column(Integer, default=0, nullable=False)
    favorites_count = Column(Integer, default=0, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    delivery_time = Column(String(50))
    tags = Column(JSON().with_variant(ARRAY(String), "postgresql"), default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_price_nonnegative"),
        CheckConstraint("stock_quantity >= 0", name="ck_product_stock_nonnegative"),
    )


class DigitalItem(Base):
    __tablename__ = "digital_items"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    encrypted_content = Column(Text, nullable=False)
    status = Column(String(20), default="available", nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sold_at = Column(DateTime(timezone=True))
    __table_args__ = (Index("ix_digital_item_product_status", "product_id", "status"),)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, default=1, nullable=False)
    total_price = Column(Numeric(14, 2), nullable=False)
    commission = Column(Numeric(14, 2), default=0, nullable=False)
    seller_earnings = Column(Numeric(14, 2), nullable=False)
    buyer_withdrawable_spent = Column(Numeric(14, 2), default=0, nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    delivery_info = Column(Text)  # legacy/non-sensitive marker
    delivery_secret = Column(Text)  # encrypted payload for buyer/seller order room
    product_title_snapshot = Column(String(200))
    product_category_snapshot = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    paid_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    auto_complete_at = Column(DateTime(timezone=True), index=True)
    settled_at = Column(DateTime(timezone=True))
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_quantity_positive"),)


class OrderMessage(Base):
    __tablename__ = "order_messages"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    message = Column(Text)
    attachment_url = Column(String(500))
    attachment_name = Column(String(255))
    attachment_mime = Column(String(100))
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    __table_args__ = (
        CheckConstraint("message IS NOT NULL OR attachment_url IS NOT NULL", name="ck_order_message_has_content"),
        Index("ix_order_messages_order_created", "order_id", "created_at"),
    )


class OrderEvent(Base):
    __tablename__ = "order_events"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type = Column(String(40), nullable=False, index=True)
    text = Column(String(500), nullable=False)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    __table_args__ = (Index("ix_order_events_order_created", "order_id", "created_at"),)


class Favorite(Base):
    __tablename__ = "favorites"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (Index("ix_chat_pair_created", "sender_id", "receiver_id", "created_at"),)


class BalanceHistory(Base):
    __tablename__ = "balance_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    type = Column(String(30), nullable=False)
    description = Column(Text)
    reference_type = Column(String(30))
    reference_id = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class PaymentDeposit(Base):
    __tablename__ = "payment_deposits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider = Column(String(32), default="yookassa", nullable=False, index=True)
    provider_payment_id = Column(String(128), unique=True, index=True)
    idempotency_key = Column(String(64), unique=True, nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), default="RUB", nullable=False)
    status = Column(String(32), default="pending", nullable=False, index=True)
    confirmation_url = Column(Text)
    failure_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    succeeded_at = Column(DateTime(timezone=True))
    canceled_at = Column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_deposit_amount_positive"),)


class WithdrawalRequest(Base):
    __tablename__ = "withdrawal_requests"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    wallet_type = Column(String(30), nullable=False)
    wallet_address = Column(String(255), nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True))
    processed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    provider = Column(String(32), default="manual", nullable=False, index=True)
    provider_payout_id = Column(String(128), unique=True, index=True)
    idempotency_key = Column(String(64), unique=True, index=True)
    bank_id = Column(String(32))
    failure_reason = Column(Text)
    __table_args__ = (CheckConstraint("amount > 0", name="ck_withdrawal_amount_positive"),)


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("order_id", "reviewer_id", name="uq_review_order_reviewer"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating"),
    )


class Dispute(Base):
    __tablename__ = "disputes"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    initiator_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    reason = Column(String(100), nullable=False)
    description = Column(Text)
    status = Column(String(30), default="open", nullable=False, index=True)
    resolution = Column(String(20))
    previous_order_status = Column(String(20))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("order_id", "status", name="uq_dispute_order_status"),)


class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(10), nullable=False, index=True)  # email / phone
    purpose = Column(String(30), default="verify_account", nullable=False, index=True)
    destination = Column(String(255), nullable=False)
    code_hash = Column(String(64), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    provider = Column(String(32))
    provider_message_id = Column(String(160))
    sent_at = Column(DateTime(timezone=True))
    request_ip = Column(String(64), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True))
    __table_args__ = (Index("ix_verification_user_channel_purpose", "user_id", "channel", "purpose"),)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    subject = Column(String(160), nullable=False)
    category = Column(String(40), default="general", nullable=False, index=True)
    priority = Column(String(20), default="normal", nullable=False, index=True)
    status = Column(String(30), default="open", nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True)
    closed_at = Column(DateTime(timezone=True))


class SupportMessage(Base):
    __tablename__ = "support_messages"
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    is_staff = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class MarketNotification(Base):
    __tablename__ = "market_notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(40), default="info", nullable=False, index=True)
    title = Column(String(160), nullable=False)
    body = Column(Text)
    link = Column(String(255))
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
