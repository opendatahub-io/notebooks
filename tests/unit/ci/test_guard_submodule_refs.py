from __future__ import annotations

import importlib
import os
import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


guard = importlib.import_module("ci.hooks.guard_submodule_refs")

PATH_A = "vendor/a"
PATH_B = "vendor/with spaces/b"
SHA_1 = "1" * 40
SHA_2 = "2" * 40
SHA_3 = "3" * 40


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
        capture_output=True,
        text=True,
        check=check,
    )


def _stage_gitlink(repo: Path, path: str, sha: str) -> None:
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},{path}")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "commit", "--no-gpg-sign", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Use real Git repositories because the guard exercises Git's index and trees."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / ".gitmodules").write_text(
        f'[submodule "a"]\n\tpath = {PATH_A}\n\turl = https://example.invalid/a.git\n'
        f'[submodule "b"]\n\tpath = {PATH_B}\n\turl = https://example.invalid/b.git\n',
    )
    _git(repo, "add", ".gitmodules")
    _stage_gitlink(repo, PATH_A, SHA_1)
    _stage_gitlink(repo, PATH_B, SHA_1)
    base = _commit(repo, "Initial submodule pointers")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.delenv("ALLOW_SUBMODULE_CHANGE", raising=False)
    assert base
    yield repo


def test_unchanged_and_staged_normal_files_are_allowed(git_repo: Path) -> None:
    (git_repo / "ordinary.txt").write_text("ordinary")
    _git(git_repo, "add", "ordinary.txt")
    assert guard.check_local("does-not-exist", [PATH_A, PATH_B]) == 0


def test_unstaged_gitlink_worktree_is_ignored_until_staged(git_repo: Path) -> None:
    nested = git_repo / PATH_A
    nested.mkdir(parents=True)
    _git(nested, "init", "-b", "main")
    _git(nested, "config", "user.name", "Test User")
    _git(nested, "config", "user.email", "test@example.com")
    (nested / "work.txt").write_text("dirty worktree")
    _git(nested, "add", "work.txt")
    _commit(nested, "Nested worktree commit")
    assert guard._changed_submodules_staged([PATH_A]) == []


def test_local_gitlink_requires_marker_and_accepts_case_insensitive_body(
    git_repo: Path,
    tmp_path: Path,
) -> None:
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("Update pointer\n")
    assert guard.check_local(str(message), [PATH_A]) == 1
    message.write_text("Details\n[SuBmOdUlE-UpDaTe] intentional\n")
    assert guard.check_local(str(message), [PATH_A]) == 0


def test_staged_gitlink_paths_are_nul_safe(git_repo: Path) -> None:
    _stage_gitlink(git_repo, PATH_B, SHA_2)
    assert guard._changed_submodules_staged([PATH_B]) == [PATH_B]


def test_local_config_cannot_hide_staged_gitlink(git_repo: Path, tmp_path: Path) -> None:
    _git(git_repo, "config", "diff.ignoreSubmodules", "all")
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("Unmarked pointer\n")
    assert guard.check_local(str(message), [PATH_A]) == 1


