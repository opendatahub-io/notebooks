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
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from hypothesis import given, settings
from hypothesis import strategies as st

from manifests.tools.package_names import (
    MANIFEST_LOWER_NAMES,
    MANIFEST_TO_PIP,
    all_workbench_pip_names,
    manifest_name_to_pip,
)
from scripts import index_url_resolver
from scripts.ci.sanitize_gitleaks_sarif import sanitize_sarif

_PATCH_EXCERPT_PATH = Path(__file__).resolve().parents[2] / "ci/agentic-reviewer/src/odh_ci_agent/patch_excerpt.py"
_spec = importlib.util.spec_from_file_location("odh_ci_agent_patch_excerpt", _PATCH_EXCERPT_PATH)
assert _spec is not None and _spec.loader is not None
patch_excerpt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(patch_excerpt)

# gen_gha_matrix_jobs.py uses bare imports (e.g. `import gha_pr_changed_files`), same as
# ci/conftest.py works around for its own test collection: put its directory on sys.path.
_CACHED_BUILDS_DIR = Path(__file__).resolve().parents[2] / "ci/cached-builds"
if str(_CACHED_BUILDS_DIR) not in sys.path:
    sys.path.insert(0, str(_CACHED_BUILDS_DIR))
import gen_gha_matrix_jobs  # noqa: E402  # pyright: ignore[reportMissingImports]

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
    usable = max_lines - 1
    head_count = usable // 2
    tail_count = usable - head_count
    ellipsis_at = head_count
    assert output_lines[ellipsis_at] == "..."
    head = output_lines[:ellipsis_at]
    tail = output_lines[ellipsis_at + 1 :]
    assert head == input_lines[:head_count]
    expected_tail = patch_excerpt._patch_lines("\n".join(input_lines[-tail_count:]))
    assert tail == expected_tail


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
    # Snapshot before sanitize_sarif mutates regions in place.
    regions = list(_iter_regions(data))
    before = [(region.get("startColumn"), region.get("endColumn")) for region in regions]

    sanitized, fixed = sanitize_sarif(data)
    assert sanitized is data

    expected_fixed = 0
    for region, (start_col, end_col) in zip(regions, before, strict=True):
        if end_col is None or end_col < 1:
            expected_fixed += 1
            # Mirrors sanitize_sarif: max(startColumn or 1, 1).
            assert region["endColumn"] == max(start_col or 1, 1)
        else:
            assert region.get("endColumn") == end_col
    assert fixed == expected_fixed

    # Idempotent: a second pass must not claim further fixes.
    _, fixed_again = sanitize_sarif(sanitized)
    assert fixed_again == 0


@st.composite
def rhoai_accelerators(draw: st.DrawFn) -> str:
    """Generate accelerator tokens shaped like parse_accelerator's output (e.g. cuda12.9)."""
    kind = draw(st.sampled_from(["cpu", "cuda", "rocm"]))
    if kind == "cpu":
        return "cpu"
    major = draw(st.integers(min_value=0, max_value=99))
    minor = draw(st.integers(min_value=0, max_value=99))
    return f"{kind}{major}.{minor}"


@st.composite
def rhoai_releases(draw: st.DrawFn) -> str:
    """Generate release strings shaped like _format_release's output (e.g. 3.5-EA2)."""
    major = draw(st.integers(min_value=0, max_value=99))
    minor = draw(st.integers(min_value=0, max_value=99))
    base = f"{major}.{minor}"
    ea = draw(st.none() | st.integers(min_value=0, max_value=99))
    return base if ea is None else f"{base}-EA{ea}"


@_settings
@given(release=rhoai_releases(), accelerator=rhoai_accelerators())
def test_rhoai_index_url_round_trip(release: str, accelerator: str) -> None:
    prod_url = index_url_resolver.build_rhoai_index_url(release=release, accelerator=accelerator)
    test_url = index_url_resolver.build_rhoai_test_index_url(release=release, accelerator=accelerator)

    assert index_url_resolver.parse_release_and_accelerator_from_url(prod_url) == (release, accelerator)
    assert index_url_resolver.parse_release_and_accelerator_from_url(test_url) == (release, accelerator)

    # build_test_variant_url must agree with the dedicated test-URL builder.
    assert index_url_resolver.build_test_variant_url(prod_url) == test_url
    # A URL that's already a -test variant has no further variant to derive.
    assert index_url_resolver.build_test_variant_url(test_url) is None


@_settings
@given(release=rhoai_releases())
def test_stable_rhoai_release_is_ea_free_prefix(release: str) -> None:
    stable = index_url_resolver.stable_rhoai_release(release)
    assert release.startswith(stable)
    assert "-EA" not in stable


@st.composite
def rhoai_urls_with_query(draw: st.DrawFn) -> str:
    """Generate a RHOAI index URL with an arbitrary, possibly format-bearing, query string."""
    release = draw(rhoai_releases())
    accelerator = draw(rhoai_accelerators())
    base = index_url_resolver.build_rhoai_index_url(release=release, accelerator=accelerator)
    key_alphabet = st.characters(blacklist_characters="&=# \n", min_codepoint=33, max_codepoint=126)
    extra_params = draw(
        st.dictionaries(
            st.text(alphabet=key_alphabet, min_size=1, max_size=8),
            st.text(alphabet=key_alphabet, max_size=8),
            max_size=3,
        )
    )
    if not extra_params:
        return base
    return f"{base}?{urlencode(extra_params)}"


@_settings
@given(url=rhoai_urls_with_query())
def test_ensure_json_format_param_idempotent(url: str) -> None:
    once = index_url_resolver.ensure_json_format_param(url)
    twice = index_url_resolver.ensure_json_format_param(once)
    assert twice == once
    assert parse_qs(urlparse(once).query).get("format") == ["json"]


@_settings
@given(targets=st.lists(st.text(min_size=1, max_size=30), max_size=15))
def test_filter_rhel_targets_partitions_input(targets: list[str]) -> None:
    excluded = gen_gha_matrix_jobs.filter_rhel_targets(targets, gen_gha_matrix_jobs.RhelImages.EXCLUDE)
    included_only = gen_gha_matrix_jobs.filter_rhel_targets(targets, gen_gha_matrix_jobs.RhelImages.INCLUDE_ONLY)

    # Each branch matches target_needs_subscription element-wise, in original order.
    assert excluded == [t for t in targets if not gen_gha_matrix_jobs.target_needs_subscription(t)]
    assert included_only == [t for t in targets if gen_gha_matrix_jobs.target_needs_subscription(t)]

    # EXCLUDE and INCLUDE_ONLY partition targets: every element goes to exactly one side.
    assert len(excluded) + len(included_only) == len(targets)
    assert gen_gha_matrix_jobs.filter_rhel_targets(targets, gen_gha_matrix_jobs.RhelImages.INCLUDE) == targets


@_settings
@given(name=st.text(max_size=30))
def test_manifest_name_to_pip_is_total(name: str) -> None:
    # Must never raise, regardless of input.
    manifest_name_to_pip(name)


@_settings
@given(name=st.sampled_from(sorted(set(MANIFEST_TO_PIP) | MANIFEST_LOWER_NAMES)))
def test_manifest_name_to_pip_matches_known_names(name: str) -> None:
    pip_name = manifest_name_to_pip(name)
    assert pip_name.lower() in all_workbench_pip_names()
