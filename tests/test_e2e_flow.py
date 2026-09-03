import pytest

from loyalty_app.loyalty import service
from loyalty_app.loyalty.errors import CustomerNotFound

from fake_unas import FakeUnasClient

QR_PREFIX = "unas-loyalty:v1:"


@pytest.mark.asyncio
async def test_full_customer_lifecycle(db_session, settings):
    client = FakeUnasClient()
    client.add_customer("41704472", "Krisztian Piller", balance=0)

    # 1. registration webhook fires -> token generated and written back to UNAS
    issue_result = await service.issue_token_for_customer(db_session, client, settings, "41704472")
    unas_id, param_id, token = client.set_param_calls[0]
    assert param_id == settings.unas_loyalty_param_id
    qr_payload = f"{QR_PREFIX}{token}"

    # 2. cashier scans the QR - resolves to the customer with a fresh balance
    scan = await service.resolve_scan(db_session, client, settings, qr_payload)
    assert scan.display_name == "Krisztian Piller"
    assert scan.points_balance == 0

    # 3. purchase -> earn
    earn_result = await service.earn(
        db_session, client, settings,
        qr_payload=qr_payload, external_receipt_id="STORE-01-000123", purchase_amount_gross=17540,
        idempotency_key="STORE-01-000123:earn", store_id=None, register_id=None, cashier_user_id=None,
    )
    assert earn_result.status == "applied"
    balance_after_earn = earn_result.balance_after
    assert balance_after_earn > 0

    # repeating the exact same receipt/idempotency key must not double the balance
    repeat_result = await service.earn(
        db_session, client, settings,
        qr_payload=qr_payload, external_receipt_id="STORE-01-000123", purchase_amount_gross=17540,
        idempotency_key="STORE-01-000123:earn", store_id=None, register_id=None, cashier_user_id=None,
    )
    assert repeat_result.balance_after == balance_after_earn

    # profile "refresh" (another scan) reflects the new balance
    scan_after_earn = await service.resolve_scan(db_session, client, settings, qr_payload)
    assert scan_after_earn.points_balance == balance_after_earn

    # 4. later, a redemption
    settings.loyalty_redemption_min_points = 1
    redeem_result = await service.redeem(
        db_session, client, settings,
        qr_payload=qr_payload, external_receipt_id="STORE-01-000200", points_to_redeem=10,
        idempotency_key="STORE-01-000200:redeem", store_id=None, register_id=None, cashier_user_id=None,
    )
    assert redeem_result.balance_after == balance_after_earn - 10

    # 5. and a reversal of that redemption
    reverse_result = await service.reverse(
        db_session, client, settings,
        transaction_id=redeem_result.transaction_id, reason="vevo meggondolta magat", actor_user_id="admin-1",
    )
    assert reverse_result.balance_after == balance_after_earn

    # a revoked/unknown token never resolves
    with pytest.raises(CustomerNotFound):
        await service.resolve_scan(db_session, client, settings, f"{QR_PREFIX}L1_totallybogus0000000")
