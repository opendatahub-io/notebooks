"""Exec agent for the in-pod (sidecar) test stage.

Runs as the MAIN PROCESS of the image-under-test sidecar container, as
root, inside a plain Tekton pod. The tenant neither allows container
runtimes in the test pods (SCC: no privileged, no_new_privs, no
CAP_SYS_ADMIN) nor gives the pipeline SA any pod RBAC (no pods/exec,
not even pods get) — so a sibling test step cannot reach this container
through the k8s exec API either. This agent is the control plane: a
localhost HTTP server over which the test step starts the image's
entrypoint, execs commands, copies files in, and restarts the server —
replacing the docker API surface the test suite normally uses
(testcontainers). Stdlib only: the image under test is the only
environment we can rely on (any workbench image ships python3).

Endpoints (127.0.0.1:$SUT_AGENT_PORT):
    POST /start   {"user", "groups", "env"}   start the entrypoint as the given user
    POST /stop    {"timeout"}                 SIGTERM (then KILL) the server child
    POST /exec    {"cmd", "user"?}            run a command; default user = image USER
    POST /files   {"tar" (b64), "path"}       extract at path (put_archive equivalent)
    GET  /status                              agent + server child state
    GET  /logs?n=                              tail of the server output file

User switching is fork + setgroups/setgid/setuid: no PAM, so the image's
environment (PATH, HOME, ...) is preserved exactly as the container
runtime would provide it.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("SUT_AGENT_PORT", "8899"))
SERVER_LOG = os.environ.get("SUT_SERVER_LOG", "/shared/server.log")
ENTRYPOINT = os.environ.get("SUT_ENTRYPOINT", "start-notebook.sh")
WORKDIR = os.environ.get("SUT_WORKDIR", "/opt/app-root/src")
DEFAULT_USER = int(os.environ.get("SUT_IMAGE_USER", "1001"))
EXEC_TIMEOUT = int(os.environ.get("SUT_EXEC_TIMEOUT", "600"))

log = logging.getLogger("sidecar-agent")
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")


class _ServerState:
    """The server-child process, shared between the handler threads and the
    SIGTERM handler (hence the re-entrant lock: start_server() stops a
    running child while holding it, and the signal handler may fire from
    the same thread mid-stop)."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.proc: subprocess.Popen | None = None
        self.started_at: float | None = None


_state = _ServerState()


def _drop_privileges(user: int, groups: list[int]) -> None:
    """preexec_fn: root -> (groups, gid=user, uid=user). Order matters.

    setgroups/setgid are root-only privileges: skipped when the agent is not
    root (local development); setuid to one's own uid is a legal no-op there,
    and the in-pod root case drops to the image user as before."""
    if os.geteuid() == 0:
        if groups:
            os.setgroups(groups)
        os.setgid(user)
    os.setuid(user)


def _server_running() -> bool:
    return _state.proc is not None and _state.proc.poll() is None


def _server_state() -> dict:
    return {
        "server_running": _server_running(),
        "server_exit_code": None if _state.proc is None else _state.proc.poll(),
        "server_started_at": _state.started_at,
    }


def _stop_locked(timeout: int = 10) -> None:
    """Stop the server child. Caller must hold _state.lock."""
    proc = _state.proc
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + timeout
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.2)
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        proc.wait()
    _state.proc = None
    _state.started_at = None


def stop_server(timeout: int = 10) -> None:
    with _state.lock:
        _stop_locked(timeout)


