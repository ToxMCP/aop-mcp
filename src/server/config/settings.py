"""Application configuration using Pydantic settings."""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    log_level: str = "INFO"
    enable_fixture_fallback: bool = False
    # enable_fixture_fallback: bool = True

    # SPARQL endpoints
    aop_wiki_sparql_endpoints: List[str] = [
        "https://aopwiki.rdf.bigcat-bioinformatics.org/sparql",
        "https://aopwiki.cloud.vhp4safety.nl/sparql/",
        # "https://sparql.aopwiki.org/sparql",
    ]
    aop_db_sparql_endpoints: List[str] = [
        "https://sparql.aopdb.org/sparql",
    ]

    # CompTox
    comptox_base_url: str = "https://comptox.epa.gov/dashboard/api/"
    comptox_api_key: Optional[str] = None

    class Config:
        env_prefix = "AOP_MCP_"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
