from __future__ import annotations

import binascii
import contextlib
import inspect
import json
import logging
import pathlib
import platform
import re
import tempfile
import textwrap
from typing import TYPE_CHECKING, Any

import allure
import pytest
import testcontainers.core.container

from tests.containers import conftest, docker_utils, skopeo_utils, utils

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    import pytest_subtests


# see also https://pypi.org/project/pytest-assert-utils/
def _assert_subdict(subdict: dict[str, str], superdict: dict[str, str]):
    """Filter subdict to only keys in superdict, then compare the remaining items."""
    __tracebackhide__ = True
    assert subdict == {k: superdict[k] for k in subdict if k in superdict}


class TestBaseImage:
    """Tests that are applicable for all images we have in this repository."""

    def _has_uv_lock_d(self, image: str) -> bool:
        """Check if the image is AIPCC-enabled by looking for uv.lock.d in source directory."""
        image_metadata = conftest.get_image_metadata(image)
        source_location = image_metadata.labels.get("io.openshift.build.source-location", "")

        # Dockerfile.konflux does not have source-location label
        if not source_location:
            image_info = skopeo_utils.get_image_info(image)
            return "PIP_INDEX_URL" not in image_info.env

        # Extract relative path from URL (after /tree/main/)
        source_dir = None
        if "/tree/main/" in source_location:
            source_dir = source_location.split("/tree/main/")[1]

        # Check if uv.lock.d directory exists in source
        workspace_root = pathlib.Path(__file__).parent.parent.parent
        return source_dir is not None and (workspace_root / source_dir / "uv.lock.d").is_dir()

    def _run_test(self, image: str, test_fn: Callable[[testcontainers.core.container.DockerContainer], None]) -> None:
        with self._test_container(image) as container:
            test_fn(container)

    @contextlib.contextmanager
    def _test_container(self, image: str) -> Generator[testcontainers.core.container.DockerContainer]:
        """Context manager that starts a test container and yields it."""
        container = testcontainers.core.container.DockerContainer(image=image, user=23456, group_add=[0])
        container.with_command("/bin/sh -c 'sleep infinity'")
        try:
            container.start()
            yield container
            return
        except Exception as e:
            pytest.fail(f"Unexpected exception in test: {e}")
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

        raise RuntimeError("Cannot happen: the test did not pass as expected.")

    def test_elf_files_can_link_runtime_libs(self, subtests: pytest_subtests.SubTests, image):
        def test_fn(container: testcontainers.core.container.DockerContainer):
            def check_elf_file():
                """This python function will be executed on the image itself.
                That's why it has to have here all imports it needs."""
                # ruff: noqa: PLC0415 `import` should be at the top-level of a file
                import glob
                import json
                import os
                import stat
                import subprocess

                dirs = ["/bin", "/lib", "/lib64", "/opt/app-root"]
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
                        with open(dlib, mode="rb") as fp:
                            magic = fp.read(4)
                        if magic != b"\x7fELF":
                            continue

                        count_scanned += 1
                        ld_library_path = (
                            os.environ.get("LD_LIBRARY_PATH", "") + os.path.pathsep + os.path.dirname(dlib)
                        )
                        output = subprocess.check_output(
                            ["ldd", dlib],
                            # search the $ORIGIN, essentially; most python libs expect this
                            env={**os.environ, "LD_LIBRARY_PATH": ld_library_path},
                            text=True,
                        )
                        for line in output.splitlines():
                            if "not found" in line:
                                unsatisfied_deps.append((dlib, line.strip()))
                        assert output
                    print(
                        "OUTPUT>",
                        json.dumps({"dir": path, "count_scanned": count_scanned, "unsatisfied": unsatisfied_deps}),
                    )

            _ecode, output = container.exec(
                encode_python_function_execution_command_interpreter("/usr/bin/python3", check_elf_file)
            )

            for line in output.decode().splitlines():
                logging.debug(line)
                if not line.startswith("OUTPUT> "):
                    continue
                data = json.loads(line[len("OUTPUT> ") :])
                assert data["count_scanned"] > 0
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

                    # AIPCC-6072: Unsatisfied library dependencies in the cuda aipcc image
                    if deps.startswith("libmpi.so"):
                        continue  # it's in ${MPI_HOME}/lib
                    if deps.startswith("liboshmem.so"):
                        continue  # it's in ${MPI_HOME}/lib

                    # torchvision video_reader requires FFmpeg 6.x - not available in RHEL9/UBI9/CentOS Stream 9
                    # EPEL 9 and RPM Fusion only provide FFmpeg 5.1.4 (libavcodec.so.59)
                    # Ignored for ODH; TODO: check if this needs resolution for production Konflux/RHDS builds
                    if dlib.endswith("video_reader.so"):
                        continue

                    with subtests.test(f"{dlib=}"):
                        pytest.fail(f"{dlib=} has unsatisfied dependencies {deps=}")

        self._run_test(image=image, test_fn=test_fn)

    def test_oc_command_runs(self, image: str):
        if utils.is_rstudio_image(image):
            pytest.skip("oc command is not preinstalled in RStudio images.")

        def test_fn(container: testcontainers.core.container.DockerContainer):
            ecode, output = container.exec(["/bin/sh", "-c", "oc version"])

            logging.debug(output.decode())
            assert ecode == 0

        self._run_test(image=image, test_fn=test_fn)

    def test_skopeo_command_runs(self, image: str):
        if utils.is_rstudio_image(image):
            pytest.skip("skopeo command is not preinstalled in RStudio images.")

        def test_fn(container: testcontainers.core.container.DockerContainer):
            ecode, output = container.exec(["/bin/sh", "-c", "skopeo --version"])

            logging.debug(output.decode())
            assert ecode == 0

        self._run_test(image=image, test_fn=test_fn)

    def test_pip_install_cowsay_runs(self, image: str):
        """Checks that the Python virtualenv in the image is writable.

        For AIPCC-enabled images, cowsay is not available on the restricted index,
        so we expect the install to fail with a specific error message.
        """
        has_uv_lock_d = self._has_uv_lock_d(image)

        def test_fn(container: testcontainers.core.container.DockerContainer):
            ecode, output = container.exec(["python3", "-m", "pip", "install", "cowsay"])
            output_str = output.decode()
            logging.debug(output_str)

            if has_uv_lock_d:
                # AIPCC-enabled: cowsay should NOT be available
                assert ecode != 0, "Expected pip install cowsay to fail on AIPCC-enabled image"
                assert (
                    "Could not find a version that satisfies the requirement cowsay" in output_str
                    or "No matching distribution found for cowsay" in output_str
                ), f"Expected AIPCC error message, got: {output_str}"
            else:
                # Non-AIPCC: cowsay should install and run successfully
                assert ecode == 0, f"Expected pip install cowsay to succeed, got: {output_str}"

                ecode, output = container.exec(["python3", "-m", "cowsay", "--text", "Hello world"])
                logging.debug(output.decode())
                assert ecode == 0

        self._run_test(image=image, test_fn=test_fn)

    # @pytest.mark.environmentss("docker")
    def test_oc_command_runs_fake_fips(self, image: str, subtests: pytest_subtests.SubTests):
        """Establishes a best-effort fake FIPS environment and attempts to execute `oc` binary in it.

        Related issue: RHOAIENG-4350 In workbench the oc CLI tool cannot be used on FIPS enabled cluster"""
        if utils.is_rstudio_image(image):
            pytest.skip("oc command is not preinstalled in RStudio images.")
        with tempfile.TemporaryDirectory() as tmp_crypto:
            # Ubuntu does not even have /proc/sys/crypto directory, unless FIPS is activated and machine
            #  is rebooted, see https://ubuntu.com/security/certifications/docs/fips-enablement
            # NOTE: mounting a temp file as `/proc/sys/crypto/fips_enabled` is further discussed in
            #  * https://issues.redhat.com/browse/RHOAIENG-4350
            #  * https://github.com/junaruga/fips-mode-user-space/blob/main/fips-mode-user-space-setup
            tmp_crypto = pathlib.Path(tmp_crypto)
            (tmp_crypto / "crypto").mkdir()
            (tmp_crypto / "crypto" / "fips_enabled").write_text("1\n")
            (tmp_crypto / "crypto" / "fips_name").write_text("Linux Kernel Cryptographic API\n")
            (tmp_crypto / "crypto" / "fips_version").write_text("6.10.10-200.fc40.aarch64\n")
            # tmpdir is by-default created with perms restricting access to user only
            tmp_crypto.chmod(0o777)

            container = testcontainers.core.container.DockerContainer(image=image, user=54321, group_add=[0])

            # if /proc/sys/crypto/fips_enabled exists, only replace this file,
            # otherwise (Ubuntu case), assume entire /proc/sys/crypto does not exist
            if platform.system().lower() == "darwin" or pathlib.Path("/proc/sys/crypto/fips_enabled").exists():
                container.with_volume_mapping(
                    str(tmp_crypto / "crypto" / "fips_enabled"), "/proc/sys/crypto/fips_enabled", mode="ro,z"
                )
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

    def test_file_permissions(self, image: str, subtests: pytest_subtests.SubTests):
        """Checks the permissions and ownership for some selected files/directories."""

        app_root_path = "/opt/app-root"
        expected_uid = "1001"  # default
        expected_gid = "0"  # root
        # Directories to assert permissions and ownerships as we did in ODS-CI
        directories_to_check: list[list[str]] = [
            [f"{app_root_path}/lib", "775", expected_gid, expected_uid],
        ]
        if not utils.is_rstudio_image(image):
            # RStudio image doesn't have '/opt/app-root/share' directory
            directories_to_check.append([f"{app_root_path}/share", "775", expected_gid, expected_uid])

        def test_fn(container: testcontainers.core.container.DockerContainer):
            for item in directories_to_check:
                with subtests.test(f"Checking permissions of the: {item[0]}"):
                    # ignore `:%u`, it does not matter what the uid is, it's the gid that is nonrandom on openshift
                    _, output = container.exec(["stat", "--format='%a:%g'", f"{item[0]}"])
                    logging.debug(output.decode())
                    cleaned_output = output.decode().strip().strip("'")
                    assert cleaned_output == f"{item[1]}:{item[2]}"

        self._run_test(image=image, test_fn=test_fn)

    @staticmethod
    @allure.step("Verify AIPCC image has config file env vars and no index URL env vars")
    def _check_aipcc_env_vars(actual: dict[str, str], subtests: pytest_subtests.SubTests) -> None:
        """AIPCC images use pip.conf and uv.toml config files instead of index URL env vars."""
        aipcc_config_vars = {
            "PIP_CONFIG_FILE": "/opt/app-root/pip.conf",
            "UV_CONFIG_FILE": "/opt/app-root/uv.toml",
        }
        pypi_index_vars = ("PIP_INDEX_URL", "UV_INDEX_URL", "UV_DEFAULT_INDEX")

        with subtests.test("AIPCC images have config file env vars"):
            _assert_subdict(aipcc_config_vars, actual)
        with subtests.test("AIPCC images do not have index URL env vars"):
            for key in pypi_index_vars:
                assert key not in actual, f"Expected {key} to NOT be present (image uses uv.lock.d)"

    @staticmethod
    @allure.step("Verify non-AIPCC image has PyPI index URL env vars")
    def _check_pypi_env_vars(actual: dict[str, str], subtests: pytest_subtests.SubTests) -> None:
        """Non-AIPCC images set PIP_INDEX_URL, UV_INDEX_URL, and UV_DEFAULT_INDEX to pypi.org."""
        pypi_env_vars = {
            "PIP_INDEX_URL": "https://pypi.org/simple",
            "UV_INDEX_URL": "https://pypi.org/simple",
            # https://docs.astral.sh/uv/reference/environment/#uv_default_index
            "UV_DEFAULT_INDEX": "https://pypi.org/simple",
        }
        with subtests.test("Non-AIPCC images have index URL env vars"):
            _assert_subdict(pypi_env_vars, actual)

    @allure.issue("RHAIENG-2189")
    def test_python_package_index(self, image: str, subtests: pytest_subtests.SubTests):
        """Checks that we use the Python Package Index we mean to use.
        https://redhat-internal.slack.com/archives/C05TTTYG599/p1764240587118899?thread_ts=1764234802.564119&cid=C05TTTYG599

        Images with uv.lock.d directory do not need these env vars since dependencies
        are pinned with exact sources in the lockfile (RHAIENG-3056).
        """

        has_uv_lock_d = self._has_uv_lock_d(image)

        with self._test_container(image=image) as container:
            _, output = container.exec(["env"])
            actual = dict(line.split("=", maxsplit=1) for line in output.decode().strip().splitlines())

            if has_uv_lock_d:
                self._check_aipcc_env_vars(actual, subtests)
            else:
                self._check_pypi_env_vars(actual, subtests)


def encode_python_function_execution_command_interpreter(
    python: str, function: Callable[..., Any], *args: list[Any]
) -> list[str]:
    """Returns a cli command that will run the given Python function encoded inline.
    All dependencies (imports, ...) must be part of function body."""
    code = textwrap.dedent(inspect.getsource(function))
    ccode = binascii.b2a_base64(code.encode())
    name = function.__name__
    parameters = ", ".join(repr(arg) for arg in args)
    program = textwrap.dedent(f"""
        import binascii;
        s=binascii.a2b_base64("{ccode.decode("ascii").strip()}");
        exec(s.decode());
        print({name}({parameters}));""")
    int_cmd = [python, "-c", program]
    return int_cmd
