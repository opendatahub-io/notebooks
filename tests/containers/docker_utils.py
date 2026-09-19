from __future__ import annotations

import contextlib
import io
import socket as pysocket
import sys
import tarfile
import time
from typing import TYPE_CHECKING

import podman

import tests.containers.pydantic_schemas
from tests.containers import container_transport, sidecar_transport
from tests.containers.container_transport import BestEffortCleanup  # re-export (historical import path)

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable
    from os import PathLike

    import docker.client
    import testcontainers.core.container
    from docker.models.containers import Container


class NotebookContainer:
    @classmethod
    def wrap(cls, container: testcontainers.core.container.DockerContainer):
        return NotebookContainer(container)

    def __init__(self, container: testcontainers.core.container.DockerContainer) -> None:
        self.testcontainer = container

    def stop(self, timeout: int = 10):
        """Stop container with customizable timeout.

        DockerContainer.stop() has unchangeable 10s timeout between SIGSTOP and SIGKILL."""
        wrapped = self.testcontainer.get_wrapped_container()
        if wrapped is not None:
            wrapped.stop(timeout=timeout)
        self.testcontainer.stop()

    def wait_for_exit(self) -> int:
        container = self.testcontainer.get_wrapped_container()
        container.reload()
        while container.status != "exited":
            time.sleep(0.2)
            container.reload()
        return container.attrs["State"]["ExitCode"]


@contextlib.contextmanager
def running_container(
    image: str,
    *,
    user: int = 23456,
    group_add: list[int] | None = None,
    env: dict[str, str] | None = None,
    **kwargs,
) -> Generator[container_transport.SleepContainer]:
    """Start a container with 'sleep infinity' and stop it on exit.

    GID 0 is always added (OpenShift runs with root supplemental group for /opt/app-root access).

    Transport selection (the single place): SUT_AGENT_URL set (the Konflux
    in-pod test stage) yields a :class:`SidecarSleepContainer` — the sidecar
    agent process IS the "sleep infinity" and execs run as the requested user;
    otherwise the docker/podman transport.
    """
    if sidecar_transport.sidecar_mode():
        yield container_transport.SidecarSleepContainer(image=image, user=user, env=env)
        return
    groups = sorted({0, *(group_add or [])})
    container = container_transport.TestcontainersSleepContainer(image=image, user=user, group_add=groups, **kwargs)
    if env:
        for key, value in env.items():
            container.with_env(key, value)
    container.with_command("/bin/sh -c 'sleep infinity'")
    try:
        container.start()
        yield container
    finally:
        with BestEffortCleanup():
            NotebookContainer(container).stop(timeout=0)


def container_cp(
    container: Container
    | testcontainers.core.container.DockerContainer
    | container_transport.Container
    | container_transport.SleepContainer,
    src: str | PathLike,
    dst: str,
    user: int | None = None,
    group: int | None = None,
) -> None:
    """Copy a file or directory into a container of any transport.

    Delegates to ``container_transport.container_cp`` (dispatch on the
    transport ABCs; legacy docker-py/testcontainers handles still work).
    """
    container_transport.container_cp(container, src, dst, user=user, group=group)


def from_container_cp(container: Container, src: str, dst: str) -> None:
    fh = io.BytesIO()
    bits, _stat = container.get_archive(src, encode_stream=True)
    for chunk in bits:
        fh.write(chunk)
    fh.seek(0)
    tar = tarfile.open(fileobj=fh, mode="r")
    try:
        tar.extractall(path=dst, filter=tarfile.data_filter)  # ruff: ignore[tarfile-unsafe-members] - data_filter rejects unsafe paths/symlinks (Python 3.12+ mitigation)
    finally:
        tar.close()
        fh.close()


def container_exec(
    container: Container,
    cmd: str | list[str],
    stdout: bool = True,
    stderr: bool = True,
    stdin: bool = False,
    tty: bool = False,
    privileged: bool = False,
    user: str = "",
    detach: bool = False,
    stream: bool = False,
    socket: bool = False,
    environment: dict[str, str] | None = None,
    workdir: str | None = None,
) -> ContainerExec:
    """
    An enhanced version of #docker.Container.exec_run() which returns an object
    that can be properly inspected for the status of the executed commands.
    Usage example:
    result = tools.container_exec(container, cmd, stream=True, **kwargs)
    res = result.communicate(line_prefix=b'--> ')
    if res != 0:
        error('exit code {!r}'.format(res))
    From https://github.com/docker/docker-py/issues/1989
    """

    exec_id = container.client.api.exec_create(
        container.id,
        cmd,
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        tty=tty,
        privileged=privileged,
        user=user,
        environment=environment,
        workdir=workdir,
    )["Id"]

    output = container.client.api.exec_start(exec_id, detach=detach, tty=tty, stream=stream, socket=socket)

    return ContainerExec(container.client, exec_id, output)


class ContainerExec:
    def __init__(self, client, id, output):
        self.client = client
        self.id = id
        self.output = output

    def inspect(self):
        return self.client.api.exec_inspect(self.id)

    def poll(self) -> int:
        return self.inspect()["ExitCode"]

    def communicate(self, line_prefix=b"") -> int:
        for data in self.output:
            if not data:
                continue
            offset = 0
            while offset < len(data):
                sys.stdout.buffer.write(line_prefix)
                nl = data.find(b"\n", offset)
                if nl >= 0:
                    slice = data[offset : nl + 1]
                    offset = nl + 1
                else:
                    slice = data[offset:]
                    offset += len(slice)
                sys.stdout.buffer.write(slice)
            sys.stdout.flush()
        while self.poll() is None:
            raise RuntimeError("Hm could that really happen?")
        return self.poll()


