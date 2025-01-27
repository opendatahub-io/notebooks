import json
import logging
import socket
import subprocess
from tests.containers.schemas import PodmanMachineInspect

logging.basicConfig(level=logging.DEBUG)

def open_ssh_tunnel(machine_name: str, local_port: int, remote_port: int, remote_interface: str = "localhost") -> subprocess.Popen:
    # Load and parse the Podman machine data
    json_data = subprocess.check_output(["podman", "machine", "inspect", machine_name], text=True)
    inspect = PodmanMachineInspect(machines=json.loads(json_data))
    machines = inspect.machines

    machine = next((m for m in machines if m.Name == machine_name), None)
    if not machine:
        raise ValueError(f"Machine '{machine_name}' not found")

    ssh_command = [
        "ssh",
        "-i", machine.SSHConfig.IdentityPath,
        "-p", str(machine.SSHConfig.Port),
        "-L", f"{local_port}:{remote_interface}:{remote_port}",
        "-N",  # Do not execute a remote command
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "StrictHostKeyChecking=no",
        f"{machine.SSHConfig.RemoteUsername}@localhost"
    ]

    # Open the SSH tunnel
    process = subprocess.Popen(ssh_command)

    logging.info(f"SSH tunnel opened for {machine_name}: {remote_interface}:{local_port} -> localhost:{remote_port}")
    return process

def find_free_port() -> int:
    """Find a free port on the local machine.
    :return: A port number that is currently free and available for use.
    """
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
        s.bind(('', 0))  # Bind to a free port provided by the system
        s.listen(1)
        port = s.getsockname()[1]
    return port

# Usage example
if __name__ == "__main__":
    tunnel_process = open_ssh_tunnel(
        "podman-machine-default",
        8080, 8080,
        remote_interface="[fc00::2]"
    )

    # Keep the tunnel open until user interrupts
    try:
        tunnel_process.wait()
    except KeyboardInterrupt:
        tunnel_process.terminate()
        print("SSH tunnel closed")
