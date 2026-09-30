from __future__ import annotations

import json
import logging
import os.path
import platform
import socket
import subprocess
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

import tests.containers.pydantic_schemas
from tests.containers import docker_utils

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import docker.client


def open_ssh_tunnel(
    machine_predicate: Callable[[tests.containers.pydantic_schemas.PodmanMachine], bool],
    local_port: int,
    remote_port: int,
    remote_interface: str = "localhost",
) -> subprocess.Popen:
    # Load and parse the Podman machine data
    machine_names = subprocess.check_output(["podman", "machine", "list", "--quiet"], text=True).splitlines()
    json_data = subprocess.check_output(["podman", "machine", "inspect", *machine_names], text=True)
    inspect = tests.containers.pydantic_schemas.PodmanMachineInspect(machines=json.loads(json_data))
    machines = inspect.machines

    machine = next((m for m in machines if machine_predicate(m)), None)
    if not machine:
        raise ValueError(f"Machine matching given predicate not found: the available machines are: {machines}")

    ssh_command = [
        "ssh",
        "-i",
        machine.SSHConfig.IdentityPath,
        "-p",
        str(machine.SSHConfig.Port),
        "-L",
        f"{local_port}:{remote_interface}:{remote_port}",
        "-N",  # Do not execute a remote command
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "LogLevel=ERROR",
        f"{machine.SSHConfig.RemoteUsername}@localhost",
    ]

    # Open the SSH tunnel
    process = subprocess.Popen(ssh_command)

    logging.info(f"SSH tunnel opened for {machine.Name}: {remote_interface}:{local_port} -> localhost:{remote_port}")
    return process


@contextmanager
def open_ssh_tunnel_for_client(
    client: docker.client.DockerClient,
    remote_port: int,
    remote_interface: str = "localhost",
) -> Iterator[tuple[str, int]]:
    """Open a local tunnel to a destination reachable from the Podman Machine.

    Open and own an SSH local-forward through the matching Podman Machine. The
    context manager waits for the endpoint and always closes the tunnel when
    leaving the context.
    """
    system = platform.system().lower()
    if system not in {"linux", "darwin"}:
        raise RuntimeError(f"Podman SSH tunneling is supported on Linux and macOS, not {platform.system()}")

    local_port = find_free_port()
    socket_path = os.path.realpath(docker_utils.get_socket_path(client))
    logging.debug("socket_path=%s", socket_path)
    process = open_ssh_tunnel(
        machine_predicate=lambda machine: os.path.realpath(machine.ConnectionInfo.PodmanSocket.Path) == socket_path,
        local_port=local_port,
        remote_port=remote_port,
        remote_interface=remote_interface,
    )
    try:
        _wait_for_local_port(local_port, process)
        yield "127.0.0.1", local_port
    finally:
        _close_process(process)


def _wait_for_local_port(port: int, process: subprocess.Popen, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"SSH tunnel exited before opening local port {port}: {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"SSH tunnel did not open local port {port} within {timeout}s")


def _close_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def find_free_port() -> int:
    """Find a free port on the local machine.
    :return: A port number that is currently free and available for use.
    """
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
        s.bind(("", 0))  # Bind to a free port provided by the system
        s.listen(1)
        port = s.getsockname()[1]
    return port


# Usage example
if __name__ == "__main__":
    tunnel_process = open_ssh_tunnel(
        machine_predicate=lambda m: m.Name == "podman-machine-default",
        local_port=8080,
        remote_port=8080,
        remote_interface="[fc00::2]",
    )

    # Keep the tunnel open until user interrupts
    try:
        tunnel_process.wait()
    except KeyboardInterrupt:
        tunnel_process.terminate()
        print("SSH tunnel closed")
