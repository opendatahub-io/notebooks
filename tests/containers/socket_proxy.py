from __future__ import annotations

import contextlib
import logging
import socket
import select
import threading
import subprocess
import typing

from tests.containers.cancellation_token import CancellationToken

"""Proxies kubernetes portforwards to a local port.

This is implemented as a thread running select() loop and managing the sockets.

There are alternative implementations for this.

1) Run oc port-forward in a subprocess
* There isn't a nice way where kubectl would report in machine-readable way the
  port number, https://github.com/kubernetes/kubectl/issues/1190#issuecomment-1075911615
2) Use the socket as is, mount a custom adaptor to the requests library
* The code to do this is weird. This is what docker-py does w.r.t. the docker socket.
  It defines a custom 'http+docker://' protocol, and an adaptor for it, that uses the docker socket.
3) Implement proxy using asyncio
* There are advantages to asyncio, but since we don't have Python asyncio anywhere else yet,
  it is probably best to avoid using asyncio.

Out of these, the oc port-forward subprocess is a decent alternative solution.
"""

class SubprocessProxy:
    #
    def __init__(self, namespace: str, name: str, port: int):
        self.namespace = namespace
        self.name = name
        self.port = port

    def start(self):
        self.forwarder = subprocess.Popen(
            ["kubectl", "port-forward", self.namespace, self.name],
            text=True,
        )
        self.forwarder.communicate()

    def stop(self):
        self.forwarder.terminate()


class SocketProxy:
    def __init__(
            self,
            remote_socket_factory: typing.ContextManager[socket.socket],
            local_host: str = "localhost",
            local_port: int = 0,
            buffer_size: int = 4096
    ) -> None:
        """

        :param local_host: probably "localhost" would make most sense here
        :param local_port: usually leave as to 0, which will make the OS choose a free port
        :param remote_socket_factory: this is a context manager for kubernetes port forwarding
        :param buffer_size: do not poke it, leave this at the default value
        """
        self.local_host = local_host
        self.local_port = local_port
        self.buffer_size = buffer_size
        self.remote_socket_factory = remote_socket_factory

        self.cancellation_token = CancellationToken()

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.local_host, self.local_port))
        self.server_socket.listen(1)
        logging.info(f"Proxy listening on {self.local_host}:{self.local_port}")

    def listen_and_serve_until_canceled(self):
        """Accepts the client, creates a new socket to the remote, and proxies the data.

        Handles at most one client at a time. """
        try:
            while not self.cancellation_token.cancelled:
                client_socket, addr = self.server_socket.accept()
                logging.info(f"Accepted connection from {addr[0]}:{addr[1]}")
                self._handle_client(client_socket)
        except Exception as e:
            logging.exception(f"Proxying failed to listen", exc_info=e)
            raise
        finally:
            self.server_socket.close()

    def get_actual_port(self) -> int:
        """Returns the port that the proxy is listening on.
        When port number 0 was passed in, this will return the actual randomly assigned port."""
        return self.server_socket.getsockname()[1]

    def _handle_client(self, client_socket):
        with client_socket as _, self.remote_socket_factory as remote_socket:
            while True:
                readable, _, _ = select.select([client_socket, remote_socket, self.cancellation_token], [], [])

                if self.cancellation_token.cancelled:
                    break

                if client_socket in readable:
                    data = client_socket.recv(self.buffer_size)
                    if not data:
                        break
                    remote_socket.send(data)

                if remote_socket in readable:
                    data = remote_socket.recv(self.buffer_size)
                    if not data:
                        break
                    client_socket.send(data)


if __name__ == "__main__":
    """Sample application to show how this can work."""


    @contextlib.contextmanager
    def remote_socket_factory():
        class MockServer(threading.Thread):
            def __init__(self, local_host: str = "localhost", local_port: int = 0):
                self.local_host = local_host
                self.local_port = local_port

                self.is_socket_bound = threading.Event()

                super().__init__()

            def run(self):
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_socket.bind((self.local_host, self.local_port))
                self.server_socket.listen(1)
                print(f"MockServer listening on {self.local_host}:{self.local_port}")
                self.is_socket_bound.set()

                client_socket, addr = self.server_socket.accept()
                logging.info(f"MockServer accepted connection from {addr[0]}:{addr[1]}")

                client_socket.send(b"Hello World\n")
                client_socket.close()

            def get_actual_port(self):
                self.is_socket_bound.wait()
                return self.server_socket.getsockname()[1]

        server = MockServer()
        server.start()

        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect(("localhost", server.get_actual_port()))

        yield client_socket

        client_socket.close()
        server.join()


    proxy = SocketProxy(remote_socket_factory(), "localhost", 0)
    thread = threading.Thread(target=proxy.listen_and_serve_until_canceled)
    thread.start()

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(("localhost", proxy.get_actual_port()))

    print(client_socket.recv(1024))  # prints Hello World

    thread.join()
