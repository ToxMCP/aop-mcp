"""Application configuration using Pydantic settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AOP_MCP_",
        case_sensitive=False,
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
    )

    environment: str = "development"
    host: str = "127.0.0.1"
    log_level: str = "INFO"
    enable_fixture_fallback: bool = False
    auth_mode: str = "disabled"
    auth_bearer_token: str | None = None
    auth_bearer_scopes: Annotated[list[str], NoDecode] = [
        "toxmcp:read",
        "toxmcp:live",
        "toxmcp:execute",
        "toxmcp:export",
        "toxmcp:admin",
    ]
    allowed_origins: Annotated[list[str], NoDecode] = []
    max_request_bytes: int = 1_000_000
    allow_unauthenticated_production: bool = False

    # SPARQL endpoints
    aop_wiki_sparql_endpoints: Annotated[list[str], NoDecode] = [
        "https://aopwiki.rdf.bigcat-bioinformatics.org/sparql",
        "https://aopwiki.cloud.vhp4safety.nl/sparql/",
    ]
    aop_db_sparql_endpoints: Annotated[list[str], NoDecode] = [
        "https://aopwiki.rdf.bigcat-bioinformatics.org/sparql",
    ]

    # CompTox
    comptox_base_url: str = "https://comptox.epa.gov/dashboard/api/"
    comptox_bioactivity_url: str = "https://comptox.epa.gov/ctx-api/"
    comptox_api_key: str | None = None

    # HGNC
    hgnc_base_url: str = "https://rest.genenames.org/"
    hgnc_timeout: float = 5.0

    # Local artifact export
    artifact_output_dir: str = "output"
    audit_log_path: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() not in {"development", "local", "test"}

    @field_validator("aop_wiki_sparql_endpoints", "aop_db_sparql_endpoints", mode="before")
    @classmethod
    def _split_csv_endpoints(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("auth_bearer_scopes", mode="before")
    @classmethod
    def _split_csv_scopes(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("audit_log_path", mode="before")
    @classmethod
    def _empty_audit_log_path_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("auth_mode")
    @classmethod
    def _normalise_auth_mode(cls, value: str) -> str:
        mode = value.strip().lower()
        if mode not in {"disabled", "bearer"}:
            raise ValueError("AOP_MCP_AUTH_MODE must be 'disabled' or 'bearer'")
        return mode

    @model_validator(mode="after")
    def _validate_security_posture(self) -> "Settings":
        if self.max_request_bytes < 1:
            raise ValueError("AOP_MCP_MAX_REQUEST_BYTES must be positive")
        if not self.is_production:
            return self
        if self.host.strip() in {"0.0.0.0", "::", "[::]"}:
            raise ValueError("AOP_MCP_HOST must not be 0.0.0.0/:: in production")
        if self.auth_mode == "disabled" and not self.allow_unauthenticated_production:
            raise ValueError("AOP_MCP_AUTH_MODE=bearer is required in production")
        if self.auth_mode == "bearer" and not self.auth_bearer_token:
            raise ValueError("AOP_MCP_AUTH_BEARER_TOKEN is required when bearer auth is enabled")
        if not self.allowed_origins:
            raise ValueError("AOP_MCP_ALLOWED_ORIGINS must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
