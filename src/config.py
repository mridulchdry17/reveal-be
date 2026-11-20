from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "staging", "production", "test"] = "local"
    database_url: str = "postgresql+asyncpg://reveal:reveal@localhost:5433/reveal"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Empty disables admin endpoints entirely.
    admin_token: SecretStr = SecretStr("")

    # Normalised form (uppercase, no spaces or dashes). Tighten once we see the real rank list.
    enrollment_pattern: str = r"[A-Z0-9]{6,20}"

    waitlist_joins_per_ip_per_hour: int = 5

    @property
    def show_docs(self) -> bool:
        return self.environment in ("local", "staging")


settings = Settings()
