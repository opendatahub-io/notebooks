from __future__ import annotations

from typing import TYPE_CHECKING

import scripts.cve.sbom_analyze as sa

if TYPE_CHECKING:
    from pytest import Subtests


# ── Fixtures: minimal SBOM documents in each supported format ─────────


def _syft_sbom(artifacts: list[dict] | None = None) -> dict:
    return {
        "artifacts": artifacts or [],
        "source": {"name": "test-image", "version": "1.0", "type": "image"},
        "distro": {"name": "rhel", "version": "9.4"},
        "descriptor": {"version": "0.99.0"},
        "schema": {"version": "16.0.0"},
        "files": [],
    }


def _spdx_sbom(packages: list[dict] | None = None) -> dict:
    return {
        "spdxVersion": "SPDX-2.3",
        "name": "test-spdx",
        "packages": packages or [],
    }


def _manifest_box_sbom(components: list[dict] | None = None) -> dict:
    return {
        "build_manifest": {
            "manifest": {
                "components": components or [],
            }
        },
        "build_component": "jupyter-minimal",
        "build_completed_at": "2025-01-01T00:00:00Z",
    }


def _syft_artifact(
    name: str,
    version: str = "1.0.0",
    pkg_type: str = "npm",
    paths: list[str] | None = None,
    purl: str | None = None,
) -> dict:
    locations = [{"path": p} for p in (paths or [])]
    return {
        "name": name,
        "version": version,
        "type": pkg_type,
        "foundBy": "cataloger",
        "locations": locations,
        "purl": purl or f"pkg:{pkg_type}/{name}@{version}",
    }


def _spdx_package(
    name: str,
    version: str = "1.0.0",
    purl: str | None = None,
    source_info: str = "",
) -> dict:
    refs = []
    if purl:
        refs.append({"referenceType": "purl", "referenceLocator": purl})
    return {
        "name": name,
        "versionInfo": version,
        "externalRefs": refs,
        "sourceInfo": source_info,
    }


# ── detect_sbom_format ────────────────────────────────────────────────


def test_detect_sbom_format_syft() -> None:
    assert sa.detect_sbom_format(_syft_sbom()) == "syft"


def test_detect_sbom_format_spdx() -> None:
    assert sa.detect_sbom_format(_spdx_sbom()) == "spdx"


def test_detect_sbom_format_spdx_manifest_box() -> None:
    assert sa.detect_sbom_format(_manifest_box_sbom()) == "spdx-manifest-box"


def test_detect_sbom_format_unknown() -> None:
    assert sa.detect_sbom_format({}) == "unknown"


def test_detect_sbom_format_spdx_version_only() -> None:
    assert sa.detect_sbom_format({"spdxVersion": "SPDX-2.3"}) == "spdx"


def test_detect_sbom_format_spdx_packages_only() -> None:
    assert sa.detect_sbom_format({"packages": []}) == "spdx"


# ── extract_purl_type ─────────────────────────────────────────────────


def test_extract_purl_type(subtests: Subtests) -> None:
    cases = [
        ("pkg:npm/lodash@4.17.21", "npm"),
        ("pkg:pypi/requests@2.31.0", "pypi"),
        ("pkg:rpm/redhat/glibc@2.34", "rpm"),
        ("pkg:golang/github.com/foo/bar@1.0", "golang"),
        ("pkg:npm/@scope/package@1.0", "npm"),
        ("", "unknown"),
        ("not-a-purl", "unknown"),
        ("pkg:", "unknown"),
        ("pkg:/lodash@1.0", "unknown"),
        ("urn:npm/lodash@4.17.21", "unknown"),
    ]
    for purl, expected in cases:
        with subtests.test(msg=f"extract_purl_type({purl!r})"):
            assert sa.extract_purl_type(purl) == expected


def test_extract_purl_type_very_long_purl() -> None:
    long_name = "a" * 10_000
    assert sa.extract_purl_type(f"pkg:npm/{long_name}@1.0") == "npm"


# ── get_components_from_sbom ──────────────────────────────────────────


def test_get_components_syft_returns_artifacts() -> None:
    arts = [_syft_artifact("foo")]
    assert sa.get_components_from_sbom(_syft_sbom(arts)) == arts


def test_get_components_spdx_returns_packages() -> None:
    pkgs = [_spdx_package("bar")]
    assert sa.get_components_from_sbom(_spdx_sbom(pkgs)) == pkgs


def test_get_components_manifest_box_returns_components() -> None:
    comps = [_spdx_package("baz")]
    assert sa.get_components_from_sbom(_manifest_box_sbom(comps)) == comps


def test_get_components_unknown_returns_empty() -> None:
    assert sa.get_components_from_sbom({}) == []


# ── normalize_component ──────────────────────────────────────────────


def test_normalize_component_syft() -> None:
    art = _syft_artifact("lodash", "4.17.21", "npm", paths=["/node_modules/lodash/package.json"])
    norm = sa.normalize_component(art, "syft")
    assert norm["name"] == "lodash"
    assert norm["version"] == "4.17.21"
    assert norm["type"] == "npm"
    assert norm["locations"] == ["/node_modules/lodash/package.json"]
    assert norm["foundBy"] == "cataloger"


def test_normalize_component_spdx_with_purl() -> None:
    pkg = _spdx_package("requests", "2.31.0", purl="pkg:pypi/requests@2.31.0")
    norm = sa.normalize_component(pkg, "spdx")
    assert norm["name"] == "requests"
    assert norm["version"] == "2.31.0"
    assert norm["type"] == "pypi"
    assert norm["purl"] == "pkg:pypi/requests@2.31.0"


