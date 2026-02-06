"""Application configuration using Pydantic settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AOP_MCP_",
        case_sensitive=False,
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
    )

    environment: str = "development"
    log_level: str = "INFO"
    enable_fixture_fallback: bool = False

    # SPARQL endpoints
    aop_wiki_sparql_endpoints: list[str] = [
        "https://aopwiki.rdf.bigcat-bioinformatics.org/sparql",
        "https://aopwiki.cloud.vhp4safety.nl/sparql/",
    ]
    aop_db_sparql_endpoints: list[str] = [
        "https://aopwiki.rdf.bigcat-bioinformatics.org/sparql",
    ]

    # CompTox
    comptox_base_url: str = "https://comptox.epa.gov/dashboard/api/"
    comptox_bioactivity_url: str = "https://comptox.epa.gov/ctx-api/"
    comptox_api_key: str | None = None

    @field_validator("aop_wiki_sparql_endpoints", "aop_db_sparql_endpoints", mode="before")
    @classmethod
    def _split_csv_endpoints(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
