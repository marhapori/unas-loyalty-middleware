import pytest

from loyalty_app.loyalty import service
from loyalty_app.loyalty.errors import TransactionAlreadyReversed, TransactionNotReversible
from loyalty_app.models import LoyaltyCustomer, LoyaltyTransaction
from loyalty_app.security import generate_loyalty_token, hash_token

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
async def test_reverse_earn_restores_previous_balance(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=1000)

    earn_result = await service.earn(
        db_session, client, settings,
        qr_payload=qr_payload, external_receipt_id="R-1", purchase_amount_gross=1000,
        idempotency_key="R-1:earn", store_id=None, register_id=None, cashier_user_id=None,
    )
    assert earn_result.balance_after == 1010

    reverse_result = await service.reverse(
        db_session, client, settings,
        transaction_id=earn_result.transaction_id, reason="vasarlo tevedesbol lett beolvasva", actor_user_id="admin-1",
    )

    assert reverse_result.balance_after == 1000
    assert reverse_result.points_delta == -10
    original = db_session.get(LoyaltyTransaction, earn_result.transaction_id)
    assert original.status == "reversed"


@pytest.mark.asyncio
async def test_reverse_redeem_gives_points_back(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=100)

    redeem_result = await service.redeem(
        db_session, client, settings,
        qr_payload=qr_payload, external_receipt_id="R-2", points_to_redeem=40,
        idempotency_key="R-2:redeem", store_id=None, register_id=None, cashier_user_id=None,
    )
    assert redeem_result.balance_after == 60

    reverse_result = await service.reverse(
        db_session, client, settings,
        transaction_id=redeem_result.transaction_id, reason="visszaru", actor_user_id="admin-1",
    )
    assert reverse_result.balance_after == 100
    assert reverse_result.points_delta == 40


@pytest.mark.asyncio
async def test_double_reverse_is_rejected(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=1000)

    earn_result = await service.earn(
        db_session, client, settings,
        qr_payload=qr_payload, external_receipt_id="R-3", purchase_amount_gross=1000,
        idempotency_key="R-3:earn", store_id=None, register_id=None, cashier_user_id=None,
    )
    await service.reverse(
        db_session, client, settings,
        transaction_id=earn_result.transaction_id, reason="teszt", actor_user_id="admin-1",
    )

    with pytest.raises(TransactionAlreadyReversed):
        await service.reverse(
            db_session, client, settings,
            transaction_id=earn_result.transaction_id, reason="masodik proba", actor_user_id="admin-1",
        )


@pytest.mark.asyncio
async def test_reverse_of_a_reversal_is_not_allowed(db_session, settings):
    client = FakeUnasClient()
    _, qr_payload = _add_customer(db_session, client, balance=1000)

    earn_result = await service.earn(
        db_session, client, settings,
        qr_payload=qr_payload, external_receipt_id="R-4", purchase_amount_gross=1000,
        idempotency_key="R-4:earn", store_id=None, register_id=None, cashier_user_id=None,
    )
    reverse_result = await service.reverse(
        db_session, client, settings,
        transaction_id=earn_result.transaction_id, reason="teszt", actor_user_id="admin-1",
    )

    with pytest.raises(TransactionNotReversible):
        await service.reverse(
            db_session, client, settings,
            transaction_id=reverse_result.transaction_id, reason="lancolt visszavonas", actor_user_id="admin-1",
        )
