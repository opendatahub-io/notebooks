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
