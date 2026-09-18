#!/usr/bin/env python3
"""Guard against accidental changes to git submodule references.

The local mode is intended for the commit-msg pre-commit hook.  It checks
staged gitlinks and permits them only when the commit message includes the
``[submodule-update]`` marker or ``ALLOW_SUBMODULE_CHANGE=1`` is set.

CI mode checks every commit in a pull request range and requires the marker
on every commit that changes a declared submodule path.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

MARKER = re.compile(r"\[submodule-update\]", re.IGNORECASE)
GITLINK_MODE = "160000"


class GuardError(RuntimeError):
    """An error that must fail the guard closed."""


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run *command* and turn process-launch errors into guard failures."""
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise GuardError(f"could not run {' '.join(command)}: {exc}") from exc


def _git_error(action: str, result: subprocess.CompletedProcess[str]) -> GuardError:
    detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic was provided"
    return GuardError(f"{action}: {detail}")


def get_submodule_paths() -> list[str]:
    """Read declared submodule paths, distinguishing an empty file from errors."""
    gitmodules = Path(".gitmodules")
    if not gitmodules.exists():
        return []
    if not gitmodules.is_file():
        raise GuardError("cannot read .gitmodules: path is not a regular file")

    result = _run(
        [
            "git",
            "config",
            "--file",
            str(gitmodules),
            "--get-regexp",
            r"^submodule\..*\.path$",
        ]
    )
    if result.returncode == 1 and not result.stderr.strip():
        return []
    if result.returncode != 0:
        raise _git_error("failed to read .gitmodules", result)

    paths: list[str] = []
    for line in result.stdout.splitlines():
        fields = line.split(None, 1)
        if len(fields) != 2 or not fields[1]:
            raise GuardError(f"failed to read .gitmodules: malformed entry {line!r}")
        paths.append(fields[1])
    return paths


def _raw_diff_paths(output: str) -> list[tuple[str, bool]]:
    """Parse ``git diff --raw -z`` into (path, is_gitlink) records."""
    fields = output.split("\0")
    records: list[tuple[str, bool]] = []
    index = 0
    while index < len(fields) and fields[index]:
        metadata = fields[index]
        index += 1
        if not metadata.startswith(":"):
            raise GuardError(f"malformed git diff output: {metadata!r}")
        metadata_fields = metadata[1:].split()
        if len(metadata_fields) < 5:
            raise GuardError(f"malformed git diff output: {metadata!r}")
        old_mode, new_mode, status = metadata_fields[0], metadata_fields[1], metadata_fields[4]
        path_count = 2 if status[0] in "RC" else 1
        paths = fields[index : index + path_count]
        if len(paths) != path_count or any(not path for path in paths):
            raise GuardError("malformed NUL-delimited git diff output")
        index += path_count
        is_gitlink = GITLINK_MODE in (old_mode, new_mode)
        records.extend((path, is_gitlink) for path in paths)
    return records


def _changed_submodules_staged(submodule_paths: list[str]) -> list[str]:
    """Return declared submodule paths changed in the index."""
    result = _run(["git", "diff", "--cached", "--raw", "-z", "--ignore-submodules=none"])
    if result.returncode != 0:
        raise _git_error("failed to inspect staged changes", result)
    declared = set(submodule_paths)
    return list(
        dict.fromkeys(path for path, is_gitlink in _raw_diff_paths(result.stdout) if is_gitlink and path in declared)
    )


def _commits_in_range(base_ref: str) -> list[str]:
    """Return commits in *base_ref*..HEAD, oldest first."""
    result = _run(["git", "rev-list", "--reverse", f"{base_ref}..HEAD"])
    if result.returncode != 0:
        raise _git_error(f"failed to list commits for {base_ref!r}..HEAD", result)
    return [sha for sha in result.stdout.splitlines() if sha]


def _commit_changed_files(sha: str) -> list[str]:
    """Return paths changed by a commit, including root and merge parents."""
    result = _run(
        [
            "git",
            "diff-tree",
            "-c",
            "--root",
            "--no-commit-id",
            "-r",
            "--name-only",
            "-z",
            "--ignore-submodules=none",
            sha,
        ]
    )
    if result.returncode != 0:
        raise _git_error(f"failed to inspect commit {sha}", result)
    return list(dict.fromkeys(path for path in result.stdout.split("\0") if path))


