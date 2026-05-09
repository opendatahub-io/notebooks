"""Unit tests for ci/check-params-env.sh validation logic.

Tests the shell functions via subprocess with fixture env files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "ci" / "check-params-env.sh"


def _get_functions_source() -> str:
    """Extract function definitions and global variables (everything before the MAIN SCRIPT section)."""
    lines = _SCRIPT_PATH.read_text().splitlines()
    for i, line in enumerate(lines):
        if "MAIN SCRIPT" in line:
            return "\n".join(lines[:i])
    raise RuntimeError("Could not find MAIN SCRIPT marker in ci/check-params-env.sh")


_FUNCTIONS_SOURCE = _get_functions_source()


def _run_bash(script_body: str) -> subprocess.CompletedProcess[str]:
    """Run a bash snippet with the script's functions and global variables pre-loaded."""
    full_script = f"{_FUNCTIONS_SOURCE}\n{script_body}"
    return subprocess.run(
        ["bash", "-c", full_script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


# --------------- check_variables_uniq ---------------


class TestCheckVariablesUniq:
    def test_unique_variables_pass(self, tmp_path: Path) -> None:
        f1 = tmp_path / "env1.env"
        f2 = tmp_path / "env2.env"
        f1.write_text("VAR_A=value_a\nVAR_B=value_b\n")
        f2.write_text("VAR_C=value_c\n")
        result = _run_bash(f'EXPECTED_NUM_RECORDS=3\ncheck_variables_uniq "{f1}" "{f2}" "false"')
        assert result.returncode == 0

    def test_duplicate_variable_names_fail(self, tmp_path: Path) -> None:
        f1 = tmp_path / "env1.env"
        f2 = tmp_path / "env2.env"
        f1.write_text("VAR_A=value_a\nVAR_A=value_b\n")
        f2.write_text("VAR_C=value_c\n")
        result = _run_bash(f'EXPECTED_NUM_RECORDS=3\ncheck_variables_uniq "{f1}" "{f2}" "false"')
        assert result.returncode != 0
        assert "variables" in result.stdout.lower()
        assert "unique" in result.stdout.lower()

    def test_duplicate_values_fail_when_not_allowed(self, tmp_path: Path) -> None:
        f1 = tmp_path / "env1.env"
        f2 = tmp_path / "env2.env"
        f1.write_text("VAR_A=same_value\nVAR_B=same_value\n")
        f2.write_text("VAR_C=other_value\n")
        result = _run_bash(f'EXPECTED_NUM_RECORDS=3\ncheck_variables_uniq "{f1}" "{f2}" "false"')
        assert result.returncode != 0
        assert "values" in result.stdout.lower()

    def test_duplicate_values_pass_when_allowed(self, tmp_path: Path) -> None:
        f1 = tmp_path / "env1.env"
        f2 = tmp_path / "env2.env"
        f1.write_text("VAR_A=same_value\nVAR_B=same_value\n")
        f2.write_text("VAR_C=other_value\n")
        result = _run_bash(f'EXPECTED_NUM_RECORDS=3\ncheck_variables_uniq "{f1}" "{f2}" "true"')
        assert result.returncode == 0

    def test_wrong_record_count_fails(self, tmp_path: Path) -> None:
        f1 = tmp_path / "env1.env"
        f2 = tmp_path / "env2.env"
        f1.write_text("VAR_A=value_a\nVAR_B=value_b\n")
        f2.write_text("VAR_C=value_c\n")
        result = _run_bash(f'EXPECTED_NUM_RECORDS=99\ncheck_variables_uniq "{f1}" "{f2}" "false"')
        assert result.returncode != 0
        assert "incorrect" in result.stdout.lower()

    def test_comments_and_blanks_are_skipped(self, tmp_path: Path) -> None:
        f1 = tmp_path / "env1.env"
        f2 = tmp_path / "env2.env"
        f1.write_text("# comment\n\nVAR_A=value_a\n\n# another\nVAR_B=value_b\n")
        f2.write_text("")
        result = _run_bash(f'EXPECTED_NUM_RECORDS=2\ncheck_variables_uniq "{f1}" "{f2}" "false"')
        assert result.returncode == 0

    def test_dummy_values_excluded_from_uniqueness(self, tmp_path: Path) -> None:
        f1 = tmp_path / "env1.env"
        f2 = tmp_path / "env2.env"
        f1.write_text("VAR_A=dummy\nVAR_B=dummy\n")
        f2.write_text("VAR_C=unique_value\n")
        result = _run_bash(f'EXPECTED_NUM_RECORDS=3\ncheck_variables_uniq "{f1}" "{f2}" "false"')
        assert result.returncode == 0

    def test_cross_file_duplicate_names_detected(self, tmp_path: Path) -> None:
        f1 = tmp_path / "env1.env"
        f2 = tmp_path / "env2.env"
        f1.write_text("SHARED=value_a\n")
        f2.write_text("SHARED=value_b\n")
        result = _run_bash(f'EXPECTED_NUM_RECORDS=2\ncheck_variables_uniq "{f1}" "{f2}" "false"')
        assert result.returncode != 0
        assert "variables" in result.stdout.lower()


# --------------- check_image_variable_matches_name_and_commitref_and_size ---------------


class TestImageVariableMatchesMetadata:
    def test_correct_metadata_passes(self) -> None:
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-minimal-ubi9-python-3.12" '
            '"main" "konflux" 1017'
        )
        assert result.returncode == 0

    def test_wrong_image_name_fails(self) -> None:
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"wrong-image-name" '
            '"main" "konflux" 1017'
        )
        assert result.returncode != 0
        assert "incorrect image" in result.stdout.lower()

    def test_wrong_build_name_fails(self) -> None:
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-minimal-ubi9-python-3.12" '
            '"main" "wrong-build" 1017'
        )
        assert result.returncode != 0
        assert "OPENSHIFT_BUILD_NAME" in result.stdout

    def test_unimplemented_variable_fails(self) -> None:
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"nonexistent-image-variable" '
            '"some-name" "main" "konflux" 1000'
        )
        assert result.returncode != 0
        assert "Unimplemented" in result.stdout

    def test_empty_commitref_skips_check(self) -> None:
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-minimal-ubi9-python-3.12" '
            '"" "konflux" 1017'
        )
        assert result.returncode == 0

    def test_wrong_commitref_fails(self) -> None:
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-minimal-ubi9-python-3.12" '
            '"wrong-branch" "konflux" 1017'
        )
        assert result.returncode != 0
        assert "commitref" in result.stdout.lower()


