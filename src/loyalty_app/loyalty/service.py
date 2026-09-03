from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from loyalty_app.concurrency import customer_locks
from loyalty_app.config import Settings
from loyalty_app.loyalty import qr, rules
from loyalty_app.loyalty.errors import (
    CustomerNotFound,
    TransactionAlreadyReversed,
    TransactionInFlight,
    TransactionNotFound,
    TransactionNotReversible,
    UnasWriteFailed,
    UnasWriteUncertain,
)
from loyalty_app.models import LoyaltyCustomer, LoyaltyTransaction
from loyalty_app.security import generate_loyalty_token, hash_token, mask_token
from loyalty_app.unas.client import UnasClient
from loyalty_app.unas.exceptions import UnasApiError, UnasTransientError

logger = logging.getLogger("loyalty_app.service")

PENDING_FRESH_SECONDS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- token issuance (webhook + backfill) ------------------------------------


@dataclass
class TokenIssueResult:
    customer: LoyaltyCustomer
    created_new_token: bool


async def issue_token_for_customer(
    session: Session, unas_client: UnasClient, settings: Settings, unas_customer_id: str
) -> TokenIssueResult:
    """Idempotent: if UNAS already has a value in the loyalty param, adopt it rather
    than generating a new one (spec: "ha mar van ervenyes tokenje, nem general
    ujat"). UNAS's param value is the source of truth, not our local DB.
    """
    lock = customer_locks.get(f"unas:{unas_customer_id}")
    async with lock:
        remote = await unas_client.get_customer_by_id(unas_customer_id)
        if remote is None:
            raise CustomerNotFound()

        existing_value = (remote.params.get(settings.unas_loyalty_param_id) or "").strip()
        created_new = False
        if existing_value:
            token = existing_value
        else:
            token = generate_loyalty_token()
            await unas_client.set_customer_param(unas_customer_id, settings.unas_loyalty_param_id, token)
            created_new = True

        token_hash = hash_token(token)
        row = session.execute(
            select(LoyaltyCustomer).where(LoyaltyCustomer.unas_customer_id == unas_customer_id)
        ).scalar_one_or_none()
        if row is None:
            row = LoyaltyCustomer(
                unas_customer_id=unas_customer_id,
                token_hash=token_hash,
                status="active",
                display_name_cache=remote.display_name,
                last_synced_at=_now(),
            )
            session.add(row)
        else:
            row.token_hash = token_hash
            row.status = "active"
            row.display_name_cache = remote.display_name
            row.last_synced_at = _now()
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row = session.execute(
                select(LoyaltyCustomer).where(LoyaltyCustomer.unas_customer_id == unas_customer_id)
            ).scalar_one()
        return TokenIssueResult(customer=row, created_new_token=created_new)


# --- scan resolve -------------------------------------------------------


@dataclass
class ScanResult:
    customer_id: str
    unas_customer_id: str
    display_name: str | None
    masked_token: str
    points_balance: int


async def resolve_scan(
    session: Session, unas_client: UnasClient, settings: Settings, qr_payload: str
) -> ScanResult:
    token = qr.extract_token(
        qr_payload, prefix=settings.loyalty_qr_prefix, max_token_length=settings.loyalty_token_max_length
    )
    if token is None:
        raise CustomerNotFound()

    row = session.execute(
        select(LoyaltyCustomer).where(
            LoyaltyCustomer.token_hash == hash_token(token), LoyaltyCustomer.status == "active"
        )
    ).scalar_one_or_none()
    if row is None:
        raise CustomerNotFound()

    remote = await unas_client.get_customer_by_id(row.unas_customer_id)
    if remote is None:
        raise CustomerNotFound()

    row.display_name_cache = remote.display_name
    row.last_synced_at = _now()
    session.commit()

    return ScanResult(
        customer_id=row.id,
        unas_customer_id=row.unas_customer_id,
        display_name=remote.display_name,
        masked_token=mask_token(token),
        points_balance=int(remote.points_balance or 0),
    )


# --- earn / redeem --------------------------------------------------------


@dataclass
class TransactionResult:
    transaction_id: str
    status: str
    balance_before: int
    balance_after: int
    points_delta: int


def _existing_transaction_for_key(session: Session, idempotency_key: str) -> LoyaltyTransaction | None:
    return session.execute(
        select(LoyaltyTransaction).where(LoyaltyTransaction.idempotency_key == idempotency_key)
    ).scalar_one_or_none()


def _is_fresh_pending(tx: LoyaltyTransaction) -> bool:
    if tx.status != "pending":
        return False
    created = tx.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return _now() - created < timedelta(seconds=PENDING_FRESH_SECONDS)


