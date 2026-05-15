"""
Unit tests for ci/check_generated_tree_clean.py

Tests the lenient vs strict mode logic for RHAIENG-4443.
"""

import os
from unittest.mock import patch

import pytest

from ci.check_generated_tree_clean import CheckConfig, GeneratedTreeChecker


class TestCheckConfig:
    """Test the CheckConfig dataclass."""

    def test_lock_patterns_defined(self):
        """Verify lock artifact patterns are defined."""
        config = CheckConfig()
        assert len(config.LOCK_ARTIFACT_PATTERNS) > 0
        assert any("pylock" in p for p in config.LOCK_ARTIFACT_PATTERNS)

    def test_generator_entrypoints_defined(self):
        """Verify generator entrypoints are defined."""
        config = CheckConfig()
        assert len(config.GENERATOR_ENTRYPOINTS) > 0
        assert "scripts/dockerfile_fragments.py" in config.GENERATOR_ENTRYPOINTS


class TestGeneratedTreeChecker:
    """Test the GeneratedTreeChecker class."""

    @pytest.fixture
    def checker(self):
        """Create a checker instance."""
        config = CheckConfig()
        return GeneratedTreeChecker(config)

    def test_is_lock_artifact_matches_pylock(self, checker):
        """Test lock artifact detection for pylock.toml files."""
        assert checker.is_lock_artifact("jupyter/minimal/uv.lock.d/pylock.cpu.toml")
        assert checker.is_lock_artifact("jupyter/minimal/uv.lock.d/pylock.cuda.toml")
        assert checker.is_lock_artifact("jupyter/minimal/uv.lock.d/pylock.rocm.toml")

    def test_is_lock_artifact_matches_requirements(self, checker):
        """Test lock artifact detection for requirements.txt files."""
        assert checker.is_lock_artifact("jupyter/minimal/requirements.cpu.txt")
        assert checker.is_lock_artifact("jupyter/minimal/requirements.cuda.txt")
        assert checker.is_lock_artifact("jupyter/minimal/requirements.rocm.txt")

    def test_is_lock_artifact_matches_uv_lock(self, checker):
        """Test lock artifact detection for uv.lock files."""
        assert checker.is_lock_artifact("jupyter/minimal/uv.lock")
        assert checker.is_lock_artifact("some/other/path/uv.lock")

    def test_is_lock_artifact_rejects_non_locks(self, checker):
        """Test that non-lock files are not matched."""
        assert not checker.is_lock_artifact("jupyter/minimal/Dockerfile.cpu")
        assert not checker.is_lock_artifact("scripts/dockerfile_fragments.py")
        assert not checker.is_lock_artifact("jupyter/minimal/pyproject.toml")
        assert not checker.is_lock_artifact("README.md")

    def test_get_directory(self, checker):
        """Test directory extraction from file paths."""
        assert checker.get_directory("jupyter/minimal/Dockerfile.cpu") == "jupyter/minimal"
        assert checker.get_directory("scripts/test.py") == "scripts"
        assert checker.get_directory("file.txt") == "."

    def test_get_top_level_directory(self, checker):
        """Test top-level directory extraction from file paths."""
        # Multi-project dirs (jupyter/, runtimes/, codeserver/) use first two components
        assert checker.get_top_level_directory("jupyter/minimal/Dockerfile.cpu") == "jupyter/minimal"
        assert checker.get_top_level_directory("jupyter/minimal/uv.lock.d/pylock.cpu.toml") == "jupyter/minimal"
        assert checker.get_top_level_directory("jupyter/trustyai/src/test.py") == "jupyter/trustyai"
        assert checker.get_top_level_directory("runtimes/minimal/Dockerfile") == "runtimes/minimal"
        assert (
            checker.get_top_level_directory("codeserver/ubi9-python-3.12/Dockerfile.cpu")
            == "codeserver/ubi9-python-3.12"
        )

        # Other dirs use first component only
        assert checker.get_top_level_directory("scripts/test.py") == "scripts"
        assert checker.get_top_level_directory("scripts/lockfile-generators/rpm.py") == "scripts"
        assert checker.get_top_level_directory("ci/check_generated_tree_clean.py") == "ci"
        assert checker.get_top_level_directory("dependencies/python.yaml") == "dependencies"
        assert checker.get_top_level_directory("file.txt") == "file.txt"

    def test_pr_touched_generator_entrypoint_detects_fragments(self, checker):
        """Test detection when dockerfile_fragments.py is modified."""
        pr_files = {"scripts/dockerfile_fragments.py", "jupyter/minimal/Dockerfile.cpu"}
        assert checker.pr_touched_generator_entrypoint(pr_files)

    def test_pr_touched_generator_entrypoint_detects_pylocks(self, checker):
        """Test detection when pylocks_generator.py is modified."""
        pr_files = {"scripts/pylocks_generator.py"}
        assert checker.pr_touched_generator_entrypoint(pr_files)

    def test_pr_touched_generator_entrypoint_detects_dependencies(self, checker):
        """Test detection when dependencies/ is modified."""
        pr_files = {"dependencies/python.yaml"}
        assert checker.pr_touched_generator_entrypoint(pr_files)

    def test_pr_touched_generator_entrypoint_detects_lockfile_generators(self, checker):
        """Test detection when lockfile-generators/ is modified."""
        pr_files = {"scripts/lockfile-generators/rpm-lockfile.py"}
        assert checker.pr_touched_generator_entrypoint(pr_files)

    def test_pr_touched_generator_entrypoint_ignores_unrelated(self, checker):
        """Test that unrelated file changes don't trigger generator detection."""
        pr_files = {"jupyter/minimal/Dockerfile.cpu", "README.md"}
        assert not checker.pr_touched_generator_entrypoint(pr_files)

    @patch.object(GeneratedTreeChecker, "get_dirty_files")
    def test_check_strict_mode_passes_on_clean_tree(self, mock_dirty, checker):
        """Test strict mode passes when tree is clean."""
        mock_dirty.return_value = []
        assert checker.check_strict_mode([]) == 0

    @patch.object(GeneratedTreeChecker, "get_dirty_files")
    @patch("subprocess.run")
    def test_check_strict_mode_fails_on_dirty_tree(self, mock_run, mock_dirty, checker):
        """Test strict mode fails when tree has changes."""
        dirty_files = ["jupyter/minimal/Dockerfile.cpu"]
        assert checker.check_strict_mode(dirty_files) == 1

    @patch.object(GeneratedTreeChecker, "get_pr_touched_files")
    @patch.object(GeneratedTreeChecker, "get_dirty_files")
    def test_check_lenient_mode_ignores_locks_in_untouched_dirs(self, mock_dirty, mock_pr_files, checker):
        """Test lenient mode ignores lock changes in directories not touched by PR."""
        # PR only touches jupyter/minimal
        mock_pr_files.return_value = {"jupyter/minimal/Dockerfile.cpu"}

        # Lock changes in jupyter/trustyai (not touched by PR)
        dirty_files = ["jupyter/trustyai/uv.lock.d/pylock.cpu.toml"]
        mock_dirty.return_value = dirty_files

        assert checker.check_lenient_mode(dirty_files, "abc123") == 0

    @patch.object(GeneratedTreeChecker, "get_pr_touched_files")
    @patch.object(GeneratedTreeChecker, "get_dirty_files")
    @patch("subprocess.run")
    def test_check_lenient_mode_fails_on_locks_in_touched_dirs(self, mock_run, mock_dirty, mock_pr_files, checker):
        """Test lenient mode fails when lock changes are in PR-touched directories."""
        # PR touches jupyter/minimal
        mock_pr_files.return_value = {"jupyter/minimal/Dockerfile.cpu"}

        # Lock changes in the same directory
        dirty_files = ["jupyter/minimal/uv.lock.d/pylock.cpu.toml"]
        mock_dirty.return_value = dirty_files

        assert checker.check_lenient_mode(dirty_files, "abc123") == 1

    @patch.object(GeneratedTreeChecker, "get_pr_touched_files")
    @patch.object(GeneratedTreeChecker, "get_dirty_files")
    @patch("subprocess.run")
    def test_check_lenient_mode_fails_on_non_lock_changes(self, mock_run, mock_dirty, mock_pr_files, checker):
        """Test lenient mode fails on non-lock file changes."""
        # PR touches one directory
        mock_pr_files.return_value = {"jupyter/minimal/Dockerfile.cpu"}

        # Non-lock file changed in different directory
        dirty_files = ["scripts/test.py"]
        mock_dirty.return_value = dirty_files

        assert checker.check_lenient_mode(dirty_files, "abc123") == 1

    @patch.object(GeneratedTreeChecker, "get_pr_touched_files")
    @patch.object(GeneratedTreeChecker, "pr_touched_generator_entrypoint")
    @patch.object(GeneratedTreeChecker, "check_strict_mode")
    def test_check_lenient_mode_strict_when_generator_touched(
        self, mock_strict, mock_gen_touched, mock_pr_files, checker
    ):
        """Test lenient mode falls back to strict when generator is modified."""
        mock_pr_files.return_value = {"scripts/dockerfile_fragments.py"}
        mock_gen_touched.return_value = True
        mock_strict.return_value = 1

        dirty_files = ["jupyter/minimal/uv.lock.d/pylock.cpu.toml"]
        assert checker.check_lenient_mode(dirty_files, "abc123") == 1
        mock_strict.assert_called_once()


