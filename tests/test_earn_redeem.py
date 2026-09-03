import asyncio

import pytest

from loyalty_app.loyalty import service
from loyalty_app.loyalty.errors import CustomerNotFound, TransactionInFlight, UnasWriteFailed, UnasWriteUncertain
from loyalty_app.loyalty.rules import RuleViolation
from loyalty_app.security import generate_loyalty_token, hash_token
from loyalty_app.models import LoyaltyCustomer, LoyaltyTransaction
from loyalty_app.unas.exceptions import UnasApiError, UnasTransientError

from fake_unas import FakeUnasClient

QR_PREFIX = "unas-loyalty:v1:"


def _add_customer(db_session, client, *, unas_id="41704472", balance=1000):
    token = generate_loyalty_token()
    client.add_customer(unas_id, "Teszt Elek", balance=balance)
    row = LoyaltyCustomer(unas_customer_id=unas_id, token_hash=hash_token(token), status="active")
    db_session.add(row)
    db_session.commit()
    return row, f"{QR_PREFIX}{token}"


@pytest.mark.asyncio
async def test_earn_computes_points_and_updates_unas_balance(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=1000)
    settings.loyalty_points_per_currency_unit = 0.01  # 1 point per 100 currency units

    result = await service.earn(
        db_session,
        client,
        settings,
        qr_payload=qr_payload,
        external_receipt_id="R-1",
        purchase_amount_gross=2000,
        idempotency_key="R-1:earn",
        store_id=None,
        register_id=None,
        cashier_user_id=None,
    )

    assert result.points_delta == 20
    assert result.balance_before == 1000
    assert result.balance_after == 1020
    assert result.status == "applied"
    assert client.set_balance_calls == [("41704472", 1020)]


@pytest.mark.asyncio
async def test_earn_unknown_qr_raises_customer_not_found(db_session, settings):
    client = FakeUnasClient()
    with pytest.raises(CustomerNotFound):
        await service.earn(
            db_session,
            client,
            settings,
            qr_payload=f"{QR_PREFIX}L1_doesnotexist12345678",
            external_receipt_id="R-1",
            purchase_amount_gross=1000,
            idempotency_key="R-1:earn",
            store_id=None,
            register_id=None,
            cashier_user_id=None,
        )


@pytest.mark.asyncio
async def test_redeem_success_reduces_balance(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=100)

    result = await service.redeem(
        db_session,
        client,
        settings,
        qr_payload=qr_payload,
        external_receipt_id="R-2",
        points_to_redeem=30,
        idempotency_key="R-2:redeem",
        store_id=None,
        register_id=None,
        cashier_user_id=None,
    )

    assert result.balance_before == 100
    assert result.balance_after == 70
    assert result.points_delta == -30


@pytest.mark.asyncio
async def test_redeem_insufficient_balance_rejected_without_calling_unas_write(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=10)

    with pytest.raises(RuleViolation) as excinfo:
        await service.redeem(
            db_session,
            client,
            settings,
            qr_payload=qr_payload,
            external_receipt_id="R-3",
            points_to_redeem=50,
            idempotency_key="R-3:redeem",
            store_id=None,
            register_id=None,
            cashier_user_id=None,
        )
    assert excinfo.value.code == "insufficient_balance"
    assert client.set_balance_calls == []


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_does_not_call_unas_twice(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=1000)

    kwargs = dict(
        qr_payload=qr_payload,
        external_receipt_id="R-4",
        purchase_amount_gross=1000,
        idempotency_key="R-4:earn",
        store_id=None,
        register_id=None,
        cashier_user_id=None,
    )
    first = await service.earn(db_session, client, settings, **kwargs)
    second = await service.earn(db_session, client, settings, **kwargs)

    assert first.transaction_id == second.transaction_id
    assert first.balance_after == second.balance_after
    assert len(client.set_balance_calls) == 1  # UNAS only written once


@pytest.mark.asyncio
async def test_unas_transient_error_leaves_transaction_pending(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=1000)
    client.fail_next_balance_write = UnasTransientError("timeout")

    with pytest.raises(UnasWriteUncertain):
        await service.earn(
            db_session,
            client,
            settings,
            qr_payload=qr_payload,
            external_receipt_id="R-5",
            purchase_amount_gross=1000,
            idempotency_key="R-5:earn",
            store_id=None,
            register_id=None,
            cashier_user_id=None,
        )

    tx = db_session.query(LoyaltyTransaction).filter_by(idempotency_key="R-5:earn").one()
    assert tx.status == "pending"


@pytest.mark.asyncio
async def test_unas_hard_error_marks_transaction_failed(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=1000)
    client.fail_next_balance_write = UnasApiError("validation error")

    with pytest.raises(UnasWriteFailed):
        await service.earn(
            db_session,
            client,
            settings,
            qr_payload=qr_payload,
            external_receipt_id="R-6",
            purchase_amount_gross=1000,
            idempotency_key="R-6:earn",
            store_id=None,
            register_id=None,
            cashier_user_id=None,
        )

    tx = db_session.query(LoyaltyTransaction).filter_by(idempotency_key="R-6:earn").one()
    assert tx.status == "failed"


@pytest.mark.asyncio
async def test_retry_after_failed_write_reuses_same_transaction_row(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=1000)
    client.fail_next_balance_write = UnasApiError("temporary validation issue")

    kwargs = dict(
        qr_payload=qr_payload,
        external_receipt_id="R-7",
        purchase_amount_gross=1000,
        idempotency_key="R-7:earn",
        store_id=None,
        register_id=None,
        cashier_user_id=None,
    )
    with pytest.raises(UnasWriteFailed):
        await service.earn(db_session, client, settings, **kwargs)

    # second attempt with same idempotency key succeeds (no injected failure this time)
    result = await service.earn(db_session, client, settings, **kwargs)
    assert result.status == "applied"

    rows = db_session.query(LoyaltyTransaction).filter_by(idempotency_key="R-7:earn").all()
    assert len(rows) == 1  # reused the same row, did not insert a second one


@pytest.mark.asyncio
async def test_concurrent_earn_requests_for_same_customer_are_serialized(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=0)
    settings.loyalty_points_per_currency_unit = 1.0  # 1 point per currency unit, easy to reason about

    async def do_earn(receipt: str):
        return await service.earn(
            db_session,
            client,
            settings,
            qr_payload=qr_payload,
            external_receipt_id=receipt,
            purchase_amount_gross=10,
            idempotency_key=f"{receipt}:earn",
            store_id=None,
            register_id=None,
            cashier_user_id=None,
        )

    results = await asyncio.gather(do_earn("A"), do_earn("B"), do_earn("C"))

    # Each of the 3 concurrent +10 earns must be reflected exactly once - no lost updates.
    final_balance = client.customers["41704472"].balance
    assert final_balance == 30
    assert {r.balance_after for r in results} == {10, 20, 30}
