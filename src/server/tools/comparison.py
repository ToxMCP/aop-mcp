"""Source-linked comparisons; shared identifiers do not establish applicability."""
from __future__ import annotations

import asyncio
import re
from itertools import combinations
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.server.dependencies import get_aop_wiki_adapter


class ComparisonError(Exception):
    """An actionable, safe comparison failure with no partial scientific result."""


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompareAopsInput(Model):
    aop_ids: list[Annotated[str, Field(pattern=r"^AOP:[1-9][0-9]*$")]] = Field(
        min_length=2, max_length=4, description="Two to four distinct AOP CURIEs, e.g. AOP:40."
    )
    species: str | None = Field(default=None, min_length=1, max_length=64,
        description="human, mouse, rat, dog, or NCBITaxon CURIE; use unspecified if unknown.")
    life_stage: str | None = Field(default=None, min_length=1, max_length=64,
        description="Life stage label or ontology CURIE; use unspecified if unknown.")
    sex: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("aop_ids")
    @classmethod
    def distinct_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Choose distinct AOP IDs for a comparison.")
        return values

    @field_validator("species")
    @classmethod
    def valid_species(cls, value: str | None) -> str | None:
        if value is None:
            return value
        aliases = {"human": "NCBITaxon:9606", "homo sapiens": "NCBITaxon:9606",
                   "mouse": "NCBITaxon:10090", "rat": "NCBITaxon:10116", "dog": "NCBITaxon:9615"}
        value = aliases.get(value.lower(), value)
        if value.lower() != "unspecified" and not re.fullmatch(r"NCBITaxon:[1-9][0-9]*", value):
            raise ValueError("Use human, mouse, rat, dog, an NCBITaxon CURIE, or unspecified.")
        return value


class EventRef(Model):
    id: str
    title: str | None = None
    url: str


class EvidenceGap(Model):
    id: str
    url: str
    not_reported_fields: list[str]


class ContextEvidence(Model):
    assessment: Literal["requires_expert_review"] = "requires_expert_review"
    key_event_count: int
    species_exact_match_count: int
    species_unreported_count: int
    life_stage_exact_match_count: int
    life_stage_unreported_count: int
    sex_exact_match_count: int
    sex_unreported_count: int
    reported_taxa: list[str]
    reported_life_stages: list[str]
    reported_sexes: list[str]


class AopComparisonRecord(Model):
    id: str
    title: str
    url: str
    key_events: list[EventRef]
    ker_ids: list[str]
    molecular_initiating_events: list[EventRef]
    adverse_outcomes: list[EventRef]
    evidence_gaps: list[EvidenceGap]
    context_evidence: ContextEvidence


class PairComparison(Model):
    aop_ids: list[str]
    shared_key_events: list[EventRef]
    shared_ker_ids: list[str]
    shared_molecular_initiating_events: list[EventRef]
    shared_adverse_outcomes: list[EventRef]
    unique_key_event_ids: dict[str, list[str]]


class ComparisonResult(Model):
    status: Literal["input_required", "completed", "cancelled"]
    requested_context: dict[str, str | None]
    missing_inputs: list[str] = Field(default_factory=list)
    aops: list[AopComparisonRecord] = Field(default_factory=list)
    pairs: list[PairComparison] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def missing_context(params: CompareAopsInput) -> list[str]:
    return [field for field in ("species", "life_stage") if getattr(params, field) is None]


def context_question(params: CompareAopsInput) -> dict[str, Any]:
    descriptions = {
        "species": "Species: human, mouse, rat, dog, NCBITaxon CURIE, or unspecified.",
        "life_stage": "Life stage label or ontology CURIE, or unspecified. No default is assumed.",
    }
    missing = missing_context(params)
    return {"type": "object", "properties": {
        field: {"type": "string", "title": field.replace("_", " ").title(),
                "description": descriptions[field], "minLength": 1, "maxLength": 64}
        for field in missing}, "required": missing, "additionalProperties": False}


def initial_result(params: CompareAopsInput, status: str = "input_required") -> dict[str, Any]:
    return ComparisonResult(status=status, requested_context={
        field: getattr(params, field) for field in ("species", "life_stage", "sex")},
        missing_inputs=missing_context(params) if status == "input_required" else [],
        limitations=["Provide species and life_stage, or explicitly use unspecified; no human/adult default is assumed."]
        if status == "input_required" else []).model_dump()


def _url(identifier: str) -> str:
    prefix, value = identifier.split(":", 1)
    namespace = {"AOP": "aop", "KE": "aop.events", "KER": "aop.relationships"}[prefix]
    return f"https://identifiers.org/{namespace}/{value}"


def _refs(records: list[dict[str, Any]]) -> list[EventRef]:
    by_id = {item["id"]: EventRef(id=item["id"], title=item.get("title"), url=_url(item["id"]))
             for item in records if item.get("id")}
    return [by_id[key] for key in sorted(by_id)]


