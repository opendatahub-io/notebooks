from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.cve import sbom_analyze

if TYPE_CHECKING:
    from pytest_subtests import SubTests


SYFT_SBOM: dict = {
    "artifacts": [
        {
            "name": "lodash",
            "version": "4.17.21",
            "type": "npm",
            "foundBy": "javascript-lock-cataloger",
            "locations": [{"path": "/app/node_modules/lodash/package.json"}],
            "purl": "pkg:npm/lodash@4.17.21",
        },
        {
            "name": "numpy",
            "version": "1.26.4",
            "type": "python",
            "foundBy": "python-installed-package-cataloger",
            "locations": [{"path": "/usr/lib/python3.12/site-packages/numpy"}],
            "purl": "pkg:pypi/numpy@1.26.4",
        },
    ],
    "source": {"name": "test-image", "version": "1.0", "type": "image"},
    "distro": {"name": "centos", "version": "9"},
    "descriptor": {"version": "0.98.0"},
    "schema": {"version": "16.0.0"},
    "files": [],
}

SPDX_SBOM: dict = {
    "spdxVersion": "SPDX-2.3",
    "name": "test-sbom",
    "packages": [
        {
            "name": "esbuild",
            "versionInfo": "0.19.0",
            "externalRefs": [
                {"referenceType": "purl", "referenceLocator": "pkg:npm/esbuild@0.19.0"},
            ],
            "sourceInfo": "acquired package info from installed node module manifest file: /jupyter/utils/addons/pnpm-lock.yaml",
        },
    ],
}

SPDX_MANIFEST_BOX_SBOM: dict = {
    "build_manifest": {
        "manifest": {
            "components": [
                {
                    "name": "requests",
                    "versionInfo": "2.31.0",
                    "externalRefs": [
                        {"referenceType": "purl", "referenceLocator": "pkg:pypi/requests@2.31.0"},
                    ],
                    "sourceInfo": "",
                },
            ],
        },
    },
    "build_component": "test-component",
    "build_completed_at": "2026-01-01T00:00:00Z",
}


def test_detect_sbom_format(subtests: SubTests) -> None:
    cases = [
        (SYFT_SBOM, "syft"),
        (SPDX_SBOM, "spdx"),
        (SPDX_MANIFEST_BOX_SBOM, "spdx-manifest-box"),
        ({}, "unknown"),
    ]
    for sbom, expected in cases:
        with subtests.test(msg=expected):
            assert sbom_analyze.detect_sbom_format(sbom) == expected


def test_extract_purl_type(subtests: SubTests) -> None:
    cases = [
        ("pkg:npm/lodash@4.17.21", "npm"),
        ("pkg:pypi/numpy@1.26.4", "pypi"),
        ("pkg:golang/github.com/foo/bar@v1.0.0", "golang"),
        ("", "unknown"),
        ("not-a-purl", "unknown"),
    ]
    for purl, expected in cases:
        with subtests.test(msg=f"extract_purl_type({purl!r})"):
            assert sbom_analyze.extract_purl_type(purl) == expected


def test_get_components_from_syft_sbom() -> None:
    components = sbom_analyze.get_components_from_sbom(SYFT_SBOM)
    assert len(components) == 2
    assert components[0]["name"] == "lodash"


def test_get_components_from_spdx_sbom() -> None:
    components = sbom_analyze.get_components_from_sbom(SPDX_SBOM)
    assert len(components) == 1
    assert components[0]["name"] == "esbuild"


def test_get_components_from_manifest_box_sbom() -> None:
    components = sbom_analyze.get_components_from_sbom(SPDX_MANIFEST_BOX_SBOM)
    assert len(components) == 1
    assert components[0]["name"] == "requests"


def test_get_components_unknown_format() -> None:
    assert sbom_analyze.get_components_from_sbom({}) == []


def test_normalize_component_syft() -> None:
    raw = SYFT_SBOM["artifacts"][0]
    normalized = sbom_analyze.normalize_component(raw, "syft")
    assert normalized["name"] == "lodash"
    assert normalized["version"] == "4.17.21"
    assert normalized["type"] == "npm"
    assert normalized["purl"] == "pkg:npm/lodash@4.17.21"
    assert "/app/node_modules/lodash/package.json" in normalized["locations"]


def test_normalize_component_spdx() -> None:
    raw = SPDX_SBOM["packages"][0]
    normalized = sbom_analyze.normalize_component(raw, "spdx")
    assert normalized["name"] == "esbuild"
    assert normalized["version"] == "0.19.0"
    assert normalized["type"] == "npm"
    assert normalized["purl"] == "pkg:npm/esbuild@0.19.0"
    assert any("/jupyter/" in loc for loc in normalized["locations"])


def test_normalize_component_unknown_format() -> None:
    raw = {"name": "mystery"}
    normalized = sbom_analyze.normalize_component(raw, "other")
    assert normalized["name"] == "mystery"
    assert normalized["version"] is None
    assert normalized["type"] == "unknown"


def test_find_package_case_insensitive() -> None:
    results = sbom_analyze.find_package(SYFT_SBOM, "LODASH")
    assert len(results) == 1
    assert results[0]["name"] == "lodash"


def test_find_package_case_sensitive() -> None:
    results = sbom_analyze.find_package(SYFT_SBOM, "LODASH", case_insensitive=False)
    assert len(results) == 0


def test_find_package_partial_match() -> None:
    results = sbom_analyze.find_package(SYFT_SBOM, "num")
    assert len(results) == 1
    assert results[0]["name"] == "numpy"


def test_find_package_not_found() -> None:
    results = sbom_analyze.find_package(SYFT_SBOM, "nonexistent")
    assert results == []


def test_find_packages_at_path() -> None:
    results = sbom_analyze.find_packages_at_path(SYFT_SBOM, "/app/node_modules/")
    assert len(results) == 1
    assert results[0]["name"] == "lodash"


def test_find_packages_at_path_spdx_source_info() -> None:
    results = sbom_analyze.find_packages_at_path(SPDX_SBOM, "/jupyter/")
    assert len(results) == 1
    assert results[0]["name"] == "esbuild"


def test_find_packages_at_path_no_match() -> None:
    results = sbom_analyze.find_packages_at_path(SYFT_SBOM, "/nonexistent/")
    assert results == []


def test_get_sbom_info_syft() -> None:
    info = sbom_analyze.get_sbom_info(SYFT_SBOM)
    assert info["format"] == "syft"
    assert info["source_name"] == "test-image"
    assert info["distro"] == "centos"
    assert info["artifact_count"] == 2


def test_get_sbom_info_spdx() -> None:
    info = sbom_analyze.get_sbom_info(SPDX_SBOM)
    assert info["format"] == "spdx"
    assert info["spdx_version"] == "SPDX-2.3"
    assert info["package_count"] == 1


def test_get_sbom_info_manifest_box() -> None:
    info = sbom_analyze.get_sbom_info(SPDX_MANIFEST_BOX_SBOM)
    assert info["format"] == "spdx (manifest-box)"
    assert info["build_component"] == "test-component"
    assert info["component_count"] == 1


def test_get_sbom_info_unknown() -> None:
    info = sbom_analyze.get_sbom_info({})
    assert info == {"format": "unknown"}


def test_summarize_by_type() -> None:
    summary = sbom_analyze.summarize_by_type(SYFT_SBOM)
    assert summary["npm"] == 1
    assert summary["python"] == 1
