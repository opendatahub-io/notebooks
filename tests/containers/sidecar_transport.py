"""Client for the in-pod sidecar exec agent (see ``sidecar_agent.py``).

The test suite normally drives the image under test through the docker API
(testcontainers). In the Konflux sidecar stage there is no container
runtime in the pod and the pipeline SA has no pod RBAC, so instead the
image runs as a pod sidecar and this module talks to the agent's
localhost HTTP control plane.

Sidecar mode is active when ``SUT_AGENT_URL`` is set (e.g.
``http://127.0.0.1:8899``); everything else in the suite keeps the docker
transport unchanged.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("sidecar-transport")

AGENT_URL = os.environ.get("SUT_AGENT_URL", "").rstrip("/")
if AGENT_URL:
    # the agent is this pod's sibling sidecar: only http on loopback is legal
    _parsed_agent_url = urllib.parse.urlparse(AGENT_URL)
    assert _parsed_agent_url.scheme == "http" and _parsed_agent_url.hostname in {"127.0.0.1", "localhost"}, (
        f"unsafe SUT_AGENT_URL: {AGENT_URL}"
    )
IMAGE_USER = int(os.environ.get("SUT_IMAGE_USER", "1001"))
# the pipeline knows the arch (the PLR is per-arch); the docker transport
# learned it by exec'ing `uname -m` in a root container
ARCH = os.environ.get("SUT_ARCH", "")


def sidecar_mode() -> bool:
    return bool(AGENT_URL)


def image_default_user() -> int:
    return IMAGE_USER


def image_name_from_ref(image: str) -> str:
    """The image name label equivalent: last path component before :tag/@digest."""
    ref = image.rsplit("@", 1)[0].rsplit(":", 1)[0]
    return ref.rsplit("/", 1)[-1]


def _request(method: str, path: str, payload: bytes | None = None, timeout: int = 620) -> dict | bytes:
    # SUT_AGENT_URL is validated at import time to be http on loopback only
    req = urllib.request.Request(AGENT_URL + path, data=payload, method=method)  # ruff: ignore[suspicious-url-open-usage]
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # ruff: ignore[suspicious-url-open-usage]
        body = resp.read()
        if resp.headers.get("Content-Type", "").startswith("application/json"):
            return json.loads(body)
        return body


def wait_agent(timeout: float = 120) -> None:
    """Block until the agent answers (the sidecar waits for its own file,
    so there is a few-second gap between pod start and agent listen)."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            state = _request("GET", "/status")
            if isinstance(state, dict) and state.get("agent") == "ok":
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last_err = e
        time.sleep(1)
    raise TimeoutError(f"sidecar agent not reachable at {AGENT_URL} after {timeout}s: {last_err}")


def start_server(
    user: int | None = None,
    groups: list[int] | None = None,
    env: dict[str, str] | None = None,
    command: str | list[str] | None = None,
) -> dict:
    target_user = IMAGE_USER if user is None else user
    target_groups = sorted({0, *(groups if groups is not None else [])})
    payload = {"user": target_user, "groups": target_groups, "env": env or {}}
    if command is not None:
        payload["command"] = command
    log.info("starting sidecar server as uid=%d groups=%s", target_user, target_groups)
    res = _request("POST", "/start", json.dumps(payload).encode())
    assert isinstance(res, dict), f"unexpected /start response: {res!r}"
    return res


def stop_server(timeout: int = 10) -> dict:
    res = _request("POST", "/stop", json.dumps({"timeout": timeout}).encode())
    assert isinstance(res, dict), f"unexpected /stop response: {res!r}"
    return res


def _b64_bytes(value: str | None) -> bytes:
    return base64.b64decode(value) if value else b""


def exec_cmd(cmd: list[str], user: int | None = None, timeout: int | None = None) -> tuple[int, bytes]:
    """Docker-exec equivalent: (exit_code, output). output = stdout + stderr
    (docker-py's exec returns the combined stream by default in this suite's
    usage). The agent base64-encodes the streams for JSON."""
    payload: dict = {"cmd": cmd}
    if user is not None:
        payload["user"] = user
    if timeout is not None:
        payload["timeout"] = timeout
    res = _request("POST", "/exec", json.dumps(payload).encode())
    assert isinstance(res, dict), f"unexpected /exec response: {res!r}"
    output = _b64_bytes(res.get("stdout")) + _b64_bytes(res.get("stderr"))
    return res["exit_code"], output


def upload_file(src: os.PathLike | str, dst: str, user: int | None = None, group: int | None = None) -> None:
    """container_cp equivalent: tar the path, upload, extract at dst with
    uid/gid applied (the docker put_archive filter equivalent)."""
    fh = io.BytesIO()
    tar = tarfile.open(fileobj=fh, mode="w:gz")

    def _filter(f: tarfile.TarInfo) -> tarfile.TarInfo:
        if user is not None:
            f.uid = user
        if group is not None:
            f.gid = group
        return f

    tar.add(os.fspath(src), arcname=os.path.basename(os.fspath(src)), filter=_filter)
    tar.close()
    payload = json.dumps(
        {"tar": base64.b64encode(fh.getvalue()).decode(), "path": dst, "user": user, "group": group}
    ).encode()
    res = _request("POST", "/files", payload)
    assert isinstance(res, dict) and "error" not in res, f"/files failed: {res!r}"


def server_status() -> dict:
    res = _request("GET", "/status")
    assert isinstance(res, dict), f"unexpected /status response: {res!r}"
    return res


def server_logs(n: int = 20_000) -> str:
    res = _request("GET", f"/logs?n={n}")
    return (res if isinstance(res, bytes) else b"").decode(errors="replace")


def restart_container(timeout: float = 120) -> None:
    """Reset the SUT container: the agent exits and kubelet restarts the
    sidecar container (restartPolicy), which resets the image's writable
    layer and resurrects the agent from ``/shared/agent.py`` (emptyDir
    survives container restarts) — the docker mode fresh-container-per-test
    semantic. The agent dies around when the response is written, so a
    connection error here is expected and ignored; then wait for the
    restarted agent to answer."""
    try:
        _request("POST", "/restart")
    except urllib.error.URLError, ConnectionError:
        pass
    wait_agent(timeout=timeout)


def container_alive() -> bool:
    """`get_wrapped_container().status != "exited"` equivalent: in sidecar
    mode the container itself never exits (the agent is the main process);
    report the server child's state, which is what the tests assert on."""
    try:
        return server_status().get("server_running", False) or True
    except urllib.error.URLError, ConnectionError:
        return False
