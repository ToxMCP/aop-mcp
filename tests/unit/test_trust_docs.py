from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_trust_auditability_doc_covers_current_trust_surface() -> None:
    text = (ROOT / "docs" / "trust-auditability.md").read_text(encoding="utf-8")

    for term in [
        "verify_tool_call_audit_log",
        "list_tool_call_audit_records",
        "export_tool_call_audit_log_evidence",
        "export_draft_replay_package",
        "runtime_manifest",
        "AOP_MCP_AUDIT_LOG_PATH",
        "not a claim of regulatory validation",
        "Process-local audit records are bounded",
    ]:
        assert term in text


def test_trust_evaluation_scenarios_are_stable_and_read_only() -> None:
    text = (ROOT / "docs" / "evaluations" / "trust-scenarios.md").read_text(
        encoding="utf-8"
    )

    assert "read-only scenarios" in text
    assert text.count("Expected answer:") == 4
    for term in [
        "verify_tool_call_audit_log",
        "export_tool_call_audit_log_evidence",
        "export_draft_replay_package",
        "docs/trust-auditability.md",
    ]:
        assert term in text


def test_public_docs_surface_trust_tools() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    catalog = (ROOT / "docs" / "contracts" / "tool-catalog.md").read_text(
        encoding="utf-8"
    )

    for text in [readme, catalog]:
        for term in [
            "export_draft_replay_package",
            "list_tool_call_audit_records",
            "verify_tool_call_audit_log",
            "export_tool_call_audit_log_evidence",
            "AOP_MCP_AUDIT_LOG_PATH",
            "docs/trust-auditability.md",
        ]:
            assert term in text