# --------------- Size threshold calculations ---------------


class TestSizeThresholdCalculations:
    def test_size_within_bounds_passes(self) -> None:
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-minimal-ubi9-python-3.12" '
            '"main" "konflux" 1017'
        )
        assert result.returncode == 0

    def test_size_under_expected_within_bounds_passes(self) -> None:
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-minimal-ubi9-python-3.12" '
            '"main" "konflux" 950'
        )
        assert result.returncode == 0

    def test_size_exceeds_percentual_threshold_fails(self) -> None:
        # expected=1017; 1200 is ~18% over → exceeds 10% threshold
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-minimal-ubi9-python-3.12" '
            '"main" "konflux" 1200'
        )
        assert result.returncode != 0
        assert "%" in result.stdout

    def test_size_exceeds_absolute_threshold_fails(self) -> None:
        # expected=1592 (datascience-n); 1700 is ~7% (within 10%) but diff=108MB (>100MB)
        result = _run_bash(
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-datascience-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-datascience-ubi9-python-3.12" '
            '"main" "konflux" 1700'
        )
        assert result.returncode != 0
        assert "MB" in result.stdout

    def test_custom_tighter_thresholds(self) -> None:
        # Override thresholds to be stricter; 1080 is ~6% over 1017
        result = _run_bash(
            "SIZE_PERCENTUAL_TRESHOLD=5\n"
            "SIZE_ABSOLUTE_TRESHOLD=50\n"
            "check_image_variable_matches_name_and_commitref_and_size "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"odh-notebook-jupyter-minimal-ubi9-python-3.12" '
            '"main" "konflux" 1080'
        )
        assert result.returncode != 0


# --------------- check_image_commit_id_matches_metadata ---------------


