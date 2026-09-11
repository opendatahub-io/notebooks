"""Container transport abstraction for the tests/containers suite.

The suite drives the image under test through a small "container" surface
(start the entrypoint, exec commands, copy files in, stop). This module
defines that surface as an ABC with two implementations, and one factory
that selects between them — tests depend on the interface only:

- :class:`TestcontainersContainer` — the docker/podman API via testcontainers.
  The GHA and local-development default.
- :class:`SidecarContainer` — the localhost HTTP control plane of the sidecar
  exec agent (see ``sidecar_agent.py`` / ``sidecar_transport.py``). The image
  runs as a pod sidecar of the test pod; this is the only in-pod transport
  for the Konflux test stage (no container runtime is allowed in the tenant,
  and the pipeline SA has no pod RBAC — see ADR-0018).

Selection happens exactly once, in :func:`workbench_container`
(``SUT_AGENT_URL`` set => sidecar, else testcontainers).

The module also hosts the transport-neutral plumbing both implementations
share: :func:`container_cp` (dispatch on the ABC), :func:`put_archive`
(docker-py's copy primitive, the docker transports' ``cp``), and
:class:`BestEffortCleanup` (teardown that swallows cleanup errors).
"""

from __future__ import annotations

import abc
import io
import logging
import os.path
import pathlib
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Self

import testcontainers.core.container
import testcontainers.core.waiting_utils

from tests.containers import sidecar_transport

if TYPE_CHECKING:
    from os import PathLike
    from types import TracebackType

    from docker.models.containers import Container as DockerPyContainer


