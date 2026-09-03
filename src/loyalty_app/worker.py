"""In-process background worker.

Two jobs, run on a simple polling loop:

1. Process pending ``webhook_events`` rows (the DB table doubles as a durable
   outbox - no Redis/Celery needed at this scale, see docs/ARCHITECTURE_DECISIONS.md).
2. Reconcile ``loyalty_transactions`` stuck in ``pending`` (UNAS write outcome was
   uncertain - timeout/5xx) by re-reading the UNAS balance and comparing it to the
   expected ``balance_after``.

Runs as a single asyncio task inside the same process as the web server (see
main.py lifespan). This is an accepted single-instance limitation: running more
than one app instance against the same SQLite file would double-process work.
See docs/KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from loyalty_app.config import Settings
from loyalty_app.loyalty.service import PENDING_FRESH_SECONDS, issue_token_for_customer
from loyalty_app.loyalty.webhook_adapter import mask_payload_for_logging, parse_customer_registration_payload
from loyalty_app.models import LoyaltyTransaction, WebhookEvent
from loyalty_app.unas.client import UnasClient

logger = logging.getLogger("loyalty_app.worker")

MAX_WEBHOOK_ATTEMPTS = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def process_pending_webhooks(session: Session, unas_client: UnasClient, settings: Settings) -> int:
    due = session.execute(
        select(WebhookEvent).where(
            WebhookEvent.process_status == "received",
        ).order_by(WebhookEvent.received_at).limit(20)
    ).scalars().all()

    processed = 0
    for event in due:
        if event.next_attempt_at is not None and event.next_attempt_at > _now():
            continue
        await _process_one_webhook(session, unas_client, settings, event)
        processed += 1
    return processed


async def _process_one_webhook(session: Session, unas_client: UnasClient, settings: Settings, event: WebhookEvent) -> None:
    event.attempts += 1
    if event.event_type != "customer_registration":
        event.process_status = "needs_review"
        event.error = f"ismeretlen esemenytipus: {event.event_type}"
        session.commit()
        return

    raw_body = event.raw_payload_masked.encode("utf-8")
    adapted = parse_customer_registration_payload(raw_body)
    if not adapted.unas_customer_id:
        event.process_status = "needs_review"
        event.error = "nem talalhato vasarlo-azonosito a webhook payloadban - lasd webhook_adapter.py"
        session.commit()
        logger.warning("webhook %s needs manual review: %s", event.id, mask_payload_for_logging(raw_body, 300))
        return

    try:
        await issue_token_for_customer(session, unas_client, settings, adapted.unas_customer_id)
        event.process_status = "processed"
        event.error = None
        session.commit()
    except Exception as exc:  # noqa: BLE001
        event.error = str(exc)[:500]
        if event.attempts >= MAX_WEBHOOK_ATTEMPTS:
            event.process_status = "failed"
        else:
            backoff_seconds = min(300, 5 * (2 ** event.attempts))
            event.next_attempt_at = _now() + timedelta(seconds=backoff_seconds)
        session.commit()
        logger.exception("failed to process webhook %s (attempt %s)", event.id, event.attempts)


async def reconcile_pending_transactions(session: Session, unas_client: UnasClient) -> int:
    cutoff = _now() - timedelta(seconds=PENDING_FRESH_SECONDS)
    stale = session.execute(
        select(LoyaltyTransaction).where(
            LoyaltyTransaction.status == "pending",
            LoyaltyTransaction.created_at < cutoff,
        ).limit(20)
    ).scalars().all()

    reconciled = 0
    for tx in stale:
        remote = await unas_client.get_customer_by_id(tx.customer.unas_customer_id)
        if remote is None or remote.points_balance is None:
            continue
        actual_balance = int(remote.points_balance)
        if actual_balance == tx.balance_after:
            tx.status = "applied"
            tx.applied_at = _now()
        else:
            tx.status = "failed"
            tx.error_code = "reconciliation_mismatch"
            tx.error_message = (
                f"varakozott egyenleg={tx.balance_after}, tenyleges UNAS egyenleg={actual_balance} - "
                "admin ellenorzest igenyel"
            )
        session.commit()
        reconciled += 1
    return reconciled


async def run_worker_loop(
    session_factory: sessionmaker, unas_client: UnasClient, settings: Settings, *, interval_seconds: float = 5.0
) -> None:
    logger.info("loyalty background worker started (interval=%ss)", interval_seconds)
    while True:
        try:
            session = session_factory()
            try:
                await process_pending_webhooks(session, unas_client, settings)
                await reconcile_pending_transactions(session, unas_client)
            finally:
                session.close()
        except asyncio.CancelledError:
            logger.info("loyalty background worker stopping")
            raise
        except Exception:  # noqa: BLE001
            logger.exception("background worker iteration failed")
        await asyncio.sleep(interval_seconds)