def _commit_message(sha: str) -> str:
    """Return a commit's complete message."""
    result = _run(["git", "show", "-s", "--format=%B", sha])
    if result.returncode != 0:
        raise _git_error(f"failed to read commit message for {sha}", result)
    return result.stdout


def check_local(commit_msg_file: str, submodule_paths: list[str]) -> int:
    """Check staged gitlinks for the local commit-msg hook."""
    changed = _changed_submodules_staged(submodule_paths)
    if not changed:
        return 0

    if os.environ.get("ALLOW_SUBMODULE_CHANGE") == "1":
        print("✅  ALLOW_SUBMODULE_CHANGE=1 set — submodule change permitted.")
        return 0

    try:
        commit_message = Path(commit_msg_file).read_text(encoding="utf-8")
    except OSError as exc:
        raise GuardError(f"cannot read commit-message file: {exc}") from exc
    if MARKER.search(commit_message):
        print("✅  [submodule-update] marker found — submodule change permitted.")
        return 0

    print(
        "⚠️   Submodule reference change detected!\n\n"
        + "\n".join(f"   • {path}" for path in changed)
        + "\n\nIf intentional, add [submodule-update] anywhere in the commit message, "
        "or use ALLOW_SUBMODULE_CHANGE=1 for this local commit.\n"
        "If accidental, unstage the pointer change with `git restore --staged -- <path>` "
        "then synchronize the worktree with `git submodule update --init --recursive`.\n",
        file=sys.stderr,
    )
    return 1


def check_ci(base_ref: str, submodule_paths: list[str]) -> int:
    """Check every commit in a pull request range."""
    commits = _commits_in_range(base_ref)
    if not submodule_paths:
        print("✅  No submodules found in .gitmodules — nothing to guard.")
        return 0
    if not commits:
        print("✅  No commits in range — nothing to check.")
        return 0

    declared = set(submodule_paths)
    offenders: list[tuple[str, list[str]]] = []
    for sha in commits:
        touched = [path for path in _commit_changed_files(sha) if path in declared]
        if touched and not MARKER.search(_commit_message(sha)):
            offenders.append((sha, touched))

    if not offenders:
        print("✅  All submodule changes (if any) are marked with [submodule-update].")
        return 0

    print(
        "❌  The following commits change submodule references without the [submodule-update] marker:\n",
        file=sys.stderr,
    )
    for sha, paths in offenders:
        subject = _commit_message(sha).split("\n", 1)[0].strip()
        print(f"   • {sha}  {subject}", file=sys.stderr)
        for path in paths:
            print(f"        — {path}", file=sys.stderr)
    return 1


def create_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Guard against accidental submodule reference bumps.")
    parser.add_argument("commit_msg_file", nargs="?", help="Commit-message file for local mode.")
    parser.add_argument("--ci", action="store_true", help="Check all commits in a pull request range.")
    parser.add_argument("--base-ref", help="Base ref for CI mode.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the selected guard."""
    parser = create_parser()
    args = parser.parse_args(argv)
    if args.ci and not args.base_ref:
        parser.error("--base-ref is required in CI mode")
    if not args.ci and args.base_ref:
        parser.error("--base-ref requires --ci")
    if not args.ci and args.commit_msg_file is None:
        parser.error("commit_msg_file is required in local mode (or use --ci)")
    if args.ci and args.commit_msg_file is not None:
        parser.error("commit_msg_file cannot be used in CI mode")

    try:
        submodule_paths = get_submodule_paths()
        if args.ci:
            return check_ci(args.base_ref, submodule_paths)
        if not submodule_paths:
            print("✅  No submodules found in .gitmodules — nothing to guard.")
            return 0
        commit_msg_file = args.commit_msg_file
        assert isinstance(commit_msg_file, str)
        return check_local(commit_msg_file, submodule_paths)
    except GuardError as exc:
        print(f"❌  {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
