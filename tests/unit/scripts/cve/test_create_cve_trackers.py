"""Unit tests for scripts/cve/create_cve_trackers.py — CVE extraction, description building."""

from __future__ import annotations

from scripts.cve.create_cve_trackers import (
    CVEInfo,
    build_description,
    build_tracker_labels,
    extract_cve_id,
    extract_description,
    extract_version,
    get_blocking_issues,
)

# ---------------------------------------------------------------------------
# extract_cve_id
# ---------------------------------------------------------------------------


class TestExtractCveId:
    def test_standard(self) -> None:
        assert extract_cve_id("CVE-2025-12345 glibc overflow") == "CVE-2025-12345"

    def test_none_when_absent(self) -> None:
        assert extract_cve_id("no cve here") is None


# ---------------------------------------------------------------------------
# extract_version
# ---------------------------------------------------------------------------


class TestExtractVersion:
    def test_extracts_rhoai_version(self) -> None:
        assert extract_version("CVE-2025-1234 something [rhoai-2.25]") == "rhoai-2.25"

    def test_extracts_three_digit(self) -> None:
        assert extract_version("vuln [rhoai-3.0]") == "rhoai-3.0"

    def test_none_when_absent(self) -> None:
        assert extract_version("CVE-2025-9999 no version") is None


# ---------------------------------------------------------------------------
# extract_description
# ---------------------------------------------------------------------------


class TestExtractDescription:
    def test_strips_cve_prefix(self) -> None:
        result = extract_description("CVE-2025-1234 buffer overflow in foo", "CVE-2025-1234")
        assert result == "buffer overflow in foo"

    def test_strips_embargoed(self) -> None:
        result = extract_description("CVE-2025-1234 EMBARGOED glibc bug", "CVE-2025-1234")
        assert result == "glibc bug"

    def test_strips_component_prefix(self) -> None:
        result = extract_description("CVE-2025-1234 rhoai/odh-notebook: vuln desc", "CVE-2025-1234")
        assert result == "vuln desc"

    def test_strips_version_suffix(self) -> None:
        result = extract_description("CVE-2025-1234 some vuln [rhoai-2.25]", "CVE-2025-1234")
        assert result == "some vuln"

    def test_combined(self) -> None:
        summary = "CVE-2025-9999 EMBARGOED rhoai/odh-nb: heap overflow [rhoai-3.0]"
        result = extract_description(summary, "CVE-2025-9999")
        assert result == "heap overflow"


# ---------------------------------------------------------------------------
# get_blocking_issues
# ---------------------------------------------------------------------------


class TestGetBlockingIssues:
    def test_inward_blocks(self) -> None:
        issue = {
            "fields": {
                "issuelinks": [
                    {
                        "type": {"name": "Blocks"},
                        "inwardIssue": {"key": "RHAIENG-100"},
                    }
                ]
            }
        }
        assert get_blocking_issues(issue) == ["RHAIENG-100"]

    def test_outward_ignored(self) -> None:
        issue = {
            "fields": {
                "issuelinks": [
                    {
                        "type": {"name": "Blocks"},
                        "outwardIssue": {"key": "RHOAIENG-200"},
                    }
                ]
            }
        }
        assert get_blocking_issues(issue) == []

    def test_no_links(self) -> None:
        assert get_blocking_issues({"fields": {}}) == []


# ---------------------------------------------------------------------------
# CVEInfo properties
# ---------------------------------------------------------------------------


class TestCVEInfo:
    def test_version_suffix(self) -> None:
        info = CVEInfo(cve_id="CVE-2025-1", version="rhoai-2.25")
        assert info.version_suffix == "[rhoai-2.25]"

    def test_version_suffix_empty(self) -> None:
        info = CVEInfo(cve_id="CVE-2025-1")
        assert info.version_suffix == ""

    def test_issue_count(self) -> None:
        info = CVEInfo(cve_id="CVE-2025-1", issues=[{"key": "A-1"}, {"key": "A-2"}])
        assert info.issue_count == 2


# ---------------------------------------------------------------------------
# build_tracker_labels
# ---------------------------------------------------------------------------


class TestBuildTrackerLabels:
    def test_labels(self) -> None:
        labels = build_tracker_labels("CVE-2025-9999")
        assert labels == ["CVE", "CVE-2025-9999", "security"]

    def test_cve_literal_first(self) -> None:
        assert build_tracker_labels("CVE-2024-1")[0] == "CVE"


# ---------------------------------------------------------------------------
# build_description (ADF output)
# ---------------------------------------------------------------------------


class TestBuildDescription:
    def test_returns_adf_document(self) -> None:
        info = CVEInfo(
            cve_id="CVE-2025-1234",
            description="buffer overflow in libfoo",
            issues=[{"key": "RHOAIENG-100"}, {"key": "RHOAIENG-200"}],
        )
        doc = build_description(info)
        assert doc["type"] == "doc"
        assert doc["version"] == 1
        assert len(doc["content"]) >= 1

    def test_includes_child_keys(self) -> None:
        info = CVEInfo(
            cve_id="CVE-2025-5678",
            description="test",
            issues=[{"key": "RHOAIENG-50"}],
        )
        doc = build_description(info)
        text_content = _flatten_adf_text(doc)
        assert "RHOAIENG-50" in text_content

    def test_no_children(self) -> None:
        info = CVEInfo(cve_id="CVE-2025-0001", description="test", issues=[])
        doc = build_description(info)
        assert doc["type"] == "doc"

    def test_with_tracker_key_adds_dynamic_jql(self) -> None:
        info = CVEInfo(
            cve_id="CVE-2025-9999",
            description="test",
            issues=[{"key": "RHOAIENG-1"}],
        )
        doc = build_description(info, tracker_key="RHAIENG-500")
        text_content = _flatten_adf_text(doc)
        assert "linkedIssues" in text_content


class TestFlattenAdfText:
    def test_handles_non_dict_content_nodes(self) -> None:
        doc = {"type": "doc", "content": [42, None, "stray-string", {"type": "text", "text": "ok"}]}
        assert "ok" in _flatten_adf_text(doc)

    def test_handles_missing_content(self) -> None:
        doc = {"type": "doc"}
        assert _flatten_adf_text(doc) == ""


def _flatten_adf_text(doc: dict) -> str:
    """Recursively extract all text from an ADF document."""
    parts: list[str] = []

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            for v in node.values():
                if isinstance(v, dict | list):
                    _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(doc)
    return " ".join(parts)
