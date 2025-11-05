"""Semantic utilities exposed for the Taskmaster MCP."""

from .curie_service import CurieService  # noqa: F401
from .applicability import ApplicabilityNormalizer, ApplicabilityInput, ApplicabilityResult  # noqa: F401
from .evidence_matrix import build_matrix, EvidenceFacet  # noqa: F401

__all__ = [
    "CurieService",
    "ApplicabilityNormalizer",
    "ApplicabilityInput",
    "ApplicabilityResult",
    "build_matrix",
    "EvidenceFacet",
]
