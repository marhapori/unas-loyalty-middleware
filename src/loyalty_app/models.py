from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from loyalty_app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(50), unique=True)

    registers: Mapped[list["Register"]] = relationship(back_populates="store")


class Register(Base):
    __tablename__ = "registers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"))
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(50), unique=True)

    store: Mapped[Store] = relationship(back_populates="registers")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # cashier | admin
    store_id: Mapped[str | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class LoyaltyCustomer(Base):
    __tablename__ = "loyalty_customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    unas_customer_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | revoked | pending
    display_name_cache: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_loyalty_tx_idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("loyalty_customers.id"), index=True)
    external_receipt_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    store_id: Mapped[str | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    register_id: Mapped[str | None] = mapped_column(ForeignKey("registers.id"), nullable=True)
    cashier_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    type: Mapped[str] = mapped_column(String(20))  # earn | redeem | reversal | adjustment
    points_delta: Mapped[int] = mapped_column(Integer)
    balance_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    balance_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|applied|failed|reversed
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)

    reversed_transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("loyalty_transactions.id"), nullable=True
    )
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    unas_response_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now)
    applied_at: Mapped[datetime | None] = mapped_column(nullable=True)

    customer: Mapped[LoyaltyCustomer] = relationship()


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    raw_payload_masked: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(default=_now)
    verify_status: Mapped[str] = mapped_column(String(20))  # verified | invalid
    process_status: Mapped[str] = mapped_column(
        String(20), default="received"
    )  # received|processed|needs_review|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
