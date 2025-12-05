#! /usr/bin/env python3

import argparse
import logging
import pathlib
import subprocess
import sys
from typing import cast

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent.parent

logging.basicConfig(level=logging.INFO)
logging.root.name = pathlib.Path(__file__).name


class Args(argparse.Namespace):
    platform: str


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--platform", default="linux/amd64", help="Target platform for the build")
    args = cast(Args, p.parse_args())

    dockerfile_path = ROOT_DIR / "scripts" / "zigcc" / "test" / "Dockerfile"
    sandbox_script_path = ROOT_DIR / "scripts" / "sandbox.py"

    return subprocess.call(
        [sys.executable, str(sandbox_script_path),
         "--dockerfile", str(dockerfile_path),
         "--platform", args.platform,
         "--",
         "podman", "build",
         "--no-cache",
         "--platform", args.platform,
         "-t", "hello-world-test",
         # dockerfile path in podman command is required, Dockerfile is not copied to sandbox
         "-f", str(dockerfile_path),
         "{};"],
        # sandbox.py assumes running from repo root
        cwd=ROOT_DIR
    )


if __name__ == "__main__":
    sys.exit(main())
