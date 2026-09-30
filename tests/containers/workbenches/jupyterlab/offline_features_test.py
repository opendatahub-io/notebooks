"""Offline JupyterLab workbench feature checks using an internal sidecar."""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import docker.errors
import pytest
import testcontainers.core.docker_client
import testcontainers.core.network

from tests.containers import conftest, docker_utils, podman_machine_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if TYPE_CHECKING:
    from collections.abc import Iterator

BASE_URL = "/offline/"
SERVER_ARGS = "\n".join(
    [
        "--ServerApp.port=8888",
        "--ServerApp.token=''",
        "--ServerApp.password=''",
        f"--ServerApp.base_url={BASE_URL}",
        "--ServerApp.quit_button=False",
        "--ServerApp.disable_check_xsrf=True",
    ]
)
DEFAULT_USER = 4321
PROBE_PATH = pathlib.Path(__file__).with_name("offline_probe.py")


def has_ipv4_default_route(table: str) -> bool:
    """Linux /proc/net/route: destination is column 1 and mask is column 7."""
    return any(
        fields[1] == "00000000" and fields[7] == "00000000"
        for line in table.splitlines()[1:]
        if (fields := line.split()) and len(fields) >= 8 and fields[0] not in {"lo", "unreachable"}
    )


def has_ipv6_default_route(table: str) -> bool:
    """Linux /proc/net/ipv6_route: destination and prefix length are columns 0 and 1."""
    return any(
        fields[0] == "0" * 32 and fields[1] == "00" and fields[-1] != "lo"
        for line in table.splitlines()
        if (fields := line.split()) and len(fields) >= 10 and fields[-1] not in {"lo", "unreachable"}
    )


class TestOfflineRouteParsers:
    def test_route_parsers(self) -> None:
        ipv4_header = "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
        ipv4_default = ipv4_header + "eth0 00000000 0100000A 0003 0 0 0 00000000 1500 0 0"
        ipv4_internal = ipv4_header + "eth0 0A000002 00000000 0001 0 0 0 00FFFFFF 1500 0 0"
        assert has_ipv4_default_route(ipv4_default)
        assert not has_ipv4_default_route(ipv4_internal)
        ipv4_unreachable = ipv4_header + "unreachable 00000000 00000000 0000 0 0 0 00000000 1500 0 0"
        assert not has_ipv4_default_route(ipv4_unreachable)
        ipv6_default = (
            "0" * 32 + " 00 " + "0" * 32 + " 00 " + "1" * 32 + " 00000000 00000000 00000000 00000000 00000000 eth0"
        )
        ipv6_internal = (
            "fd000000000000000000000000000001 40 "
            + "0" * 32
            + " 00 "
            + "0" * 32
            + " 00000000 00000000 00000000 00000000 00000000 eth0"
        )
        assert has_ipv6_default_route(ipv6_default)
        assert not has_ipv6_default_route(ipv6_internal)
        assert not has_ipv6_default_route(ipv6_default.replace("eth0", "unreachable"))


@pytest.fixture(scope="session")
def offline_jupyterlab_image(image: str) -> conftest.Image:
    docker_client = testcontainers.core.docker_client.DockerClient()
    try:
        local_image = docker_client.client.images.get(image)
    except docker.errors.ImageNotFound as exc:
        pytest.fail(
            f"Offline tests require a preloaded image: {image!r}; pull it separately.",
            pytrace=False,
        )
        raise AssertionError from exc
    finally:
        docker_client.client.close()
    metadata = conftest.Image.from_docker(local_image, name=image)
    if metadata.workbench_type is not conftest.WorkbenchType.JUPYTER:
        pytest.skip(f"Image {image} is not a Jupyter workbench")
    return metadata


def _image_id(image: conftest.Image) -> str:
    assert image.id is not None
    return image.id


class OfflineWorkbenchContainer(WorkbenchContainer):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.ports.clear()
        self.with_kwargs(user=DEFAULT_USER, group_add=[0])


