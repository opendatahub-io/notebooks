from __future__ import annotations

import os
from types import SimpleNamespace
from typing import TYPE_CHECKING

from scripts.ci import renovate_run

if TYPE_CHECKING:
    import pytest


def clear_renovate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CONTAINER_ENGINE",
        "DOCKER_CONFIG",
        "LOG_FORMAT",
        "LOG_LEVEL",
        "RENOVATE_CONFIG_FILE",
        "RENOVATE_DRY_RUN",
        "RENOVATE_GIT_AUTHOR",
        "RENOVATE_HOST_RULES",
        "RENOVATE_INHERIT_CONFIG",
        "RENOVATE_REPOSITORIES",
        "RENOVATE_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)


def test_build_command_lookup_uses_remote_dry_run_lookup(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_renovate_env(monkeypatch)

    cmd = renovate_run.build_command("lookup", "docker", "renovate:test", str(tmp_path))

    assert os.environ["LOG_FORMAT"] == "json"
    assert os.environ["RENOVATE_CONFIG_FILE"] == "/github-action/renovate.json5"
    assert os.environ["RENOVATE_REPOSITORIES"] == renovate_run.REMOTE_DEFAULT_REPO
    assert "--dry-run=lookup" in cmd
    assert "--platform=local" not in cmd


def test_build_command_local_lookup_preserves_local_lookup_behavior(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_renovate_env(monkeypatch)

    cmd = renovate_run.build_command("local-lookup", "docker", "renovate:test", str(tmp_path))

    assert os.environ["LOG_FORMAT"] == "json"
    assert os.environ["RENOVATE_CONFIG_FILE"] == str(renovate_run.ROOT / ".github/renovate.json5")
    assert "--platform=local" in cmd
    assert "--dry-run=lookup" in cmd


def test_main_lookup_requires_token(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_renovate_env(monkeypatch)
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    monkeypatch.setattr(renovate_run, "detect_engine", lambda: "docker")
    monkeypatch.setattr(renovate_run, "maybe_load_host_rules", lambda _: None)

    def fake_run(cmd: list[str], check: bool) -> SimpleNamespace:
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(renovate_run.subprocess, "run", fake_run)

    exit_code = renovate_run.main(["lookup"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "set RENOVATE_TOKEN (required for lookup)" in captured.err


def test_main_local_lookup_exits_before_container(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_renovate_env(monkeypatch)
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))

    def fail_if_run(cmd: list[str], check: bool) -> SimpleNamespace:
        raise AssertionError("subprocess.run should not be called for local-lookup")

    monkeypatch.setattr(renovate_run.subprocess, "run", fail_if_run)

    exit_code = renovate_run.main(["local-lookup"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "matchRepositories" in captured.err
    assert "renovate_run.py lookup" in captured.err
