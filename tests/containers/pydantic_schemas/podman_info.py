from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class Conmon(BaseModel):
    package: str
    path: str
    version: str


class CpuUtilization(BaseModel):
    idlePercent: float
    systemPercent: float
    userPercent: float


class Distribution(BaseModel):
    distribution: str
    variant: str
    version: str


class IdMapping(BaseModel):
    container_id: int
    host_id: int
    size: int


class IdMappings(BaseModel):
    gidmap: List[IdMapping] | None = None
    uidmap: List[IdMapping] | None = None


class NetworkBackendInfo(BaseModel):
    backend: str
    dns: Dict[str, str]
    package: str
    path: str
    version: str


class OciRuntime(BaseModel):
    name: str
    package: str
    path: str
    version: str


class Pasta(BaseModel):
    executable: str
    package: str
    version: str


class RemoteSocket(BaseModel):
    exists: bool
    path: str


class Security(BaseModel):
    apparmorEnabled: bool
    capabilities: str
    rootless: bool
    seccompEnabled: bool
    seccompProfilePath: str
    selinuxEnabled: bool


class Slirp4netns(BaseModel):
    executable: str
    package: str
    version: str


class Host(BaseModel):
    arch: str
    buildahVersion: str
    cgroupControllers: List[str]
    cgroupManager: str
    cgroupVersion: str
    conmon: Conmon
    cpuUtilization: CpuUtilization
    cpus: int
    databaseBackend: str
    distribution: Distribution
    eventLogger: str
    freeLocks: int
    hostname: str
    idMappings: IdMappings
    kernel: str
    linkmode: str
    logDriver: str
    memFree: int
    memTotal: int
    networkBackend: str
    networkBackendInfo: NetworkBackendInfo
    ociRuntime: OciRuntime
    os: str
    pasta: Pasta
    remoteSocket: RemoteSocket
    rootlessNetworkCmd: str
    security: Security
    serviceIsRemote: bool
    slirp4netns: Slirp4netns
    swapFree: int
    swapTotal: int
    uptime: str
    variant: str


class Plugins(BaseModel):
    authorization: Optional[str] = None
    log: List[str]
    network: List[str]
    volume: List[str]


class Registries(BaseModel):
    search: List[str]


class ContainerStore(BaseModel):
    number: int
    paused: int
    running: int
    stopped: int


class GraphStatus(BaseModel):
    backing_filesystem: str = Field(..., alias="Backing Filesystem")
    native_overlay_diff: str = Field(..., alias="Native Overlay Diff")
    supports_d_type: str = Field(..., alias="Supports d_type")
    supports_shifting: str = Field(..., alias="Supports shifting")
    supports_volatile: str = Field(..., alias="Supports volatile")
    using_metacopy: str = Field(..., alias="Using metacopy")


class ImageStore(BaseModel):
    number: int


class Store(BaseModel):
    configFile: str
    containerStore: ContainerStore
    graphDriverName: str
    graphOptions: Dict[str, str]
    graphRoot: str
    graphRootAllocated: int
    graphRootUsed: int
    graphStatus: GraphStatus
    imageCopyTmpDir: str
    imageStore: ImageStore
    runRoot: str
    transientStore: bool
    volumePath: str


class Version(BaseModel):
    APIVersion: str
    Built: int
    BuiltTime: str
    GitCommit: str
    GoVersion: str
    Os: str
    OsArch: str
    Version: str


class PodmanInfo(BaseModel):
    host: Host
    plugins: Plugins
    registries: Registries
    store: Store
    version: Version


