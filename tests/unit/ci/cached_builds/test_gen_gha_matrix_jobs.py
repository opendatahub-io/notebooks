"""Unit tests for ci/cached-builds/gen_gha_matrix_jobs.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import pytest

_CI_CACHED_BUILDS = Path(__file__).resolve().parents[4] / "ci" / "cached-builds"
if str(_CI_CACHED_BUILDS) not in sys.path:
    sys.path.insert(0, str(_CI_CACHED_BUILDS))

import gen_gha_matrix_jobs as gm  # noqa: E402  # type: ignore[reportMissingImports]

SAMPLE_MAKEFILE_OUTPUT = """\
# GNU Make 4.3

all-images: jupyter-minimal-ubi9-python-3.12 jupyter-datascience-ubi9-python-3.12 codeserver-ubi9-python-3.12 runtime-minimal-ubi9-python-3.12 runtime-cuda-tensorflow-ubi9-python-3.12
"""


class TestExtractImageTargets:
    def test_parses_targets_from_makefile_output(self, tmp_path: Path) -> None:
        with patch("makefile_helper.dry_run_makefile", return_value=SAMPLE_MAKEFILE_OUTPUT):
            targets = gm.extract_image_targets(makefile_dir=tmp_path)

        assert targets == [
            "jupyter-minimal-ubi9-python-3.12",
            "jupyter-datascience-ubi9-python-3.12",
            "codeserver-ubi9-python-3.12",
            "runtime-minimal-ubi9-python-3.12",
            "runtime-cuda-tensorflow-ubi9-python-3.12",
        ]

    def test_single_target(self, tmp_path: Path) -> None:
        output = "all-images: only-one-target\n"
        with patch("makefile_helper.dry_run_makefile", return_value=output):
            targets = gm.extract_image_targets(makefile_dir=tmp_path)
        assert targets == ["only-one-target"]

    def test_raises_on_empty_makefile_output(self, tmp_path: Path) -> None:
        with patch("makefile_helper.dry_run_makefile", return_value=""):
            with pytest.raises(Exception, match="No image dependencies found"):
                gm.extract_image_targets(makefile_dir=tmp_path)

    def test_raises_when_no_prerequisites(self, tmp_path: Path) -> None:
        output = "all-images:\n"
        with patch("makefile_helper.dry_run_makefile", return_value=output):
            with pytest.raises(Exception, match="No image dependencies found"):
                gm.extract_image_targets(makefile_dir=tmp_path)

    def test_multiline_makefile_output(self, tmp_path: Path) -> None:
        output = "# some preamble\nother-target: dep1\nall-images: target-a target-b\n# trailing\n"
        with patch("makefile_helper.dry_run_makefile", return_value=output):
            targets = gm.extract_image_targets(makefile_dir=tmp_path)
        assert targets == ["target-a", "target-b"]


class TestFilterRhelImages:
    TARGETS: ClassVar[list[str]] = [
        "jupyter-minimal-ubi9-python-3.12",
        "jupyter-datascience-rhel9-python-3.12",
        "codeserver-ubi9-python-3.12",
        "runtime-rhel9-python-3.12",
    ]

    def test_include_keeps_all(self) -> None:
        result = gm.filter_rhel_images(self.TARGETS, gm.RhelImages.INCLUDE)
        assert result == self.TARGETS

    def test_exclude_removes_rhel(self) -> None:
        result = gm.filter_rhel_images(self.TARGETS, gm.RhelImages.EXCLUDE)
        assert result == ["jupyter-minimal-ubi9-python-3.12", "codeserver-ubi9-python-3.12"]

    def test_include_only_keeps_only_rhel(self) -> None:
        result = gm.filter_rhel_images(self.TARGETS, gm.RhelImages.INCLUDE_ONLY)
        assert result == ["jupyter-datascience-rhel9-python-3.12", "runtime-rhel9-python-3.12"]

    def test_empty_targets(self) -> None:
        assert gm.filter_rhel_images([], gm.RhelImages.INCLUDE) == []
        assert gm.filter_rhel_images([], gm.RhelImages.EXCLUDE) == []
        assert gm.filter_rhel_images([], gm.RhelImages.INCLUDE_ONLY) == []

    def test_no_rhel_targets_with_include_only(self) -> None:
        targets = ["jupyter-minimal-ubi9-python-3.12"]
        assert gm.filter_rhel_images(targets, gm.RhelImages.INCLUDE_ONLY) == []


class TestAssignPlatforms:
    def test_amd64_only_non_compatible_target(self) -> None:
        targets = ["some-generic-target"]
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        assert result == [("some-generic-target", "linux/amd64")]

    def test_arm64_compatible_target_gets_both_platforms(self) -> None:
        targets = ["codeserver-ubi9-python-3.12"]
        assert targets[0] in gm.ARM64_COMPATIBLE
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/amd64" in platforms
        assert "linux/arm64" in platforms

    def test_arm64_exclude_removes_arm64_platform(self) -> None:
        targets = ["codeserver-ubi9-python-3.12"]
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.EXCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/amd64" in platforms
        assert "linux/arm64" not in platforms

    def test_arm64_only_suppresses_amd64_and_s390x(self) -> None:
        targets = ["codeserver-ubi9-python-3.12"]
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.ONLY,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/amd64" not in platforms
        assert "linux/arm64" in platforms
        assert "linux/s390x" not in platforms

    def test_ppc64le_compatible_target(self) -> None:
        targets = ["jupyter-minimal-ubi9-python-3.12"]
        assert targets[0] in gm.PPC64LE_COMPATIBLE
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/ppc64le" in platforms

    def test_ppc64le_exclude(self) -> None:
        targets = ["jupyter-minimal-ubi9-python-3.12"]
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.EXCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/ppc64le" not in platforms

    def test_s390x_compatible_target(self) -> None:
        targets = ["runtime-minimal-ubi9-python-3.12"]
        assert targets[0] in gm.S390X_COMPATIBLE
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/s390x" in platforms

    def test_s390x_exclude(self) -> None:
        targets = ["runtime-minimal-ubi9-python-3.12"]
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.EXCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/s390x" not in platforms

    def test_s390x_only_suppresses_amd64_and_arm64(self) -> None:
        targets = ["runtime-minimal-ubi9-python-3.12"]
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.ONLY,
        )
        platforms = [p for _, p in result]
        assert "linux/amd64" not in platforms
        assert "linux/arm64" not in platforms
        assert "linux/s390x" in platforms

    def test_empty_targets(self) -> None:
        result = gm.assign_platforms(
            [],
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        assert result == []

    def test_multi_platform_target(self) -> None:
        targets = ["jupyter-minimal-ubi9-python-3.12"]
        assert targets[0] in gm.PPC64LE_COMPATIBLE
        assert targets[0] in gm.S390X_COMPATIBLE
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert platforms == ["linux/amd64", "linux/ppc64le", "linux/s390x"]

    def test_s390x_only_suppresses_amd64_and_arm64_on_arm64_target(self) -> None:
        targets = ["codeserver-ubi9-python-3.12"]
        assert targets[0] in gm.ARM64_COMPATIBLE
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.ONLY,
        )
        platforms = [p for _, p in result]
        assert "linux/arm64" not in platforms
        assert "linux/amd64" not in platforms

    def test_arm64_only_suppresses_amd64_and_s390x_on_s390x_target(self) -> None:
        targets = ["runtime-minimal-ubi9-python-3.12"]
        assert targets[0] in gm.S390X_COMPATIBLE
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.ONLY,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/s390x" not in platforms
        assert "linux/amd64" not in platforms

    def test_arm64_only_suppresses_ppc64le(self) -> None:
        targets = ["jupyter-minimal-ubi9-python-3.12"]
        assert targets[0] in gm.PPC64LE_COMPATIBLE
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.ONLY,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        platforms = [p for _, p in result]
        assert "linux/ppc64le" not in platforms

    def test_s390x_only_suppresses_ppc64le(self) -> None:
        targets = ["jupyter-minimal-ubi9-python-3.12"]
        assert targets[0] in gm.PPC64LE_COMPATIBLE
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.ONLY,
        )
        platforms = [p for _, p in result]
        assert "linux/ppc64le" not in platforms

    def test_both_only_skips_amd64(self) -> None:
        targets = ["some-target"]
        result = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.ONLY,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.ONLY,
        )
        platforms = [p for _, p in result]
        assert "linux/amd64" not in platforms


class TestBuildMatrixOutput:
    def test_basic_output(self) -> None:
        targets_with_platform = [("jupyter-minimal-ubi9-python-3.12", "linux/amd64")]
        output = gm.build_matrix_output(targets_with_platform)

        assert len(output) == 2

        matrix_line = output[0]
        assert matrix_line.startswith("matrix=")
        matrix = json.loads(matrix_line.removeprefix("matrix="))
        assert len(matrix["include"]) == 1
        entry = matrix["include"][0]
        assert entry["target"] == "jupyter-minimal-ubi9-python-3.12"
        assert entry["python"] == "3.12"
        assert entry["platform"] == "linux/amd64"
        assert entry["subscription"] is False

    def test_rhel_target_sets_subscription_true(self) -> None:
        targets_with_platform = [("runtime-rhel9-python-3.12", "linux/amd64")]
        output = gm.build_matrix_output(targets_with_platform)
        matrix = json.loads(output[0].removeprefix("matrix="))
        assert matrix["include"][0]["subscription"] is True

    def test_has_jobs_true_with_targets(self) -> None:
        targets_with_platform = [("target-a", "linux/amd64")]
        output = gm.build_matrix_output(targets_with_platform)
        has_jobs_line = output[1]
        assert has_jobs_line == "has_jobs=true"

    def test_has_jobs_false_when_empty(self) -> None:
        output = gm.build_matrix_output([])
        has_jobs_line = output[1]
        assert has_jobs_line == "has_jobs=false"

        matrix = json.loads(output[0].removeprefix("matrix="))
        assert matrix["include"] == []

    def test_multiple_targets_and_platforms(self) -> None:
        targets_with_platform = [
            ("jupyter-minimal-ubi9-python-3.12", "linux/amd64"),
            ("jupyter-minimal-ubi9-python-3.12", "linux/ppc64le"),
            ("codeserver-ubi9-python-3.12", "linux/amd64"),
            ("codeserver-ubi9-python-3.12", "linux/arm64"),
        ]
        output = gm.build_matrix_output(targets_with_platform)
        matrix = json.loads(output[0].removeprefix("matrix="))
        assert len(matrix["include"]) == 4

    def test_output_uses_compact_json(self) -> None:
        targets_with_platform = [("target-a", "linux/amd64")]
        output = gm.build_matrix_output(targets_with_platform)
        raw_json = output[0].removeprefix("matrix=")
        assert " " not in raw_json


class TestCompatibilitySets:
    def test_arm64_compatible_is_a_set(self) -> None:
        assert isinstance(gm.ARM64_COMPATIBLE, set)
        assert len(gm.ARM64_COMPATIBLE) > 0

    def test_ppc64le_compatible_is_a_set(self) -> None:
        assert isinstance(gm.PPC64LE_COMPATIBLE, set)
        assert len(gm.PPC64LE_COMPATIBLE) > 0

    def test_s390x_compatible_is_a_set(self) -> None:
        assert isinstance(gm.S390X_COMPATIBLE, set)
        assert len(gm.S390X_COMPATIBLE) > 0


class TestEndToEndMatrixGeneration:
    """Sociable test that exercises extract_image_targets through build_matrix_output."""

    def test_full_pipeline(self, tmp_path: Path) -> None:
        makefile_output = (
            "all-images: jupyter-minimal-ubi9-python-3.12 codeserver-ubi9-python-3.12"
            " runtime-minimal-ubi9-python-3.12\n"
        )
        with patch("makefile_helper.dry_run_makefile", return_value=makefile_output):
            targets = gm.extract_image_targets(makefile_dir=tmp_path)

        targets = gm.filter_rhel_images(targets, gm.RhelImages.INCLUDE)
        targets_with_platform = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        output = gm.build_matrix_output(targets_with_platform)

        matrix = json.loads(output[0].removeprefix("matrix="))
        entries = matrix["include"]

        target_platform_pairs = {(e["target"], e["platform"]) for e in entries}
        assert ("jupyter-minimal-ubi9-python-3.12", "linux/amd64") in target_platform_pairs
        assert ("jupyter-minimal-ubi9-python-3.12", "linux/ppc64le") in target_platform_pairs
        assert ("jupyter-minimal-ubi9-python-3.12", "linux/s390x") in target_platform_pairs
        assert ("codeserver-ubi9-python-3.12", "linux/amd64") in target_platform_pairs
        assert ("codeserver-ubi9-python-3.12", "linux/arm64") in target_platform_pairs
        assert ("runtime-minimal-ubi9-python-3.12", "linux/amd64") in target_platform_pairs
        assert ("runtime-minimal-ubi9-python-3.12", "linux/s390x") in target_platform_pairs

        assert output[1] == "has_jobs=true"

    def test_full_pipeline_with_rhel_exclude(self, tmp_path: Path) -> None:
        makefile_output = "all-images: jupyter-minimal-ubi9-python-3.12 runtime-rhel9-python-3.12\n"
        with patch("makefile_helper.dry_run_makefile", return_value=makefile_output):
            targets = gm.extract_image_targets(makefile_dir=tmp_path)

        targets = gm.filter_rhel_images(targets, gm.RhelImages.EXCLUDE)
        targets_with_platform = gm.assign_platforms(
            targets,
            arm64_images=gm.Arm64Images.INCLUDE,
            ppc64le_images=gm.Ppc64leImages.INCLUDE,
            s390x_images=gm.S390xImages.INCLUDE,
        )
        output = gm.build_matrix_output(targets_with_platform)

        matrix = json.loads(output[0].removeprefix("matrix="))
        target_names = {e["target"] for e in matrix["include"]}
        assert "runtime-rhel9-python-3.12" not in target_names
        assert "jupyter-minimal-ubi9-python-3.12" in target_names

    def test_full_pipeline_empty_makefile(self, tmp_path: Path) -> None:
        with patch("makefile_helper.dry_run_makefile", return_value=""):
            with pytest.raises(Exception, match="No image dependencies found"):
                gm.extract_image_targets(makefile_dir=tmp_path)
