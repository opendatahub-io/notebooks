from __future__ import annotations

import json
import re
import shlex
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import allure
import pytest

from tests import PROJECT_ROOT
from tests.containers import conftest, docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if TYPE_CHECKING:
    from pytest import Subtests

CODESERVER_ROOT = PROJECT_ROOT / "codeserver/ubi9-python-3.12"
ACCESS_CGI_PATH = CODESERVER_ROOT / "nginx/api/kernels/access.cgi"
HTTPD_CONF_PATH = CODESERVER_ROOT / "httpd/httpd.conf"
PROXY_TEMPLATE_PATH = CODESERVER_ROOT / "nginx/serverconf/proxy.conf.template"
PROXY_TEMPLATE_NBPREFIX_PATH = CODESERVER_ROOT / "nginx/serverconf/proxy.conf.template_nbprefix"

# date -Iseconds output: 2026-03-18T01:23:45+00:00
RFC3339_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

# date -Iseconds has 1s resolution; allow 1s slack on each side of the CGI window.
_LAST_ACTIVITY_WINDOW_SLACK_S = 1.0


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


def _healthz_url(*, nb_prefix: str | None = None) -> str:
    probe_path = f"{nb_prefix}/api" if nb_prefix else "/api"
    return f"http://127.0.0.1:8888{probe_path}"


def _wait_for_healthz(container: WorkbenchContainer, *, nb_prefix: str | None = None, timeout: float = 120) -> None:
    """Poll code-server readiness via the platform probe path inside the container."""
    healthz_url = _healthz_url(nb_prefix=nb_prefix)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        container.get_wrapped_container().reload()
        assert container.get_wrapped_container().status != "exited", "codeserver container exited during startup"

        exit_code, _ = container.exec(["curl", "-sS", "-f", "-L", "-o", "/dev/null", "--max-time", "2", healthz_url])
        if exit_code == 0:
            return
        time.sleep(2)

    raise TimeoutError(f"code-server healthz did not become ready at {healthz_url} within {timeout}s")


def _fetch_healthz(container: WorkbenchContainer, *, nb_prefix: str | None = None) -> dict[str, Any]:
    """Return the parsed code-server healthz JSON from the platform probe path."""
    healthz_url = _healthz_url(nb_prefix=nb_prefix)
    exit_code, output = container.exec(["curl", "-sS", "-f", "-L", "--max-time", "5", healthz_url])
    assert exit_code == 0, f"healthz fetch failed: {output.decode(errors='replace')}"
    return json.loads(output.decode())


def _install_culling_stack(container: WorkbenchContainer) -> None:
    """Install workspace CGI + httpd + nginx proxy templates and reload the serving stack.

    Baked images may lag workspace; tests must exercise current routing, not only CGI bash logic.
    """
    wrapped = container.get_wrapped_container()
    docker_utils.container_cp(wrapped, str(ACCESS_CGI_PATH), "/opt/app-root/api/kernels", user=1001, group=0)
    docker_utils.container_cp(wrapped, str(HTTPD_CONF_PATH), "/etc/httpd/conf", user=1001, group=0)
    docker_utils.container_cp(
        wrapped, str(PROXY_TEMPLATE_PATH), "/opt/app-root/etc/nginx.default.d", user=1001, group=0
    )
    docker_utils.container_cp(
        wrapped, str(PROXY_TEMPLATE_NBPREFIX_PATH), "/opt/app-root/etc/nginx.default.d", user=1001, group=0
    )

    # Mirror run-nginx.sh template selection, then reload nginx and httpd.
    # Use `httpd -k start|graceful` (daemonizes) — NOT `httpd -D FOREGROUND &` under
    # container.exec, which gets SIGTERM (exit 143) when the exec session ends.
    exit_code, output = container.exec(
        [
            "bash",
            "-c",
            """
set -euo pipefail
if [ -z "${NB_PREFIX:-}" ]; then
  cp /opt/app-root/etc/nginx.default.d/proxy.conf.template \\
    /opt/app-root/etc/nginx.default.d/proxy.conf
else
  export BASE_URL=_
  envsubst '${NB_PREFIX},${BASE_URL}' \\
    < /opt/app-root/etc/nginx.default.d/proxy.conf.template_nbprefix \\
    > /opt/app-root/etc/nginx.default.d/proxy.conf
fi
nginx -s reload
if pgrep httpd >/dev/null 2>&1; then
  /usr/sbin/httpd -k graceful
else
  /usr/sbin/httpd -k start
fi
pgrep httpd >/dev/null
""",
        ]
    )
    assert exit_code == 0, f"failed to reload nginx/httpd stack: {output.decode(errors='replace')}"