def test_normalize_component_spdx_source_info_extracts_path() -> None:
    pkg = _spdx_package(
        "undici",
        "5.0.0",
        source_info="acquired package info from installed node module manifest file: /jupyter/utils/pnpm-lock.yaml",
    )
    norm = sa.normalize_component(pkg, "spdx")
    assert norm["locations"] == ["/jupyter/utils/pnpm-lock.yaml"]


def test_normalize_component_spdx_no_purl_gives_unknown_type() -> None:
    pkg = _spdx_package("mystery", "0.0.1")
    norm = sa.normalize_component(pkg, "spdx")
    assert norm["type"] == "unknown"
    assert norm["purl"] is None


def test_normalize_component_spdx_source_info_no_colon_separator() -> None:
    pkg = _spdx_package("pkg", "1.0", source_info="no path separator here")
    norm = sa.normalize_component(pkg, "spdx")
    assert norm["locations"] == []


def test_normalize_component_spdx_empty_source_info() -> None:
    pkg = _spdx_package("pkg", "1.0", source_info="")
    norm = sa.normalize_component(pkg, "spdx")
    assert norm["locations"] == []


def test_normalize_component_unknown_format() -> None:
    norm = sa.normalize_component({"name": "x"}, "other")
    assert norm["name"] == "x"
    assert norm["type"] == "unknown"
    assert norm["locations"] == []


# ── find_package ──────────────────────────────────────────────────────


def test_find_package_case_insensitive_match() -> None:
    sbom = _syft_sbom([_syft_artifact("Lodash"), _syft_artifact("express")])
    results = sa.find_package(sbom, "lodash")
    assert len(results) == 1
    assert results[0]["name"] == "Lodash"


def test_find_package_case_sensitive_exact_match() -> None:
    sbom = _syft_sbom([_syft_artifact("Lodash"), _syft_artifact("lodash")])
    results = sa.find_package(sbom, "Lodash", case_insensitive=False)
    assert len(results) == 1
    assert results[0]["name"] == "Lodash"


def test_find_package_substring_match() -> None:
    sbom = _syft_sbom([_syft_artifact("is-core-module"), _syft_artifact("core-js")])
    results = sa.find_package(sbom, "core")
    assert len(results) == 2


def test_find_package_no_match_returns_empty() -> None:
    sbom = _syft_sbom([_syft_artifact("foo")])
    assert sa.find_package(sbom, "zzz-no-match") == []


def test_find_package_spdx_format() -> None:
    sbom = _spdx_sbom([_spdx_package("numpy", "1.26.0", purl="pkg:pypi/numpy@1.26.0")])
    results = sa.find_package(sbom, "numpy")
    assert len(results) == 1
    assert results[0]["type"] == "pypi"


# ── find_packages_at_path ─────────────────────────────────────────────


def test_find_packages_at_path_matches_location() -> None:
    sbom = _syft_sbom(
        [
            _syft_artifact("a", paths=["/jupyter/lib/a"]),
            _syft_artifact("b", paths=["/opt/lib/b"]),
        ]
    )
    results = sa.find_packages_at_path(sbom, "/jupyter/")
    assert len(results) == 1
    assert results[0]["name"] == "a"


def test_find_packages_at_path_matches_source_info() -> None:
    pkg = _spdx_package("c", source_info="acquired from: /jupyter/data/lock.yaml")
    sbom = _spdx_sbom([pkg])
    results = sa.find_packages_at_path(sbom, "/jupyter/")
    assert len(results) == 1


def test_find_packages_at_path_no_match() -> None:
    sbom = _syft_sbom([_syft_artifact("x", paths=["/usr/lib/x"])])
    assert sa.find_packages_at_path(sbom, "/nonexistent/") == []


# ── get_sbom_info ─────────────────────────────────────────────────────


def test_get_sbom_info_syft() -> None:
    sbom = _syft_sbom([_syft_artifact("a")])
    info = sa.get_sbom_info(sbom)
    assert info["format"] == "syft"
    assert info["source_name"] == "test-image"
    assert info["distro"] == "rhel"
    assert info["artifact_count"] == 1


def test_get_sbom_info_spdx() -> None:
    info = sa.get_sbom_info(_spdx_sbom([_spdx_package("x")]))
    assert info["format"] == "spdx"
    assert info["package_count"] == 1


def test_get_sbom_info_manifest_box() -> None:
    info = sa.get_sbom_info(_manifest_box_sbom([_spdx_package("y")]))
    assert info["format"] == "spdx (manifest-box)"
    assert info["component_count"] == 1


def test_get_sbom_info_unknown() -> None:
    assert sa.get_sbom_info({})["format"] == "unknown"


# ── summarize_by_type ─────────────────────────────────────────────────


def test_summarize_by_type_counts() -> None:
    sbom = _syft_sbom(
        [
            _syft_artifact("a", pkg_type="npm"),
            _syft_artifact("b", pkg_type="npm"),
            _syft_artifact("c", pkg_type="python"),
        ]
    )
    summary = sa.summarize_by_type(sbom)
    assert summary == {"npm": 2, "python": 1}


def test_summarize_by_type_empty_sbom() -> None:
    assert sa.summarize_by_type(_syft_sbom()) == {}


def test_summarize_by_type_sorted_descending() -> None:
    sbom = _syft_sbom(
        [
            _syft_artifact("a", pkg_type="go-module"),
            _syft_artifact("b", pkg_type="npm"),
            _syft_artifact("c", pkg_type="npm"),
            _syft_artifact("d", pkg_type="npm"),
        ]
    )
    summary = sa.summarize_by_type(sbom)
    keys = list(summary.keys())
    assert keys[0] == "npm"
