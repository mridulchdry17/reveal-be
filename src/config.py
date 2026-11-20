from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "staging", "production", "test"] = "local"
    database_url: str = "postgresql+asyncpg://reveal:reveal@localhost:5433/reveal"
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def show_docs(self) -> bool:
        return self.environment in ("local", "staging")


settings = Settings()
