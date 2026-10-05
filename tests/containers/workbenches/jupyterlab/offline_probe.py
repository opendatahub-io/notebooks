"""Host-side probes for JupyterLab behavior that needs a protocol client."""

from __future__ import annotations

import importlib
import json
import logging
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jupyter_client.session import Session
    from websocket import WebSocket

BASE = os.environ.get("OFFLINE_BASE_URL", "/offline/")
HOST = os.environ.get("OFFLINE_JUPYTER_HOST", "127.0.0.1")
PORT = int(os.environ.get("OFFLINE_JUPYTER_PORT", "8888"))
TIMEOUT = 20
# Kernel startup is noticeably slower on non-amd64 workbench runners. The
# caller supplies a longer bound only for those images.
KERNEL_TIMEOUT = int(os.environ.get("OFFLINE_KERNEL_TIMEOUT", "30"))
CHANNEL_TIMEOUT = 5


def kernel_api(method: str, path: str, payload: object | None = None) -> object | None:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://{HOST}:{PORT}{BASE}{path.lstrip('/')}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # ruff: ignore[suspicious-url-open-usage] -- fixed HTTP URL
        raw = response.read()
        return json.loads(raw) if raw else None


def _close_channels(ws: WebSocket) -> None:
    try:
        ws.close(timeout=1)
    except Exception:
        logging.exception("Failed to close kernel WebSocket")


def _ready_channels(kernel_id: str) -> tuple[WebSocket, Session]:
    """Connect to the same kernel until a correlated shell reply proves readiness."""
    websocket = importlib.import_module("websocket")
    Session = importlib.import_module("jupyter_client.session").Session

    deadline = time.monotonic() + KERNEL_TIMEOUT
    attempts = 0
    while (remaining := deadline - time.monotonic()) > 0:
        attempts += 1
        session = Session()
        ws = None
        ready = False
        try:
            ws = websocket.create_connection(
                f"ws://{HOST}:{PORT}{BASE}api/kernels/{kernel_id}/channels?session_id={session.session}",
                timeout=min(CHANNEL_TIMEOUT, remaining),
            )
            info = session.msg("kernel_info_request", content={})
            ws.send(json.dumps({**info, "channel": "shell"}, default=str))
            attempt_deadline = min(deadline, time.monotonic() + CHANNEL_TIMEOUT)
            while (remaining := attempt_deadline - time.monotonic()) > 0:
                ws.settimeout(remaining)
                raw = ws.recv()
                if not raw:
                    raise RuntimeError("kernel WebSocket closed during kernel-info handshake")
                incoming = json.loads(raw)
                if (
                    incoming.get("channel") == "shell"
                    and incoming.get("msg_type") == "kernel_info_reply"
                    and incoming.get("parent_header", {}).get("msg_id") == info["header"]["msg_id"]
                ):
                    ready = True
                    return ws, session
        except websocket.WebSocketTimeoutException:
            pass
        finally:
            if ws is not None and not ready:
                _close_channels(ws)
        # Work around ipykernel 7's lost ZMQ wake-up:
        # https://github.com/ipython/ipykernel/issues/1554
        # Resending on the same socket cannot wake it. A fresh session_id
        # opens new ZMQ channels instead of restoring the server's buffered
        # connection. Retry only readiness; never replay submitted code.
        logging.warning("Kernel %s did not answer readiness attempt %d; refreshing channels", kernel_id, attempts)
    raise TimeoutError(f"kernel did not answer kernel-info request within {KERNEL_TIMEOUT}s ({attempts} connections)")


