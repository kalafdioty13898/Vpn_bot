"""All SQLAlchemy models (SQLAlchemy 2.x style)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------- Order / Invoice / Payment statuses (explicit, no ambiguity) ----------------
class OrderStatus:
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAYMENT_SUBMITTED = "PAYMENT_SUBMITTED"
    PAYMENT_REVIEW = "PAYMENT_REVIEW"
    PAID = "PAID"
    PAYMENT_REJECTED = "PAYMENT_REJECTED"
    PROVISIONING = "PROVISIONING"
    PROVISIONED = "PROVISIONED"
    PROVISION_FAILED = "PROVISION_FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"

    SOLD_STATUSES = (PAID, PROVISIONING, PROVISIONED, PROVISION_FAILED)


class InvoiceStatus:
    PENDING = "PENDING"
    PAID = "PAID"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PaymentMethod:
    CARD_TO_CARD = "CARD_TO_CARD"
    WALLET = "WALLET"
    ADMIN = "ADMIN"


class PaymentStatus:
    PENDING = "PENDING"
    PAID = "PAID"
    REJECTED = "REJECTED"


class ReceiptStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class InvoiceType:
    SERVICE = "SERVICE"
    WALLET_DEPOSIT = "WALLET_DEPOSIT"


class UserRole:
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"


class UserStatus:
    ACTIVE = "ACTIVE"
    BANNED = "BANNED"


# ---------------- Models ----------------
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str] = mapped_column(String(128), default="")
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.ACTIVE, index=True)
    free_trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)


class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)  # مثبت = واریز، منفی = برداشت
    tx_type: Mapped[str] = mapped_column(String(32), index=True)  # DEPOSIT/PURCHASE/REFUND/COMMISSION/ADMIN_ADJUST
    reference: Mapped[str] = mapped_column(String(64), default="")
    balance_after: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Admin(Base, TimestampMixin):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(16), default=UserRole.ADMIN)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ServicePlan(Base, TimestampMixin):
    __tablename__ = "service_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    volume_gb: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class VPNService(Base, TimestampMixin):
    __tablename__ = "vpn_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vpn_username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("service_plans.id"), nullable=True)
    volume_gb: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    subscription_url: Mapped[str] = mapped_column(Text, default="")
    panel_mode: Mapped[str] = mapped_column(String(16), default="mock")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow().replace(tzinfo=self.expires_at.tzinfo) > self.expires_at


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("service_plans.id"), nullable=True)
    invoice_id: Mapped[str] = mapped_column(String(32), index=True)
    service_kind: Mapped[str] = mapped_column(String(16), default="PLAN")  # PLAN/CUSTOM/TRIAL
    vpn_username: Mapped[str] = mapped_column(String(64))
    volume_gb: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.PENDING_PAYMENT, index=True)
    paid_by: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    invoice_type: Mapped[str] = mapped_column(String(16), default=InvoiceType.SERVICE, index=True)
    order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default=InvoiceStatus.PENDING, index=True)


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    invoice_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.PENDING, index=True)


class Receipt(Base, TimestampMixin):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[str] = mapped_column(String(32), index=True)
    invoice_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    file_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # PHOTO/DOCUMENT/TEXT
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default=ReceiptStatus.PENDING, index=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommissionTransaction(Base):
    __tablename__ = "commission_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    percent: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="PAID", index=True)  # PAID/REVERSED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupportMessage(Base, TimestampMixin):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    admin_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)  # OPEN/REPLIED


class Tutorial(Base, TimestampMixin):
    __tablename__ = "tutorials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)  # ANDROID/IOS/WINDOWS/V2RAY/V2BOX
    title: Mapped[str] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def default_expiry(days: int) -> datetime:
    return datetime.utcnow() + timedelta(days=days)