class TestCheckImageCommitIdMatchesMetadata:
    def test_matching_commit_id_passes(self, tmp_path: Path) -> None:
        commit_env = tmp_path / "commit.env"
        commit_latest_env = tmp_path / "commit-latest.env"
        commit_env.write_text("odh-workbench-jupyter-minimal-cpu-py312-ubi9-commit-n=abc1234\n")
        commit_latest_env.write_text("")
        result = _run_bash(
            f'COMMIT_ENV_PATH="{commit_env}"\n'
            f'COMMIT_LATEST_ENV_PATH="{commit_latest_env}"\n'
            "check_image_commit_id_matches_metadata "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"abc1234def5678"'
        )
        assert result.returncode == 0

    def test_non_matching_commit_id_fails(self, tmp_path: Path) -> None:
        commit_env = tmp_path / "commit.env"
        commit_latest_env = tmp_path / "commit-latest.env"
        commit_env.write_text("odh-workbench-jupyter-minimal-cpu-py312-ubi9-commit-n=abc1234\n")
        commit_latest_env.write_text("")
        result = _run_bash(
            f'COMMIT_ENV_PATH="{commit_env}"\n'
            f'COMMIT_LATEST_ENV_PATH="{commit_latest_env}"\n'
            "check_image_commit_id_matches_metadata "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"zzz9999def5678"'
        )
        assert result.returncode != 0

    def test_pipeline_runtime_skips_check(self, tmp_path: Path) -> None:
        commit_env = tmp_path / "commit.env"
        commit_latest_env = tmp_path / "commit-latest.env"
        commit_env.write_text("odh-pipeline-runtime-minimal-cpu-py312-ubi9-commit-n=0000000\n")
        commit_latest_env.write_text("")
        result = _run_bash(
            f'COMMIT_ENV_PATH="{commit_env}"\n'
            f'COMMIT_LATEST_ENV_PATH="{commit_latest_env}"\n'
            "check_image_commit_id_matches_metadata "
            '"odh-pipeline-runtime-minimal-cpu-py312-ubi9-n" '
            '"mismatchedcommitid"'
        )
        assert result.returncode == 0

    def test_commit_in_latest_env_passes(self, tmp_path: Path) -> None:
        commit_env = tmp_path / "commit.env"
        commit_latest_env = tmp_path / "commit-latest.env"
        commit_env.write_text("")
        commit_latest_env.write_text("odh-workbench-jupyter-minimal-cpu-py312-ubi9-commit-n=f00ba12\n")
        result = _run_bash(
            f'COMMIT_ENV_PATH="{commit_env}"\n'
            f'COMMIT_LATEST_ENV_PATH="{commit_latest_env}"\n'
            "check_image_commit_id_matches_metadata "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"f00ba12abcdef0"'
        )
        assert result.returncode == 0


# --------------- check_image_repo_name ---------------


class TestCheckImageRepoName:
    def test_matching_repo_name_sha_passes(self) -> None:
        result = _run_bash(
            "check_image_repo_name "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312@sha256:abc123"'
        )
        assert result.returncode == 0

    def test_matching_repo_name_tag_passes(self) -> None:
        result = _run_bash(
            "check_image_repo_name "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312:latest"'
        )
        assert result.returncode == 0

    def test_non_matching_repo_name_fails(self) -> None:
        result = _run_bash(
            "check_image_repo_name "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"quay.io/opendatahub/wrong-repo-name@sha256:abc123"'
        )
        assert result.returncode != 0
        assert "doesn't match" in result.stdout.lower()

    def test_year_version_suffix_stripped(self) -> None:
        result = _run_bash(
            "check_image_repo_name "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-2025-2" '
            '"quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312@sha256:abc123"'
        )
        assert result.returncode == 0

    def test_numeric_version_suffix_stripped(self) -> None:
        result = _run_bash(
            "check_image_repo_name "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-3-4" '
            '"quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312@sha256:abc123"'
        )
        assert result.returncode == 0

    def test_ubi9_suffix_stripped_from_both(self) -> None:
        result = _run_bash(
            "check_image_repo_name "
            '"odh-workbench-jupyter-minimal-cpu-py312-ubi9-n" '
            '"quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9@sha256:abc"'
        )
        assert result.returncode == 0