class Container(abc.ABC):
    """The container surface the workbench tests drive.

    ``port`` is the container port the suite tests (8888 for workbenches).
    ``get_wrapped_container()`` returns the low-level (docker-py-shaped)
    handle; the sidecar implementation returns a stand-in exposing the
    attributes the tests touch (``reload``, ``status``, ``id``, ``stop``).
    """

    port: int

    @abc.abstractmethod
    def start(self, wait_for_readiness: bool = True) -> Self:
        """Start the container (sidecar: launch the entrypoint) and, optionally,
        wait until the HTTP endpoint answers."""

    @abc.abstractmethod
    def _connect(
        self,
        container_host: str | None = None,
        container_port: int | None = None,
        base_url: str = "",
    ) -> None:
        """One readiness probe against the container's HTTP endpoint.

        Implementations raise ``urllib.error.URLError`` while the endpoint is
        not ready, so callers can wrap them in ``wait_container_is_ready``.
        """

    @abc.abstractmethod
    def exec(self, cmd: list[str] | str) -> tuple[int, bytes]:
        """docker exec equivalent: (exit_code, combined output)."""

    @abc.abstractmethod
    def get_exposed_port(self, port: int) -> int:
        """The host port that maps to the container port."""

    @abc.abstractmethod
    def get_container_host_ip(self) -> str:
        """The IP to reach the container's published ports on."""

    @abc.abstractmethod
    def get_wrapped_container(self) -> Any:
        """The low-level (docker-py-shaped) container handle."""

    @abc.abstractmethod
    def stop(self, timeout: int = 10) -> None:
        """Suite-level teardown (sidecar: kill the server child)."""

    @abc.abstractmethod
    def cp(self, src: str | PathLike, dst: str, user: int | None = None, group: int | None = None) -> None:
        """Copy a file or directory into the container (put_archive equivalent)."""

    @abc.abstractmethod
    def with_env(self, key: str, value: str) -> Self:
        """Set an environment variable for the next start (testcontainers builder)."""

    @abc.abstractmethod
    def with_command(self, command: str | list[str]) -> Self:
        """Override the entrypoint command for the next start (testcontainers builder)."""

    @abc.abstractmethod
    def get_logs(self, **kwargs: Any) -> tuple[bytes, bytes]:
        """docker-py-shaped logs: (stdout, stderr) bytes of the server process."""

    def exec_script(
        self,
        script_content: str,
        script_name: str = "test_script.py",
        dest: str = "/opt/app-root/src",
        python: str = "python",
    ) -> tuple[int, str]:
        """Copy a Python script into the container and execute it.

        Note: script_name and dest are not sanitized against path traversal (CWE-22)
        because all callers are hardcoded test code in this repo, not user input.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = pathlib.Path(tmpdir) / script_name
            script_path.write_text(script_content)
            self.cp(script_path, dst=dest)
        exit_code, output = self.exec([python, f"{dest}/{script_name}"])
        assert exit_code is not None, f"exec() returned no exit code for script {script_name}"
        return exit_code, output.decode()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        with BestEffortCleanup(exc_type):
            self.stop(timeout=0)


class TestcontainersContainer(testcontainers.core.container.DockerContainer, Container):
    """The docker/podman transport (testcontainers): GHA and local development."""

    def __init__(
        self,
        port: int = 8888,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        self.port = port
        self.with_exposed_ports(self.port)

    @testcontainers.core.waiting_utils.wait_container_is_ready(urllib.error.URLError)
    def _connect(
        self,
        container_host: str | None = None,
        container_port: int | None = None,
        base_url: str = "",
    ) -> None:
        # are we still alive?
        self.get_wrapped_container().reload()
        assert self.get_wrapped_container().status != "exited"

        # connect
        host = container_host or self.get_container_host_ip()
        # Podman publishes IPv4 ports; connecting to "localhost" may resolve to ::1 first.
        if host == "localhost":
            host = "127.0.0.1"
        port = container_port or self.get_exposed_port(self.port)
        try:
            # host may be an ipv6 address, need to be careful with formatting this
            host_for_url = f"[{host}]" if ":" in host else host
            # /api redirects to /codeserver/healthz/ and avoids the / -> /codeserver/ hop
            # (absolute redirects on / previously broke Podman port-forward readiness checks).
            probe_path = base_url or "/api"
            result = urllib.request.urlopen(
                urllib.request.Request(f"http://{host_for_url}:{port}{probe_path}"), timeout=1
            )
        except urllib.error.URLError as e:
            raise e

        # get /
        try:
            if result.status != 200:
                raise ConnectionError(f"Failed to connect to container, {result.status=}")
        finally:
            result.close()

    def start(self, wait_for_readiness: bool = True) -> Self:
        super().start()
        container_id = self.get_wrapped_container().id
        assert container_id is not None
        docker_client = testcontainers.core.docker_client.DockerClient().client
        logging.debug(docker_client.api.inspect_container(container_id)["HostConfig"])
        if wait_for_readiness:
            self._connect()
        return self

    def stop(self, timeout: int = 10) -> None:
        # suite-level teardown: force remove (the grace-period stop already
        # happened on the wrapped docker-py container via NotebookContainer)
        super().stop()

    def cp(self, src: str | PathLike, dst: str, user: int | None = None, group: int | None = None) -> None:
        put_archive(self.get_wrapped_container(), src, dst, user, group)


class _SidecarWrappedContainer:
    """docker-py-shaped stand-in for the sidecar's ``get_wrapped_container()``.

    The pod sidecar never "exits" (the agent is its main process), so the
    status checks the tests perform (``status != "exited"``) are no-ops; the
    server child's state is exposed via ``sidecar_transport.server_status()``.
    """

    def __init__(self) -> None:
        self.status = "running"
        self.id = "sidecar"
        self.attrs: dict = {}

    def reload(self) -> None:
        pass

    def stop(self, timeout: int = 10) -> None:
        pass


class SidecarContainer(Container):
    """The in-pod transport: the image-under-test runs as a pod sidecar whose
    main process is the exec agent; this drives it over localhost HTTP.

    docker-only kwargs are accepted and deliberately ignored in-pod (sysctls,
    network isolation, network_mode) — the test variants that need them are
    deselected in conftest in sidecar mode (see ADR-0018). ``with_env`` and
    ``with_command`` are supported (the agent applies them at start).
    """

    def __init__(
        self,
        port: int = 8888,
        **kwargs,
    ) -> None:
        self.port = port
        self.image = kwargs.get("image")
        self.user = kwargs.get("user")
        group_add: list[int] = kwargs.get("group_add") or []
        self.groups = sorted({0, *group_add})
        self.env = dict(kwargs.get("environment") or {})
        self._command: str | list[str] | None = None

    def start(self, wait_for_readiness: bool = True) -> Self:
        sidecar_transport.start_server(user=self.user, groups=self.groups, env=self.env, command=self._command)
        if wait_for_readiness:
            self._connect()
        return self

    def with_env(self, key: str, value: str) -> Self:
        self.env[key] = value
        return self

    def with_command(self, command: str | list[str]) -> Self:
        self._command = command
        return self

    def get_logs(self, **kwargs: Any) -> tuple[bytes, bytes]:
        # the agent tees the server's stdout and stderr into one file
        return sidecar_transport.server_logs().encode(), b""

    @testcontainers.core.waiting_utils.wait_container_is_ready(urllib.error.URLError)
    def _connect(
        self,
        container_host: str | None = None,
        container_port: int | None = None,
        base_url: str = "",
    ) -> None:
        # the server child listens on the container port in the shared netns
        host, port = "127.0.0.1", container_port or self.port
        # /api redirects to /codeserver/healthz/ and avoids the / -> /codeserver/ hop
        probe_path = base_url or "/api"
        result = urllib.request.urlopen(urllib.request.Request(f"http://{host}:{port}{probe_path}"), timeout=1)
        try:
            if result.status != 200:
                raise ConnectionError(f"Failed to connect to container, {result.status=}")
        finally:
            result.close()

    def exec(self, cmd: list[str] | str) -> tuple[int, bytes]:
        # docker exec default user = the container's user; the agent's default
        # is the image USER, so pass the container user explicitly
        return sidecar_transport.exec_cmd([str(c) for c in cmd], user=self.user)

    def get_exposed_port(self, port: int) -> int:
        return port  # shared netns: container port == host port on localhost

    def get_container_host_ip(self) -> str:
        return "127.0.0.1"

    def get_wrapped_container(self) -> _SidecarWrappedContainer:
        return _SidecarWrappedContainer()

    def stop(self, timeout: int = 10) -> None:
        sidecar_transport.stop_server(timeout=timeout)

    def cp(self, src: str | PathLike, dst: str, user: int | None = None, group: int | None = None) -> None:
        sidecar_transport.upload_file(src, dst, user=user, group=group)


# ---------------------------------------------------------------------------
# Sleep containers (docker_utils.running_container): 'sleep infinity' + execs
# ---------------------------------------------------------------------------


class SleepContainer(abc.ABC):
    """A container running ``sleep infinity``: the surface the
    ``running_container`` consumers use (exec/cp/stop, no server lifecycle).
    """

    @abc.abstractmethod
    def exec(self, cmd: list[str] | str) -> tuple[int, bytes]: ...

    @abc.abstractmethod
    def cp(self, src: str | PathLike, dst: str, user: int | None = None, group: int | None = None) -> None: ...

    @abc.abstractmethod
    def stop(self, timeout: int = 10) -> None: ...


class TestcontainersSleepContainer(testcontainers.core.container.DockerContainer, SleepContainer):
    """The docker/podman sleep container (the historical running_container)."""

    def stop(self, timeout: int = 10) -> None:
        super().stop()

    def cp(self, src: str | PathLike, dst: str, user: int | None = None, group: int | None = None) -> None:
        put_archive(self.get_wrapped_container(), src, dst, user, group)


class SidecarSleepContainer(SleepContainer):
    """The in-pod sleep container: the sidecar agent process IS the
    "sleep infinity" (it is the sidecar's main process); execs run as the
    requested user through the agent.
    """

    def __init__(self, image: str, user: int, env: dict[str, str] | None = None) -> None:
        self.image = image
        self.user = user
        self.env = env or {}

    def exec(self, cmd: list[str] | str) -> tuple[int, bytes]:
        return sidecar_transport.exec_cmd([str(c) for c in cmd], user=self.user)

    def cp(self, src: str | PathLike, dst: str, user: int | None = None, group: int | None = None) -> None:
        sidecar_transport.upload_file(src, dst, user=user, group=group)

    def stop(self, timeout: int = 10) -> None:
        # session-shared sidecar: do not kill the agent
        pass


# ---------------------------------------------------------------------------
# Transport-neutral plumbing shared by both implementations
# ---------------------------------------------------------------------------


def put_archive(
    container: DockerPyContainer,
    src: str | PathLike,
    dst: str,
    user: int | None = None,
    group: int | None = None,
) -> None:
    """Low-level docker-py put_archive copy (the docker transports' ``cp``).

    From https://stackoverflow.com/questions/46390309/how-to-copy-a-file-from-host-to-container-using-docker-py-docker-sdk
    """
    fh = io.BytesIO()
    tar = tarfile.open(fileobj=fh, mode="w:gz")

    def tar_filter(f: tarfile.TarInfo) -> tarfile.TarInfo:
        if user is not None:
            f.uid = user
        if group is not None:
            f.gid = group
        return f

    logging.debug(f"Adding {src=} to archive {dst=}")
    try:
        tar.add(
            src,
            arcname=os.path.basename(src),
            filter=tar_filter if (user is not None or group is not None) else None,
        )
    finally:
        tar.close()

    fh.seek(0)
    container.put_archive(dst, fh)


class BestEffortCleanup:
    """Context manager that suppresses cleanup errors only when another exception is in-flight.

    If cleanup raises and no other exception is active, the error propagates normally.
    If cleanup raises while handling another exception, the error is logged and suppressed
    so the original exception is not masked.

    Design choices:

    - Class-based, not @contextmanager: a generator-based CM's try/yield/except
      catches body and cleanup exceptions indistinguishably.

    - Auto-detection uses sys.exc_info() in __enter__, not __exit__: inside
      __exit__, sys.exc_info() already reflects the cleanup error being handled,
      not the original. Capturing in __enter__ gets the correct answer.

    Usage in __exit__ (pass exc_type so auto-detect is skipped):
        with BestEffortCleanup(exc_type):
            container.stop()

    Usage in @contextmanager finally (auto-detects via sys.exc_info):
        with BestEffortCleanup():
            container.stop()
    """

    def __init__(self, exc_type: type[BaseException] | None = None) -> None:
        self._has_active_exception = exc_type is not None

    def __enter__(self) -> None:
        if not self._has_active_exception:
            self._has_active_exception = sys.exc_info()[0] is not None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        if exc_type is None:
            return False
        if not self._has_active_exception:
            return False
        logging.exception("Cleanup failed (suppressed because another exception is active)")
        return True


def container_cp(
    container: Container | SleepContainer | testcontainers.core.container.DockerContainer | DockerPyContainer,
    src: str | PathLike,
    dst: str,
    user: int | None = None,
    group: int | None = None,
) -> None:
    """Copy a file or directory into a container of any transport.

    Accepts a suite transport object (the ``cp`` on the ABC decides how —
    docker put_archive or the sidecar agent's /files endpoint) or the legacy
    docker-py ``Container`` / testcontainers ``DockerContainer`` (the latter
    is unwrapped — ``DockerContainer`` has no ``put_archive``).
    """
    if isinstance(container, (Container, SleepContainer)):
        container.cp(src, dst, user=user, group=group)
        return
    if isinstance(container, testcontainers.core.container.DockerContainer):
        container = container.get_wrapped_container()
    put_archive(container, src, dst, user, group)


# ---------------------------------------------------------------------------
# Factory — the single place transport is selected
# ---------------------------------------------------------------------------


def workbench_container(port: int = 8888, **kwargs) -> Container:
    """Return the workbench container implementation for this environment.

    ``SUT_AGENT_URL`` set (the Konflux in-pod test stage) => sidecar;
    otherwise the docker/podman transport.
    """
    if sidecar_transport.sidecar_mode():
        return SidecarContainer(port=port, **kwargs)
    return TestcontainersContainer(port=port, **kwargs)
