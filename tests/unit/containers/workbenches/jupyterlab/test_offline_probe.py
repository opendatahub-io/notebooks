from __future__ import annotations

import json
import urllib.error
from collections import deque
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
import websocket

from tests.containers.workbenches.jupyterlab import offline_probe as probe

if TYPE_CHECKING:
    from collections.abc import Callable


class KernelSocket:
    def __init__(self, server: KernelServer, url: str, timeout: float) -> None:
        self.server = server
        self.url = url
        self.timeout = timeout
        self.closed = False
        self.messages: deque[str] = deque()

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def send(self, raw: str) -> None:
        request = json.loads(raw)
        self.server.sent.append(request)
        assert request["channel"] == "shell"
        self.server.respond(self, request)

    def reply(self, request: dict[str, Any], kind: str, content: dict[str, Any], channel: str = "shell") -> None:
        self.messages.append(
            json.dumps(
                {
                    "header": {"msg_type": kind},
                    "msg_type": kind,
                    "parent_header": request["header"],
                    "content": content,
                    "channel": channel,
                }
            )
        )

    def recv(self) -> str:
        if self.messages:
            self.server.now += 0.01
            return self.messages.popleft()
        self.server.now += self.timeout
        raise websocket.WebSocketTimeoutException("stalled channel")

    def close(self, timeout: float = 1) -> None:
        self.closed = True


class KernelServer:
    def __init__(self) -> None:
        self.now = 0.0
        self.sockets: list[KernelSocket] = []
        self.sent: list[dict[str, Any]] = []
        self.api_calls: list[tuple[str, str]] = []
        self.respond: Callable[[KernelSocket, dict[str, Any]], None] = self.success

    def connect(self, url: str, timeout: float) -> KernelSocket:
        socket = KernelSocket(self, url, timeout)
        self.sockets.append(socket)
        return socket

    def api(self, method: str, path: str, payload: object = None) -> object:
        self.api_calls.append((method, path))
        if method == "POST":
            return {"id": "one-kernel"}
        if method == "GET":
            raise urllib.error.HTTPError("http://localhost", 404, "deleted", None, None)
        return None

    def success(self, socket: KernelSocket, request: dict[str, Any]) -> None:
        if request["header"]["msg_type"] == "kernel_info_request":
            socket.reply(request, "kernel_info_reply", {"status": "ok"})
        else:
            socket.reply(request, "stream", {"text": "42\n"}, "iopub")
            # Shell replies and IOPub idle can arrive in either order.
            socket.reply(request, "status", {"execution_state": "idle"}, "iopub")
            socket.reply(request, "execute_reply", {"status": "ok"})

    def assert_cleaned_up(self) -> None:
        assert self.api_calls == [
            ("POST", "/api/kernels"),
            ("DELETE", "/api/kernels/one-kernel"),
            ("GET", "/api/kernels/one-kernel"),
        ]
        assert all(socket.closed for socket in self.sockets)


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> KernelServer:
    server = KernelServer()
    monkeypatch.setattr(probe, "kernel_api", server.api)
    monkeypatch.setattr(probe, "KERNEL_TIMEOUT", 12)
    monkeypatch.setattr(probe, "time", SimpleNamespace(monotonic=lambda: server.now))
    monkeypatch.setattr(websocket, "create_connection", server.connect)
    return server


def test_recovers_stalled_readiness_with_fresh_connection_to_same_kernel(server: KernelServer) -> None:
    def respond(socket: KernelSocket, request: dict[str, Any]) -> None:
        # Model ipykernel #1554: resending on the first socket never wakes it.
        if socket is not server.sockets[0]:
            server.success(socket, request)

    server.respond = respond
    assert probe.execute("print(6 * 7)") == "42\n"
    sessions = [parse_qs(urlsplit(socket.url).query)["session_id"][0] for socket in server.sockets]
    assert len(sessions) == len(set(sessions)) == 2
    executions = [request for request in server.sent if request["header"]["msg_type"] == "execute_request"]
    assert len(executions) == 1
    assert executions[0]["header"]["session"] == sessions[-1]
    server.assert_cleaned_up()


def test_permanently_unresponsive_kernel_has_one_total_readiness_deadline(server: KernelServer) -> None:
    server.respond = lambda socket, request: None
    with pytest.raises(TimeoutError, match="kernel-info"):
        probe.execute("print(6 * 7)")
    assert server.now <= probe.KERNEL_TIMEOUT
    assert all(request["header"]["msg_type"] == "kernel_info_request" for request in server.sent)
    server.assert_cleaned_up()


@pytest.mark.parametrize("reply_first", [True, False])
def test_execution_accepts_shell_reply_and_idle_in_either_order(server: KernelServer, reply_first: bool) -> None:
    def respond(socket: KernelSocket, request: dict[str, Any]) -> None:
        server.success(socket, request)
        if request["header"]["msg_type"] == "execute_request" and reply_first:
            socket.messages.appendleft(socket.messages.pop())

    server.respond = respond
    assert probe.execute("print(6 * 7)") == "42\n"
    server.assert_cleaned_up()


@pytest.mark.parametrize("missing", ["execute_reply", "status"])
def test_execution_requires_both_reply_and_idle(server: KernelServer, missing: str) -> None:
    def respond(socket: KernelSocket, request: dict[str, Any]) -> None:
        server.success(socket, request)
        if request["header"]["msg_type"] == "execute_request":
            socket.messages = deque(raw for raw in socket.messages if json.loads(raw)["msg_type"] != missing)

    server.respond = respond
    with pytest.raises(TimeoutError, match="did not complete"):
        probe.execute("print(6 * 7)")
    assert len(server.sockets) == 1
    server.assert_cleaned_up()


@pytest.mark.parametrize("failure", ["timeout", "error"])
def test_execution_failure_never_reconnects_or_replays_code(server: KernelServer, failure: str) -> None:
    def respond(socket: KernelSocket, request: dict[str, Any]) -> None:
        if request["header"]["msg_type"] == "kernel_info_request":
            server.success(socket, request)
        elif failure == "error":
            socket.reply(request, "error", {"ename": "ValueError", "evalue": "sentinel"}, "iopub")

    server.respond = respond
    with pytest.raises(TimeoutError if failure == "timeout" else RuntimeError):
        probe.execute("raise ValueError('sentinel')")
    assert len(server.sockets) == 1
    assert sum(request["header"]["msg_type"] == "execute_request" for request in server.sent) == 1
    server.assert_cleaned_up()


def test_unrelated_kernel_info_reply_does_not_establish_readiness(server: KernelServer) -> None:
    def respond(socket: KernelSocket, request: dict[str, Any]) -> None:
        unrelated = {**request, "header": {**request["header"], "msg_id": "another-request"}}
        socket.reply(unrelated, "kernel_info_reply", {"status": "ok"})

    server.respond = respond
    with pytest.raises(TimeoutError, match="kernel-info"):
        probe.execute("print(6 * 7)")
    assert all(request["header"]["msg_type"] == "kernel_info_request" for request in server.sent)
    server.assert_cleaned_up()