def container_exec_with_stdin(
    container: Container,
    cmd: str | list[str],
    stdin_data: str | bytes,
    read_timeout: float = 1.0,
) -> tuple[int, bytes]:
    """
    Executes a command in a container, writing stdin_data to its stdin.

    :param container: The container to execute the command in.
    :param cmd: The command to execute.
    :param stdin_data: The string or bytes to send to the command's stdin.
    :return: A tuple of (exit_code, output_bytes).
    """
    if isinstance(stdin_data, str):
        stdin_data = stdin_data.encode("utf-8")

    # Using the low-level API for precise control over the socket.
    exec_id = container.client.api.exec_create(
        container=container.id,
        cmd=cmd,
        stdin=True,
        stdout=True,
        stderr=True,
        tty=True,
    )["Id"]

    # When using a podman client, exec_start(socket=True) returns a file-like
    # object (a wrapper around SocketIO), not a raw socket. We must use
    # file-like methods (write, read) instead of raw socket methods.
    stream = container.client.api.exec_start(exec_id, socket=True, tty=True)

    # The stream object can be a raw socket or a file-like wrapper which might
    # be incorrectly marked as read-only. We need to find the underlying raw
    # socket to reliably write to stdin.
    raw_sock = None
    if isinstance(stream, pysocket.socket):
        raw_sock = stream
    else:
        # Try to unwrap a file-like object (e.g., BufferedReader -> SocketIO -> socket)
        raw_io = getattr(stream, "raw", stream)
        if hasattr(raw_io, "_sock"):
            raw_sock = raw_io._sock

    if raw_sock:
        raw_sock.sendall(stdin_data)
    else:
        # Fallback to stream.write() if no raw socket found. This may fail.
        try:
            stream.write(stdin_data)
            stream.flush()
        except (OSError, io.UnsupportedOperation) as e:
            raise OSError(f"Could not write to container exec stdin using stream of type {type(stream)}") from e

    # Shut down the write-half of the connection to signal EOF to the process.
    try:
        if raw_sock:
            raw_sock.shutdown(pysocket.SHUT_WR)
        else:
            # Fallback for stream objects that have a shutdown method.
            raw_io = getattr(stream, "raw", stream)
            if hasattr(raw_io, "_sock"):
                raw_io._sock.shutdown(pysocket.SHUT_WR)
            else:
                stream.shutdown(pysocket.SHUT_WR)
    except OSError, AttributeError:
        # This is expected if the remote process closes the connection first.
        pass

    if raw_sock:
        # If we unwrapped and used the raw socket, we must continue using it
        # for reading to avoid state inconsistencies with the wrapper object.
        output_chunks = []
        while True:
            # we set the timeout in order not to be blocked afterwards with blocking read
            raw_sock.settimeout(read_timeout)
            # Reading in a loop is the standard way to consume a socket's content.
            try:
                chunk = raw_sock.recv(4096)
            except TimeoutError:
                break
            if not chunk:
                # An empty chunk signifies that the remote end has closed the connection.
                break
            output_chunks.append(chunk)
        output = b"".join(output_chunks)
        raw_sock.close()
    else:
        # Fallback to stream.read() if we couldn't get a raw socket.
        # This may hang if the shutdown logic above also failed.
        output = stream.read()
        stream.close()

    # Get the exit code of the process.
    exit_code = container.client.api.exec_inspect(exec_id)["ExitCode"]

    return exit_code, output


def get_socket_path(client: docker.client.DockerClient) -> str:
    """Determine the local socket path.
    This works even when `podman machine` with its own host-mounts is involved
    NOTE: this will not work for remote docker, but we will cross the bridge when we come to it"""
    socket_path = _the_one(adapter.socket_path for adapter in client.api.adapters.values())
    return socket_path


def get_podman_machine_socket_path(docker_client: docker.client.DockerClient) -> str:
    """Determine the podman socket path that's valid from inside Podman Machine.
    * rootful podman: both the host (`ls`) and podman machine (`podman machine ssh ls`) have it at `/var/run/docker.sock`.
    * rootless podman: the location on host is still the same while podman machine has it in `/var/run/user/${PID}/podman/podman.sock`.
    """
    socket_path = get_socket_path(docker_client)
    podman_client = podman.PodmanClient(base_url="http+unix://" + socket_path)
    info = tests.containers.pydantic_schemas.PodmanInfo.model_validate(podman_client.info())
    assert info.host.remoteSocket.exists, "Failed to determine the podman remote socket"
    assert info.host.remoteSocket.path.startswith("unix://"), "Unexpected remote socket path"
    machine_socket_path = info.host.remoteSocket.path[len("unix://") :]
    return machine_socket_path


def get_container_pid(container: Container) -> int | None:
    """Get the network namespace of a Docker container."""
    container.reload()
    container_pid = container.attrs["State"]["Pid"]
    return container_pid


# https://docs.python.org/3/library/functions.html#iter
def _the_one[T](iterable: Iterable[T]) -> T:
    """Checks that there is exactly one element in the iterable, and returns it."""
    it = iter(iterable)
    try:
        v = next(it)
    except StopIteration:
        raise ValueError("No elements in iterable") from None
    try:
        next(it)
    except StopIteration:
        return v
    raise ValueError("More than one element in iterable")
