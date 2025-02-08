from __future__ import annotations
import asyncio
import logging
import os
import socket
import select
import threading
import time
import sys
import subprocess
import typing

from kubernetes.client.rest import ApiException

import kubernetes.stream.ws_client
import kubernetes.stream

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

Out of these, the oc port-forward subprocess is a very good solution.
"""

"""
        # p = SubprocessProxy(pod.metadata.namespace, pod.metadata.name, 8080)
        # t = threading.Thread(target=SubprocessProxy.start)
        # t.start()
        # self.tf.add(t, lambda _: p.stop())
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
    def __init__(self, local_host: str, local_port: int, core_v1_api, pod, buffer_size: int = 4096):
        self.local_host = local_host
        self.local_port = local_port
        self.core_v1_api = core_v1_api
        self.pod = pod
        # self.remote_namespace = remote_namespace
        # self.remote_name = remote_name
        # self.remote_port = remote_port
        self.buffer_size = buffer_size

    def start(self, cancellation_token: CancellationToken = CancellationToken()):
        try:
            self.cancellation_token = cancellation_token

            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.local_host, self.local_port))
            self.server_socket.listen(1)
            logging.info(f"Proxy listening on {self.local_host}:{self.local_port}")

            while True:
                client_socket, addr = self.server_socket.accept()
                logging.info(f"Accepted connection from {addr[0]}:{addr[1]}")
                self.handle_client(client_socket)

        except Exception as e:
            logging.exception(f"Proxying failed to listen", exc_info=e)
            raise
        finally:
            self.server_socket.close()

    def get_actual_port(self) -> int:
        return self.server_socket.getsockname()[1]

    def establish_connection(self, core_v1_api, pod: kubernetes.client.models.V1Pod) -> socket.socket:
        # if we e.g. specify wrong port, the pf = portforward() call succeeds,
        # but pf.connected will later flip to False
        # we need to check that _everything_ works before moving on
        pf = None
        s = None
        while not pf or not pf.connected or not s:
            pf: kubernetes.stream.ws_client.PortForward = kubernetes.stream.portforward(
                # api_method=
                core_v1_api.connect_get_namespaced_pod_portforward,
                # name=
                pod.metadata.name,
                # namespace=
                pod.metadata.namespace,
                ports=",".join(str(p) for p in [8888]),
            )
            s: typing.Union[kubernetes.stream.ws_client.PortForward._Port._Socket, socket.socket] | None = pf.socket(8888)
        assert s, "Failed to establish connection"
        return s

    def handle_client(self, client_socket):
        remote_socket = self.establish_connection(self.core_v1_api, self.pod)

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

        client_socket.close()
        remote_socket.close()

# if __name__ == "__main__":
#     local_host = "127.0.0.1"
#     local_port = 8080
#     remote_host = "example.com"
#     remote_port = 80
#
#     proxy = SocketProxy(local_host, local_port, remote_host, remote_port)
#     proxy.start()
