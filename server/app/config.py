from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central place for configurable settings so deployments stay flexible."""

    database_url: str = "sqlite:///./villagebank.db"
    # When set, Lenco operations are proxied through the local `lenco_pay` service.
    # Example: http://localhost:8001/api/v1
    lenco_pay_base: str = ""
    lenco_api_base: str = "https://api.lenco.ng/v1"
    lenco_api_key: str = ""
    lenco_webhook_secret: str = ""
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
