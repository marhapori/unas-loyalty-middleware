from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/loyalty.db"

    unas_api_base_url: str = "https://api.unas.eu/shop"
    unas_api_key: str = ""
    unas_loyalty_param_id: str = "6590861"
    unas_webhook_hmac_secret: str = ""
    unas_max_requests_per_second: float = 5.0
    unas_request_timeout_seconds: float = 30.0

    loyalty_qr_prefix: str = "unas-loyalty:v1:"
    loyalty_token_max_length: int = 64

    loyalty_points_rule_mode: str = "per_currency_unit"
    loyalty_points_per_currency_unit: float = 0.0
    loyalty_points_rounding: str = "floor"
    loyalty_redemption_value_per_point: float = 0.0
    loyalty_redemption_min_points: int = 0
    loyalty_redemption_max_points_per_tx: int = 0

    session_secret: str = Field(default="dev-insecure-secret-change-me")
    app_base_url: str = "http://localhost:8000"

    log_level: str = "INFO"

    # Empty (default) disables /api/admin/bootstrap entirely (fail-closed) - only
    # set this when a hosting platform gives no other way to run the seed-store /
    # create-user CLI commands against the deployed database (e.g. Render's free
    # tier, which has no Shell access). See docs/DEPLOYMENT.md.
    admin_bootstrap_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