def test_local_environment_bypass_is_local_only(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("Update pointer\n")
    monkeypatch.setenv("ALLOW_SUBMODULE_CHANGE", "1")
    assert guard.check_local(str(message), [PATH_A]) == 0
    commit = _commit(git_repo, "Unmarked pointer")
    assert guard.check_ci(_git(git_repo, "rev-parse", f"{commit}^").stdout.strip(), [PATH_A]) == 1


def test_local_commit_message_read_error_fails_closed(git_repo: Path) -> None:
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    with pytest.raises(guard.GuardError, match="commit-message file"):
        guard.check_local("missing-commit-message", [PATH_A])


def test_ci_reports_all_unmarked_commits_and_paths(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    (git_repo / "ordinary.txt").write_text("ordinary")
    _git(git_repo, "add", "ordinary.txt")
    _commit(git_repo, "Ordinary change")
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    first_sha = _commit(git_repo, "Unmarked first pointer")
    _stage_gitlink(git_repo, PATH_B, SHA_2)
    _commit(git_repo, "Intentional [submodule-update] pointer")
    _stage_gitlink(git_repo, PATH_B, SHA_3)
    last_sha = _commit(git_repo, "Unmarked second pointer")

    assert guard.check_ci(base, [PATH_A, PATH_B]) == 1
    output = capsys.readouterr().err
    assert first_sha in output
    assert last_sha in output
    assert PATH_A in output
    assert PATH_B in output


def test_ci_ignores_local_environment_bypass(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    _commit(git_repo, "Unmarked pointer")
    monkeypatch.setenv("ALLOW_SUBMODULE_CHANGE", "1")
    assert guard.check_ci(base, [PATH_A]) == 1


def test_ci_accepts_intentional_marker(git_repo: Path) -> None:
    base = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    _commit(git_repo, "Pointer [SUBMODULE-UPDATE]")
    assert guard.check_ci(base, [PATH_A]) == 0


def test_root_commit_is_included(git_repo: Path) -> None:
    sha = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    assert PATH_A in guard._commit_changed_files(sha)


def test_merge_commit_diff_includes_gitlink(git_repo: Path) -> None:
    _git(git_repo, "checkout", "-b", "submodule")
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    _commit(git_repo, "Side pointer")
    _git(git_repo, "checkout", "main")
    _stage_gitlink(git_repo, PATH_A, SHA_3)
    _commit(git_repo, "Base pointer")
    (git_repo / "ordinary.txt").write_text("main")
    _git(git_repo, "add", "ordinary.txt")
    _commit(git_repo, "Main change")
    merge_base = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    _git(git_repo, "merge", "--no-commit", "--no-ff", "submodule", check=False)
    _stage_gitlink(git_repo, PATH_A, SHA_1)
    _commit(git_repo, "Resolve pointer")
    merge = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    assert merge_base in _git(git_repo, "rev-list", "--parents", "-1", merge).stdout
    assert PATH_A in guard._commit_changed_files(merge)
    assert guard.check_ci(merge_base, [PATH_A]) == 1


def test_merge_inheriting_base_change_is_not_reported(git_repo: Path) -> None:
    base_before_bump = _git(git_repo, "rev-parse", "HEAD").stdout.strip()
    _stage_gitlink(git_repo, PATH_A, SHA_2)
    base_bump = _commit(git_repo, "Base pointer [submodule-update]")

    _git(git_repo, "checkout", "-b", "pr", base_before_bump)
    (git_repo / "ordinary.txt").write_text("side")
    _git(git_repo, "add", "ordinary.txt")
    _commit(git_repo, "Side change")
    _git(git_repo, "merge", "--no-ff", "-m", "Merge base", base_bump)

    assert guard.check_ci(base_bump, [PATH_A]) == 0


def test_missing_or_empty_gitmodules_is_valid(git_repo: Path) -> None:
    (git_repo / ".gitmodules").unlink()
    assert guard.get_submodule_paths() == []
    (git_repo / ".gitmodules").write_text("")
    assert guard.get_submodule_paths() == []


def test_git_errors_fail_closed(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    failed = subprocess.CompletedProcess(["git"], 1, "", "simulated failure")
    monkeypatch.setattr(guard, "_run", lambda command: failed)
    with pytest.raises(guard.GuardError, match="failed to read"):
        guard.get_submodule_paths()


def test_malformed_gitmodules_fails_closed(git_repo: Path) -> None:
    (git_repo / ".gitmodules").write_text("[submodule\n")
    assert guard.main(["message"]) == 1


def test_invalid_ci_base_fails_before_missing_gitmodules(git_repo: Path) -> None:
    (git_repo / ".gitmodules").unlink()
    assert guard.main(["--ci", "--base-ref", "missing"]) == 1


@pytest.mark.parametrize(
    ("helper", "args", "message"),
    [
        (guard._changed_submodules_staged, ([PATH_A],), "staged changes"),
        (guard._commits_in_range, ("missing",), "list commits"),
        (guard._commit_changed_files, ("missing",), "inspect commit"),
        (guard._commit_message, ("missing",), "read commit message"),
    ],
)
def test_git_operation_errors_fail_closed(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    helper: object,
    args: tuple[str | list[str], ...],
    message: str,
) -> None:
    failed = subprocess.CompletedProcess(["git"], 1, "", "simulated failure")
    monkeypatch.setattr(guard, "_run", lambda command: failed)
    with pytest.raises(guard.GuardError, match=message):
        helper(*args)  # type: ignore[operator]


def test_cli_validates_required_arguments_before_repository_state() -> None:
    with pytest.raises(SystemExit, match="2"):
        guard.main([])
    with pytest.raises(SystemExit, match="2"):
        guard.main(["--ci"])
    with pytest.raises(SystemExit, match="2"):
        guard.main(["message", "--base-ref", "main"])
