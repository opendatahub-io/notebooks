"""Unit tests for scripts/cve/sbom_analyze.py — SBOM parsing, searching, and aggregation."""

from __future__ import annotations

import scripts.cve.sbom_analyze as sa

# ---------------------------------------------------------------------------
# Fixtures: minimal SBOM documents in each supported format
# ---------------------------------------------------------------------------


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
    name: str, version: str = "1.0.0", pkg_type: str = "npm", paths: list[str] | None = None, purl: str | None = None
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


def _spdx_package(name: str, version: str = "1.0.0", purl: str | None = None, source_info: str = "") -> dict:
    refs = []
    if purl:
        refs.append({"referenceType": "purl", "referenceLocator": purl})
    return {
        "name": name,
        "versionInfo": version,
        "externalRefs": refs,
        "sourceInfo": source_info,
    }


# ---------------------------------------------------------------------------
# detect_sbom_format
# ---------------------------------------------------------------------------


class TestDetectSbomFormat:
    def test_syft(self) -> None:
        assert sa.detect_sbom_format(_syft_sbom()) == "syft"

    def test_spdx(self) -> None:
        assert sa.detect_sbom_format(_spdx_sbom()) == "spdx"

    def test_spdx_manifest_box(self) -> None:
        assert sa.detect_sbom_format(_manifest_box_sbom()) == "spdx-manifest-box"

    def test_unknown(self) -> None:
        assert sa.detect_sbom_format({}) == "unknown"

    def test_spdx_version_only(self) -> None:
        assert sa.detect_sbom_format({"spdxVersion": "SPDX-2.3"}) == "spdx"


# ---------------------------------------------------------------------------
# extract_purl_type
# ---------------------------------------------------------------------------


class TestExtractPurlType:
    def test_npm(self) -> None:
        assert sa.extract_purl_type("pkg:npm/lodash@4.17.21") == "npm"

    def test_pypi(self) -> None:
        assert sa.extract_purl_type("pkg:pypi/requests@2.31.0") == "pypi"

    def test_rpm(self) -> None:
        assert sa.extract_purl_type("pkg:rpm/redhat/glibc@2.34") == "rpm"

    def test_empty(self) -> None:
        assert sa.extract_purl_type("") == "unknown"

    def test_no_match(self) -> None:
        assert sa.extract_purl_type("not-a-purl") == "unknown"

    def test_malformed_pkg_no_slash(self) -> None:
        assert sa.extract_purl_type("pkg:") == "unknown"

    def test_malformed_missing_type(self) -> None:
        assert sa.extract_purl_type("pkg:/lodash@1.0") == "unknown"

    def test_purl_with_namespace(self) -> None:
        assert sa.extract_purl_type("pkg:golang/github.com/foo/bar@1.0") == "golang"


# ---------------------------------------------------------------------------
# get_components_from_sbom
# ---------------------------------------------------------------------------


class TestGetComponentsFromSbom:
    def test_syft_returns_artifacts(self) -> None:
        arts = [_syft_artifact("foo")]
        assert sa.get_components_from_sbom(_syft_sbom(arts)) == arts

    def test_spdx_returns_packages(self) -> None:
        pkgs = [_spdx_package("bar")]
        assert sa.get_components_from_sbom(_spdx_sbom(pkgs)) == pkgs

    def test_manifest_box_returns_components(self) -> None:
        comps = [_spdx_package("baz")]
        assert sa.get_components_from_sbom(_manifest_box_sbom(comps)) == comps

    def test_unknown_returns_empty(self) -> None:
        assert sa.get_components_from_sbom({}) == []


# ---------------------------------------------------------------------------
# normalize_component
# ---------------------------------------------------------------------------


class TestNormalizeComponent:
    def test_syft_component(self) -> None:
        art = _syft_artifact("lodash", "4.17.21", "npm", paths=["/node_modules/lodash/package.json"])
        norm = sa.normalize_component(art, "syft")
        assert norm["name"] == "lodash"
        assert norm["version"] == "4.17.21"
        assert norm["type"] == "npm"
        assert norm["locations"] == ["/node_modules/lodash/package.json"]
        assert norm["foundBy"] == "cataloger"

    def test_spdx_component_with_purl(self) -> None:
        pkg = _spdx_package("requests", "2.31.0", purl="pkg:pypi/requests@2.31.0")
        norm = sa.normalize_component(pkg, "spdx")
        assert norm["name"] == "requests"
        assert norm["version"] == "2.31.0"
        assert norm["type"] == "pypi"
        assert norm["purl"] == "pkg:pypi/requests@2.31.0"

    def test_spdx_source_info_extracts_path(self) -> None:
        pkg = _spdx_package(
            "undici",
            "5.0.0",
            source_info="acquired package info from installed node module manifest file: /jupyter/utils/pnpm-lock.yaml",
        )
        norm = sa.normalize_component(pkg, "spdx")
        assert norm["locations"] == ["/jupyter/utils/pnpm-lock.yaml"]

    def test_spdx_no_purl_gives_unknown_type(self) -> None:
        pkg = _spdx_package("mystery", "0.0.1")
        norm = sa.normalize_component(pkg, "spdx")
        assert norm["type"] == "unknown"

    def test_unknown_format(self) -> None:
        norm = sa.normalize_component({"name": "x"}, "other")
        assert norm["name"] == "x"
        assert norm["type"] == "unknown"
        assert norm["locations"] == []


