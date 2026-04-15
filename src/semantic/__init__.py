"""Semantic utilities exposed for the AOP MCP server."""

from .curie_service import CurieService, CurieResolver, AOP_CURIE_RESOLVER  # noqa: F401
from .applicability import ApplicabilityNormalizer, ApplicabilityInput, ApplicabilityResult  # noqa: F401
from .evidence_matrix import build_matrix, EvidenceFacet  # noqa: F401

__all__ = [
    "CurieService",
    "CurieResolver",
    "AOP_CURIE_RESOLVER",
    "ApplicabilityNormalizer",
    "ApplicabilityInput",
    "ApplicabilityResult",
    "build_matrix",
    "EvidenceFacet",
]
