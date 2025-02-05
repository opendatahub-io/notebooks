import json

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ConfigDir(BaseModel):
    Path: str


class PodmanSocket(BaseModel):
    Path: str


class ConnectionInfo(BaseModel):
    PodmanSocket: PodmanSocket
    PodmanPipe: Optional[str] = None


class Resources(BaseModel):
    CPUs: int
    DiskSize: int
    Memory: int
    USBs: list[str] = []


class SSHConfig(BaseModel):
    IdentityPath: str
    Port: int
    RemoteUsername: str


class PodmanMachine(BaseModel):
    ConfigDir: ConfigDir
    ConnectionInfo: ConnectionInfo
    Created: datetime
    LastUp: datetime
    Name: str
    Resources: Resources
    SSHConfig: SSHConfig
    State: str
    UserModeNetworking: bool
    Rootful: bool
    Rosetta: bool


# generated from `podman machine inspect` output by smart tooling
class PodmanMachineInspect(BaseModel):
    machines: list[PodmanMachine]


def test_podman_machine_inspect():
    # given
    podman_machine_inspect = PodmanMachineInspect(machines=json.loads("""\
[
     {
          "ConfigDir": {
               "Path": "/Users/jdanek/.config/containers/podman/machine/applehv"
          },
          "ConnectionInfo": {
               "PodmanSocket": {
                    "Path": "/var/folders/f1/3m518k5d34l72v_9nqyjzqm80000gn/T/podman/podman-machine-default-api.sock"
               },
               "PodmanPipe": null
          },
          "Created": "2025-01-28T12:36:07.415697+01:00",
          "LastUp": "2025-01-29T09:37:49.361334+01:00",
          "Name": "podman-machine-default",
          "Resources": {
               "CPUs": 6,
               "DiskSize": 100,
               "Memory": 2048,
               "USBs": []
          },
          "SSHConfig": {
               "IdentityPath": "/Users/jdanek/.local/share/containers/podman/machine/machine",
               "Port": 53903,
               "RemoteUsername": "core"
          },
          "State": "running",
          "UserModeNetworking": true,
          "Rootful": true,
          "Rosetta": true
     }
]
"""))

    assert podman_machine_inspect.machines[0].Name == "podman-machine-default"