def _container_env() -> dict[str, str]:
    """The environment the image's processes would see under docker/podman.

    The pod injects in-cluster variables (``KUBERNETES_SERVICE_*``) that a
    plain docker container never has; ``oc``/``kubectl`` pick them up and try
    to read the service-account token, so strip them to keep exec/server
    behavior docker-faithful.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("KUBERNETES_")}


def _reset_foreign_workdir_state(uid: int) -> None:
    """Cross-test pollution guard.

    Docker mode gives every test a fresh container (clean ``$WORKDIR``); the
    sidecar shares one workdir across tests, so a previous test's per-user
    state (e.g. ``.local`` created by its uid) can block a later test running
    as a different uid. Drop state dirs owned by anyone but the target uid;
    same-uid restarts keep state (tests rely on files surviving restarts).
    """
    for entry in (".local", ".jupyter", ".ipython"):
        path = os.path.join(WORKDIR, entry)
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if st.st_uid != uid:
            shutil.rmtree(path, ignore_errors=True)


def start_server(user: int, groups: list[int], env: dict[str, str], command: str | list[str] | None = None) -> dict:
    """Launch the server child: the image entrypoint, or ``command`` if given
    (the docker ``with_command`` equivalent; a string runs via ``/bin/sh -c``)."""
    with _state.lock:
        if _server_running():
            _stop_locked()
        if not os.path.isdir(WORKDIR):
            workdir = "/"
        else:
            workdir = WORKDIR
            _reset_foreign_workdir_state(user)
        full_env = _container_env()
        full_env.update(env or {})
        argv = ["/bin/sh", "-c", command] if isinstance(command, str) else (list(command) if command else [ENTRYPOINT])
        # fresh log per start: docker container logs begin at container start,
        # so a test's log check must not see other tests' (or runs') output
        logf = open(SERVER_LOG, "wb", buffering=0)
        # start_new_session: the child gets its own process group so /stop can
        # kill the whole server tree (nginx + jupyter + extensions)
        # fork+setuid: it is the only PAM-free way to keep the image env
        proc = subprocess.Popen(
            argv,
            cwd=workdir,
            env=full_env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            preexec_fn=lambda: _drop_privileges(user, groups),  # ruff: ignore[subprocess-popen-preexec-fn]
            start_new_session=True,
        )
        _state.proc = proc
        _state.started_at = time.time()
        log.info("server started: %s as uid=%d pid=%d", " ".join(argv), user, proc.pid)
        return _server_state()


def _restart_process(delay: float = 0.2) -> None:
    """Exit the agent so the container (and its writable layer) restarts.

    Self-kill through the SIGTERM handler (the graceful _on_term path).
    The agent is the container's PID 1: when it exits, the container
    exits and the kernel tears down the container's PID namespace,
    taking any in-flight /exec children with it; kubelet then restarts
    the sidecar container and the command loop re-execs the agent.
    (A killpg of the agent's own group is not reliable for a container
    PID 1: its group is inherited from the dead runtime and the kernel
    answers ESRCH.)"""
    time.sleep(delay)
    os.kill(os.getpid(), signal.SIGTERM)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def exec_cmd(cmd: list[str], user: int | None = None, timeout: int | None = None) -> dict:
    """Run a command. Output is base64 in the JSON response (the client
    decodes it); the client concatenates stdout+stderr."""
    target_user = DEFAULT_USER if user is None else int(user)
    target_groups = [target_user, 0]  # image user + GID 0 (app-root access, mirrors GHA)
    if user is None:
        # docker exec default: the image's USER, only its own group
        target_groups = [target_user]
    try:
        proc = subprocess.run(
            cmd,
            cwd=WORKDIR if os.path.isdir(WORKDIR) else "/",
            env=_container_env(),
            capture_output=True,
            check=False,
            timeout=timeout or EXEC_TIMEOUT,
            preexec_fn=lambda: _drop_privileges(target_user, target_groups),
        )
        return {
            "exit_code": proc.returncode,
            "stdout": _b64(proc.stdout),
            "stderr": _b64(proc.stderr),
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": 124,
            "stdout": "",
            "stderr": _b64(f"exec timed out after {timeout or EXEC_TIMEOUT}s".encode()),
        }
    except FileNotFoundError as e:
        return {"exit_code": 127, "stdout": "", "stderr": _b64(str(e).encode())}


def _tar_filter(uid: int | None, gid: int | None):
    def _filter(member: tarfile.TarInfo, dest_path: str) -> tarfile.TarInfo | None:
        # data_filter first: rejects unsafe paths/symlinks (Python 3.12+ mitigation)
        filtered = tarfile.data_filter(member, dest_path)
        if filtered is not None and uid is not None:
            filtered.uid = uid
            filtered.gid = gid or 0
        return filtered

    return _filter


def extract_tar(payload: bytes, path: str, uid: int | None, gid: int | None) -> dict:
    os.makedirs(path, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as tf:
        tf.extractall(path, filter=_tar_filter(uid, gid))  # ruff: ignore[tarfile-unsafe-members]
    return {"extracted_to": path}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        log.debug(fmt, *args)

    def _send(self, code: int, payload: dict | bytes) -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header(
            "Content-Type", "application/json" if not isinstance(payload, bytes) else "application/octet-stream"
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_GET(self) -> None:
        if self.path.startswith("/status"):
            state = _server_state()
            state["agent"] = "ok"
            state["entrypoint"] = ENTRYPOINT
            self._send(200, state)
        elif self.path.startswith("/logs"):
            n = 10_000
            if "?" in self.path:
                try:
                    n = int(self.path.split("n=", 1)[1])
                except ValueError:
                    pass
            try:
                with open(SERVER_LOG, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - n))
                    tail = f.read()
            except FileNotFoundError:
                tail = b""
            self._send(200, tail)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            raw = self._body()
            if self.path.startswith("/start"):
                req = json.loads(raw or b"{}")
                user = int(req.get("user", DEFAULT_USER))
                groups = sorted({int(g) for g in req.get("groups", [0])})
                env = {str(k): str(v) for k, v in (req.get("env") or {}).items()}
                command = req.get("command")
                self._send(200, start_server(user, groups, env, command=command))
            elif self.path.startswith("/stop"):
                req = json.loads(raw or b"{}")
                stop_server(timeout=int(req.get("timeout", 10)))
                self._send(200, _server_state())
            elif self.path.startswith("/restart"):
                # container reset (docker parity, opt-in from the suite):
                # stop the server child, then exit the agent itself. kubelet
                # restarts the sidecar container (restartPolicy), the
                # container command loop re-execs the agent from
                # /shared/agent.py (emptyDir survives), and the image's
                # writable layer is fresh. The kill is deferred so this
                # response can flush first; the client should treat it as
                # fire-and-forget and poll /status.
                stop_server(timeout=5)
                threading.Thread(target=_restart_process, daemon=True).start()
                self._send(200, {"restarting": True})
            elif self.path.startswith("/exec"):
                req = json.loads(raw or b"{}")
                cmd = [str(c) for c in req["cmd"]]
                user = req.get("user")
                timeout = req.get("timeout")
                res = exec_cmd(cmd, user=user, timeout=timeout)
                self._send(200, res)
            elif self.path.startswith("/files"):
                req = json.loads(raw or b"{}")
                if not req.get("tar"):
                    self._send(400, {"error": "missing 'tar' payload"})
                    return
                if not req.get("path"):
                    self._send(400, {"error": "missing 'path'"})
                    return
                res = extract_tar(base64.b64decode(req["tar"]), str(req["path"]), req.get("user"), req.get("group"))
                self._send(200, res)
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:
            log.exception("handler error")
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


def main() -> None:
    # signal handling: the task teardown SIGTERMs the sidecar; kill the
    # server child on the way out
    def _on_term(signum, frame) -> None:
        stop_server(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log.info("sidecar agent listening on 127.0.0.1:%d (entrypoint=%s)", PORT, ENTRYPOINT)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
