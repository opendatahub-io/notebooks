#!/usr/bin/env python3

import pathlib
import platform
import subprocess
import sys


def exec_makefile(target: str, makefile_dir: pathlib.Path | str, options: list[str] = []) -> str:
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


def dry_run_makefile(target: str, makefile_dir: pathlib.Path | str) -> str:
    return exec_makefile(
        target=target, makefile_dir=makefile_dir, options=["--dry-run", "--print-data-base", "--quiet"]
    )
