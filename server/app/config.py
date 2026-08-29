from functools import lru_cache
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SANDBOX_LIPILA_ORIGIN = "https://api.lipila.dev"
LIVE_LIPILA_ORIGIN = "https://blz.lipila.io"


class Settings(BaseSettings):
    """Central place for configurable settings so deployments stay flexible."""

    database_url: str = "sqlite:///./villagebank.db"

    # Lipila payments. Sandbox by default; going live is a deliberate switch that
    # also forces the production origin, so a live key can never be pointed at
    # the sandbox host (or the reverse) by accident.
    lipila_live_enabled: bool = False
    lipila_base_url: str = SANDBOX_LIPILA_ORIGIN
    lipila_api_key: str = ""
    lipila_webhook_secret_current: str = ""
    lipila_webhook_secret_previous: str = ""
    lipila_timeout_seconds: float = 15.0
    lipila_webhook_replay_window_seconds: int = 300
    # Public origin Lipila calls back on. Must reach this API from the internet.
    lipila_callback_base_url: str = "http://localhost:8000"
    # Where a card payer lands once the hosted page is done with them.
    lipila_card_return_url: str = "http://localhost:5173/?payment=return"

    # Payouts. Lipila's disbursement API is not covered by the collections
    # integration these paths were derived from, so they stay configurable and
    # the feature stays off until the paths below are confirmed against the
    # Lipila dashboard docs.
    lipila_disbursements_enabled: bool = False
    lipila_disbursement_mobile_money_path: str = "/api/v1/disbursements/mobile-money"
    lipila_disbursement_bank_path: str = "/api/v1/disbursements/bank"
    lipila_disbursement_status_path: str = "/api/v1/disbursements/check-status"

    interest_compound_days: int = 30
    auth_secret_key: str = "change-me"
    auth_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    default_admin_email: Optional[str] = None
    default_admin_password: Optional[str] = None
    scheduler_timezone: str = "UTC"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def validate_lipila_origin(self) -> "Settings":
        expected = LIVE_LIPILA_ORIGIN if self.lipila_live_enabled else SANDBOX_LIPILA_ORIGIN
        if self.safe_lipila_base_url != expected:
            environment = "live" if self.lipila_live_enabled else "sandbox"
            raise ValueError(f"{environment} payments require lipila_base_url={expected}")
        return self

    @property
    def safe_lipila_base_url(self) -> str:
        return self.lipila_base_url.rstrip("/")

    @property
    def lipila_configured(self) -> bool:
        return bool(self.lipila_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
