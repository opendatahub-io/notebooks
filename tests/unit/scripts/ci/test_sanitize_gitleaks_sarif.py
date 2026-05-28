"""Tests for scripts/ci/sanitize_gitleaks_sarif.py."""

from __future__ import annotations

import pytest

from scripts.ci.sanitize_gitleaks_sarif import sanitize_sarif


@pytest.mark.parametrize("end_column", [0, None])
def test_sanitize_sarif_fixes_invalid_end_column(end_column: int | None) -> None:
    data = _sarif_data_with_region(
        region={
            "startLine": 1,
            "startColumn": 1,
            "endLine": 1,
            "endColumn": end_column,
        }
    )
    _, fixed = sanitize_sarif(data)
    region = _get_region(sarif_data=data)
    assert fixed == 1
    assert region["endColumn"] == 1


def test_sanitize_sarif_sets_missing_end_column_from_start_column() -> None:
    data = _sarif_data_with_region(
        region={
            "startLine": 3,
            "startColumn": 7,
            "endLine": 3,
        }
    )
    _, fixed = sanitize_sarif(data)
    region = _get_region(sarif_data=data)
    assert fixed == 1
    assert region["endColumn"] == 7


@pytest.mark.parametrize(
    ("region", "expected_end_column"),
    [
        ({"startLine": 1, "endLine": 1, "endColumn": 0}, 1),
        ({"startLine": 1, "startColumn": 0, "endLine": 1, "endColumn": 0}, 1),
    ],
    ids=["missing_start_column", "zero_start_column"],
)
def test_sanitize_sarif_defaults_end_column_when_start_column_unusable(
    region: dict,
    expected_end_column: int,
) -> None:
    data = _sarif_data_with_region(region=region)
    _, fixed = sanitize_sarif(data)
    assert fixed == 1
    assert _get_region(sarif_data=data)["endColumn"] == expected_end_column


def test_sanitize_sarif_leaves_valid_regions() -> None:
    data = _sarif_data_with_region(
        region={
            "startLine": 10,
            "startColumn": 5,
            "endLine": 10,
            "endColumn": 20,
        }
    )
    _, fixed = sanitize_sarif(data)
    assert fixed == 0


def _sarif_data_with_region(region: dict) -> dict:
    return {"runs": [{"results": [{"locations": [{"physicalLocation": {"region": region}}]}]}]}


def _get_region(sarif_data: dict) -> dict:
    return sarif_data["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