@contextmanager
def running_offline_workbench(
    image: str, *, env: dict[str, str] | None = None, volume: pathlib.Path | None = None
) -> Iterator[OfflineWorkbenchContainer]:
    network = testcontainers.core.network.Network(docker_network_kw={"internal": True, "enable_ipv6": False})
    container = None
    docker_client = testcontainers.core.docker_client.DockerClient()
    try:
        network.create()
        container = OfflineWorkbenchContainer(image=image, user=DEFAULT_USER, group_add=[0])
        container.with_network(network).with_network_aliases("jupyterlab")
        container.with_kwargs(network=network.name, user=DEFAULT_USER, group_add=[0])
        container.with_env("NOTEBOOK_ARGS", SERVER_ARGS)
        if env:
            for key, value in env.items():
                container.with_env(key, value)
        if volume is not None:
            volume.mkdir(parents=True, exist_ok=True)
            volume.chmod(0o777)
            container.with_volume_mapping(str(volume), "/opt/app-root/src/persistent", "rw")
        container.start(wait_for_readiness=False)
        _wait_for_http_inside_container(container, timeout=60)
        _assert_internal(container, network)
        wrapped = container.get_wrapped_container()
        assert wrapped is not None
        remote_interface = wrapped.attrs["NetworkSettings"]["Networks"][network.name]["IPAddress"]
        assert remote_interface
        with podman_machine_utils.open_ssh_tunnel_for_client(
            client=docker_client.client,
            remote_port=container.port,
            remote_interface=remote_interface,
        ) as endpoint:
            container._offline_endpoint = endpoint
            yield container
    finally:
        primary_error = sys.exc_info()[1]
        if container is not None and container.get_wrapped_container() is not None:
            try:
                stdout, stderr = container.get_logs()
                logging.log(
                    logging.WARNING if primary_error is not None else logging.DEBUG,
                    "JupyterLab logs before cleanup:\n%s",
                    (stdout + stderr).decode(errors="replace")[-8000:],
                )
            except Exception:
                logging.exception("Could not collect JupyterLab logs before cleanup")
        cleanup_errors: list[BaseException] = []
        for resource in (container, network):
            try:
                if resource is network:
                    network.remove()
                elif resource is not None:
                    docker_utils.NotebookContainer(resource).stop(timeout=0)
            except Exception as exc:
                cleanup_errors.append(exc)
                logging.exception("Offline cleanup failed; continuing")
        if cleanup_errors and primary_error is None:
            raise ExceptionGroup("offline cleanup failed", cleanup_errors)
        docker_client.client.close()


def _assert_internal(container: OfflineWorkbenchContainer, network: testcontainers.core.network.Network) -> None:
    wrapped = container.get_wrapped_container()
    assert wrapped is not None
    wrapped.reload()
    attrs = wrapped.attrs
    assert set(attrs.get("NetworkSettings", {}).get("Networks", {})) == {network.name}
    assert not attrs.get("NetworkSettings", {}).get("Ports")
    network._unwrap_network.reload()
    assert network._unwrap_network.attrs.get("Internal") is True
    assert container.exec(["id", "-u"])[1].decode().strip() == str(DEFAULT_USER)
    assert "0" in container.exec(["id", "-G"])[1].decode().split()
    code, output = container.exec(["cat", "/proc/net/route"])
    assert code == 0 and not has_ipv4_default_route(output.decode())
    code, output = container.exec(["cat", "/proc/net/ipv6_route"])
    assert code == 0 and not has_ipv6_default_route(output.decode())


def _wait_for_http_inside_container(container: OfflineWorkbenchContainer, *, timeout: float) -> None:
    check = f"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8888{BASE_URL}lab', timeout=2)"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        wrapped = container.get_wrapped_container()
        assert wrapped is not None
        wrapped.reload()
        assert wrapped.status != "exited"
        if container.exec(["python", "-c", check])[0] == 0:
            return
        time.sleep(2)
    raise TimeoutError(f"JupyterLab at {BASE_URL}lab did not become ready")


def _http_url(endpoint: tuple[str, int], path: str) -> str:
    host, port = endpoint
    host_for_url = f"[{host}]" if ":" in host else host
    return f"http://{host_for_url}:{port}{BASE_URL}{path.lstrip('/')}"


def _api(
    endpoint: tuple[str, int], method: str, path: str, payload: object | None = None
) -> tuple[int, dict[str, str], object | None]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage] -- URL is built from the local tunnel endpoint
        _http_url(endpoint, f"api/contents/{path}"),
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # ruff: ignore[suspicious-url-open-usage] -- local test server
        raw = response.read()
        return response.status, dict(response.headers), json.loads(raw) if raw else None


