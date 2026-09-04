"""Regression tests for the datetime naive/aware bug found in production
(2026-09-04, see docs/KNOWN_LIMITATIONS.md): comparing a DB-read datetime
against datetime.now(timezone.utc) crashed on Postgres (naive columns by
default) but never surfaced on SQLite locally, since that code path was never
exercised there with a real value."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from loyalty_app.models import WebhookEvent
from loyalty_app.worker import _aware, process_pending_webhooks

from fake_unas import FakeUnasClient


def test_aware_leaves_already_aware_datetime_untouched():
    dt = datetime.now(timezone.utc)
    assert _aware(dt) is dt


def test_aware_attaches_utc_to_naive_datetime():
    naive = datetime(2026, 9, 4, 12, 0, 0)
    result = _aware(naive)
    assert result.tzinfo == timezone.utc
    assert result.replace(tzinfo=None) == naive


@pytest.mark.asyncio
async def test_process_pending_webhooks_handles_naive_next_attempt_at(db_session, settings):
    # Simulates what a Postgres TIMESTAMP WITHOUT TIME ZONE column hands back:
    # a naive datetime, even though it was written as timezone-aware. Before the
    # fix, this raised "can't compare offset-naive and offset-aware datetimes"
    # and crashed the whole worker loop.
    future_naive = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    event = WebhookEvent(
        event_key="evt-1",
        event_type="customer_registration",
        raw_payload_masked="{}",
        verify_status="verified",
        process_status="received",
        next_attempt_at=future_naive,
    )
    db_session.add(event)
    db_session.commit()

    client = FakeUnasClient()
    processed = await process_pending_webhooks(db_session, client, settings)

    assert processed == 0  # not due yet - skipped, not crashed
