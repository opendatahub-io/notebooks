# SPDX-License-Identifier: Apache-2.0
"""Copr build submission and status polling."""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger(__name__)


class CoprBuildError(Exception):
    """Raised when a Copr build fails."""

    def __init__(self, build_id: int, status: str) -> None:
        self.build_id = build_id
        self.status = status
        super().__init__(f"Copr build {build_id} ended with status: {status}")


class CoprClient:
    """Client for submitting and monitoring builds on Fedora Copr."""

    def __init__(self, project: str) -> None:
        """Initialize with a Copr project identifier.

        Args:
            project: Copr project in owner/name format (e.g. 'opendatahub/rhelai-el9')
        """
        self.project = project

    def submit_build(self, srpm_url: str) -> int:
        """Submit a build to Copr from an SRPM URL.

        Args:
            srpm_url: URL to the source RPM to build.

        Returns:
            The Copr build ID.

        Raises:
            RuntimeError: If the build ID cannot be parsed from copr-cli output.
            subprocess.CalledProcessError: If copr-cli returns a non-zero exit code.
        """
        logger.info("Submitting build to %s: %s", self.project, srpm_url)
        result = subprocess.run(
            ["copr-cli", "build", "--nowait", self.project, srpm_url],
            capture_output=True,
            text=True,
            check=True,
        )
        # Parse build ID from output like "Created builds: 12345"
        for line in result.stdout.splitlines():
            if "Created builds:" in line:
                return int(line.split(":")[-1].strip())
        msg = f"Could not parse build ID from copr-cli output:\n{result.stdout}"
        raise RuntimeError(msg)

    def get_build_status(self, build_id: int) -> str:
        """Query the status of a Copr build.

        Args:
            build_id: The Copr build ID.

        Returns:
            Build status string (e.g. 'succeeded', 'failed', 'pending', 'running').
        """
        result = subprocess.run(
            ["copr-cli", "status", str(build_id)],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def wait_for_build(self, build_id: int, poll_interval: int = 30) -> bool:
        """Poll until a build completes.

        Args:
            build_id: The Copr build ID.
            poll_interval: Seconds between status polls.

        Returns:
            True if the build succeeded, False if it failed or was canceled.
        """
        while True:
            status = self.get_build_status(build_id)
            logger.info("Build %d: %s", build_id, status)
            if status == "succeeded":
                return True
            if status in ("failed", "canceled"):
                return False
            time.sleep(poll_interval)

    def submit_wave(self, srpm_urls: list[str]) -> list[int]:
        """Submit all packages in a build wave.

        Args:
            srpm_urls: List of SRPM URLs to submit.

        Returns:
            List of Copr build IDs.
        """
        return [self.submit_build(url) for url in srpm_urls]

    def wait_for_wave(self, build_ids: list[int], poll_interval: int = 30) -> None:
        """Wait for all builds in a wave to complete.

        Args:
            build_ids: List of Copr build IDs to monitor.
            poll_interval: Seconds between status polls.

        Raises:
            CoprBuildError: If any build in the wave fails.
        """
        for bid in build_ids:
            if not self.wait_for_build(bid, poll_interval=poll_interval):
                status = self.get_build_status(bid)
                raise CoprBuildError(bid, status)
