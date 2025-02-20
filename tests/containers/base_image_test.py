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

    # There are two ways how the image is being updated
    # 1. A change to the image is being done (e.g. package update, Dockerfile update etc.). This is what this test does.
    #    In this case, we need to check the size of the build image that contains these updates. We're checking the compressed image size.
    # 2. A change is done to the params.env file or runtimes images definitions, where we update manifest references to a new image.
    #    Check for this scenario is being done in 'ci/[check-params-env.sh|check-runtime-images.sh]'.
    size_treshold: int = 100 # in MBs
    percent_treshold: int = 10
    def test_image_size_change(self, image: str):
        f"""Checks the image size didn't change extensively - treshold is {self.percent_treshold}% or {self.size_treshold} MB."""

        # Map of image label names with expected size in MBs.
        expected_image_name_size_map = {
            "odh-notebook-base-centos-stream9-python-3.11": 1350,
            "odh-notebook-base-ubi9-python-3.11": 1262,
            "odh-notebook-cuda-c9s-python-3.11": 11519,
            "odh-notebook-cuda-ubi9-python-3.11": 9070, # TODO
            "odh-notebook-jupyter-datascience-ubi9-python-3.11": 2845,
            "odh-notebook-jupyter-minimal-ubi9-python-3.11": 1472, # gpu 9070; rocm 26667 ???
            "odh-notebook-jupyter-pytorch-ubi9-python-3.11": 15861, #15444,
            "odh-notebook-cuda-jupyter-tensorflow-ubi9-python-3.11": 20401, #15218,
            "odh-notebook-jupyter-trustyai-ubi9-python-3.11": 8866, #8613,
            "odh-notebook-jupyter-rocm-pytorch-ubi9-python-3.11": 33268, #33001,
            "odh-notebook-jupyter-rocm-tensorflow-ubi9-python-3.11": 30507, #30241,
            "odh-notebook-rstudio-server-c9s-python-3.11": 13201, # 3221 ??
            "odh-notebook-runtime-datascience-ubi9-python-3.11": 2690, #2518,
            "odh-notebook-runtime-minimal-ubi9-python-3.11": 1527, #1362,
            "odh-notebook-runtime-pytorch-ubi9-python-3.11": 7711, #7487,
            "odh-notebook-cuda-runtime-tensorflow-ubi9-python-3.11": 15114, #14572,
            "odh-notebook-runtime-rocm-pytorch-ubi9-python-3.11": 32864, #32682,
            "odh-notebook-rocm-runtime-tensorflow-ubi9-python-3.11": 29985, #29805,
            "odh-notebook-code-server-ubi9-python-3.11": 2993, #2598,
            "odh-notebook-rocm-python-3.11": 26667, # TODO
        }

        import docker
        client = testcontainers.core.container.DockerClient()
        try:
            image_metadata = client.client.images.get(image)
        except docker.errors.ImageNotFound:
            image_metadata = client.client.images.pull(image)
            assert isinstance(image_metadata, docker.models.images.Image)

        actual_img_size = image_metadata.attrs["Size"]
        actual_img_size = round(actual_img_size / 1024 / 1024)
        logging.info(f"The size of the image is {actual_img_size} MBs.")
        logging.debug(f"The image metadata: {image_metadata}")

        img_label_name = image_metadata.labels["name"]
        if img_label_name in expected_image_name_size_map:
            expected_img_size = expected_image_name_size_map[img_label_name]
            logging.debug(f"Expected size of the '{img_label_name}' image is {expected_img_size} MBs.")
        else:
            pytest.fail(f"Image name label '{img_label_name}' is not in the expected image size map {expected_image_name_size_map}")

        # Check the size change constraints now
        # 1. Percentual size change
        abs_percent_change = abs(actual_img_size / expected_img_size * 100 - 100)
        assert abs_percent_change < self.percent_treshold, f"Image size of '{img_label_name}' changed by {abs_percent_change}% (expected: {expected_img_size} MB; actual: {actual_img_size} MB; treshold: {self.percent_treshold}%)."
        # 2. Absolute size change
        abs_size_difference = abs(actual_img_size - expected_img_size)
        assert abs_size_difference < self.size_treshold, f"Image size of '{img_label_name}' changed by {abs_size_difference} MB (expected: {expected_img_size} MB; actual: {actual_img_size} MB; treshold: {self.size_treshold} MB)."

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
