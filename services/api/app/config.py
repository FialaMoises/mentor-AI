from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da API. Segredo nenhum mora no código."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://mentor:mentor@localhost:5432/mentor"
    cors_origins: str = "http://localhost:4200"
    engine_k: float = 10.0
    engine_review_offsets_days: str = "1,7,30"
    engine_inactivity_days: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def review_offsets(self) -> tuple[int, ...]:
        return tuple(int(part) for part in self.engine_review_offsets_days.split(","))


@lru_cache
def get_settings() -> Settings:
    return Settings()