# ---------------------------------------------------------------------------
# find_package
# ---------------------------------------------------------------------------


class TestFindPackage:
    def test_case_insensitive_match(self) -> None:
        sbom = _syft_sbom([_syft_artifact("Lodash"), _syft_artifact("express")])
        results = sa.find_package(sbom, "lodash")
        assert len(results) == 1
        assert results[0]["name"] == "Lodash"

    def test_case_sensitive_exact_match(self) -> None:
        sbom = _syft_sbom([_syft_artifact("Lodash"), _syft_artifact("lodash")])
        results = sa.find_package(sbom, "Lodash", case_insensitive=False)
        assert len(results) == 1
        assert results[0]["name"] == "Lodash"

    def test_substring_match(self) -> None:
        sbom = _syft_sbom([_syft_artifact("is-core-module"), _syft_artifact("core-js")])
        results = sa.find_package(sbom, "core")
        assert len(results) == 2

    def test_no_match_returns_empty(self) -> None:
        sbom = _syft_sbom([_syft_artifact("foo")])
        assert sa.find_package(sbom, "zzz-no-match") == []

    def test_spdx_format(self) -> None:
        sbom = _spdx_sbom([_spdx_package("numpy", "1.26.0", purl="pkg:pypi/numpy@1.26.0")])
        results = sa.find_package(sbom, "numpy")
        assert len(results) == 1
        assert results[0]["type"] == "pypi"


# ---------------------------------------------------------------------------
# find_packages_at_path
# ---------------------------------------------------------------------------


class TestFindPackagesAtPath:
    def test_matches_location(self) -> None:
        sbom = _syft_sbom(
            [
                _syft_artifact("a", paths=["/jupyter/lib/a"]),
                _syft_artifact("b", paths=["/opt/lib/b"]),
            ]
        )
        results = sa.find_packages_at_path(sbom, "/jupyter/")
        assert len(results) == 1
        assert results[0]["name"] == "a"

    def test_matches_source_info(self) -> None:
        pkg = _spdx_package("c", source_info="acquired from: /jupyter/data/lock.yaml")
        sbom = _spdx_sbom([pkg])
        results = sa.find_packages_at_path(sbom, "/jupyter/")
        assert len(results) == 1

    def test_no_path_match(self) -> None:
        sbom = _syft_sbom([_syft_artifact("x", paths=["/usr/lib/x"])])
        assert sa.find_packages_at_path(sbom, "/nonexistent/") == []


# ---------------------------------------------------------------------------
# get_sbom_info
# ---------------------------------------------------------------------------


class TestGetSbomInfo:
    def test_syft_metadata(self) -> None:
        sbom = _syft_sbom([_syft_artifact("a")])
        info = sa.get_sbom_info(sbom)
        assert info["format"] == "syft"
        assert info["source_name"] == "test-image"
        assert info["distro"] == "rhel"
        assert info["artifact_count"] == 1

    def test_spdx_metadata(self) -> None:
        info = sa.get_sbom_info(_spdx_sbom([_spdx_package("x")]))
        assert info["format"] == "spdx"
        assert info["package_count"] == 1

    def test_manifest_box_metadata(self) -> None:
        info = sa.get_sbom_info(_manifest_box_sbom([_spdx_package("y")]))
        assert info["format"] == "spdx (manifest-box)"
        assert info["component_count"] == 1

    def test_unknown(self) -> None:
        assert sa.get_sbom_info({})["format"] == "unknown"


# ---------------------------------------------------------------------------
# summarize_by_type
# ---------------------------------------------------------------------------


class TestSummarizeByType:
    def test_counts_by_type(self) -> None:
        sbom = _syft_sbom(
            [
                _syft_artifact("a", pkg_type="npm"),
                _syft_artifact("b", pkg_type="npm"),
                _syft_artifact("c", pkg_type="python"),
            ]
        )
        summary = sa.summarize_by_type(sbom)
        assert summary == {"npm": 2, "python": 1}

    def test_empty_sbom(self) -> None:
        assert sa.summarize_by_type(_syft_sbom()) == {}

    def test_sorted_descending(self) -> None:
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
