from __future__ import annotations

import re
import xml.etree.ElementTree as ET
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
    assert "docs/evaluations/trust-scenarios.xml" in text
    assert text.count("Expected answer:") == 4
    for term in [
        "verify_tool_call_audit_log",
        "export_tool_call_audit_log_evidence",
        "export_draft_replay_package",
        "docs/trust-auditability.md",
    ]:
        assert term in text


def test_trust_evaluation_xml_pack_is_machine_readable_and_read_only() -> None:
    tree = ET.parse(ROOT / "docs" / "evaluations" / "trust-scenarios.xml")
    root = tree.getroot()
    pairs = root.findall("qa_pair")

    assert root.tag == "evaluation"
    assert len(pairs) == 10
    assert len({pair.attrib["id"] for pair in pairs}) == len(pairs)

    combined_text = " ".join(
        (pair.findtext("question", "") + " " + pair.findtext("answer", ""))
        for pair in pairs
    )
    for term in [
        "auditability",
        "verifiability",
        "scientific review",
        "regulatory acceptance",
        "review_registry_handoff_bundle",
        "export_draft_replay_package",
        "verify_tool_call_audit_log",
        "export_tool_call_audit_log_evidence",
    ]:
        assert term in combined_text

    for pair in pairs:
        assert pair.attrib["id"]
        assert pair.findtext("question", "").strip().endswith("?")
        assert pair.findtext("answer", "").strip()

    for write_tool in [
        "create_draft_aop",
        "add_or_update_ke",
        "add_or_update_ker",
        "link_stressor",
        "attach_registry_handoff_to_draft",
        "save_draft_review_artifact",
    ]:
        assert write_tool not in combined_text

    hex_phrase = "64-character lowercase hexadecimal"
    assert hex_phrase in combined_text
    assert re.search(r"\btargetConsumer\b", combined_text)


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

    assert "docs/evaluations/trust-scenarios.xml" in readme
