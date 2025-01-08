from __future__ import annotations

import logging
import pathlib
import tempfile
from typing import TYPE_CHECKING

import testcontainers.core.container
import testcontainers.core.waiting_utils

from tests.containers import docker_utils

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pytest_subtests


class TestBaseImage:
    """Tests that are applicable for all images we have in this repository."""

    def test_oc_command_runs(self, image: str):
        container = testcontainers.core.container.DockerContainer(image=image, user=123456, group_add=[0])
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

            container = testcontainers.core.container.DockerContainer(image=image, user=654321, group_add=[0])
            container.with_volume_mapping(str(tmp_crypto), "/proc/sys")
            container.with_command("/bin/sh -c 'sleep infinity'")

            try:
                container.start()

                with subtests.test("/proc/sys/crypto/fips_enabled is 1"):
                    ecode, output = container.exec(["/bin/sh", "-c", "sysctl crypto.fips_enabled"])
                    assert ecode == 0, output.decode()
                    assert "crypto.fips_enabled = 1\n" == output.decode(), output.decode()

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