def _container_epoch_s(container: WorkbenchContainer) -> float:
    """Return the container's current Unix epoch seconds (avoids host/container clock skew)."""
    exit_code, output = container.exec(["date", "+%s"])
    assert exit_code == 0, f"date failed: {output.decode(errors='replace')}"
    return float(output.decode().strip())


def _get_kernels_via_http(
    container: WorkbenchContainer, *, kernels_path: str
) -> tuple[int, list[dict[str, Any]] | None]:
    """GET the culling kernels URL through nginx→httpd (not a direct CGI bash invoke)."""
    assert kernels_path.startswith("/"), f"kernels_path must be absolute, got {kernels_path!r}"
    url = f"http://127.0.0.1:8888{kernels_path}"
    # Body then a final line with the HTTP status code.
    cmd = f"curl -sS -L --max-time 10 -w '\\n%{{http_code}}' {shlex.quote(url)}"
    exit_code, output = container.exec(["bash", "-c", cmd])
    text = output.decode(errors="replace")
    assert exit_code == 0, f"kernels HTTP request failed for {url}: {text}"

    body, _, status_str = text.rstrip("\n").rpartition("\n")
    status = int(status_str)
    if status != 200:
        return status, None
    return status, json.loads(body)


def _invoke_access_cgi_with_healthz_stub(
    container: WorkbenchContainer, *, healthz_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Direct CGI invoke with a stubbed healthz body (HTTP path cannot inject curl stubs under httpd)."""
    payload = shlex.quote(json.dumps(healthz_payload, separators=(",", ":")))
    cmd = f"""
set -euo pipefail
STUBDIR=$(mktemp -d)
printf '%s' {payload} > "$STUBDIR/healthz.json"
cat > "$STUBDIR/curl" << 'EOF'
#!/bin/bash
cat "$(dirname "$0")/healthz.json"
exit 0
EOF
chmod +x "$STUBDIR/curl"
PATH="$STUBDIR:$PATH" bash /opt/app-root/api/kernels/access.cgi | tail -1
"""
    exit_code, output = container.exec(["bash", "-c", cmd])
    assert exit_code == 0, f"access.cgi stub execution failed: {output.decode(errors='replace')}"
    return json.loads(output.decode())


def _assert_valid_kernel_record(kernel: dict[str, Any]) -> None:
    assert kernel.get("id") == "code-server", f"expected id 'code-server', got {kernel.get('id')!r}"
    assert kernel.get("name") == "code-server", f"expected name 'code-server', got {kernel.get('name')!r}"
    assert kernel.get("connections") == 1, f"expected connections 1, got {kernel.get('connections')!r}"

    last_activity = kernel.get("last_activity")
    assert isinstance(last_activity, str) and last_activity, "last_activity must be a non-empty RFC3339 timestamp"
    assert RFC3339_PATTERN.match(last_activity), f"last_activity is not RFC3339: {last_activity!r}"

    execution_state = kernel.get("execution_state")
    assert execution_state in {"busy", "idle"}, f"execution_state must be busy or idle, got {execution_state!r}"


def _assert_last_activity_within_window(last_activity: str, *, before: float, after: float) -> None:
    """Assert last_activity is a current-time fallback within the CGI invocation window."""
    ts = datetime.fromisoformat(last_activity).timestamp()
    lo = before - _LAST_ACTIVITY_WINDOW_SLACK_S
    hi = after + _LAST_ACTIVITY_WINDOW_SLACK_S
    assert lo <= ts <= hi, (
        f"last_activity {last_activity!r} (epoch {ts}) not within CGI window [{before}, {after}] "
        f"(±{_LAST_ACTIVITY_WINDOW_SLACK_S}s)"
    )


@pytest.mark.codeserver
class TestCullingApi:
    """Regression tests for access.cgi /api/kernels/ shim (RHAIENG-3712)."""

    @allure.issue("RHAIENG-3712")
    @allure.description(
        "With NB_PREFIX set, nginx must proxy ${NB_PREFIX}/api/kernels/ to httpd CGI. "
        "Legacy /api/kernels/ is not registered in the prefixed nginx template."
    )
    def test_kernels_api_with_nb_prefix(self, codeserver_image: conftest.Image) -> None:
        env = _codeserver_platform_env()
        nb_prefix = env["NB_PREFIX"]

        with WorkbenchContainer(image=codeserver_image.name, user=1000, group_add=[0]) as container:
            for key, value in env.items():
                container.with_env(key, value)
            container.start(wait_for_readiness=False)
            _wait_for_healthz(container, nb_prefix=nb_prefix)
            _install_culling_stack(container)

            healthz = _fetch_healthz(container, nb_prefix=nb_prefix)
            status, kernels = _get_kernels_via_http(container, kernels_path=f"{nb_prefix}/api/kernels/")
            assert status == 200, f"expected 200 for prefixed kernels URL, got {status}"
            assert kernels is not None and len(kernels) == 1
            _assert_valid_kernel_record(kernels[0])
            # Fresh pod healthz is expired (lastHeartbeat=0). CGI polls code-server
            # directly on :8787 (not nginx), so NB_PREFIX must not affect this mapping.
            expected_state = "busy" if healthz.get("status") == "alive" else "idle"
            assert kernels[0]["execution_state"] == expected_state, (
                f"CGI must map healthz status={healthz.get('status')!r} to "
                f"execution_state={expected_state!r} (got {kernels[0]!r}; healthz={healthz!r})."
            )

            legacy_status, legacy_kernels = _get_kernels_via_http(container, kernels_path="/api/kernels/")
            assert legacy_status == 404, f"expected 404 for legacy kernels URL under NB_PREFIX, got {legacy_status}"
            assert legacy_kernels is None

    @allure.issue("RHAIENG-3712")
    @allure.description(
        "On a fresh pod, code-server reports lastHeartbeat=0 until the first user interaction. "
        "access.cgi must fall back to current time for last_activity (same as when lastHeartbeat is absent)."
    )
    def test_kernels_api_fresh_pod_last_heartbeat_zero(
        self, subtests: Subtests, codeserver_image: conftest.Image
    ) -> None:
        platform_env = _codeserver_platform_env()
        scenarios = [
            ("without NB_PREFIX", "", "/api/kernels/", {}),
            (
                "with NB_PREFIX",
                platform_env["NB_PREFIX"],
                f"{platform_env['NB_PREFIX']}/api/kernels/",
                platform_env,
            ),
        ]
        for label, nb_prefix, kernels_path, env in scenarios:
            with subtests.test(label):
                with WorkbenchContainer(image=codeserver_image.name, user=1000, group_add=[0]) as container:
                    for key, value in env.items():
                        container.with_env(key, value)
                    container.start(wait_for_readiness=False)
                    _wait_for_healthz(container, nb_prefix=nb_prefix or None)
                    _install_culling_stack(container)

                    healthz = _fetch_healthz(container, nb_prefix=nb_prefix or None)
                    assert healthz.get("lastHeartbeat") == 0, f"expected fresh-pod lastHeartbeat 0, got {healthz!r}"

                    before = _container_epoch_s(container)
                    status, kernels = _get_kernels_via_http(container, kernels_path=kernels_path)
                    after = _container_epoch_s(container)

                    assert status == 200, f"expected 200 for {kernels_path}, got {status}"
                    assert kernels is not None and len(kernels) == 1
                    _assert_valid_kernel_record(kernels[0])
                    _assert_last_activity_within_window(kernels[0]["last_activity"], before=before, after=after)

        with subtests.test("missing lastHeartbeat falls back to now"):
            # Controlled healthz stub cannot be injected through httpd's CGI child PATH.
            with WorkbenchContainer(image=codeserver_image.name, user=1000, group_add=[0]) as container:
                container.start(wait_for_readiness=False)
                docker_utils.container_cp(
                    container.get_wrapped_container(),
                    str(ACCESS_CGI_PATH),
                    "/opt/app-root/api/kernels",
                    user=1001,
                    group=0,
                )

                before = _container_epoch_s(container)
                kernels = _invoke_access_cgi_with_healthz_stub(container, healthz_payload={"status": "alive"})
                after = _container_epoch_s(container)

                assert len(kernels) == 1
                _assert_valid_kernel_record(kernels[0])
                _assert_last_activity_within_window(kernels[0]["last_activity"], before=before, after=after)

    @allure.issue("RHAIENG-3712")
    @allure.description("Without NB_PREFIX, the legacy /api/kernels/ nginx→httpd path must keep working.")
    def test_kernels_api_without_nb_prefix(self, codeserver_image: conftest.Image) -> None:
        with WorkbenchContainer(image=codeserver_image.name, user=1000, group_add=[0]) as container:
            container.start(wait_for_readiness=False)
            _wait_for_healthz(container)
            _install_culling_stack(container)

            status, kernels = _get_kernels_via_http(container, kernels_path="/api/kernels/")
            assert status == 200, f"expected 200 for legacy kernels URL, got {status}"
            assert kernels is not None and len(kernels) == 1
            _assert_valid_kernel_record(kernels[0])
