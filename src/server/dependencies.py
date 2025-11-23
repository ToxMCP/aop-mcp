"""Factories for reusable service instances."""

from __future__ import annotations

from functools import lru_cache

from src.adapters import (
    AOPDBAdapter,
    AOPWikiAdapter,
    SparqlClient,
    SparqlEndpoint,
)
from src.adapters.comp_tox import CompToxClient
from src.instrumentation.cache import InMemoryCache
from src.instrumentation.metrics import MetricsRecorder
from src.tools.semantic import SemanticToolConfig, SemanticTools
from src.services.draft_store import DraftStoreService, InMemoryDraftRepository
from src.services.jobs import JobService
from src.tools.write import WriteTools
from src.server.config.settings import get_settings


@lru_cache
def get_metrics() -> MetricsRecorder:
    return MetricsRecorder()


def _build_sparql_client(endpoints: list[str]) -> SparqlClient:
    return SparqlClient(
        [SparqlEndpoint(url=e) for e in endpoints],
        cache=InMemoryCache(),
        metrics=get_metrics(),
    )


@lru_cache
def get_aop_wiki_adapter() -> AOPWikiAdapter:
    settings = get_settings()
    client = _build_sparql_client(settings.aop_wiki_sparql_endpoints)
    return AOPWikiAdapter(client=client, enable_fixture_fallback=settings.enable_fixture_fallback)


@lru_cache
def get_aop_db_adapter() -> AOPDBAdapter:
    settings = get_settings()
    client = _build_sparql_client(settings.aop_db_sparql_endpoints)
    comptox = get_comptox_client()
    return AOPDBAdapter(
        client,
        comptox_client=comptox,
        enable_fixture_fallback=settings.enable_fixture_fallback,
    )


@lru_cache
def get_comptox_client() -> CompToxClient:
    settings = get_settings()
    return CompToxClient(
        base_url=settings.comptox_base_url,
        bioactivity_url=settings.comptox_bioactivity_url,
        api_key=settings.comptox_api_key,
    )


@lru_cache
def get_semantic_tools() -> SemanticTools:
    config = SemanticToolConfig(
        curie_namespaces={
            "NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_",
            "PATO": "http://purl.obolibrary.org/obo/PATO_",
            "HsapDv": "http://purl.obolibrary.org/obo/HsapDv_",
        },
        species_map={
            "human": "NCBITaxon:9606",
            "homo sapiens": "NCBITaxon:9606",
        },
        life_stage_map={"adult": "HsapDv:0000087"},
        sex_map={"female": "PATO:0000383", "male": "PATO:0000384"},
    )
    return SemanticTools(config)


@lru_cache
def get_draft_store() -> DraftStoreService:
    return DraftStoreService(InMemoryDraftRepository())


@lru_cache
def get_write_tools() -> WriteTools:
    return WriteTools(
        draft_service=get_draft_store(),
        semantic_tools=get_semantic_tools(),
    )


@lru_cache
def get_job_service() -> JobService:
    return JobService()