async def _apply_balance_change(
    session: Session,
    unas_client: UnasClient,
    *,
    customer: LoyaltyCustomer,
    tx_type: str,
    points_delta: int,
    idempotency_key: str,
    external_receipt_id: str | None,
    store_id: str | None,
    register_id: str | None,
    cashier_user_id: str | None,
    reversed_transaction_id: str | None = None,
    reversal_reason: str | None = None,
) -> TransactionResult:
    existing = _existing_transaction_for_key(session, idempotency_key)
    if existing is not None and existing.status == "applied":
        return TransactionResult(
            transaction_id=existing.id,
            status=existing.status,
            balance_before=existing.balance_before or 0,
            balance_after=existing.balance_after or 0,
            points_delta=existing.points_delta,
        )
    if existing is not None and _is_fresh_pending(existing):
        raise TransactionInFlight()

    remote = await unas_client.get_customer_by_id(customer.unas_customer_id)
    if remote is None:
        raise CustomerNotFound()
    balance_before = int(remote.points_balance or 0)
    balance_after = balance_before + points_delta

    if existing is not None:
        tx = existing
        tx.balance_before = balance_before
        tx.balance_after = balance_after
        tx.status = "pending"
        tx.error_code = None
        tx.error_message = None
    else:
        tx = LoyaltyTransaction(
            customer_id=customer.id,
            external_receipt_id=external_receipt_id,
            store_id=store_id,
            register_id=register_id,
            cashier_user_id=cashier_user_id,
            type=tx_type,
            points_delta=points_delta,
            balance_before=balance_before,
            balance_after=balance_after,
            status="pending",
            idempotency_key=idempotency_key,
            reversed_transaction_id=reversed_transaction_id,
            reversal_reason=reversal_reason,
        )
        session.add(tx)
    session.commit()

    try:
        await unas_client.set_customer_balance(customer.unas_customer_id, balance_after)
    except UnasTransientError as exc:
        tx.error_message = str(exc)
        session.commit()
        logger.warning("unas balance write uncertain for tx=%s: %s", tx.id, exc)
        raise UnasWriteUncertain() from exc
    except UnasApiError as exc:
        tx.status = "failed"
        tx.error_message = str(exc)
        session.commit()
        raise UnasWriteFailed(str(exc)) from exc

    tx.status = "applied"
    tx.applied_at = _now()
    customer.last_synced_at = _now()
    session.commit()

    return TransactionResult(
        transaction_id=tx.id,
        status=tx.status,
        balance_before=balance_before,
        balance_after=balance_after,
        points_delta=points_delta,
    )


async def earn(
    session: Session,
    unas_client: UnasClient,
    settings: Settings,
    *,
    qr_payload: str,
    external_receipt_id: str,
    purchase_amount_gross: int,
    idempotency_key: str,
    store_id: str | None,
    register_id: str | None,
    cashier_user_id: str | None,
) -> TransactionResult:
    token = qr.extract_token(
        qr_payload, prefix=settings.loyalty_qr_prefix, max_token_length=settings.loyalty_token_max_length
    )
    if token is None:
        raise CustomerNotFound()
    customer = session.execute(
        select(LoyaltyCustomer).where(
            LoyaltyCustomer.token_hash == hash_token(token), LoyaltyCustomer.status == "active"
        )
    ).scalar_one_or_none()
    if customer is None:
        raise CustomerNotFound()

    points = rules.calculate_earn_points(purchase_amount_gross, settings)

    lock = customer_locks.get(customer.id)
    async with lock:
        return await _apply_balance_change(
            session,
            unas_client,
            customer=customer,
            tx_type="earn",
            points_delta=points,
            idempotency_key=idempotency_key,
            external_receipt_id=external_receipt_id,
            store_id=store_id,
            register_id=register_id,
            cashier_user_id=cashier_user_id,
        )


async def redeem(
    session: Session,
    unas_client: UnasClient,
    settings: Settings,
    *,
    qr_payload: str,
    external_receipt_id: str,
    points_to_redeem: int,
    idempotency_key: str,
    store_id: str | None,
    register_id: str | None,
    cashier_user_id: str | None,
) -> TransactionResult:
    token = qr.extract_token(
        qr_payload, prefix=settings.loyalty_qr_prefix, max_token_length=settings.loyalty_token_max_length
    )
    if token is None:
        raise CustomerNotFound()
    customer = session.execute(
        select(LoyaltyCustomer).where(
            LoyaltyCustomer.token_hash == hash_token(token), LoyaltyCustomer.status == "active"
        )
    ).scalar_one_or_none()
    if customer is None:
        raise CustomerNotFound()

    lock = customer_locks.get(customer.id)
    async with lock:
        remote = await unas_client.get_customer_by_id(customer.unas_customer_id)
        if remote is None:
            raise CustomerNotFound()
        current_balance = int(remote.points_balance or 0)
        rules.validate_redeem_request(points_to_redeem, current_balance, settings)

        return await _apply_balance_change(
            session,
            unas_client,
            customer=customer,
            tx_type="redeem",
            points_delta=-points_to_redeem,
            idempotency_key=idempotency_key,
            external_receipt_id=external_receipt_id,
            store_id=store_id,
            register_id=register_id,
            cashier_user_id=cashier_user_id,
        )


async def reverse(
    session: Session,
    unas_client: UnasClient,
    settings: Settings,
    *,
    transaction_id: str,
    reason: str,
    actor_user_id: str | None,
) -> TransactionResult:
    original = session.get(LoyaltyTransaction, transaction_id)
    if original is None:
        raise TransactionNotFound()
    if original.type not in ("earn", "redeem"):
        raise TransactionNotReversible("csak jovairas vagy bevaltas vonhato vissza")
    if original.status == "reversed":
        raise TransactionAlreadyReversed()
    if original.status != "applied":
        raise TransactionNotReversible("csak sikeresen alkalmazott tranzakcio vonhato vissza")

    customer = session.get(LoyaltyCustomer, original.customer_id)
    if customer is None:
        raise CustomerNotFound()

    idempotency_key = f"reverse:{original.id}"

    lock = customer_locks.get(customer.id)
    async with lock:
        session.refresh(original)
        if original.status == "reversed":
            raise TransactionAlreadyReversed()

        result = await _apply_balance_change(
            session,
            unas_client,
            customer=customer,
            tx_type="reversal",
            points_delta=-original.points_delta,
            idempotency_key=idempotency_key,
            external_receipt_id=original.external_receipt_id,
            store_id=original.store_id,
            register_id=original.register_id,
            cashier_user_id=actor_user_id,
            reversed_transaction_id=original.id,
            reversal_reason=reason,
        )
        if result.status == "applied":
            original.status = "reversed"
            session.commit()
        return result
