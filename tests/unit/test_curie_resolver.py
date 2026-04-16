from __future__ import annotations

import pytest

from src.semantic import AOP_CURIE_RESOLVER, CurieResolver
from src.semantic.migration import OntologyMigrator, UnsupportedMigration


def test_aop_curie_resolver_identifiers_org() -> None:
    assert AOP_CURIE_RESOLVER.resolve("https://identifiers.org/aop/1") == "AOP:1"
    assert AOP_CURIE_RESOLVER.resolve("https://identifiers.org/aop.events/2") == "KE:2"
    assert AOP_CURIE_RESOLVER.resolve("https://identifiers.org/aop.relationships/3") == "KER:3"


def test_aop_curie_resolver_aopwiki_org() -> None:
    assert AOP_CURIE_RESOLVER.resolve("http://aopwiki.org/aops/1") == "AOP:1"
    assert AOP_CURIE_RESOLVER.resolve("http://aopwiki.org/events/2") == "KE:2"
    assert AOP_CURIE_RESOLVER.resolve("http://aopwiki.org/relationships/3") == "KER:3"


def test_aop_curie_resolver_fallback() -> None:
    unknown = "http://example.org/unknown/1"
    assert AOP_CURIE_RESOLVER.resolve(unknown) == unknown


def test_curie_resolver_precedence() -> None:
    resolver = CurieResolver([
        ("https://alpha.example/", "ALPHA"),
        ("https://beta.example/", "BETA"),
    ])
    assert resolver.resolve("https://alpha.example/item") == "ALPHA:item"
    assert resolver.resolve("https://beta.example/item") == "BETA:item"


def test_ontology_migrator_noop_same_version() -> None:
    migrator = OntologyMigrator()
    assert migrator.migrate({"a": 1}, "v1", "v1") == {"a": 1}


def test_ontology_migrator_single_step() -> None:
    migrator = OntologyMigrator()
    migrator.register_migration("v1", "v2", lambda d: {**d, "version": "v2"})
    result = migrator.migrate({"name": "test"}, "v1", "v2")
    assert result == {"name": "test", "version": "v2"}


def test_ontology_migrator_multi_step() -> None:
    migrator = OntologyMigrator()
    migrator.register_migration("v1", "v2", lambda d: {**d, "step": 1})
    migrator.register_migration("v2", "v3", lambda d: {**d, "step": 2})
    result = migrator.migrate({"name": "test"}, "v1", "v3")
    assert result == {"name": "test", "step": 2}


def test_ontology_migrator_term_mapping() -> None:
    migrator = OntologyMigrator()
    migrator.register_migration("v1", "v2", lambda d: d)
    migrator.register_term_mapping("v2", {"old_term": "new_term"})
    result = migrator.migrate({"old_term": "value"}, "v1", "v2")
    assert result == {"new_term": "value"}


def test_ontology_migrator_unsupported_migration() -> None:
    migrator = OntologyMigrator()
    with pytest.raises(UnsupportedMigration):
        migrator.migrate({}, "v1", "v2")
