#! /usr/bin/env python3

import argparse
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import json
from typing import cast, Literal

ROOT_DIR = pathlib.Path(__file__).parent.parent
MAKE = shutil.which("gmake") or shutil.which("make")

logging.basicConfig()
logging.root.name = pathlib.Path(__file__).name


class Args(argparse.Namespace):
    dockerfile: pathlib.Path
    platform: Literal["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"]
    remaining: list[str]


def main() -> int:
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument("--dockerfile", type=pathlib.Path, required=True)
    p.add_argument("--platform", type=str,
                   choices=["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"],
                   required=True)
    p.add_argument('remaining', nargs=argparse.REMAINDER)

    args = cast(Args, p.parse_args())

    print(f"{__file__=} started with {args=}")

    if not args.remaining or args.remaining[0] != "--":
        print("must specify command to execute after double dashes at the end, such as `-- command --args ...`")
        return 1
    if not "{};" in args.remaining:
        print("must give a `{};` parameter that will be replaced with new build context")
        return 1

    build_args = extract_build_args(args.remaining[1:])
    prereqs = buildinputs(dockerfile=args.dockerfile, platform=args.platform, build_args=build_args)

    with tempfile.TemporaryDirectory(delete=True) as tmpdir:
        setup_sandbox(prereqs, pathlib.Path(tmpdir))
        command = [arg if arg != "{};" else tmpdir for arg in args.remaining[1:]]
        print(f"running {command=}")
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError as err:
            logging.error("Failed to execute process, see errors logged above ^^^")
            return err.returncode
    return 0


def extract_build_args(remaining: list[str]) -> dict[str, str]:
    """Extract --build-arg KEY=VALUE pairs from the command line using argparse."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--build-arg", action="append", default=[])
    known, _ = parser.parse_known_args(remaining)
    build_args = {}
    for arg in known.build_arg:
        if "=" not in arg:
            raise ValueError(f"--build-arg must be in KEY=VALUE format, got: {arg!r}")
        key, value = arg.split("=", 1)
        build_args[key] = value
    return build_args


def buildinputs(
        dockerfile: pathlib.Path | str,
        platform: Literal["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"] = "linux/amd64",
        build_args: dict[str, str] | None = None
) -> list[pathlib.Path]:
    if not (ROOT_DIR / "bin/buildinputs").exists():
        subprocess.check_call([MAKE, "bin/buildinputs"], cwd=ROOT_DIR)
    if not build_args:
        build_args = {}
    stdout = subprocess.check_output([ROOT_DIR / "bin/buildinputs",
                                      *[f"-build-arg={k}={v}" for k, v in build_args.items()],
                                      str(dockerfile)],
                                     text=True, cwd=ROOT_DIR,
                                     env={**os.environ, "TARGETPLATFORM": platform})
    prereqs = [pathlib.Path(file) for file in json.loads(stdout)]
    print(f"{prereqs=}")
    return prereqs


def setup_sandbox(prereqs: list[pathlib.Path], tmpdir: pathlib.Path):
    # always adding .gitignore
    gitignore = ROOT_DIR / ".gitignore"
    if gitignore.exists():
        shutil.copy(gitignore, tmpdir)

    for dep in prereqs:
        if dep.is_absolute():
            dep = dep.relative_to(ROOT_DIR)
        if dep.is_dir():
            shutil.copytree(dep, tmpdir / dep, symlinks=False, dirs_exist_ok=True)
        else:
            (tmpdir / dep.parent).mkdir(parents=True, exist_ok=True)
            shutil.copy(dep, tmpdir / dep.parent)


if __name__ == '__main__':
    sys.exit(main())