def _check_lab_contents(endpoint: tuple[str, int]) -> None:
    with urllib.request.urlopen(_http_url(endpoint, "lab"), timeout=20) as response:  # ruff: ignore[suspicious-url-open-usage] -- local test server
        page = response.read().decode("utf-8", errors="replace")
        assert response.status == 200
    assert "JupyterLab" in page and "<script" in page and "static/" in page
    asset = re.search(r'<script[^>]+src="([^"]*static/[^\"]+)', page)
    assert asset is not None
    asset_path = asset.group(1)
    if asset_path.startswith("http"):
        asset_url = asset_path
    elif asset_path.startswith("/"):
        host, port = endpoint
        host_for_url = f"[{host}]" if ":" in host else host
        asset_url = f"http://{host_for_url}:{port}{asset_path}"
    else:
        asset_url = _http_url(endpoint, asset_path)
    with urllib.request.urlopen(asset_url, timeout=20) as response:  # ruff: ignore[suspicious-url-open-usage] -- local test server
        assert response.status == 200 and response.read(1)

    notebook = {
        "type": "notebook",
        "format": "json",
        "content": {
            "cells": [
                {
                    "id": "uploaded-cell",
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": ["print('uploaded-cell')"],
                }
            ],
            "metadata": {"offline": True},
            "nbformat": 4,
            "nbformat_minor": 5,
        },
    }
    status, _, created = _api(endpoint, "PUT", "uploaded.ipynb", notebook)
    assert status in (200, 201) and isinstance(created, dict)
    status, _, loaded = _api(endpoint, "GET", "uploaded.ipynb")
    assert status == 200 and isinstance(loaded, dict)
    expected_content = {
        **notebook["content"],
        "cells": [
            {**notebook["content"]["cells"][0], "metadata": {"trusted": True}, "source": "print('uploaded-cell')"}
        ],
    }
    assert loaded["content"] == expected_content
    status, _, renamed = _api(endpoint, "PATCH", "uploaded.ipynb", {"path": "renamed.ipynb"})
    assert status == 200 and renamed["name"] == "renamed.ipynb"
    with pytest.raises(urllib.error.HTTPError) as error:
        _api(endpoint, "GET", "uploaded.ipynb")
    assert error.value.code == 404
    status, _, renamed_content = _api(endpoint, "GET", "renamed.ipynb")
    assert status == 200 and renamed_content["content"] == expected_content
    assert _api(endpoint, "DELETE", "renamed.ipynb")[0] == 204
    with pytest.raises(urllib.error.HTTPError) as error:
        _api(endpoint, "GET", "renamed.ipynb")
    assert error.value.code == 404