def execute(code: str) -> str:
    websocket = importlib.import_module("websocket")

    kernel = kernel_api("POST", "/api/kernels", {"name": "python3"})
    assert isinstance(kernel, dict)
    kernel_id = kernel["id"]
    ws = None
    try:
        ws, session = _ready_channels(kernel_id)
        message = session.msg(
            "execute_request",
            content={
                "code": code,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
                "stop_on_error": True,
            },
        )
        ws.settimeout(CHANNEL_TIMEOUT)
        ws.send(json.dumps({**message, "channel": "shell"}, default=str))
        deadline = time.monotonic() + KERNEL_TIMEOUT
        output: list[str] = []
        saw_reply = False
        saw_idle = False
        while (remaining := deadline - time.monotonic()) > 0:
            ws.settimeout(min(CHANNEL_TIMEOUT, remaining))
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                raise RuntimeError("kernel WebSocket closed before execute completed")
            incoming = json.loads(raw)
            if incoming.get("parent_header", {}).get("msg_id") != message["header"]["msg_id"]:
                continue
            if incoming["msg_type"] == "stream":
                output.append(incoming["content"]["text"])
            elif incoming["msg_type"] == "error":
                raise RuntimeError(incoming["content"])
            elif incoming["msg_type"] == "execute_reply":
                saw_reply = True
                if incoming["content"]["status"] != "ok":
                    raise RuntimeError(incoming["content"])
            elif incoming["msg_type"] == "status" and incoming["content"]["execution_state"] == "idle":
                saw_idle = True
            if saw_reply and saw_idle:
                return "".join(output)
        raise TimeoutError(f"kernel did not complete within {KERNEL_TIMEOUT}s")
    finally:
        primary_error = sys.exc_info()[1]
        if ws is not None:
            _close_channels(ws)
        delete_error: BaseException | None = None
        try:
            kernel_api("DELETE", f"/api/kernels/{kernel_id}")
            try:
                kernel_api("GET", f"/api/kernels/{kernel_id}")
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
            else:
                raise AssertionError(f"server-managed kernel {kernel_id} still exists after DELETE")
        except Exception as error:
            delete_error = error
        if delete_error is not None:
            if primary_error is not None:
                logging.exception("Failed to shut down server-managed kernel %s", kernel_id)
            else:
                raise delete_error


def git_roundtrip() -> None:
    def run(*args: str) -> None:
        subprocess.run(args, check=True, text=True, capture_output=True, timeout=15)

    root = pathlib.Path(os.environ.get("OFFLINE_WORKDIR", "/opt/app-root/src/.offline-git-workdir"))
    remote, first, second = (root / name for name in ("remote.git", "first", "second"))
    run("git", "init", "--bare", str(remote))
    run("git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main")
    run("git", "clone", f"file://{remote}", str(first))
    run("git", "-C", str(first), "config", "user.email", "offline@example.invalid")
    run("git", "-C", str(first), "config", "user.name", "Offline Test")
    original = {
        "cells": [
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": "print('original')"}
        ],
        "metadata": {"offline": True},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (first / "roundtrip.ipynb").write_text(json.dumps(original))
    run("git", "-C", str(first), "add", "roundtrip.ipynb")
    run("git", "-C", str(first), "commit", "-m", "first")
    run("git", "-C", str(first), "push", "--set-upstream", "origin", "HEAD:main")
    run("git", "clone", f"file://{remote}", str(second))
    assert json.loads((second / "roundtrip.ipynb").read_text())["cells"][0]["source"] == "print('original')"
    run("git", "-C", str(second), "config", "user.email", "offline@example.invalid")
    run("git", "-C", str(second), "config", "user.name", "Offline Test")
    updated = {**original, "cells": [{**original["cells"][0], "source": "print('updated')"}]}
    (second / "roundtrip.ipynb").write_text(json.dumps(updated))
    run("git", "-C", str(second), "add", "roundtrip.ipynb")
    run("git", "-C", str(second), "commit", "-m", "second")
    run("git", "-C", str(second), "push")
    run("git", "-C", str(first), "pull", "--ff-only")
    assert json.loads((first / "roundtrip.ipynb").read_text())["cells"][0]["source"] == "print('updated')"
    print("git roundtrip ready")


def main() -> None:
    case = os.environ.get("OFFLINE_PROBE_CASE") or sys.argv[1]
    if case == "kernel":
        print(execute(os.environ["OFFLINE_KERNEL_CODE"]), end="")
    elif case == "git_roundtrip":
        git_roundtrip()
    else:
        raise ValueError(f"unknown probe case: {case}")


if __name__ == "__main__":
    main()
