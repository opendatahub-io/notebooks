from __future__ import annotations

import binascii
import inspect
import json
import logging
import pathlib
import platform
import re
import tempfile
import textwrap
from typing import TYPE_CHECKING, Any, Callable

import pytest
import testcontainers.core.container
import testcontainers.core.waiting_utils

from tests.containers import docker_utils

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pytest_subtests


class TestBaseImage:
    """Tests that are applicable for all images we have in this repository."""

    def test_elf_files_can_link_runtime_libs(self, subtests: pytest_subtests.SubTests, image):
        container = testcontainers.core.container.DockerContainer(image=image, user=0, group_add=[0])
        container.with_command("/bin/sh -c 'sleep infinity'")

        def check_elf_file():
            """This python function will be executed on the image itself.
            That's why it has to have here all imports it needs."""
            import glob
            import os
            import json
            import subprocess
            import stat

            dirs = [
                "/bin",
                "/lib",
                "/lib64",
                "/opt/app-root"
            ]
            for path in dirs:
                count_scanned = 0
                unsatisfied_deps: list[tuple[str, str]] = []
                for dlib in glob.glob(os.path.join(path, "**"), recursive=True):
                    # we will visit all files eventually, no need to bother with symlinks
                    s = os.stat(dlib, follow_symlinks=False)
                    isdirectory = stat.S_ISDIR(s.st_mode)
                    isfile = stat.S_ISREG(s.st_mode)
                    executable = bool(s.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
                    if isdirectory or not executable or not isfile:
                        continue
                    with open(dlib, mode='rb') as fp:
                        magic = fp.read(4)
                    if magic != b'\x7fELF':
                        continue

                    count_scanned += 1
                    ld_library_path = os.environ.get("LD_LIBRARY_PATH", "") + os.path.pathsep + os.path.dirname(dlib)
                    output = subprocess.check_output(["ldd", dlib],
                                                     # search the $ORIGIN, essentially; most python libs expect this
                                                     env={**os.environ, "LD_LIBRARY_PATH": ld_library_path},
                                                     text=True)
                    for line in output.splitlines():
                        if "not found" in line:
                            unsatisfied_deps.append((dlib, line.strip()))
                    assert output
                print("OUTPUT>", json.dumps({"dir": path, "count_scanned": count_scanned, "unsatisfied": unsatisfied_deps}))

        try:
            container.start()
            ecode, output = container.exec(
                encode_python_function_execution_command_interpreter("/usr/bin/python3", check_elf_file))
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

        for line in output.decode().splitlines():
            logging.debug(line)
            if not line.startswith("OUTPUT> "):
                continue
            data = json.loads(line[len("OUTPUT> "):])
            assert data['count_scanned'] > 0
            for dlib, deps in data["unsatisfied"]:
                # here goes the allowlist
                if re.search(r"^/lib64/python3.\d+/site-packages/hawkey/test/_hawkey_test.so", dlib) is not None:
                    continue  # this is some kind of self test or what
                if re.search(r"^/lib64/systemd/libsystemd-core-\d+.so", dlib) is not None:
                    continue  # this is expected and we don't use systemd anyway
                if deps.startswith("libodbc.so.2"):
                    continue  # todo(jdanek): known issue RHOAIENG-18904
                if deps.startswith("libcuda.so.1"):
                    continue  # cuda magic will mount this into /usr/lib64/libcuda.so.1 and it will be found
                if deps.startswith("libjvm.so"):
                    continue  # it's in ../server
                if deps.startswith("libtracker-extract.so"):
                    continue  # it's in ../

                with subtests.test(f"{dlib=}"):
                    pytest.fail(f"{dlib=} has unsatisfied dependencies {deps=}")

    def test_oc_command_runs(self, image: str):
        container = testcontainers.core.container.DockerContainer(image=image, user=23456, group_add=[0])
        container.with_command("/bin/sh -c 'sleep infinity'")
        try:
            container.start()
            ecode, output = container.exec(["/bin/sh", "-c", "oc version"])
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

        logging.debug(output.decode())
        assert ecode == 0

    def test_oc_command_runs_fake_fips(self, image: str, subtests: pytest_subtests.SubTests):
        """Establishes a best-effort fake FIPS environment and attempts to execute `oc` binary in it.

        Related issue: RHOAIENG-4350 In workbench the oc CLI tool cannot be used on FIPS enabled cluster"""
        with tempfile.TemporaryDirectory() as tmp_crypto:
            # Ubuntu does not even have /proc/sys/crypto directory, unless FIPS is activated and machine
            #  is rebooted, see https://ubuntu.com/security/certifications/docs/fips-enablement
            # NOTE: mounting a temp file as `/proc/sys/crypto/fips_enabled` is further discussed in
            #  * https://issues.redhat.com/browse/RHOAIENG-4350
            #  * https://github.com/junaruga/fips-mode-user-space/blob/main/fips-mode-user-space-setup
            tmp_crypto = pathlib.Path(tmp_crypto)
            (tmp_crypto / 'crypto').mkdir()
            (tmp_crypto / 'crypto' / 'fips_enabled').write_text("1\n")
            (tmp_crypto / 'crypto' / 'fips_name').write_text("Linux Kernel Cryptographic API\n")
            (tmp_crypto / 'crypto' / 'fips_version').write_text("6.10.10-200.fc40.aarch64\n")
            # tmpdir is by-default created with perms restricting access to user only
            tmp_crypto.chmod(0o777)

            container = testcontainers.core.container.DockerContainer(image=image, user=54321, group_add=[0])

            # if /proc/sys/crypto/fips_enabled exists, only replace this file,
            # otherwise (Ubuntu case), assume entire /proc/sys/crypto does not exist
            if platform.system().lower() == "darwin" or pathlib.Path("/proc/sys/crypto/fips_enabled").exists():
                container.with_volume_mapping(str(tmp_crypto / 'crypto' / 'fips_enabled'), "/proc/sys/crypto/fips_enabled", mode="ro,z")
            else:
                container.with_volume_mapping(str(tmp_crypto), "/proc/sys", mode="ro,z")

            container.with_command("/bin/sh -c 'sleep infinity'")

            try:
                container.start()

                with subtests.test("/proc/sys/crypto/fips_enabled is 1"):
                    # sysctl here works too, but it may not be present in image
                    ecode, output = container.exec(["/bin/sh", "-c", "cat /proc/sys/crypto/fips_enabled"])
                    assert ecode == 0, output.decode()
                    assert "1\n" == output.decode(), f"Unexpected crypto/fips_enabled content: {output.decode()}"

                # 0: enabled, 1: partial success, 2: not enabled
                with subtests.test("/fips-mode-setup --is-enabled reports 1"):
                    ecode, output = container.exec(["/bin/sh", "-c", "fips-mode-setup --is-enabled"])
                    assert ecode == 1, output.decode()

                with subtests.test("/fips-mode-setup --check reports partial success"):
                    ecode, output = container.exec(["/bin/sh", "-c", "fips-mode-setup --check"])
                    assert ecode == 1, output.decode()
                    assert "FIPS mode is enabled.\n" in output.decode(), output.decode()
                    assert "Inconsistent state detected.\n" in output.decode(), output.decode()

                with subtests.test("oc version command runs"):
                    ecode, output = container.exec(["/bin/sh", "-c", "oc version"])
                    assert ecode == 0, output.decode()
            finally:
                docker_utils.NotebookContainer(container).stop(timeout=0)

    def test_pip_install_cowsay_runs(self, image: str):
        """Checks that the Python virtualenv in the image is writable."""
        container = testcontainers.core.container.DockerContainer(image=image, user=23456, group_add=[0])
        container.with_command("/bin/sh -c 'sleep infinity'")
        try:
            container.start()

            ecode, output = container.exec(["python3", "-m", "pip", "install", "cowsay"])
            logging.debug(output.decode())
            assert ecode == 0

            ecode, output = container.exec(["python3", "-m", "cowsay", "--text", "Hello world"])
            logging.debug(output.decode())
            assert ecode == 0
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)


def encode_python_function_execution_command_interpreter(python: str, function: Callable[..., Any], *args: list[Any]) -> list[str]:
    """Returns a cli command that will run the given Python function encoded inline.
    All dependencies (imports, ...) must be part of function body."""
    code = textwrap.dedent(inspect.getsource(function))
    ccode = binascii.b2a_base64(code.encode())
    name = function.__name__
    parameters = ', '.join(repr(arg) for arg in args)
    program = textwrap.dedent(f"""
        import binascii;
        s=binascii.a2b_base64("{ccode.decode('ascii').strip()}");
        exec(s.decode());
        print({name}({parameters}));""")
    int_cmd = [python, "-c", program]
    return int_cmd
