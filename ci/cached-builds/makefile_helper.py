#!/usr/bin/env python3

from __future__ import annotations

import platform
import string
import subprocess
import sys
from typing import TYPE_CHECKING

from gha_pr_changed_files import PROJECT_ROOT

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence


def exec_makefile(target: str, makefile_dir: pathlib.Path | str, options: Sequence[str] = ()) -> str:
    """Returns the stdout of the make command."""
    # Check if the operating system is macOS
    if platform.system() == "Darwin":
        make_command = "gmake"
    else:
        make_command = "make"

    try:
        # Run the make (or gmake) command and capture the output
        result = subprocess.run(
            [make_command, *options, target],
            capture_output=True,
            text=True,
            check=True,
            cwd=makefile_dir,
        )
    except subprocess.CalledProcessError as e:
        # Handle errors if the make command fails
        print(f"{make_command} failed with return code: {e.returncode}:\n{e.stderr}", file=sys.stderr)
        raise
    except Exception as e:
        # Handle any other exceptions
        print(f"Error occurred attempting to parse Makefile:\n{e!s}", file=sys.stderr)
        raise

    return result.stdout


def dry_run_makefile(target: str, makefile_dir: pathlib.Path | str, env: dict[str, str] | None = None) -> str:
    if env is None:
        env = {}

    envs = []
    for k, v in env.items():
        envs.extend(("-e", f"{k}={v}"))

    return exec_makefile(
        target=target, makefile_dir=makefile_dir, options=["--dry-run", "--print-data-base", "--quiet", *envs]
    )


class TestMakefile:
    MINIMAL_IMAGE = "jupyter-minimal-ubi9-python-3.12"

    def test_makefile__build_image__konflux(self):
        konflux_default = dry_run_makefile(target=self.MINIMAL_IMAGE, makefile_dir=PROJECT_ROOT)
        konflux_yes = dry_run_makefile(target=self.MINIMAL_IMAGE, makefile_dir=PROJECT_ROOT, env={"KONFLUX": "yes"})

        _assert_subdict(
            {
                "VARIANT": "cpu",
                "DOCKERFILE_NAME": "Dockerfile.cpu",
                "CONF_FILE": "jupyter/minimal/ubi9-python-3.12/build-args/cpu.conf",
            },
            _extract_assignments(konflux_default),
        )

        _assert_subdict(
            {
                "VARIANT": "cpu",
                "DOCKERFILE_NAME": "Dockerfile.konflux.cpu",
                "CONF_FILE": "jupyter/minimal/ubi9-python-3.12/build-args/konflux.cpu.conf",
            },
            _extract_assignments(konflux_yes),
        )

        assert "--file 'jupyter/minimal/ubi9-python-3.12/Dockerfile.cpu'" in konflux_default
        assert "--file 'jupyter/minimal/ubi9-python-3.12/Dockerfile.konflux.cpu'" in konflux_yes

def _extract_assignments(makefile_output: str) -> dict[str, str]:
    assignments = {}
    for line in makefile_output.splitlines():
        if not line.strip():
            continue
        if line[0] not in string.ascii_letters:
            continue

        if ":=" not in line:
            continue
        key, value = line.split(":=", 1)
        assignments[key.strip()] = value.strip()
    return assignments


# see also https://pypi.org/project/pytest-assert-utils/
def _assert_subdict(subdict: dict[str, str], superdict: dict[str, str]):
    """Filter subdict to only keys in superdict, then compare the remaining items."""
    __tracebackhide__ = True
    assert subdict == {k: superdict[k] for k in subdict if k in superdict}
