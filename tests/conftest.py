from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("UNAS_WEBHOOK_HMAC_SECRET", "test-hmac-secret")
os.environ.setdefault("LOYALTY_POINTS_PER_CURRENCY_UNIT", "0.01")
os.environ.setdefault("LOYALTY_REDEMPTION_VALUE_PER_POINT", "1")
os.environ.setdefault("LOYALTY_REDEMPTION_MIN_POINTS", "10")
os.environ.setdefault("LOYALTY_REDEMPTION_MAX_POINTS_PER_TX", "5000")

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from loyalty_app.config import Settings  # noqa: E402
from loyalty_app.db import Base  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        session_secret="test-secret",
        unas_webhook_hmac_secret="test-hmac-secret",
        loyalty_points_per_currency_unit=0.01,
        loyalty_points_rounding="floor",
        loyalty_redemption_value_per_point=1.0,
        loyalty_redemption_min_points=10,
        loyalty_redemption_max_points_per_tx=5000,
    )


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
