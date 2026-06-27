from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.cve.syft_scan import Artifact, Location, SyftOutput, filter_artifacts

if TYPE_CHECKING:
    from pytest_subtests import SubTests


def _make_artifact(name: str, version: str, pkg_type: str, path: str | None = None) -> Artifact:
    locations = [Location(path=path)] if path else []
    return Artifact(name=name, version=version, type=pkg_type, locations=locations)


SAMPLE_ARTIFACTS = [
    _make_artifact("lodash", "4.17.21", "npm", "/app/node_modules/lodash/package.json"),
    _make_artifact("numpy", "1.26.4", "python", "/usr/lib/python3.12/site-packages/numpy"),
    _make_artifact("express", "4.18.2", "npm", "/app/node_modules/express/package.json"),
    _make_artifact("go-stdlib", "1.22.0", "go-module", None),
]


def test_filter_by_package_name() -> None:
    result = filter_artifacts(SAMPLE_ARTIFACTS, package="lodash")
    assert len(result) == 1
    assert result[0].name == "lodash"


def test_filter_by_package_name_case_insensitive() -> None:
    result = filter_artifacts(SAMPLE_ARTIFACTS, package="NUMPY")
    assert len(result) == 1
    assert result[0].name == "numpy"


def test_filter_by_package_name_partial() -> None:
    result = filter_artifacts(SAMPLE_ARTIFACTS, package="lo")
    assert len(result) == 1
    assert result[0].name == "lodash"


def test_filter_by_type() -> None:
    result = filter_artifacts(SAMPLE_ARTIFACTS, pkg_type="npm")
    assert len(result) == 2
    assert all(a.type == "npm" for a in result)


def test_filter_by_type_case_insensitive() -> None:
    result = filter_artifacts(SAMPLE_ARTIFACTS, pkg_type="NPM")
    assert len(result) == 2


def test_filter_by_package_and_type() -> None:
    result = filter_artifacts(SAMPLE_ARTIFACTS, package="express", pkg_type="npm")
    assert len(result) == 1
    assert result[0].name == "express"


def test_filter_no_match() -> None:
    result = filter_artifacts(SAMPLE_ARTIFACTS, package="nonexistent")
    assert result == []


def test_filter_no_filters_returns_all() -> None:
    result = filter_artifacts(SAMPLE_ARTIFACTS)
    assert len(result) == len(SAMPLE_ARTIFACTS)


def test_syft_output_model_parse() -> None:
    raw = {
        "artifacts": [
            {
                "name": "lodash",
                "version": "4.17.21",
                "type": "npm",
                "locations": [{"path": "/app/node_modules/lodash/package.json"}],
                "purl": "pkg:npm/lodash@4.17.21",
            },
        ],
    }
    output = SyftOutput.model_validate(raw)
    assert len(output.artifacts) == 1
    assert output.artifacts[0].name == "lodash"
    assert output.artifacts[0].locations[0].path == "/app/node_modules/lodash/package.json"


def test_syft_output_empty() -> None:
    output = SyftOutput.model_validate({})
    assert output.artifacts == []


def test_artifact_defaults() -> None:
    a = Artifact()
    assert a.name == ""
    assert a.version is None
    assert a.type == "unknown"
    assert a.locations == []
    assert a.purl is None
