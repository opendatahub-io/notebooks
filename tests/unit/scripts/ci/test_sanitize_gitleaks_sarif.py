"""Tests for scripts/ci/sanitize_gitleaks_sarif.py."""

from __future__ import annotations

from scripts.ci.sanitize_gitleaks_sarif import sanitize_sarif


def test_sanitize_sarif_fixes_invalid_end_column() -> None:
    data = {
        "runs": [
            {
                "results": [
                    {
                        "locations": [
                            {
                                "physicalLocation": {
                                    "region": {
                                        "startLine": 1,
                                        "startColumn": 1,
                                        "endLine": 1,
                                        "endColumn": 0,
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }
    _, fixed = sanitize_sarif(data)
    region = data["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert fixed == 1
    assert region["endColumn"] == 1


def test_sanitize_sarif_leaves_valid_regions() -> None:
    data = {
        "runs": [
            {
                "results": [
                    {
                        "locations": [
                            {
                                "physicalLocation": {
                                    "region": {
                                        "startLine": 10,
                                        "startColumn": 5,
                                        "endLine": 10,
                                        "endColumn": 20,
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }
    _, fixed = sanitize_sarif(data)
    assert fixed == 0