class TestMainLogic:
    """Test the main entry point logic."""

    @patch.object(GeneratedTreeChecker, "get_dirty_files")
    @patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push"})
    def test_main_uses_strict_mode_for_push_events(self, mock_dirty):
        """Test that push events use strict mode."""
        mock_dirty.return_value = []
        config = CheckConfig()
        checker = GeneratedTreeChecker(config)

        with patch.object(checker, "check_strict_mode") as mock_strict:
            mock_strict.return_value = 0
            checker.run()
            mock_strict.assert_called_once()

    @patch.object(GeneratedTreeChecker, "get_dirty_files")
    @patch.dict(
        os.environ,
        {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_BASE_SHA": "abc123"},
    )
    def test_main_uses_lenient_mode_for_pr_events(self, mock_dirty):
        """Test that PR events use lenient mode when base SHA is available."""
        mock_dirty.return_value = []
        config = CheckConfig()
        checker = GeneratedTreeChecker(config)

        with patch.object(checker, "check_lenient_mode") as mock_lenient:
            mock_lenient.return_value = 0
            checker.run()
            mock_lenient.assert_called_once()

    @patch.object(GeneratedTreeChecker, "get_dirty_files")
    @patch.dict(os.environ, {"GITHUB_EVENT_NAME": "pull_request"})
    def test_main_uses_strict_mode_for_pr_without_base_sha(self, mock_dirty):
        """Test that PR events without base SHA fall back to strict mode."""
        mock_dirty.return_value = []
        config = CheckConfig()
        checker = GeneratedTreeChecker(config)

        with patch.object(checker, "check_strict_mode") as mock_strict:
            mock_strict.return_value = 0
            checker.run()
            mock_strict.assert_called_once()
