"""Registry of MCP tools exposed by the server."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict

from pydantic import BaseModel

from src.server.mcp.protocol import ToolDescription
from src.tools import load_schema


class RegisteredTool:
    def __init__(
        self,
        *,
        name: str,
        description: str,
        handler: Callable[[BaseModel], Any],
        input_model: type[BaseModel],
        output_schema: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.handler = handler
        self.input_model = input_model
        self.output_schema = output_schema or {"type": "object"}
        # Ensure input_schema is always a dictionary, even if the model has no fields
        self.input_schema = input_model.model_json_schema() or {}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, RegisteredTool] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        handler: Callable[[BaseModel], Any],
        input_model: type[BaseModel],
        output_schema: dict[str, Any] | None = None,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            handler=handler,
            input_model=input_model,
            output_schema=output_schema,
        )

    def list_tools(self) -> list[ToolDescription]:
        return [
            ToolDescription(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
            )
            for tool in self._tools.values()
        ]

    async def call_tool(self, name: str, params: dict[str, Any] | None) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        tool = self._tools[name]
        model_input = tool.input_model.model_validate(params or {})
        result = tool.handler(model_input)
        if asyncio.iscoroutine(result):
            result = await result
        return result


tool_registry = ToolRegistry()


def _schema(namespace: str, name: str) -> dict[str, Any]:
    return load_schema(namespace, name)

# Register AOP tools
from src.server.tools import aop  # noqa: E402  pylint: disable=wrong-import-position


tool_registry.register(
    name="search_aops",
    description="Search Adverse Outcome Pathways by text query.",
    handler=aop.search_aops,
    input_model=aop.SearchAopsInput,
    output_schema=_schema("read", "search_aops.response.schema"),
)
tool_registry.register(
    name="get_aop",
    description="Fetch a single AOP with metadata.",
    handler=aop.get_aop,
    input_model=aop.GetAopInput,
    output_schema=_schema("read", "get_aop.response.schema"),
)
tool_registry.register(
    name="get_key_event",
    description="Fetch a single key event with OECD-style metadata fields.",
    handler=aop.get_key_event,
    input_model=aop.GetKeyEventInput,
    output_schema=_schema("read", "get_key_event.response.schema"),
)

tool_registry.register(
    name="list_key_events",
    description="List key events for an AOP.",
    handler=aop.list_key_events,
    input_model=aop.ListKeyEventsInput,
    output_schema=_schema("read", "list_key_events.response.schema"),
)

tool_registry.register(
    name="list_kers",
    description="List key event relationships for an AOP.",
    handler=aop.list_kers,
    input_model=aop.ListKersInput,
    output_schema=_schema("read", "list_kers.response.schema"),
)
tool_registry.register(
    name="get_ker",
    description="Fetch a single key event relationship with plausibility, evidence, and quantitative-support text.",
    handler=aop.get_ker,
    input_model=aop.GetKerInput,
    output_schema=_schema("read", "get_ker.response.schema"),
)
tool_registry.register(
    name="get_related_aops",
    description="Find AOPs related to a source AOP through shared key events or KERs.",
    handler=aop.get_related_aops,
    input_model=aop.GetRelatedAopsInput,
    output_schema=_schema("read", "get_related_aops.response.schema"),
)
tool_registry.register(
    name="assess_aop_confidence",
    description="Build an OECD-style heuristic confidence summary for an AOP from AOP-, KE-, and KER-level evidence text.",
    handler=aop.assess_aop_confidence,
    input_model=aop.AssessAopConfidenceInput,
    output_schema=_schema("read", "assess_aop_confidence.response.schema"),
)
tool_registry.register(
    name="find_paths_between_events",
    description="Find directed KE/KER paths between two events within a selected AOP.",
    handler=aop.find_paths_between_events,
    input_model=aop.FindPathsBetweenEventsInput,
    output_schema=_schema("read", "find_paths_between_events.response.schema"),
)

tool_registry.register(
    name="map_chemical_to_aops",
    description="Map a chemical to related AOPs using AOP-DB and CompTox.",
    handler=aop.map_chemical_to_aops,
    input_model=aop.MapChemicalInput,
    output_schema=_schema("read", "map_chemical_to_aops.response.schema"),
)

tool_registry.register(
    name="map_assay_to_aops",
    description="Given an assay identifier, return related AOPs. Do not pass AOP IDs.",
    handler=aop.map_assay_to_aops,
    input_model=aop.MapAssayInput,
    output_schema=_schema("read", "map_assay_to_aops.response.schema"),
)

tool_registry.register(
    name="search_assays_for_key_event",
    description="Given a key event, return candidate assays using KE-derived gene and phrase terms. This is a discovery helper, not a curated KE-to-assay mapping.",
    handler=aop.search_assays_for_key_event,
    input_model=aop.SearchAssaysForKeyEventInput,
    output_schema=_schema("read", "search_assays_for_key_event.response.schema"),
)

tool_registry.register(
    name="list_assays_for_aop",
    description="List assay candidates for one AOP using linked stressor chemicals and CompTox bioactivity, with diagnostics explaining empty results.",
    handler=aop.list_assays_for_aop,
    input_model=aop.ListAssaysForAopInput,
    output_schema=_schema("read", "list_assays_for_aop.response.schema"),
)

tool_registry.register(
    name="get_assays_for_aop",
    description="Given one AOP identifier, return assay candidates. Use this when you have an AOP ID and want assays.",
    handler=aop.get_assays_for_aop,
    input_model=aop.GetAssaysForAopInput,
    output_schema=_schema("read", "list_assays_for_aop.response.schema"),
)

tool_registry.register(
    name="list_assays_for_aops",
    description="Aggregate and deduplicate assay candidates across multiple AOPs, with per-AOP diagnostics for empty results.",
    handler=aop.list_assays_for_aops,
    input_model=aop.ListAssaysForAopsInput,
    output_schema=_schema("read", "list_assays_for_aops.response.schema"),
)

tool_registry.register(
    name="get_assays_for_aops",
    description="Given multiple AOP identifiers, return aggregated assay candidates. Use this when you have a list of AOP IDs.",
    handler=aop.get_assays_for_aops,
    input_model=aop.GetAssaysForAopsInput,
    output_schema=_schema("read", "list_assays_for_aops.response.schema"),
)

tool_registry.register(
    name="list_assays_for_query",
    description="Given a phenotype or mechanism query, search AOPs and return aggregated assay candidates with query and per-AOP diagnostics.",
    handler=aop.list_assays_for_query,
    input_model=aop.ListAssaysForQueryInput,
    output_schema=_schema("read", "list_assays_for_query.response.schema"),
)

tool_registry.register(
    name="export_assays_table",
    description="Export aggregated assay candidates as CSV or TSV from a query or explicit AOP list.",
    handler=aop.export_assays_table,
    input_model=aop.ExportAssaysTableInput,
    output_schema=_schema("read", "export_assays_table.response.schema"),
)

tool_registry.register(
    name="get_applicability",
    description="Normalize applicability parameters (species, sex, life stage).",
    handler=aop.get_applicability,
    input_model=aop.GetApplicabilityInput,
    output_schema=_schema("semantic", "get_applicability.response.schema"),
)

tool_registry.register(
    name="get_evidence_matrix",
    description="Build an evidence matrix from KER facets.",
    handler=aop.get_evidence_matrix,
    input_model=aop.EvidenceMatrixInput,
    output_schema=_schema("semantic", "get_evidence_matrix.response.schema"),
)

tool_registry.register(
    name="create_draft_aop",
    description="Create a new draft AOP for write-path workflows.",
    handler=aop.create_draft_aop,
    input_model=aop.CreateDraftInputModel,
    output_schema=_schema("write", "create_draft_aop.response.schema"),
)

tool_registry.register(
    name="add_or_update_ke",
    description="Add or update a key event within a draft.",
    handler=aop.add_or_update_ke,
    input_model=aop.KeyEventInputModel,
    output_schema=_schema("write", "update_draft.response.schema"),
)

tool_registry.register(
    name="add_or_update_ker",
    description="Add or update a key event relationship within a draft.",
    handler=aop.add_or_update_ker,
    input_model=aop.KerInputModel,
    output_schema=_schema("write", "update_draft.response.schema"),
)

tool_registry.register(
    name="link_stressor",
    description="Link a stressor to a draft entity.",
    handler=aop.link_stressor,
    input_model=aop.StressorLinkInputModel,
    output_schema=_schema("write", "update_draft.response.schema"),
)
tool_registry.register(
    name="validate_draft_oecd",
    description="Validate a draft against OECD AOP handbook-style completeness expectations.",
    handler=aop.validate_draft_oecd,
    input_model=aop.ValidateDraftOecdInput,
    output_schema=_schema("write", "validate_draft_oecd.response.schema"),
)
