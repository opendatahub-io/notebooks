# SPDX-License-Identifier: Apache-2.0
"""Copr build submission and status polling."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import tempfile
import time

import stamina

logger = logging.getLogger(__name__)

_DEFAULT_WAIT_TIMEOUT = 12 * 3600  # 12 hours

# Terminal build statuses
_SUCCEEDED = "succeeded"
_FAILED = "failed"
_CANCELED = "canceled"
_TERMINAL_STATUSES = frozenset({_SUCCEEDED, _FAILED, _CANCELED})

_SKIP_TESTS_SCRIPT_TEMPLATE = """\
#!/bin/bash
set -Eeuxo pipefail
curl --retry 5 --retry-delay 3 --fail -L -o original.src.rpm {srpm_url}
rpm2cpio original.src.rpm | cpio -idmv
rm original.src.rpm
sed -i '/^%check/a exit 0' *.spec
"""

_SCRIPT_CHROOT = "fedora-rawhide-x86_64"
_SCRIPT_BUILDDEPS = "curl rpm cpio"


class CoprBuildError(Exception):
    """Raised when a Copr build fails."""

    def __init__(self, build_id: int, status: str) -> None:
        self.build_id = build_id
        self.status = status
        super().__init__(f"Copr build {build_id} ended with status: {status}")


class CoprCliError(Exception):
    """Raised when copr-cli returns a non-zero exit code."""

    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        detail = stderr.strip() or stdout.strip() or "(no output)"
        super().__init__(f"copr-cli failed (exit {returncode}): {detail}")


class CoprClient:
    """Client for submitting and monitoring builds on Fedora Copr."""

    def __init__(self, project: str) -> None:
        """Initialize with a Copr project identifier.

        Args:
            project: Copr project in owner/name format (e.g. 'opendatahub/rhelai-el9')
        """
        self.project = project

    _CLI_TIMEOUT_SECONDS = 300

    def _run_copr_cli(self, cmd: list[str]) -> str:
        """Run a copr-cli command and return stdout.

        Raises:
            CoprCliError: If copr-cli returns a non-zero exit code.
            subprocess.TimeoutExpired: If the command exceeds ``_CLI_TIMEOUT_SECONDS``.
        """
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=self._CLI_TIMEOUT_SECONDS)
        if result.returncode != 0:
            raise CoprCliError(cmd, result.returncode, result.stdout, result.stderr)
        return result.stdout

    def _parse_build_id(self, stdout: str) -> int:
        """Extract build ID from copr-cli output like 'Created builds: 12345'.

        Raises:
            RuntimeError: If the build ID cannot be parsed.
        """
        for line in stdout.splitlines():
            if "Created builds:" in line:
                try:
                    return int(line.split(":")[-1].strip())
                except ValueError:
                    break
        msg = f"Could not parse build ID from copr-cli output:\n{stdout}"
        raise RuntimeError(msg)

    def configure_chroot(
        self,
        chroot: str,
        *,
        packages: list[str] | None = None,
    ) -> None:
        """Configure a Copr mock chroot.

        Calls ``copr-cli edit-chroot`` to set additional buildroot packages.

        Note: ``--packages`` *replaces* the current additional-package list.

        Args:
            chroot: Chroot name (e.g. 'epel-9-x86_64').
            packages: Extra packages to install in the buildroot.

        Raises:
            CoprCliError: If copr-cli returns a non-zero exit code.
        """
        chroot_path = f"{self.project}/{chroot}"
        cmd: list[str] = ["copr-cli", "edit-chroot", chroot_path]

        if not packages:
            return

        cmd.extend(["--packages", " ".join(packages)])
        logger.info("Configuring chroot %s: %s", chroot_path, " ".join(cmd[3:]))
        self._run_copr_cli(cmd)

    @staticmethod
    def _append_batch_args(
        cmd: list[str],
        *,
        timeout: int | None = None,
        with_build_id: int | None = None,
        after_build_id: int | None = None,
    ) -> None:
        """Append timeout and batch-ordering flags to a copr-cli command."""
        if timeout is not None:
            cmd.extend(["--timeout", str(timeout)])
        if with_build_id is not None:
            cmd.extend(["--with-build-id", str(with_build_id)])
        if after_build_id is not None:
            cmd.extend(["--after-build-id", str(after_build_id)])

    def submit_build(
        self,
        srpm_url: str,
        *,
        timeout: int | None = None,
        with_build_id: int | None = None,
        after_build_id: int | None = None,
    ) -> int:
        """Submit a build to Copr from an SRPM URL.

        Args:
            srpm_url: URL to the source RPM to build.
            timeout: Build timeout in seconds. If not set, Copr's default
                (~5 hours) applies.
            with_build_id: Add this build to the same batch as the given build ID.
                Builds in the same batch run in parallel.
            after_build_id: Create a new batch for this build that is blocked until
                the batch containing the given build ID finishes.

        Returns:
            The Copr build ID.

        Raises:
            RuntimeError: If the build ID cannot be parsed from copr-cli output.
            CoprCliError: If copr-cli returns a non-zero exit code.
        """
        logger.info("Submitting build to %s: %s", self.project, srpm_url)
        cmd = ["copr-cli", "build", "--nowait", self.project, srpm_url]
        self._append_batch_args(cmd, timeout=timeout, with_build_id=with_build_id, after_build_id=after_build_id)
        stdout = self._run_copr_cli(cmd)
        return self._parse_build_id(stdout)

    def submit_custom_build(
        self,
        srpm_url: str,
        *,
        timeout: int | None = None,
        with_build_id: int | None = None,
        after_build_id: int | None = None,
    ) -> int:
        """Submit a custom build that patches the spec to skip %check.

        Downloads the SRPM, extracts it, injects ``exit 0`` after ``%check``
        in the spec file, and lets Copr build from the unpacked content.

        Args:
            srpm_url: URL to the source RPM to download and patch.
            timeout: Build timeout in seconds.
            with_build_id: Add this build to the same batch as the given build ID.
            after_build_id: Chain this build after the given build ID's batch.

        Returns:
            The Copr build ID.

        Raises:
            RuntimeError: If the build ID cannot be parsed from copr-cli output.
            CoprCliError: If copr-cli returns a non-zero exit code.
        """
        logger.info("Submitting custom build (skip_tests) to %s: %s", self.project, srpm_url)
        script_content = _SKIP_TESTS_SCRIPT_TEMPLATE.format(srpm_url=shlex.quote(srpm_url))

        fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="copr_skip_tests_")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(script_content)

            cmd = [
                "copr-cli",
                "buildcustom",
                "--nowait",
                "--script",
                script_path,
                "--script-builddeps",
                _SCRIPT_BUILDDEPS,
                "--script-chroot",
                _SCRIPT_CHROOT,
                "--script-resultdir",
                ".",
                "--enable-net",
                "on",
                self.project,
            ]
            self._append_batch_args(cmd, timeout=timeout, with_build_id=with_build_id, after_build_id=after_build_id)

            stdout = self._run_copr_cli(cmd)
            return self._parse_build_id(stdout)
        finally:
            os.unlink(script_path)

    @stamina.retry(on=CoprCliError, attempts=5, wait_initial=2.0, wait_max=60.0, wait_jitter=5.0)
    def get_build_status(self, build_id: int) -> str:
        """Query the status of a Copr build.

        Transient ``CoprCliError`` failures (e.g. network blips) are retried
        automatically via stamina with exponential backoff.

        Args:
            build_id: The Copr build ID.

        Returns:
            Build status string (e.g. 'succeeded', 'failed', 'pending', 'running').

        Raises:
            CoprCliError: If copr-cli returns a non-zero exit code after retries.
        """
        cmd = ["copr-cli", "status", str(build_id)]
        return self._run_copr_cli(cmd).strip()

    def wait_for_build(
        self,
        build_id: int,
        poll_interval: int = 30,
        timeout: int = _DEFAULT_WAIT_TIMEOUT,
    ) -> str:
        """Poll until a build reaches a terminal state.

        Uses exponential backoff (capped at 5 minutes) for CI-friendly polling,
        and emits periodic keep-alive summaries for long-running builds.

        Args:
            build_id: The Copr build ID.
            poll_interval: Initial seconds between status polls.
            timeout: Maximum seconds to wait before raising TimeoutError.

        Returns:
            The terminal status string ('succeeded', 'failed', or 'canceled').

        Raises:
            TimeoutError: If the build does not finish within ``timeout`` seconds.
        """
        deadline = time.monotonic() + timeout
        interval = poll_interval
        max_interval = 300  # 5 minutes
        polls = 0

        while True:
            status = self.get_build_status(build_id)
            polls += 1
            elapsed = timeout - (deadline - time.monotonic())

            if status in _TERMINAL_STATUSES:
                logger.info("Build %d: %s (after %d polls, %.0fs)", build_id, status, polls, elapsed)
                return status

            # Keep-alive summary every ~10 polls
            if polls % 10 == 0:
                logger.info(
                    "Build %d: still %s (poll #%d, %.0fs elapsed, next check in %ds)",
                    build_id,
                    status,
                    polls,
                    elapsed,
                    interval,
                )
            else:
                logger.info("Build %d: %s", build_id, status)

            if time.monotonic() + interval > deadline:
                msg = f"Timed out waiting for build {build_id} after {timeout}s (last status: {status})"
                raise TimeoutError(msg)

            time.sleep(interval)
            interval = min(interval * 1.5, max_interval)

    def submit_wave(self, srpm_urls: list[str], *, timeout: int | None = None) -> list[int]:
        """Submit all packages in a build wave.

        Args:
            srpm_urls: List of SRPM URLs to submit.
            timeout: Build timeout in seconds per build.

        Returns:
            List of Copr build IDs.
        """
        return [self.submit_build(url, timeout=timeout) for url in srpm_urls]

    def submit_all_waves(
        self,
        waves: list[list[tuple[str, str]]],
        *,
        timeout: int | None = None,
        skip_tests_names: frozenset[str] = frozenset(),
    ) -> list[list[int]]:
        """Submit all build waves at once using Copr batch ordering.

        Builds within the same wave are placed in the same batch
        (``--with-build-id``) so they run in parallel.  Each wave's batch
        is chained after the previous wave's batch (``--after-build-id``)
        so Copr enforces the correct build order server-side.

        Packages whose names appear in ``skip_tests_names`` are submitted
        via ``submit_custom_build`` (which patches ``%check`` to skip tests).

        Args:
            waves: List of waves, where each wave is a list of
                ``(package_name, srpm_url)`` tuples.
            timeout: Build timeout in seconds per build.
            skip_tests_names: Package names that should skip ``%check``.

        Returns:
            List of lists of Copr build IDs (one inner list per wave).
        """
        all_wave_ids: list[list[int]] = []
        prev_wave_anchor: int | None = None

        for wave_items in waves:
            wave_ids: list[int] = []
            wave_anchor: int | None = None

            for i, (name, url) in enumerate(wave_items):
                submit = self.submit_custom_build if name in skip_tests_names else self.submit_build
                if i == 0:
                    # First build in the wave: chain after previous wave (if any)
                    build_id = submit(
                        url,
                        timeout=timeout,
                        after_build_id=prev_wave_anchor,
                    )
                    wave_anchor = build_id
                else:
                    # Subsequent builds: same batch as the first build in this wave
                    build_id = submit(
                        url,
                        timeout=timeout,
                        with_build_id=wave_anchor,
                    )
                wave_ids.append(build_id)

            all_wave_ids.append(wave_ids)
            prev_wave_anchor = wave_anchor

        return all_wave_ids

    def wait_for_wave(
        self,
        build_ids: list[int],
        poll_interval: int = 30,
        timeout: int = _DEFAULT_WAIT_TIMEOUT,
    ) -> None:
        """Wait for all builds to complete, polling round-robin for fast failure detection.

        Args:
            build_ids: List of Copr build IDs to monitor.
            poll_interval: Seconds between polling rounds.
            timeout: Maximum seconds to wait before raising TimeoutError.

        Raises:
            CoprBuildError: If any build fails or is canceled.
            TimeoutError: If builds do not finish within ``timeout`` seconds.
        """
        deadline = time.monotonic() + timeout
        pending = set(build_ids)
        while pending:
            for bid in list(pending):
                status = self.get_build_status(bid)
                logger.info("Build %d: %s", bid, status)
                if status == _SUCCEEDED:
                    pending.discard(bid)
                elif status in (_FAILED, _CANCELED):
                    raise CoprBuildError(bid, status)
            if pending:
                if time.monotonic() + poll_interval > deadline:
                    raise TimeoutError(f"Timed out waiting for builds {sorted(pending)} after {timeout}s")
                time.sleep(poll_interval)
