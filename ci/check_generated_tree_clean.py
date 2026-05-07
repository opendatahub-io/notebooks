#!/usr/bin/env python3
"""
Check that the working tree is clean after running code generators.

RHAIENG-4443: Handle AIPCC index churn gracefully in CI.

This script implements a two-mode check:
- STRICT mode (main branch pushes): Fails on ANY modified files
- LENIENT mode (pull requests): Allows lock file changes in directories
  not touched by the PR, but fails if lock changes are in modified directories
  or if any generator entrypoint was touched.

The lenient mode prevents false-positive CI failures when the AIPCC index
publishes new wheel builds (same version, different hash) that fall within
the --exclude-newer window, causing lock regeneration unrelated to PR changes.
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass
class CheckConfig:
    """Configuration for the generated tree cleanliness check."""

    # Patterns matching lock artifact files (regex)
    LOCK_ARTIFACT_PATTERNS: ClassVar[list[str]] = [
        r".*\/uv\.lock\.d\/pylock\.(cpu|cuda|rocm)\.toml$",
        r".*\/requirements\.(cpu|cuda|rocm)\.txt$",
        r".*\/uv\.lock$",
    ]

    # Paths that, if modified in a PR, trigger strict checking
    # (any of these touched = treat all dirty files as failures)
    GENERATOR_ENTRYPOINTS: ClassVar[list[str]] = [
        "scripts/dockerfile_fragments.py",
        "manifests/tools/generate_kustomization.py",
        "scripts/pylocks_generator.py",
        "scripts/lockfile-generators/",
        "dependencies/",
    ]


class GeneratedTreeChecker:
    """Check if the working tree is clean after running code generators."""

    def __init__(self, config: CheckConfig):
        self.config = config
        self.repo_root = self._get_repo_root()

    def _get_repo_root(self) -> Path:
        """Get the repository root directory."""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())

    def _run_git_command(self, args: list[str]) -> str:
        """Run a git command and return stdout."""
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
            cwd=self.repo_root,
        )
        return result.stdout.strip()

    def get_dirty_files(self) -> list[str]:
        """Get list of modified/untracked files in the working tree."""
        porcelain_output = self._run_git_command(["status", "--porcelain"])
        if not porcelain_output:
            return []
        return [line.split(None, 1)[1] for line in porcelain_output.split("\n") if line]

    def is_lock_artifact(self, file_path: str) -> bool:
        """Check if a file matches lock artifact patterns."""
        return any(re.match(pattern, file_path) for pattern in self.config.LOCK_ARTIFACT_PATTERNS)

    def get_pr_touched_files(self, base_sha: str) -> set[str]:
        """Get files modified in the PR (diff from base to HEAD)."""
        try:
            diff_output = self._run_git_command(["diff", "--name-only", f"{base_sha}...HEAD"])
            if not diff_output:
                return set()
            return set(diff_output.split("\n"))
        except subprocess.CalledProcessError:
            print(f"::warning::Could not determine PR diff from base {base_sha}")
            return set()

    def get_directory(self, file_path: str) -> str:
        """Get the directory containing a file."""
        return str(Path(file_path).parent)

    def get_top_level_directory(self, file_path: str) -> str:
        """
        Get the top-level project directory for a file.

        For multi-project directories (jupyter/, runtimes/, codeserver/),
        returns first two components (e.g., jupyter/minimal).
        For other directories, returns just the first component (e.g., scripts).

        Examples:
            jupyter/minimal/Dockerfile.cpu -> jupyter/minimal
            jupyter/minimal/uv.lock.d/pylock.cpu.toml -> jupyter/minimal
            scripts/test.py -> scripts
            scripts/lockfile-generators/rpm.py -> scripts/lockfile-generators
        """
        parts = Path(file_path).parts
        if len(parts) == 0:
            return "."

        # Multi-project directories where each subdir is a separate project
        MULTI_PROJECT_DIRS = {"jupyter", "runtimes", "codeserver"}

        if parts[0] in MULTI_PROJECT_DIRS:
            # Use first two components for multi-project dirs
            if len(parts) >= 2:
                return str(Path(parts[0]) / parts[1])
            return parts[0]
        else:
            # For other directories, just use the first component
            return parts[0]

    def pr_touched_generator_entrypoint(self, pr_files: set[str]) -> bool:
        """Check if any generator entrypoint was modified in the PR."""
        for file_path in pr_files:
            for entrypoint in self.config.GENERATOR_ENTRYPOINTS:
                if file_path.startswith(entrypoint):
                    return True
        return False

    def check_strict_mode(self, dirty_files: list[str]) -> int:
        """
        Strict mode: fail on any dirty files.

        Used for main branch pushes where all changes should be committed.
        """
        if not dirty_files:
            print("✓ Working tree is clean (strict mode)")
            return 0

        print("::error::Working tree has uncommitted changes (strict mode)")
        print("::error::Please run 'bash ci/generate_code.sh', commit the changed files, and push again.")
        print(f"\nUncommitted files ({len(dirty_files)}):")
        for file in dirty_files:
            print(f"  - {file}")

        # Show full diff for context
        print("\n" + "=" * 80)
        print("Full diff:")
        print("=" * 80)
        subprocess.run(["git", "diff"], cwd=self.repo_root, check=False)

        return 1

    def check_lenient_mode(self, dirty_files: list[str], base_sha: str) -> int:
        """
        Lenient mode: allow lock changes in untouched directories.

        Used for pull requests to handle AIPCC index churn. Allows lock file
        changes in directories not modified by the PR, but fails if:
        - Lock changes are in directories touched by the PR
        - Any generator entrypoint was modified
        - Non-lock files are dirty
        """
        if not dirty_files:
            print("✓ Working tree is clean (lenient mode)")
            return 0

        # Get files modified in the PR
        pr_files = self.get_pr_touched_files(base_sha)
        if not pr_files:
            print("::warning::Could not determine PR changes, falling back to strict check")
            return self.check_strict_mode(dirty_files)

        # Check if any generator entrypoint was touched
        if self.pr_touched_generator_entrypoint(pr_files):
            print("::error::Generator entrypoint was modified in PR, all dirty files must be committed")
            print("\nGenerator entrypoints modified:")
            for file_path in sorted(pr_files):
                for entrypoint in self.config.GENERATOR_ENTRYPOINTS:
                    if file_path.startswith(entrypoint):
                        print(f"  - {file_path}")
            return self.check_strict_mode(dirty_files)

        # Classify dirty files
        # Use top-level directories (e.g., jupyter/minimal) for comparison
        # so that lock files in subdirectories (e.g., jupyter/minimal/uv.lock.d/)
        # are correctly associated with PR changes in parent directories
        pr_top_dirs = {self.get_top_level_directory(f) for f in pr_files}
        dirty_locks_in_pr_dirs = []
        dirty_locks_in_other_dirs = []
        dirty_non_locks = []

        for file in dirty_files:
            file_top_dir = self.get_top_level_directory(file)
            if self.is_lock_artifact(file):
                if file_top_dir in pr_top_dirs:
                    dirty_locks_in_pr_dirs.append(file)
                else:
                    dirty_locks_in_other_dirs.append(file)
            else:
                dirty_non_locks.append(file)

        # Report findings
        has_errors = False

        if dirty_locks_in_other_dirs:
            print(
                f"INFO: Ignoring {len(dirty_locks_in_other_dirs)} lock file(s) "
                "in directories not touched by this PR (likely AIPCC index churn):"
            )
            for file in sorted(dirty_locks_in_other_dirs):
                print(f"  - {file}")
            print()

        if dirty_locks_in_pr_dirs:
            print(
                f"::error::Found {len(dirty_locks_in_pr_dirs)} modified lock file(s) in directories touched by this PR:"
            )
            for file in sorted(dirty_locks_in_pr_dirs):
                print(f"  - {file}")
            print("These changes must be committed.\n")
            has_errors = True

        if dirty_non_locks:
            print(f"::error::Found {len(dirty_non_locks)} modified non-lock file(s):")
            for file in sorted(dirty_non_locks):
                print(f"  - {file}")
            print("These changes must be committed.\n")
            has_errors = True

        if has_errors:
            print("=" * 80)
            print("Files that must be committed:")
            print("=" * 80)
            for file in sorted(dirty_locks_in_pr_dirs + dirty_non_locks):
                print(f"  - {file}")
            print("\nPlease run 'bash ci/generate_code.sh', commit the files above, and push again.")
            print("\n" + "=" * 80)
            print("Full diff:")
            print("=" * 80)
            subprocess.run(["git", "diff"], cwd=self.repo_root, check=False)
            return 1

        print("✓ Working tree is acceptable (lenient mode)")
        return 0

    def run(self) -> int:
        """
        Main entry point for the check.

        Determines mode based on environment variables:
        - GITHUB_EVENT_NAME: 'pull_request' triggers lenient mode
        - GITHUB_BASE_SHA: Required for lenient mode (PR base commit)

        Returns:
            0 if check passes, 1 if check fails
        """
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        base_sha = os.environ.get("GITHUB_BASE_SHA", "")

        # Get dirty files
        dirty_files = self.get_dirty_files()

        # Determine mode
        is_pull_request = event_name == "pull_request"
        has_base_sha = bool(base_sha)

        if is_pull_request and has_base_sha:
            print(f"Running in LENIENT mode (PR against base {base_sha[:8]})\n")
            return self.check_lenient_mode(dirty_files, base_sha)
        else:
            mode_reason = "not a pull request" if not is_pull_request else "missing GITHUB_BASE_SHA"
            print(f"Running in STRICT mode ({mode_reason})\n")
            return self.check_strict_mode(dirty_files)


def main() -> int:
    """Main entry point."""
    config = CheckConfig()
    checker = GeneratedTreeChecker(config)
    return checker.run()


if __name__ == "__main__":
    sys.exit(main())
