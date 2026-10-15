"""Unit tests for jupyter/universal dual-mode entrypoint-universal.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests import PROJECT_ROOT

_ENTRYPOINT_SRC = (
    PROJECT_ROOT / "jupyter" / "universal" / "ubi9-python-3.12" / "entrypoint-universal.sh"
)


def _prepare_dual_mode_tree(tmp_path: Path) -> tuple[Path, Path]:
    """Install a path-rewritten entrypoint with stub start-notebook and bootstrapper.

    Returns (entrypoint_path, record_file).
    """
    bin_dir = tmp_path / "opt" / "app-root" / "bin"
    utils = bin_dir / "utils"
    utils.mkdir(parents=True)
    record = tmp_path / "invoked.txt"

    start = bin_dir / "start-notebook.sh"
    start.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "workbench\\n" > "{record}"\n'
        f'printf "%s\\n" "$@" >> "{record}"\n',
        encoding="utf-8",
    )
    start.chmod(0o755)

    bootstrapper = utils / "bootstrapper.py"
    bootstrapper.write_text(
        "# stub — real invocation goes through fake python below\n",
        encoding="utf-8",
    )

    fake_python = bin_dir / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "runtime\\n" > "{record}"\n'
        f'printf "%s\\n" "$@" >> "{record}"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    ep = tmp_path / "entrypoint-universal.sh"
    rewritten = _ENTRYPOINT_SRC.read_text(encoding="utf-8").replace(
        "/opt/app-root/bin", str(bin_dir)
    )
    ep.write_text(rewritten, encoding="utf-8")
    ep.chmod(0o755)
    return ep, record


def _run(
    entrypoint: Path,
    *args: str,
    env: dict[str, str] | None = None,
    bin_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    if bin_dir is not None:
        run_env["PATH"] = f"{bin_dir}{os.pathsep}{run_env.get('PATH', '')}"
    return subprocess.run(
        [str(entrypoint), *args],
        check=False,
        capture_output=True,
        text=True,
        env=run_env,
    )


@pytest.fixture
def dual_mode(tmp_path: Path) -> tuple[Path, Path, Path]:
    ep, record = _prepare_dual_mode_tree(tmp_path)
    bin_dir = tmp_path / "opt" / "app-root" / "bin"
    return ep, record, bin_dir


class TestEntrypointUniversal:
    def test_no_args_starts_workbench(self, dual_mode: tuple[Path, Path, Path]) -> None:
        ep, record, bin_dir = dual_mode
        result = _run(ep, bin_dir=bin_dir)
        assert result.returncode == 0, result.stderr
        lines = record.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "workbench"

    def test_start_notebook_basename_starts_workbench(
        self, dual_mode: tuple[Path, Path, Path]
    ) -> None:
        ep, record, bin_dir = dual_mode
        result = _run(ep, "start-notebook.sh", bin_dir=bin_dir)
        assert result.returncode == 0, result.stderr
        assert record.read_text(encoding="utf-8").splitlines()[0] == "workbench"

    def test_runtime_shortcut_invokes_bootstrapper(
        self, dual_mode: tuple[Path, Path, Path]
    ) -> None:
        ep, record, bin_dir = dual_mode
        result = _run(ep, "runtime", "--help", bin_dir=bin_dir)
        assert result.returncode == 0, result.stderr
        lines = record.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "runtime"
        assert lines[1].endswith("bootstrapper.py")
        assert "--help" in lines

    def test_command_override_wins_over_notebook_args(
        self, dual_mode: tuple[Path, Path, Path], tmp_path: Path
    ) -> None:
        ep, record, bin_dir = dual_mode
        marker = tmp_path / "override.txt"
        result = _run(
            ep,
            "bash",
            "-c",
            f'printf override > "{marker}"',
            env={"NOTEBOOK_ARGS": "--ServerApp.port=8888"},
            bin_dir=bin_dir,
        )
        assert result.returncode == 0, result.stderr
        assert marker.read_text(encoding="utf-8") == "override"
        assert not record.exists() or "workbench" not in record.read_text(encoding="utf-8")

    def test_absolute_start_notebook_path_starts_workbench(
        self, dual_mode: tuple[Path, Path, Path]
    ) -> None:
        ep, record, bin_dir = dual_mode
        result = _run(ep, str(bin_dir / "start-notebook.sh"), bin_dir=bin_dir)
        assert result.returncode == 0, result.stderr
        assert record.read_text(encoding="utf-8").splitlines()[0] == "workbench"
