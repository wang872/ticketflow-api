from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "TicketFlow"
    secret_key: str = "dev-only-change-me-use-env-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    database_url: str = "sqlite:///./data/ticketflow.db"
    sla_check_interval_seconds: int = 30
    sla_checker_enabled: bool = True
    seed_on_startup: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