def _same_context(value: Any, requested: str | None, field: str) -> bool:
    if requested is None or requested.lower() == "unspecified" or not isinstance(value, str):
        return False
    aliases = {"female": "pato:0000383", "male": "pato:0000384"} if field == "sex" else {}
    # Human development terms are not inferred for other taxa.
    left, right = value.strip().lower(), requested.strip().lower()
    return aliases.get(left, left) == aliases.get(right, right)


async def _gather(*awaitables):
    tasks = [asyncio.create_task(item) for item in awaitables]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def compare_aops(params: CompareAopsInput) -> dict[str, Any]:
    if missing_context(params):
        return initial_result(params)
    adapter = get_aop_wiki_adapter()
    semaphore = asyncio.Semaphore(8)

    async def fetch(fn, identifier):
        async with semaphore:
            return await fn(identifier)

    async def summarize(identifier: str) -> AopComparisonRecord:
        aop, events, kers = await _gather(
            fetch(adapter.get_aop_assessment, identifier), fetch(adapter.list_key_events, identifier),
            fetch(adapter.list_kers, identifier))
        if not aop.get("title"):
            raise ComparisonError(f"No AOP-Wiki record returned for {identifier}; check the ID.")
        event_refs = _refs(events)
        ker_ids = sorted({item["id"] for item in kers if item.get("id")})
        details, relationships = await _gather(
            _gather(*(fetch(adapter.get_key_event, item.id) for item in event_refs)),
            _gather(*(fetch(adapter.get_ker, item) for item in ker_ids)))
        gaps = []
        for record, fields in [(item, ("measurement_methods", "taxonomic_applicability",
                                     "life_stage_applicability", "sex_applicability")) for item in details] + [
                (item, ("biological_plausibility", "empirical_support", "quantitative_understanding"))
                for item in relationships]:
            missing = [field for field in fields if not record.get(field) or
                       (isinstance(record[field], str) and not record[field].strip())]
            if missing:
                gaps.append(EvidenceGap(id=record["id"], url=_url(record["id"]), not_reported_fields=missing))
        counts = {"key_event_count": len(details),
                  "species_exact_match_count": sum(params.species in item.get("taxonomic_applicability", []) for item in details),
                  "species_unreported_count": sum(not item.get("taxonomic_applicability") for item in details)}
        for field in ("life_stage", "sex"):
            counts[field + "_exact_match_count"] = sum(_same_context(item.get(field + "_applicability"), getattr(params, field), field) for item in details)
            counts[field + "_unreported_count"] = sum(not item.get(field + "_applicability") for item in details)
        counts["reported_taxa"] = sorted({taxon for item in details for taxon in item.get("taxonomic_applicability", [])})
        counts["reported_life_stages"] = sorted({item["life_stage_applicability"] for item in details if item.get("life_stage_applicability")})
        counts["reported_sexes"] = sorted({item["sex_applicability"] for item in details if item.get("sex_applicability")})
        return AopComparisonRecord(id=identifier, title=aop["title"], url=_url(identifier),
            key_events=event_refs, ker_ids=ker_ids,
            molecular_initiating_events=_refs(aop.get("molecular_initiating_events", [])),
            adverse_outcomes=_refs(aop.get("adverse_outcomes", [])), evidence_gaps=gaps,
            context_evidence=ContextEvidence(**counts))

    from src.adapters.sparql_client import SparqlClientError
    try:
        async with asyncio.timeout(60):
            aops = await _gather(*(summarize(identifier) for identifier in params.aop_ids))
    except (TimeoutError, SparqlClientError) as error:
        raise ComparisonError("AOP-Wiki did not return a complete comparison; try again later. No partial comparison is reported.") from error
    pairs = []
    for left, right in combinations(aops, 2):
        def shared(field: str) -> list[EventRef]:
            right_ids = {item.id for item in getattr(right, field)}
            return [item for item in getattr(left, field) if item.id in right_ids]
        shared_ids = {item.id for item in shared("key_events")}
        pairs.append(PairComparison(aop_ids=[left.id, right.id], shared_key_events=shared("key_events"),
            shared_ker_ids=sorted(set(left.ker_ids) & set(right.ker_ids)),
            shared_molecular_initiating_events=shared("molecular_initiating_events"),
            shared_adverse_outcomes=shared("adverse_outcomes"), unique_key_event_ids={
                item.id: [event.id for event in item.key_events if event.id not in shared_ids] for item in (left, right)}))
    return ComparisonResult(status="completed", requested_context={
        field: getattr(params, field) for field in ("species", "life_stage", "sex")}, aops=aops, pairs=pairs,
        limitations=[
            "Shared KE/KER identifiers show recorded pathway overlap, not causal equivalence or chemical read-across validity.",
            "Not-reported fields describe the returned AOP-Wiki RDF; they do not prove evidence is absent from the literature.",
            "Context counts use exact recorded identifiers or labels; taxonomic ancestry and life-stage equivalence are not inferred.",
            "KE context annotations and their union do not establish whole-pathway applicability; expert review is required.",
            "This comparison does not rank confidence, establish dose-response relationships, or predict chemical toxicity.",
        ]).model_dump()
