from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, Any

import allure
import pytest

from tests import PROJECT_ROOT
from tests.containers import conftest, docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if TYPE_CHECKING:
    import pytest_subtests

ACCESS_CGI_PATH = PROJECT_ROOT / "codeserver/ubi9-python-3.12/nginx/api/kernels/access.cgi"

# date -Iseconds output: 2026-03-18T01:23:45+00:00
RFC3339_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


def _codeserver_platform_env(project: str = "test-ns", notebook: str = "test-notebook") -> dict[str, str]:
    """Env vars notebook-controller injects for a prefixed workbench route."""
    nb_prefix = f"/notebook/{project}/{notebook}"
    notebook_args = " ".join(
        [
            "--ServerApp.port=8888",
            "--ServerApp.token=''",
            "--ServerApp.password=''",
            f"--ServerApp.base_url={nb_prefix}",
            "--ServerApp.quit_button=False",
        ]
    )
    return {
        "NB_PREFIX": nb_prefix,
        "NOTEBOOK_ARGS": notebook_args,
    }


def _wait_for_healthz(container: WorkbenchContainer, *, nb_prefix: str | None = None, timeout: float = 120) -> None:
    """Poll code-server readiness via the platform probe path inside the container."""
    probe_path = f"{nb_prefix}/api" if nb_prefix else "/api"
    healthz_url = f"http://127.0.0.1:8888{probe_path}"
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        container.get_wrapped_container().reload()
        assert container.get_wrapped_container().status != "exited", "codeserver container exited during startup"

        exit_code, _ = container.exec(
            ["curl", "-sS", "-f", "-L", "-o", "/dev/null", "--max-time", "2", healthz_url]
        )
        if exit_code == 0:
            return
        time.sleep(2)

    raise TimeoutError(f"code-server healthz did not become ready at {healthz_url} within {timeout}s")


def _install_access_cgi(container: WorkbenchContainer) -> None:
    """Install the workspace access.cgi so tests exercise current source, not only a baked image."""
    docker_utils.container_cp(
        container.get_wrapped_container(),
        str(ACCESS_CGI_PATH),
        "/opt/app-root/api/kernels",
        user=1001,
        group=0,
    )


def _invoke_access_cgi(container: WorkbenchContainer, *, nb_prefix: str = "") -> list[dict[str, Any]]:
    """Execute access.cgi directly (RHAIENG-3712 scope: CGI logic, not httpd/nginx routing)."""
    exit_code, output = container.exec(
        [
            "bash",
            "-c",
            f"NB_PREFIX={nb_prefix!r} bash /opt/app-root/api/kernels/access.cgi | tail -1",
        ]
    )
    assert exit_code == 0, f"access.cgi execution failed: {output.decode(errors='replace')}"
    return json.loads(output.decode())


def _assert_valid_kernel_record(kernel: dict[str, Any]) -> None:
    assert kernel.get("id") == "code-server"
    assert kernel.get("name") == "code-server"
    assert kernel.get("connections") == 1

    last_activity = kernel.get("last_activity")
    assert isinstance(last_activity, str) and last_activity, "last_activity must be a non-empty RFC3339 timestamp"
    assert RFC3339_PATTERN.match(last_activity), f"last_activity is not RFC3339: {last_activity!r}"

    execution_state = kernel.get("execution_state")
    assert execution_state in {"busy", "idle"}, f"execution_state must be busy or idle, got {execution_state!r}"


@pytest.mark.codeserver
class TestCullingApi:
    """Regression tests for access.cgi /api/kernels/ shim (RHAIENG-3712)."""

    @allure.issue("RHAIENG-3712")
    @allure.description(
        "With NB_PREFIX set, access.cgi must reach healthz via ${NB_PREFIX}/api (the platform probe path). "
        "A hardcoded /codeserver/healthz leaves last_activity and execution_state empty."
    )
    def test_kernels_api_with_nb_prefix(self, codeserver_image: conftest.Image) -> None:
        env = _codeserver_platform_env()
        nb_prefix = env["NB_PREFIX"]

        with WorkbenchContainer(image=codeserver_image.name, user=1000, group_add=[0]) as container:
            for key, value in env.items():
                container.with_env(key, value)
            container.start(wait_for_readiness=False)
            _wait_for_healthz(container, nb_prefix=nb_prefix)
            _install_access_cgi(container)

            kernels = _invoke_access_cgi(container, nb_prefix=nb_prefix)
            assert len(kernels) == 1
            _assert_valid_kernel_record(kernels[0])

    @allure.issue("RHAIENG-3712")
    @allure.description(
        "On a fresh pod, code-server reports lastHeartbeat=0 until the first user interaction. "
        "access.cgi must still emit a valid last_activity and execution_state."
    )
    def test_kernels_api_fresh_pod_last_heartbeat_zero(
        self, subtests: pytest_subtests.SubTests, codeserver_image: conftest.Image
    ) -> None:
        platform_env = _codeserver_platform_env()
        scenarios = [
            ("without NB_PREFIX", "", {}),
            ("with NB_PREFIX", platform_env["NB_PREFIX"], platform_env),
        ]
        for label, nb_prefix, env in scenarios:
            with subtests.test(label):
                with WorkbenchContainer(image=codeserver_image.name, user=1000, group_add=[0]) as container:
                    for key, value in env.items():
                        container.with_env(key, value)
                    container.start(wait_for_readiness=False)
                    _wait_for_healthz(container, nb_prefix=nb_prefix or None)
                    _install_access_cgi(container)

                    kernels = _invoke_access_cgi(container, nb_prefix=nb_prefix)
                    assert len(kernels) == 1
                    _assert_valid_kernel_record(kernels[0])

    @allure.issue("RHAIENG-3712")
    @allure.description("Without NB_PREFIX, the legacy /codeserver/healthz path must keep working.")
    def test_kernels_api_without_nb_prefix(self, codeserver_image: conftest.Image) -> None:
        with WorkbenchContainer(image=codeserver_image.name, user=1000, group_add=[0]) as container:
            container.start(wait_for_readiness=False)
            _wait_for_healthz(container)
            _install_access_cgi(container)

            kernels = _invoke_access_cgi(container)
            assert len(kernels) == 1
            _assert_valid_kernel_record(kernels[0])
