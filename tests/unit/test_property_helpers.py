"""Hypothesis property tests for small pure helpers.

These run under the normal ``make test`` / ``make test-unit`` pytest jobs
(same ``pytest-tests`` CI job). There is no separate Hypothesis workflow:
default ``max_examples`` is enough for PR CI.

``capped_patch_excerpt`` lives in the ``odh-ci-agent`` workspace package, which
``uv sync --locked`` (used by ``make test`` / CI) does not install. Load that
stdlib-only module from source so these properties stay in the default suite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.ci.sanitize_gitleaks_sarif import sanitize_sarif

_PATCH_EXCERPT_PATH = Path(__file__).resolve().parents[2] / "ci/agentic-reviewer/src/odh_ci_agent/patch_excerpt.py"
_spec = importlib.util.spec_from_file_location("odh_ci_agent_patch_excerpt", _PATCH_EXCERPT_PATH)
assert _spec is not None and _spec.loader is not None
patch_excerpt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(patch_excerpt)

# Keep CI deterministic and fast; Hypothesis shrinks failures either way.
_settings = settings(max_examples=100, deadline=None)


@st.composite
def patches(draw: st.DrawFn) -> str | None:
    """Generate ``None``, empty, short, or multi-line patch text."""
    kind = draw(st.sampled_from(["none", "empty", "text"]))
    if kind == "none":
        return None
    if kind == "empty":
        return ""
    # Allow \\r inside lines (content); records are joined with \\n only.
    line = st.text(alphabet=st.characters(blacklist_characters="\n"), max_size=40)
    lines = draw(st.lists(line, max_size=80))
    body = "\n".join(lines)
    if draw(st.booleans()) and body:
        body += "\n"
    return body


@_settings
@given(patch=patches(), max_lines=st.integers(min_value=-5, max_value=60))
def test_capped_patch_excerpt_properties(patch: str | None, max_lines: int) -> None:
    # max_lines is a caller precondition; validate before empty-patch handling.
    if max_lines < 1:
        try:
            patch_excerpt.capped_patch_excerpt(patch, max_lines=max_lines)
        except ValueError as exc:
            assert "max_lines" in str(exc)
        else:
            raise AssertionError("expected ValueError for max_lines < 1")
        return

    result = patch_excerpt.capped_patch_excerpt(patch, max_lines=max_lines)

    if not patch:
        assert result is None
        return

    assert result is not None
    input_lines = patch_excerpt._patch_lines(patch)
    output_lines = patch_excerpt._patch_lines(result)
    assert len(output_lines) <= max_lines

    if len(input_lines) <= max_lines:
        assert result == patch
        return

    if max_lines == 1:
        assert result == input_lines[0]
        return

    # Truncation uses "\\n".join; a trailing empty line is not always
    # round-trippable. The contract is a line budget, not blank-line preservation.
    # Locate the ellipsis by its deterministic position (matches head_count in
    # capped_patch_excerpt), not by content: a generated line can equal "...".
    ellipsis_at = (max_lines - 1) // 2
    assert output_lines[ellipsis_at] == "..."
    head = output_lines[:ellipsis_at]
    tail = output_lines[ellipsis_at + 1 :]
    assert head == input_lines[: len(head)]
    if tail:
        assert tail == input_lines[-len(tail) :]


@st.composite
def sarif_documents(draw: st.DrawFn) -> dict[str, Any]:
    """Generate shallow SARIF-like docs with optional invalid endColumn values."""
    column = st.one_of(st.none(), st.integers(min_value=-3, max_value=40))
    region = st.fixed_dictionaries(
        {
            "startLine": st.integers(min_value=1, max_value=500),
            "endLine": st.integers(min_value=1, max_value=500),
        },
        optional={
            "startColumn": column,
            "endColumn": column,
        },
    )
    location = st.fixed_dictionaries(
        {},
        optional={
            "physicalLocation": st.fixed_dictionaries(
                {},
                optional={"region": st.one_of(st.none(), region)},
            ),
        },
    )
    result = st.fixed_dictionaries(
        {},
        optional={"locations": st.lists(location, max_size=4)},
    )
    run = st.fixed_dictionaries(
        {},
        optional={"results": st.lists(result, max_size=4)},
    )
    return draw(
        st.fixed_dictionaries(
            {},
            optional={"runs": st.lists(run, max_size=3)},
        )
    )


def _iter_regions(data: dict[str, Any]):
    for run in data.get("runs", []) or []:
        for result in run.get("results", []) or []:
            for location in result.get("locations", []) or []:
                region = (location.get("physicalLocation") or {}).get("region")
                if region is not None:
                    yield region


@_settings
@given(data=sarif_documents())
def test_sanitize_sarif_properties(data: dict[str, Any]) -> None:
    before_invalid = 0
    for region in _iter_regions(data):
        end_col = region.get("endColumn")
        if end_col is None or end_col < 1:
            before_invalid += 1

    sanitized, fixed = sanitize_sarif(data)
    assert sanitized is data
    assert fixed == before_invalid

    for region in _iter_regions(sanitized):
        end_col = region.get("endColumn")
        # Regions that already had a valid endColumn keep it; previously
        # invalid/missing ones are clamped to >= 1.
        if end_col is not None:
            assert end_col >= 1

    # Idempotent: a second pass must not claim further fixes.
    _, fixed_again = sanitize_sarif(sanitized)
    assert fixed_again == 0
