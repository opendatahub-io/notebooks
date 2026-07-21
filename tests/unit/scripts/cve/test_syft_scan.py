from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.cve.syft_scan import Artifact, Location, SyftOutput, filter_artifacts

if TYPE_CHECKING:
    from pytest import Subtests


# ── Pydantic model parsing ────────────────────────────────────────────


def test_location_model_parses_path() -> None:
    loc = Location(path="/app/node_modules/lodash/package.json")
    assert loc.path == "/app/node_modules/lodash/package.json"


def test_location_model_defaults_to_none() -> None:
    loc = Location()
    assert loc.path is None


def test_location_model_allows_extra_fields() -> None:
    loc = Location.model_validate({"path": "/foo", "layerID": "sha256:abc"})
    assert loc.path == "/foo"


def test_artifact_model_defaults() -> None:
    art = Artifact()
    assert art.name == ""
    assert art.version is None
    assert art.type == "unknown"
    assert art.locations == []
    assert art.purl is None


def test_artifact_model_full_parse() -> None:
    data = {
        "name": "lodash",
        "version": "4.17.21",
        "type": "npm",
        "purl": "pkg:npm/lodash@4.17.21",
        "locations": [
            {"path": "/app/node_modules/lodash/package.json"},
            {"path": "/alt/node_modules/lodash/package.json"},
        ],
    }
    art = Artifact.model_validate(data)
    assert art.name == "lodash"
    assert art.version == "4.17.21"
    assert art.type == "npm"
    assert art.purl == "pkg:npm/lodash@4.17.21"
    assert len(art.locations) == 2
    assert art.locations[0].path == "/app/node_modules/lodash/package.json"


def test_artifact_model_allows_extra_fields() -> None:
    data = {"name": "foo", "foundBy": "cataloger-x", "metadataType": "some-meta"}
    art = Artifact.model_validate(data)
    assert art.name == "foo"


def test_syft_output_model_empty() -> None:
    output = SyftOutput()
    assert output.artifacts == []


def test_syft_output_model_with_artifacts() -> None:
    data = {
        "artifacts": [
            {"name": "lodash", "version": "4.17.21", "type": "npm", "locations": []},
            {"name": "express", "version": "4.18.0", "type": "npm", "locations": []},
        ],
    }
    output = SyftOutput.model_validate(data)
    assert len(output.artifacts) == 2
    assert output.artifacts[0].name == "lodash"
    assert output.artifacts[1].name == "express"


def test_syft_output_model_allows_extra_fields() -> None:
    data = {
        "artifacts": [],
        "source": {"name": "quay.io/test", "type": "image"},
        "distro": {"name": "rhel"},
    }
    output = SyftOutput.model_validate(data)
    assert output.artifacts == []


def test_syft_output_parses_json() -> None:
    raw = '{"artifacts": [{"name": "foo", "version": "1.0", "type": "npm"}]}'
    out = SyftOutput.model_validate_json(raw)
    assert len(out.artifacts) == 1
    assert out.artifacts[0].name == "foo"


# ── filter_artifacts ──────────────────────────────────────────────────


def _make_artifacts() -> list[Artifact]:
    return [
        Artifact(name="lodash", version="4.17.21", type="npm"),
        Artifact(name="lodash.merge", version="4.6.2", type="npm"),
        Artifact(name="express", version="4.18.0", type="npm"),
        Artifact(name="requests", version="2.31.0", type="python"),
        Artifact(name="openssl", version="3.0.7", type="rpm"),
    ]


def test_filter_artifacts_no_filters() -> None:
    arts = _make_artifacts()
    result = filter_artifacts(arts)
    assert len(result) == 5


def test_filter_artifacts_by_package_name(subtests: Subtests) -> None:
    arts = _make_artifacts()
    cases = [
        ("lodash", 2),
        ("express", 1),
        ("nonexistent", 0),
        ("LODASH", 2),
    ]
    for name, expected_count in cases:
        with subtests.test(msg=f"filter by package={name!r}"):
            result = filter_artifacts(arts, package=name)
            assert len(result) == expected_count


def test_filter_artifacts_by_type(subtests: Subtests) -> None:
    arts = _make_artifacts()
    cases = [
        ("npm", 3),
        ("python", 1),
        ("rpm", 1),
        ("golang", 0),
        ("NPM", 3),
    ]
    for pkg_type, expected_count in cases:
        with subtests.test(msg=f"filter by type={pkg_type!r}"):
            result = filter_artifacts(arts, pkg_type=pkg_type)
            assert len(result) == expected_count


def test_filter_artifacts_by_both_package_and_type() -> None:
    arts = _make_artifacts()
    result = filter_artifacts(arts, package="lodash", pkg_type="npm")
    assert len(result) == 2
    assert all("lodash" in a.name.lower() for a in result)


def test_filter_artifacts_combined_no_match() -> None:
    arts = _make_artifacts()
    result = filter_artifacts(arts, package="lodash", pkg_type="python")
    assert len(result) == 0


def test_filter_artifacts_regex_metacharacters_treated_literally() -> None:
    arts = [Artifact(name="foo.bar", type="npm"), Artifact(name="fooXbar", type="npm")]
    result = filter_artifacts(arts, package="foo.bar")
    assert len(result) == 1
    assert result[0].name == "foo.bar"


def test_filter_artifacts_empty_list() -> None:
    assert filter_artifacts([], package="anything") == []
