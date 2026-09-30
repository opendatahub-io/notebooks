from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import nbformat
import websocket
from jupyter_client.session import Session

BASE = os.environ.get("OFFLINE_BASE_URL", "/offline/")
HOST = os.environ.get("OFFLINE_JUPYTER_HOST", "127.0.0.1")
TIMEOUT = 20
KERNEL_TIMEOUT = 30


def api(method: str, path: str, payload: object | None = None) -> tuple[int, dict, object | None]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://{HOST}:8888{BASE}api/contents/{path.lstrip('/')}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # ruff: ignore[suspicious-url-open-usage] -- fixed HTTP URL
        raw = response.read()
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw.decode("utf-8", errors="replace")
        return response.status, dict(response.headers), parsed


def kernel_api(method: str, path: str, payload: object | None = None) -> object | None:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://{HOST}:8888{BASE}{path.lstrip('/')}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # ruff: ignore[suspicious-url-open-usage] -- fixed HTTP URL
        raw = response.read()
        return json.loads(raw) if raw else None


def execute(code: str) -> str:
    kernel = kernel_api("POST", "/api/kernels", {"name": "python3"})
    assert isinstance(kernel, dict)
    kernel_id = kernel["id"]
    session = Session()
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
    ws = None
    try:
        ws = websocket.create_connection(
            f"ws://{HOST}:8888{BASE}api/kernels/{kernel_id}/channels",
            timeout=5,
        )
        ws.send(json.dumps(message, default=str))
        deadline = time.monotonic() + KERNEL_TIMEOUT
        output: list[str] = []
        saw_reply = False
        saw_idle = False
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if raw is None:
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
            try:
                ws.close()
            except Exception:
                logging.exception("Failed to close kernel WebSocket")
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


def lab_contents() -> None:
    with urllib.request.urlopen(f"http://{HOST}:8888{BASE}lab", timeout=TIMEOUT) as response:
        page = response.read().decode("utf-8", errors="replace")
        assert response.status == 200
    assert "JupyterLab" in page and "<script" in page and "static/" in page
    asset = re.search(r'<script[^>]+src="([^"]*static/[^"]+)', page)
    assert asset is not None
    asset_url = asset.group(1) if asset.group(1).startswith("http") else f"http://{HOST}:8888{asset.group(1)}"
    with urllib.request.urlopen(asset_url, timeout=TIMEOUT) as response:  # ruff: ignore[suspicious-url-open-usage] -- local server asset URL
        assert response.status == 200 and response.read(1)

    notebook = {
        "type": "notebook",
        "format": "json",
        "content": {
            "cells": [
                {
                    "id": "uploaded-cell",
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": ["print('uploaded-cell')"],
                }
            ],
            "metadata": {"offline": True},
            "nbformat": 4,
            "nbformat_minor": 5,
        },
    }
    status, _, created = api("PUT", "uploaded.ipynb", notebook)
    assert status in (200, 201) and isinstance(created, dict)
    status, _, loaded = api("GET", "uploaded.ipynb")
    assert status == 200 and isinstance(loaded, dict)
    expected_content = {
        **notebook["content"],
        "cells": [
            {
                **notebook["content"]["cells"][0],
                "metadata": {"trusted": True},
                "source": "print('uploaded-cell')",
            }
        ],
    }
    assert loaded["content"] == expected_content
    assert loaded["content"]["nbformat"] == 4
    assert loaded["content"]["cells"][0]["id"] == "uploaded-cell"
    status, _, renamed = api("PATCH", "uploaded.ipynb", {"path": "renamed.ipynb"})
    assert status == 200 and renamed["name"] == "renamed.ipynb"
    try:
        api("GET", "uploaded.ipynb")
    except urllib.error.HTTPError as error:
        assert error.code == 404
    else:
        raise AssertionError("old notebook path remained readable after rename")
    status, _, renamed_content = api("GET", "renamed.ipynb")
    assert status == 200 and isinstance(renamed_content, dict)
    assert renamed_content["content"] == expected_content
    assert api("DELETE", "renamed.ipynb")[0] == 204
    try:
        api("GET", "renamed.ipynb")
    except urllib.error.HTTPError as error:
        assert error.code == 404
    else:
        raise AssertionError("deleted notebook remained readable")
    print("page endpoint ready")
    print("contents CRUD ready")


def persistent_create() -> None:
    notebook = {
        "type": "notebook",
        "format": "json",
        "content": {
            "cells": [
                {
                    "id": "persistent-cell",
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": ["print('persisted-cell')"],
                }
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        },
    }
    status, _, result = api("PUT", "persistent/surviving.ipynb", notebook)
    assert status in (200, 201), result
    print("persistent notebook created")


def persistent_read() -> None:
    status, _, loaded = api("GET", "persistent/surviving.ipynb")
    assert status == 200 and isinstance(loaded, dict)
    source = loaded["content"]["cells"][0]["source"]
    assert ("".join(source) if isinstance(source, list) else source) == "print('persisted-cell')"
    print("persistent notebook survived")


def git_roundtrip() -> None:
    def run(*args: str) -> None:
        subprocess.run(args, check=True, text=True, capture_output=True, timeout=15)

    root = pathlib.Path("/opt/app-root/src")
    remote, first, second = (root / name for name in ("remote.git", "first", "second"))
    run("git", "init", "--bare", str(remote))
    run("git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main")
    run("git", "clone", f"file://{remote}", str(first))
    run("git", "-C", str(first), "config", "user.email", "offline@example.invalid")
    run("git", "-C", str(first), "config", "user.name", "Offline Test")
    original = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_code_cell("print('original')")],
        metadata={"offline": True},
    )
    (first / "roundtrip.ipynb").write_text(nbformat.writes(original))
    run("git", "-C", str(first), "add", "roundtrip.ipynb")
    run("git", "-C", str(first), "commit", "-m", "first")
    run("git", "-C", str(first), "push", "--set-upstream", "origin", "HEAD:main")
    run("git", "clone", f"file://{remote}", str(second))
    assert nbformat.read(second / "roundtrip.ipynb", as_version=4)["cells"][0]["source"] == "print('original')"
    run("git", "-C", str(second), "config", "user.email", "offline@example.invalid")
    run("git", "-C", str(second), "config", "user.name", "Offline Test")
    updated = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_code_cell("print('updated')")],
        metadata={"offline": True},
    )
    (second / "roundtrip.ipynb").write_text(nbformat.writes(updated))
    run("git", "-C", str(second), "add", "roundtrip.ipynb")
    run("git", "-C", str(second), "commit", "-m", "second")
    run("git", "-C", str(second), "push")
    run("git", "-C", str(first), "pull", "--ff-only")
    assert nbformat.read(first / "roundtrip.ipynb", as_version=4)["cells"][0]["source"] == "print('updated')"
    print("git roundtrip ready")


def main() -> None:
    case = os.environ.get("OFFLINE_PROBE_CASE") or sys.argv[1]
    if case == "lab_contents":
        lab_contents()
    elif case == "persistent_create":
        persistent_create()
    elif case == "persistent_read":
        persistent_read()
    elif case == "git_roundtrip":
        git_roundtrip()
    elif case == "kernel":
        output = execute(os.environ["OFFLINE_KERNEL_CODE"])
        print(output, end="")
    else:
        raise ValueError(f"unknown probe case: {case}")


if __name__ == "__main__":
    main()
