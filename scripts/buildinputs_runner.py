from __future__ import annotations

import functools
import json
import os
import pathlib
import re
import shutil
import subprocess
from typing import Literal

ROOT_DIR = pathlib.Path(__file__).parent.parent.resolve()
MAKE = shutil.which("gmake") or shutil.which("make")

Platform = Literal["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"]


@functools.lru_cache
def _repository_slug() -> str:
    if repository := os.environ.get("GITHUB_REPOSITORY"):
        return repository.lower()

    try:
        origin = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT_DIR,
            text=True,
        ).strip()
    except FileNotFoundError, subprocess.CalledProcessError:
        return "opendatahub-io/notebooks"

    if match := re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", origin):
        return match.group(1).lower()
    return "opendatahub-io/notebooks"


def buildinputs_image() -> str:
    if image := os.environ.get("BUILDINPUTS_IMAGE"):
        return image
    return f"ghcr.io/{_repository_slug()}/buildinputs:main"


def _container_runtime() -> str:
    if runtime := os.environ.get("BUILDINPUTS_RUNTIME"):
        return runtime

    for candidate in ("podman", "docker"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("need podman or docker to run the buildinputs image")


def containarized_buildinputs(
    dockerfile: pathlib.Path | str,
    platform: Platform = "linux/amd64",
    build_args: dict[str, str] | None = None,
) -> str:
    if build_args is None:
        build_args = {}

    dockerfile_path = pathlib.Path(dockerfile)
    if not dockerfile_path.is_absolute():
        dockerfile_path = (ROOT_DIR / dockerfile_path).resolve()
    else:
        dockerfile_path = dockerfile_path.resolve()

    command = [
        _container_runtime(),
        "run",
        "--rm",
        "-e",
        f"TARGETPLATFORM={platform}",
        "-v",
        f"{ROOT_DIR}:{ROOT_DIR}:ro,z",
        "-w",
        str(ROOT_DIR),
        buildinputs_image(),
        *[f"-build-arg={key}={value}" for key, value in build_args.items()],
        str(dockerfile_path),
    ]

    stdout = subprocess.check_output(command, text=True, cwd=ROOT_DIR)
    return stdout


def local_buildinputs(
    dockerfile: pathlib.Path | str,
    platform: Literal["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"] = "linux/amd64",
    build_args: dict[str, str] | None = None,
) -> str:
    if not (ROOT_DIR / "bin/buildinputs").exists():
        subprocess.check_call([MAKE, "bin/buildinputs"], cwd=ROOT_DIR)
    if not build_args:
        build_args = {}
    stdout = subprocess.check_output(
        [ROOT_DIR / "bin/buildinputs", *[f"-build-arg={k}={v}" for k, v in build_args.items()], str(dockerfile)],
        text=True,
        cwd=ROOT_DIR,
        env={**os.environ, "TARGETPLATFORM": platform},
    )
    return stdout


def buildinputs(
    dockerfile: pathlib.Path | str,
    platform: Literal["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"] = "linux/amd64",
    build_args: dict[str, str] | None = None,
) -> list[pathlib.Path]:

    if "CI" in os.environ and os.environ["CI"] == "true":
        stdout = containarized_buildinputs(dockerfile, platform, build_args)
    else:
        stdout = local_buildinputs(dockerfile, platform, build_args)

    prereqs = list(dict.fromkeys(pathlib.Path(file) for file in json.loads(stdout)))
    print(f"{prereqs=}")
    return prereqs
