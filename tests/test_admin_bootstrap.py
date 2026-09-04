"""Tests the /api/admin/bootstrap endpoint in isolation (own FastAPI app mounting
just this router, with get_db/get_settings overridden) - avoids needing the full
app's lifespan/UnasClient/background worker, which aren't relevant here."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loyalty_app.api import admin_routes
from loyalty_app.api.deps import get_db
from loyalty_app.config import get_settings
from loyalty_app.models import Store, User
from loyalty_app.rate_limit import admin_bootstrap_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # admin_bootstrap_limiter is a module-level singleton shared across every
    # test in the process - without resetting it, earlier tests' calls would
    # count against later tests' quota and trip a spurious 429.
    admin_bootstrap_limiter._hits.clear()
    yield
    admin_bootstrap_limiter._hits.clear()


def _client(db_session, settings) -> TestClient:
    app = FastAPI()
    app.include_router(admin_routes.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_disabled_by_default_returns_404(db_session, settings):
    settings.admin_bootstrap_token = ""
    client = _client(db_session, settings)
    response = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Token": "anything"},
        json={"storeName": "Bolt", "storeCode": "B1", "username": "admin1", "password": "verysecret1"},
    )
    assert response.status_code == 404


def test_wrong_token_rejected(db_session, settings):
    settings.admin_bootstrap_token = "correct-token"
    client = _client(db_session, settings)
    response = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Token": "wrong-token"},
        json={"storeName": "Bolt", "storeCode": "B1", "username": "admin1", "password": "verysecret1"},
    )
    assert response.status_code == 403


def test_missing_token_header_rejected(db_session, settings):
    settings.admin_bootstrap_token = "correct-token"
    client = _client(db_session, settings)
    response = client.post(
        "/api/admin/bootstrap",
        json={"storeName": "Bolt", "storeCode": "B1", "username": "admin1", "password": "verysecret1"},
    )
    assert response.status_code == 403


def test_creates_store_and_admin_user(db_session, settings):
    settings.admin_bootstrap_token = "correct-token"
    client = _client(db_session, settings)
    response = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Token": "correct-token"},
        json={"storeName": "Fo bolt", "storeCode": "BOLT01", "username": "kassza1", "password": "verysecret1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"storeCreated": True, "userCreated": True}

    store = db_session.query(Store).filter_by(code="BOLT01").one()
    assert store.name == "Fo bolt"
    user = db_session.query(User).filter_by(username="kassza1").one()
    assert user.role == "admin"
    assert user.store_id == store.id


def test_is_idempotent_on_rerun(db_session, settings):
    settings.admin_bootstrap_token = "correct-token"
    client = _client(db_session, settings)
    payload = {"storeName": "Fo bolt", "storeCode": "BOLT01", "username": "kassza1", "password": "verysecret1"}

    first = client.post("/api/admin/bootstrap", headers={"X-Bootstrap-Token": "correct-token"}, json=payload)
    second = client.post("/api/admin/bootstrap", headers={"X-Bootstrap-Token": "correct-token"}, json=payload)

    assert first.json() == {"storeCreated": True, "userCreated": True}
    assert second.json() == {"storeCreated": False, "userCreated": False}
    assert db_session.query(Store).filter_by(code="BOLT01").count() == 1
    assert db_session.query(User).filter_by(username="kassza1").count() == 1


def test_short_password_returns_422(db_session, settings):
    settings.admin_bootstrap_token = "correct-token"
    client = _client(db_session, settings)
    response = client.post(
        "/api/admin/bootstrap",
        headers={"X-Bootstrap-Token": "correct-token"},
        json={"storeName": "Bolt", "storeCode": "B1", "username": "admin1", "password": "short"},
    )
    assert response.status_code == 422
