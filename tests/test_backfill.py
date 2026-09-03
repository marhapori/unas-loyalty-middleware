import pytest

from loyalty_app.cli import run_backfill
from loyalty_app.models import LoyaltyCustomer

from fake_unas import FakeUnasClient


def _seed_customers(client, settings, count, *, with_existing_token=0):
    for i in range(count):
        params = {}
        if i < with_existing_token:
            params[settings.unas_loyalty_param_id] = f"L1_existing{i}"
        client.add_customer(str(1000 + i), f"Vasarlo {i}", balance=0, params=params)


@pytest.mark.asyncio
async def test_dry_run_does_not_write_to_unas_or_db(db_session, settings):
    client = FakeUnasClient()
    _seed_customers(client, settings, 5)

    summary = await run_backfill(db_session, client, settings, dry_run=True, limit=0)

    assert summary.processed == 5
    assert summary.created == 5
    assert client.set_param_calls == []
    assert db_session.query(LoyaltyCustomer).count() == 0


@pytest.mark.asyncio
async def test_real_run_writes_tokens_and_skips_existing(db_session, settings):
    client = FakeUnasClient()
    _seed_customers(client, settings, 5, with_existing_token=2)

    summary = await run_backfill(db_session, client, settings, dry_run=False, limit=0)

    assert summary.processed == 5
    assert summary.created == 3
    assert summary.skipped == 2
    assert len(client.set_param_calls) == 3
    # every processed customer (created AND skipped-because-already-had-a-token)
    # gets a local DB row upserted, so scan lookups work for both groups
    assert db_session.query(LoyaltyCustomer).count() == 5


@pytest.mark.asyncio
async def test_backfill_paginates_across_multiple_pages(db_session, settings, monkeypatch):
    from loyalty_app import cli as cli_module

    monkeypatch.setattr(cli_module, "PAGE_SIZE", 2)
    client = FakeUnasClient()
    _seed_customers(client, settings, 5)

    summary = await run_backfill(db_session, client, settings, dry_run=False, limit=0)

    assert summary.processed == 5
    assert summary.created == 5


@pytest.mark.asyncio
async def test_backfill_respects_limit(db_session, settings):
    client = FakeUnasClient()
    _seed_customers(client, settings, 10)

    summary = await run_backfill(db_session, client, settings, dry_run=True, limit=3)

    assert summary.processed == 3


@pytest.mark.asyncio
async def test_backfill_is_idempotent_when_rerun(db_session, settings):
    client = FakeUnasClient()
    _seed_customers(client, settings, 3)

    first = await run_backfill(db_session, client, settings, dry_run=False, limit=0)
    second = await run_backfill(db_session, client, settings, dry_run=False, limit=0)

    assert first.created == 3
    assert second.created == 0
    assert second.skipped == 3
