#! /usr/bin/env python3

import argparse
import logging
import pathlib
import subprocess
import sys
import unittest
from typing import cast

ROOT_DIR = pathlib.Path(__file__).parent.parent.parent.parent

logging.basicConfig(level=logging.INFO)
logging.root.name = pathlib.Path(__file__).name


# class Args(argparse.Namespace):
#     platform: str


def main(dockerfile: str, platform: str) -> int:
    # p = argparse.ArgumentParser()
    # p.add_argument("--platform", default="linux/amd64", help="Target platform for the build")
    # args = cast(Args, p.parse_args())

    dockerfile_path = ROOT_DIR / "scripts" / "zigcc" / "test" / dockerfile
    sandbox_script_path = ROOT_DIR / "scripts" / "sandbox.py"

    return subprocess.call(
        [sys.executable, str(sandbox_script_path),
         "--dockerfile", str(dockerfile_path),
         "--platform", platform,
         "--",
         "podman", "build",
         # "--no-cache",
         "--platform", platform,
         "-t", "hello-world-test",
         # dockerfile path in podman command is required, Dockerfile is not copied to sandbox
         "-f", str(dockerfile_path),
         "{};"],
        # sandbox.py assumes running from repo root
        cwd=ROOT_DIR
    )

class TestBuilds(unittest.TestCase):
    def test_build(self):
        self.assertEqual(
            0,
            main(dockerfile="Dockerfile", platform="linux/amd64")
        )

    def test_build_openblas(self):
        self.assertEqual(
            0,
            main(dockerfile="Dockerfile.openblas", platform="linux/amd64")
        )

    def test_build_openblas_minimal(self):
        self.assertEqual(
            0,
            main(dockerfile="Dockerfile.openblas.minimal", platform="linux/amd64")
        )

if __name__ == "__main__":
    sys.exit(main())
