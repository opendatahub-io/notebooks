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

    prereqs = buildinputs(dockerfile=args.dockerfile, platform=args.platform)

    with tempfile.TemporaryDirectory(delete=True) as tmpdir:
        setup_sandbox(prereqs, pathlib.Path(tmpdir))
        # target glibc 2.28 or newer (supports FORTIFY_SOURCE)
        target = "s390x-linux-gnu.2.34"
        additional_arguments = [
            f"--volume={os.getcwd()}/bin/zig-0.15.1:/mnt",
            # f"--env=CC=/mnt/zig cc -target {target}",
            # f"--env=CXX=/mnt/zig c++ -target {target}",
            # f"--env=CC=/mnt/zig-cc",
            # f"--env=CXX=/mnt/zig-c++",
            # -Wp,-D_FORTIFY_SOURCE=2
            # https://github.com/giampaolo/psutil/blob/master/setup.py#L254
            # defaults to using python's flags
            # f"--env=CFLAGS=",
            f"--env=bustcachez=",
            "--env=CXXFLAGS=-Dundefined=64",
            f"--unsetenv=CC",
            f"--unsetenv=CXX",
            tmpdir,
        ]
        command = []
        for arg in args.remaining[1:]:
            if arg == "{};":
                command.extend(additional_arguments)
            else:
                command.append(arg)
        print(f"running {command=}")
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError as err:
            logging.error("Failed to execute process, see errors logged above ^^^")
            return err.returncode
    return 0

"""
Downloading jedi
  × Failed to build `pyzmq==27.1.0`
  ├─▶ The build backend returned an error
  ╰─▶ Call to `scikit_build_core.build.build_wheel` failed (exit status: 1)
      [stdout]
      *** scikit-build-core 0.11.6 using CMake 3.26.5 (wheel)
      *** Configuring CMake...
      loading initial cache file /tmp/tmpf9bnfh5o/build/CMakeInit.txt
      -- Configuring incomplete, errors occurred!
      [stderr]
      CMake Error at /usr/share/cmake/Modules/CMakeDetermineCCompiler.cmake:49
      (message):
        Could not find compiler set in environment variable CC:
        /mnt/zig-0.15.1/zig cc -target s390x-linux-gnu.
      Call Stack (most recent call first):
        CMakeLists.txt:2 (project)
"""

"""
creating build/temp.linux-s390x-cpython-312/psutil/arch/linux
      /mnt/zig cc -target s390x-linux-gnu -fno-strict-overflow
      -Wsign-compare -DDYNAMIC_ANNOTATIONS_ENABLED=1 -DNDEBUG
      -O2 -fexceptions -g -grecord-gcc-switches -pipe
      -Wall -Werror=format-security -Wp,-D_FORTIFY_SOURCE=2
      -Wp,-D_GLIBCXX_ASSERTIONS -fstack-protector-strong
      -m64 -march=z14 -mtune=z15 -fasynchronous-unwind-tables
      -fstack-clash-protection -O2 -fexceptions -g -grecord-gcc-switches
      -pipe -Wall -Werror=format-security -Wp,-D_FORTIFY_SOURCE=2
      -Wp,-D_GLIBCXX_ASSERTIONS -fstack-protector-strong
      -m64 -march=z14 -mtune=z15 -fasynchronous-unwind-tables
      -fstack-clash-protection -O2 -fexceptions -g -grecord-gcc-switches
      -pipe -Wall -Werror=format-security -Wp,-D_FORTIFY_SOURCE=2
      -Wp,-D_GLIBCXX_ASSERTIONS -fstack-protector-strong
      -m64 -march=z14 -mtune=z15 -fasynchronous-unwind-tables
      -fstack-clash-protection -fPIC -DPSUTIL_POSIX=1 -DPSUTIL_SIZEOF_PID_T=4
      -DPSUTIL_VERSION=700 -DPy_LIMITED_API=0x03060000
      -DPSUTIL_LINUX=1 -I/tmp/.tmpWlL4ZP/builds-v0/.tmpOwAhw2/include
      -I/usr/include/python3.12 -c psutil/_psutil_common.c -o
      build/temp.linux-s390x-cpython-312/psutil/_psutil_common.o
      [stderr]
      /tmp/.tmpWlL4ZP/builds-v0/.tmpOwAhw2/lib64/python3.12/site-packages/setuptools/dist.py:759:
      SetuptoolsDeprecationWarning: License classifiers are deprecated.
      !!

      ********************************************************************************
              Please consider removing the following classifiers in favor of a
      SPDX license expression:
              License :: OSI Approved :: BSD License
              See
      https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license
      for details.

      ********************************************************************************
      !!
        self._finalize_license_expression()
      error: unsupported preprocessor arg: -D_FORTIFY_SOURCE
"""

def buildinputs(
        dockerfile: pathlib.Path | str,
        platform: Literal["linux/amd64", "linux/arm64", "linux/s390x", "linux/ppc64le"] = "linux/amd64"
) -> list[pathlib.Path]:
    if not (ROOT_DIR / "bin/buildinputs").exists():
        subprocess.check_call([MAKE, "bin/buildinputs"], cwd=ROOT_DIR)
    if not (ROOT_DIR / "bin/zig-0.15.1").exists():
        subprocess.check_call([MAKE, "bin/zig-0.15.1"], cwd=ROOT_DIR)
    if not (ROOT_DIR / "bin/zig-0.15.1/zigcc").exists():
        subprocess.check_call([MAKE, "build"], cwd=ROOT_DIR / "scripts/zigcc")
        shutil.copy(ROOT_DIR / "scripts/zigcc/bin/zigcc", ROOT_DIR / "bin/zig-0.15.1/zig-cc")
        shutil.copy(ROOT_DIR / "scripts/zigcc/bin/zigcc", ROOT_DIR / "bin/zig-0.15.1/zig-c++")
    stdout = subprocess.check_output([ROOT_DIR / "bin/buildinputs", str(dockerfile)],
                                     text=True, cwd=ROOT_DIR,
                                     env={"TARGETPLATFORM": platform, **os.environ})
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
