"""Unit tests for scripts/cve/syft_scan.py — Pydantic models and artifact filtering."""

from __future__ import annotations

from scripts.cve.syft_scan import Artifact, Location, SyftOutput, filter_artifacts

# ---------------------------------------------------------------------------
# Pydantic model construction
# ---------------------------------------------------------------------------


class TestModels:
    def test_location_defaults(self) -> None:
        loc = Location()
        assert loc.path is None

    def test_location_with_path(self) -> None:
        loc = Location(path="/usr/lib/foo")
        assert loc.path == "/usr/lib/foo"

    def test_artifact_defaults(self) -> None:
        a = Artifact()
        assert a.name == ""
        assert a.version is None
        assert a.type == "unknown"
        assert a.locations == []
        assert a.purl is None

    def test_artifact_full(self) -> None:
        a = Artifact(
            name="lodash",
            version="4.17.21",
            type="npm",
            locations=[Location(path="/node_modules/lodash")],
            purl="pkg:npm/lodash@4.17.21",
        )
        assert a.name == "lodash"
        assert a.version == "4.17.21"
        assert len(a.locations) == 1

    def test_syft_output_empty(self) -> None:
        out = SyftOutput()
        assert out.artifacts == []

    def test_syft_output_parses_json(self) -> None:
        raw = '{"artifacts": [{"name": "foo", "version": "1.0", "type": "npm"}]}'
        out = SyftOutput.model_validate_json(raw)
        assert len(out.artifacts) == 1
        assert out.artifacts[0].name == "foo"

    def test_extra_fields_allowed(self) -> None:
        a = Artifact.model_validate({"name": "x", "extraField": 42})
        assert a.name == "x"


# ---------------------------------------------------------------------------
# filter_artifacts
# ---------------------------------------------------------------------------


def _make_artifacts() -> list[Artifact]:
    return [
        Artifact(name="lodash", version="4.17.21", type="npm"),
        Artifact(name="express", version="4.18.0", type="npm"),
        Artifact(name="requests", version="2.31.0", type="python"),
        Artifact(name="glibc", version="2.34", type="rpm"),
    ]


class TestFilterArtifacts:
    def test_no_filter(self) -> None:
        arts = _make_artifacts()
        assert filter_artifacts(arts) == arts

    def test_filter_by_package_name(self) -> None:
        result = filter_artifacts(_make_artifacts(), package="lodash")
        assert len(result) == 1
        assert result[0].name == "lodash"

    def test_filter_by_package_case_insensitive(self) -> None:
        result = filter_artifacts(_make_artifacts(), package="LODASH")
        assert len(result) == 1

    def test_filter_by_package_substring(self) -> None:
        result = filter_artifacts(_make_artifacts(), package="es")
        assert {a.name for a in result} == {"express", "requests"}

    def test_filter_by_type(self) -> None:
        result = filter_artifacts(_make_artifacts(), pkg_type="npm")
        assert len(result) == 2
        assert all(a.type == "npm" for a in result)

    def test_filter_by_type_case_insensitive(self) -> None:
        result = filter_artifacts(_make_artifacts(), pkg_type="NPM")
        assert len(result) == 2

    def test_combined_filter(self) -> None:
        result = filter_artifacts(_make_artifacts(), package="express", pkg_type="npm")
        assert len(result) == 1
        assert result[0].name == "express"

    def test_no_match(self) -> None:
        assert filter_artifacts(_make_artifacts(), package="zzz") == []

    def test_type_no_match(self) -> None:
        assert filter_artifacts(_make_artifacts(), pkg_type="golang") == []

    def test_regex_metacharacters_treated_literally(self) -> None:
        arts = [Artifact(name="foo.bar", type="npm"), Artifact(name="fooXbar", type="npm")]
        result = filter_artifacts(arts, package="foo.bar")
        assert len(result) == 1
        assert result[0].name == "foo.bar"

    def test_very_long_package_name(self) -> None:
        long_name = "a" * 10_000
        arts = [Artifact(name=long_name, type="npm")]
        result = filter_artifacts(arts, package=long_name)
        assert len(result) == 1

    def test_empty_artifact_list(self) -> None:
        assert filter_artifacts([], package="anything") == []
