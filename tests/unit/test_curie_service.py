from __future__ import annotations

import pytest

from src.semantic import CurieService


def test_normalize_curie_accepts_existing_prefix() -> None:
    service = CurieService({"NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_"})
    assert service.normalize("NCBITaxon:9606") == "NCBITaxon:9606"


def test_normalize_curie_converts_iri() -> None:
    service = CurieService({"NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_"})
    assert service.normalize("http://purl.obolibrary.org/obo/NCBITaxon_9606") == "NCBITaxon:9606"


def test_normalize_curie_rejects_unknown_prefix() -> None:
    service = CurieService({"NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_"})
    with pytest.raises(ValueError):
        service.normalize("http://example.com/unknown/123")


def test_mint_curie_generates_uuid() -> None:
    service = CurieService({"NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_"})
    minted = service.mint()
    assert minted.startswith("TMP:")
