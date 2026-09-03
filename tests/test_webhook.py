import json

import pytest

from loyalty_app.loyalty.service import issue_token_for_customer
from loyalty_app.loyalty.webhook_adapter import parse_customer_registration_payload
from loyalty_app.models import LoyaltyCustomer
from loyalty_app.security import hash_token

from fake_unas import FakeUnasClient


def test_adapter_extracts_id_from_common_field_names():
    for payload in (
        {"Id": "41704472"},
        {"id": "41704472"},
        {"CustomerId": "41704472"},
        {"Customer": {"Id": "41704472"}},
        {"data": {"customerId": "41704472"}},
    ):
        result = parse_customer_registration_payload(json.dumps(payload).encode("utf-8"))
        assert result.unas_customer_id == "41704472", payload


def test_adapter_returns_none_for_unrecognized_shape():
    result = parse_customer_registration_payload(json.dumps({"totally": "unexpected"}).encode("utf-8"))
    assert result.unas_customer_id is None


def test_adapter_handles_non_json_body_gracefully():
    result = parse_customer_registration_payload(b"not json at all")
    assert result.unas_customer_id is None


@pytest.mark.asyncio
async def test_issue_token_for_new_customer_generates_and_writes_token(db_session, settings):
    client = FakeUnasClient()
    client.add_customer("41704472", "Teszt Elek", balance=0)

    result = await issue_token_for_customer(db_session, client, settings, "41704472")

    assert result.created_new_token is True
    assert len(client.set_param_calls) == 1
    unas_id, param_id, token = client.set_param_calls[0]
    assert unas_id == "41704472"
    assert param_id == settings.unas_loyalty_param_id
    assert token.startswith("L1_")

    row = db_session.get(LoyaltyCustomer, result.customer.id)
    assert row.token_hash == hash_token(token)
    assert row.status == "active"


@pytest.mark.asyncio
async def test_issue_token_adopts_existing_unas_param_without_rewriting(db_session, settings):
    client = FakeUnasClient()
    client.add_customer("41704472", "Teszt Elek", balance=0, params={settings.unas_loyalty_param_id: "L1_existing"})

    result = await issue_token_for_customer(db_session, client, settings, "41704472")

    assert result.created_new_token is False
    assert client.set_param_calls == []  # never re-wrote UNAS
    assert result.customer.token_hash == hash_token("L1_existing")


@pytest.mark.asyncio
async def test_issue_token_is_idempotent_across_repeated_webhook_delivery(db_session, settings):
    client = FakeUnasClient()
    client.add_customer("41704472", "Teszt Elek", balance=0)

    first = await issue_token_for_customer(db_session, client, settings, "41704472")
    second = await issue_token_for_customer(db_session, client, settings, "41704472")

    assert first.customer.token_hash == second.customer.token_hash
    assert len(client.set_param_calls) == 1  # only written once