def test_podman_info():
    # given
    rootful_podman_info = PodmanInfo.model_validate({
        'host': {
            'arch': 'arm64',
            'buildahVersion': '1.38.1',
            'cgroupControllers': [
                'cpuset',
                'cpu',
                'io',
                'memory',
                'pids',
                'rdma',
                'misc'],
            'cgroupManager': 'systemd',
            'cgroupVersion': 'v2',
            'conmon': {
                'package': 'conmon-2.1.12-3.fc41.aarch64',
                'path': '/usr/bin/conmon',
                'version': 'conmon version 2.1.12, commit: '},
            'cpuUtilization': {
                'idlePercent': 97.99,
                'systemPercent': 1.15,
                'userPercent': 0.86},
            'cpus': 6,
            'databaseBackend': 'sqlite',
            'distribution': {
                'distribution': 'fedora',
                'variant': 'coreos',
                'version': '41'},
            'eventLogger': 'journald',
            'freeLocks': 2048,
            'hostname': 'localhost.localdomain',
            'idMappings': {'gidmap': None, 'uidmap': None},
            'kernel': '6.12.7-200.fc41.aarch64',
            'linkmode': 'dynamic',
            'logDriver': 'journald',
            'memFree': 1624608768,
            'memTotal': 2041810944,
            'networkBackend': 'netavark',
            'networkBackendInfo': {
                'backend': 'netavark',
                'dns': {
                    'package': 'aardvark-dns-1.13.1-1.fc41.aarch64',
                    'path': '/usr/libexec/podman/aardvark-dns',
                    'version': 'aardvark-dns 1.13.1'},
                'package': 'netavark-1.13.1-1.fc41.aarch64',
                'path': '/usr/libexec/podman/netavark',
                'version': 'netavark 1.13.1'},
            'ociRuntime': {
                'name': 'crun',
                'package': 'crun-1.19.1-1.fc41.aarch64',
                'path': '/usr/bin/crun',
                'version': 'crun version 1.19.1\n'
                           'commit: '
                           '3e32a70c93f5aa5fea69b50256cca7fd4aa23c80\n'
                           'rundir: /run/crun\n'
                           'spec: 1.0.0\n'
                           '+SYSTEMD +SELINUX +APPARMOR +CAP +SECCOMP '
                           '+EBPF +CRIU +LIBKRUN +WASM:wasmedge '
                           '+YAJL'},
            'os': 'linux',
            'pasta': {'executable': '/usr/bin/pasta',
                      'package': 'passt-0^20241211.g09478d5-1.fc41.aarch64',
                      'version': 'pasta '
                                 '0^20241211.g09478d5-1.fc41.aarch64-pasta\n'
                                 'Copyright Red Hat\n'
                                 'GNU General Public License, version 2 or '
                                 'later\n'
                                 '  '
                                 '<https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>\n'
                                 'This is free software: you are free to change '
                                 'and redistribute it.\n'
                                 'There is NO WARRANTY, to the extent permitted '
                                 'by law.\n'},
            'remoteSocket': {
                'exists': True,
                'path': 'unix:///run/podman/podman.sock'},
            'rootlessNetworkCmd': 'pasta',
            'security': {
                'apparmorEnabled': False,
                'capabilities': 'CAP_CHOWN,CAP_DAC_OVERRIDE,CAP_FOWNER,CAP_FSETID,CAP_KILL,CAP_NET_BIND_SERVICE,CAP_SETFCAP,CAP_SETGID,CAP_SETPCAP,CAP_SETUID,CAP_SYS_CHROOT',
                'rootless': False,
                'seccompEnabled': True,
                'seccompProfilePath': '/usr/share/containers/seccomp.json',
                'selinuxEnabled': True},
            'serviceIsRemote': False,
            'slirp4netns': {
                'executable': '/usr/bin/slirp4netns',
                'package': 'slirp4netns-1.3.1-1.fc41.aarch64',
                'version': 'slirp4netns version 1.3.1\n'
                           'commit: '
                           'e5e368c4f5db6ae75c2fce786e31eef9da6bf236\n'
                           'libslirp: 4.8.0\n'
                           'SLIRP_CONFIG_VERSION_MAX: 5\n'
                           'libseccomp: 2.5.5'},
            'swapFree': 0,
            'swapTotal': 0,
            'uptime': '0h 1m 33.00s',
            'variant': 'v8'},
        'plugins': {
            'authorization': None,
            'log': ['k8s-file', 'none', 'passthrough', 'journald'],
            'network': ['bridge', 'macvlan', 'ipvlan'],
            'volume': ['local']},
        'registries': {
            'search': ['docker.io']},
        'store': {
            'configFile': '/usr/share/containers/storage.conf',
            'containerStore': {
                'number': 0,
                'paused': 0,
                'running': 0,
                'stopped': 0},
            'graphDriverName': 'overlay',
            'graphOptions': {
                'overlay.imagestore': '/usr/lib/containers/storage',
                'overlay.mountopt': 'nodev,metacopy=on'},
            'graphRoot': '/var/lib/containers/storage',
            'graphRootAllocated': 106415992832,
            'graphRootUsed': 15990263808,
            'graphStatus': {
                'Backing Filesystem': 'xfs',
                'Native Overlay Diff': 'false',
                'Supports d_type': 'true',
                'Supports shifting': 'true',
                'Supports volatile': 'true',
                'Using metacopy': 'true'},
            'imageCopyTmpDir': '/var/tmp',
            'imageStore': {'number': 15},
            'runRoot': '/run/containers/storage',
            'transientStore': False,
            'volumePath': '/var/lib/containers/storage/volumes'},
        'version': {
            'APIVersion': '5.3.2',
            'Built': 1737504000,
            'BuiltTime': 'Wed Jan 22 01:00:00 2025',
            'GitCommit': '',
            'GoVersion': 'go1.23.4',
            'Os': 'linux',
            'OsArch': 'linux/arm64',
            'Version': '5.3.2'}})

    rootless_podman_info = PodmanInfo.model_validate({
        'host': {
            'arch': 'arm64',
            'buildahVersion': '1.38.1',
            'cgroupControllers': ['cpu', 'io', 'memory', 'pids'],
            'cgroupManager': 'systemd',
            'cgroupVersion': 'v2',
            'conmon': {
                'package': 'conmon-2.1.12-3.fc41.aarch64',
                'path': '/usr/bin/conmon',
                'version': 'conmon version 2.1.12, commit: '},
            'cpuUtilization': {
                'idlePercent': 99.34,
                'systemPercent': 0.35,
                'userPercent': 0.31},
            'cpus': 6,
            'databaseBackend': 'sqlite',
            'distribution': {
                'distribution': 'fedora',
                'variant': 'coreos',
                'version': '41'},
            'eventLogger': 'journald',
            'freeLocks': 2047,
            'hostname': 'localhost.localdomain',
            'idMappings': {
                'gidmap': [{'container_id': 0,
                            'host_id': 1000,
                            'size': 1},
                           {'container_id': 1,
                            'host_id': 100000,
                            'size': 1000000}],
                'uidmap': [{'container_id': 0,
                            'host_id': 501,
                            'size': 1},
                           {'container_id': 1,
                            'host_id': 100000,
                            'size': 1000000}]},
            'kernel': '6.12.7-200.fc41.aarch64',
            'linkmode': 'dynamic',
            'logDriver': 'journald',
            'memFree': 1607774208,
            'memTotal': 2041810944,
            'networkBackend': 'netavark',
            'networkBackendInfo': {
                'backend': 'netavark',
                'dns': {
                    'package': 'aardvark-dns-1.13.1-1.fc41.aarch64',
                    'path': '/usr/libexec/podman/aardvark-dns',
                    'version': 'aardvark-dns 1.13.1'},
                'package': 'netavark-1.13.1-1.fc41.aarch64',
                'path': '/usr/libexec/podman/netavark',
                'version': 'netavark 1.13.1'},
            'ociRuntime': {
                'name': 'crun',
                'package': 'crun-1.19.1-1.fc41.aarch64',
                'path': '/usr/bin/crun',
                'version': 'crun version 1.19.1\n'
                           'commit: '
                           '3e32a70c93f5aa5fea69b50256cca7fd4aa23c80\n'
                           'rundir: /run/user/501/crun\n'
                           'spec: 1.0.0\n'
                           '+SYSTEMD +SELINUX +APPARMOR +CAP +SECCOMP '
                           '+EBPF +CRIU +LIBKRUN +WASM:wasmedge '
                           '+YAJL'},
            'os': 'linux',
            'pasta': {
                'executable': '/usr/bin/pasta',
                'package': 'passt-0^20241211.g09478d5-1.fc41.aarch64',
                'version': 'pasta '
                           '0^20241211.g09478d5-1.fc41.aarch64-pasta\n'
                           'Copyright Red Hat\n'
                           'GNU General Public License, version 2 or '
                           'later\n'
                           '  '
                           '<https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>\n'
                           'This is free software: you are free to change '
                           'and redistribute it.\n'
                           'There is NO WARRANTY, to the extent permitted '
                           'by law.\n'},
            'remoteSocket': {
                'exists': True,
                'path': 'unix:///run/user/501/podman/podman.sock'},
            'rootlessNetworkCmd': 'pasta',
            'security': {
                'apparmorEnabled': False,
                'capabilities': 'CAP_CHOWN,CAP_DAC_OVERRIDE,CAP_FOWNER,CAP_FSETID,CAP_KILL,CAP_NET_BIND_SERVICE,CAP_SETFCAP,CAP_SETGID,CAP_SETPCAP,CAP_SETUID,CAP_SYS_CHROOT',
                'rootless': True,
                'seccompEnabled': True,
                'seccompProfilePath': '/usr/share/containers/seccomp.json',
                'selinuxEnabled': True},
            'serviceIsRemote': False,
            'slirp4netns': {
                'executable': '/usr/bin/slirp4netns',
                'package': 'slirp4netns-1.3.1-1.fc41.aarch64',
                'version': 'slirp4netns version 1.3.1\n'
                           'commit: '
                           'e5e368c4f5db6ae75c2fce786e31eef9da6bf236\n'
                           'libslirp: 4.8.0\n'
                           'SLIRP_CONFIG_VERSION_MAX: 5\n'
                           'libseccomp: 2.5.5'},
            'swapFree': 0,
            'swapTotal': 0,
            'uptime': '0h 2m 2.00s',
            'variant': 'v8'},
        'plugins': {
            'authorization': None,
            'log': ['k8s-file', 'none', 'passthrough', 'journald'],
            'network': ['bridge', 'macvlan', 'ipvlan'],
            'volume': ['local']},
        'registries': {
            'search': ['docker.io']},
        'store': {
            'configFile': '/var/home/core/.config/containers/storage.conf',
            'containerStore': {
                'number': 1,
                'paused': 0,
                'running': 0,
                'stopped': 1},
            'graphDriverName': 'overlay',
            'graphOptions': {},
            'graphRoot': '/var/home/core/.local/share/containers/storage',
            'graphRootAllocated': 106415992832,
            'graphRootUsed': 15990403072,
            'graphStatus': {
                'Backing Filesystem': 'xfs',
                'Native Overlay Diff': 'true',
                'Supports d_type': 'true',
                'Supports shifting': 'false',
                'Supports volatile': 'true',
                'Using metacopy': 'false'},
            'imageCopyTmpDir': '/var/tmp',
            'imageStore': {'number': 2},
            'runRoot': '/run/user/501/containers',
            'transientStore': False,
            'volumePath': '/var/home/core/.local/share/containers/storage/volumes'},
        'version': {
            'APIVersion': '5.3.2',
            'Built': 1737504000,
            'BuiltTime': 'Wed Jan 22 01:00:00 2025',
            'GitCommit': '',
            'GoVersion': 'go1.23.4',
            'Os': 'linux',
            'OsArch': 'linux/arm64',
            'Version': '5.3.2'}})

    assert rootful_podman_info.host.remoteSocket.exists
    assert rootless_podman_info.host.remoteSocket.exists