def _persistent_notebook() -> dict[str, object]:
    return {
        "type": "notebook",
        "format": "json",
        "content": {
            "cells": [
                {
                    "id": "persistent-cell",
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": ["print('persisted-cell')"],
                }
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        },
    }


def _create_persistent_notebook(endpoint: tuple[str, int]) -> None:
    status, _, result = _api(endpoint, "PUT", "persistent/surviving.ipynb", _persistent_notebook())
    assert status in (200, 201), result


def _assert_persistent_notebook(endpoint: tuple[str, int]) -> None:
    status, _, loaded = _api(endpoint, "GET", "persistent/surviving.ipynb")
    assert status == 200 and isinstance(loaded, dict)
    source = loaded["content"]["cells"][0]["source"]
    assert ("".join(source) if isinstance(source, list) else source) == "print('persisted-cell')"


def _run_probe(
    container: OfflineWorkbenchContainer,
    case: str,
    *,
    kernel_code: str | None = None,
) -> str:
    endpoint = container._offline_endpoint
    with urllib.request.urlopen(_http_url(endpoint, "lab"), timeout=5) as response:  # ruff: ignore[suspicious-url-open-usage] -- local test server
        assert response.status == 200
    host, port = endpoint
    environment = {
        **os.environ,
        "OFFLINE_PROBE_CASE": case,
        "OFFLINE_BASE_URL": BASE_URL,
        "OFFLINE_JUPYTER_HOST": host,
        "OFFLINE_JUPYTER_PORT": str(port),
    }
    if kernel_code is not None:
        environment["OFFLINE_KERNEL_CODE"] = kernel_code
    if case == "git_roundtrip":
        with tempfile.TemporaryDirectory() as workdir:
            environment["OFFLINE_WORKDIR"] = workdir
            result = subprocess.run(
                [sys.executable, str(PROBE_PATH)],
                capture_output=True,
                text=True,
                env=environment,
                timeout=120,
                check=False,
            )
    else:
        result = subprocess.run(
            [sys.executable, str(PROBE_PATH)],
            capture_output=True,
            text=True,
            env=environment,
            timeout=120,
            check=False,
        )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"probe {case!r} failed (exit {result.returncode}):\n{output}"
    return output


def _make_wheel(destination: pathlib.Path) -> pathlib.Path:
    wheel_path = destination / "offline_feature-0.1.0-py3-none-any.whl"
    files = {
        "offline_feature/__init__.py": "VALUE = 'offline-wheel-ok'\n",
        "offline_feature-0.1.0.dist-info/METADATA": ("Metadata-Version: 2.1\nName: offline-feature\nVersion: 0.1.0\n"),
        "offline_feature-0.1.0.dist-info/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: offline-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        "offline_feature-0.1.0.dist-info/RECORD": "",
    }
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for filename, value in files.items():
            wheel.writestr(filename, value)
    return wheel_path


class TestJupyterLabOfflineFeatures:
    def test_lab_page_contents_api_and_prefixed_base_url(self, offline_jupyterlab_image: conftest.Image) -> None:
        with running_offline_workbench(_image_id(offline_jupyterlab_image)) as container:
            _check_lab_contents(container._offline_endpoint)

    def test_server_managed_kernel_executes_and_creates_file(self, offline_jupyterlab_image: conftest.Image) -> None:
        with running_offline_workbench(_image_id(offline_jupyterlab_image)) as container:
            output = _run_probe(
                container,
                "kernel",
                kernel_code=(
                    "from pathlib import Path; Path('kernel-created.txt').write_text('ok'); print('kernel-ok')"
                ),
            )
            assert "kernel-ok" in output
            assert container.exec(["cat", "/opt/app-root/src/kernel-created.txt"])[1].decode().strip() == "ok"

    def test_package_installation_is_offline_and_visible_to_kernel(
        self, offline_jupyterlab_image: conftest.Image
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wheel = _make_wheel(pathlib.Path(tmpdir))
            with running_offline_workbench(_image_id(offline_jupyterlab_image)) as container:
                docker_utils.container_cp(container, wheel, "/opt/app-root/src")
                command = [
                    "python",
                    "-c",
                    (
                        "import subprocess,sys; "
                        "subprocess.run([sys.executable,'-m','pip','install',"
                        "'--no-index',sys.argv[1]],check=True,timeout=60)"
                    ),
                    f"/opt/app-root/src/{wheel.name}",
                ]
                code, output = container.exec(command)
                assert code == 0, output.decode(errors="replace")
                code, output = container.exec(
                    [
                        "python",
                        "-c",
                        (
                            "import subprocess,sys; "
                            "subprocess.run([sys.executable,'-m','pip','list',"
                            "'--format=json'],check=True,timeout=30)"
                        ),
                    ]
                )
                assert code == 0 and b"offline-feature" in output
                assert "offline-wheel-ok" in _run_probe(
                    container,
                    "kernel",
                    kernel_code="import offline_feature; print(offline_feature.VALUE)",
                )

    def test_local_git_clone_commit_push_pull_roundtrip(self, offline_jupyterlab_image: conftest.Image) -> None:
        with running_offline_workbench(_image_id(offline_jupyterlab_image)) as container:
            assert "git roundtrip ready" in _run_probe(container, "git_roundtrip")

    def test_environment_secret_recreated_and_persistent_volume_survives(
        self, offline_jupyterlab_image: conftest.Image
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            volume = pathlib.Path(tmpdir)
            with running_offline_workbench(
                _image_id(offline_jupyterlab_image),
                env={"OFFLINE_ENV": "first", "OFFLINE_SECRET": "fake-secret"},
                volume=volume,
            ) as container:
                _create_persistent_notebook(container._offline_endpoint)
                output = _run_probe(
                    container,
                    "kernel",
                    kernel_code=("import os; print(os.environ['OFFLINE_ENV']); print(os.environ['OFFLINE_SECRET'])"),
                )
                assert "first" in output and "fake-secret" in output
                assert container.exec(["sh", "-c", "echo ephemeral > /opt/app-root/src/ephemeral.txt"])[0] == 0
            with running_offline_workbench(
                _image_id(offline_jupyterlab_image),
                env={"OFFLINE_ENV": "second", "OFFLINE_SECRET": "changed-secret"},
                volume=volume,
            ) as container:
                _assert_persistent_notebook(container._offline_endpoint)
                output = _run_probe(
                    container,
                    "kernel",
                    kernel_code=(
                        "import json; from pathlib import Path; "
                        "nb=json.loads(Path("
                        "'persistent/surviving.ipynb').read_text()); "
                        "exec(''.join(nb['cells'][0]['source']))"
                    ),
                )
                assert "persisted-cell" in output
                output = _run_probe(
                    container,
                    "kernel",
                    kernel_code=("import os; print(os.environ['OFFLINE_ENV']); print(os.environ['OFFLINE_SECRET'])"),
                )
                assert "second" in output and "changed-secret" in output
                assert container.exec(["test", "!", "-e", "/opt/app-root/src/ephemeral.txt"])[0] == 0
