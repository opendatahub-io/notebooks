from __future__ import annotations

import functools
import http.cookiejar
import logging
import os
import platform
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

import docker.errors
import docker.models.images
import docker.types
import pytest
import testcontainers.core.container
import testcontainers.core.docker_client
import testcontainers.core.network
import testcontainers.core.waiting_utils

from tests.containers import docker_utils, kubernetes_utils, podman_machine_utils

if TYPE_CHECKING:
    import pytest_subtests


class TestWorkbenchImage:
    """Tests for workbench images in this repository.
    A workbench image is an image running a web IDE that listens on port 8888."""

    @pytest.mark.parametrize(
        "sysctls",
        [
            {},
            # disable ipv6 https://danwalsh.livejournal.com/47118.html
            {"net.ipv6.conf.all.disable_ipv6": "1"},
        ],
    )
    def test_image_entrypoint_starts(self, subtests: pytest_subtests.SubTests, workbench_image: str, sysctls) -> None:
        container = WorkbenchContainer(image=workbench_image, user=1000, group_add=[0], sysctls=sysctls)
        try:
            try:
                container.start()
                # check explicitly that we can connect to the ide running in the workbench
                with subtests.test("Attempting to connect to the workbench..."):
                    container._connect()
            finally:
                # try to grab logs regardless of whether container started or not
                grab_and_check_logs(subtests, container)
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

    def test_ipv6_only(self, subtests: pytest_subtests.SubTests, workbench_image: str, test_frame):
        """Test that workbench image is accessible via IPv6.
        Workarounds for macOS will be needed, so that's why it's a separate test."""

        # network is made ipv6 by only defining the ipv6 subnet for it
        # do _not_ set the ipv6=true option, that would actually make it dual-stack
        # https://github.com/containers/podman/issues/22359#issuecomment-2196817604
        network = testcontainers.core.network.Network(
            docker_network_kw={
                "ipam": docker.types.IPAMConfig(
                    pool_configs=[
                        docker.types.IPAMPool(subnet="fd00::/64"),
                    ]
                )
            }
        )
        test_frame.append(network)

        container = WorkbenchContainer(image=workbench_image)
        container.with_network(network)
        try:
            try:
                client = testcontainers.core.docker_client.DockerClient()
                rootless: bool = client.client.info()["Rootless"]
                # with rootful podman, --publish does not expose IPv6-only ports
                # see https://github.com/containers/podman/issues/14491 and friends
                container.start(wait_for_readiness=rootless)
                # check explicitly that we can connect to the ide running in the workbench
                if rootless:
                    container._connect()
                else:
                    # rootful containers have an IP assigned, so we can connect to that
                    # NOTE: this is only reachable from the host machine, so remote podman won't work
                    container.get_wrapped_container().reload()
                    ipv6_address = container.get_wrapped_container().attrs["NetworkSettings"]["Networks"][network.name][
                        "GlobalIPv6Address"
                    ]
                    if platform.system().lower() == "darwin":
                        # the container host is a podman machine, we need to expose port on podman machine first
                        host = "localhost"
                        port = podman_machine_utils.find_free_port()
                        socket_path = os.path.realpath(docker_utils.get_socket_path(client.client))
                        logging.debug(f"{socket_path=}")
                        process = podman_machine_utils.open_ssh_tunnel(
                            machine_predicate=lambda m: os.path.realpath(m.ConnectionInfo.PodmanSocket.Path)
                            == socket_path,
                            local_port=port,
                            remote_port=container.port,
                            remote_interface=f"[{ipv6_address}]",
                        )
                        test_frame.append(process, lambda p: p.kill())
                    else:
                        host = ipv6_address
                        port = container.port

                    container._connect(container_host=host, container_port=port)
            finally:
                # try to grab logs regardless of whether container started or not
                grab_and_check_logs(subtests, container)
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

    @pytest.mark.openshift
    def test_image_run_on_openshift(self, workbench_image: str):
        client = kubernetes_utils.get_client()
        print(client)

        username = kubernetes_utils.get_username(client)
        print(username)

        with kubernetes_utils.ImageDeployment(client, workbench_image) as image:
            image.deploy(container_name="notebook-tests-pod")


class WorkbenchContainer(testcontainers.core.container.DockerContainer):
    @functools.wraps(testcontainers.core.container.DockerContainer.__init__)
    def __init__(
        self,
        port: int = 8888,
        **kwargs,
    ) -> None:
        defaults = {
            # because rstudio only prints out errors when TTY is present
            # > TTY detected. Printing informational message about logging configuration.
            "tty": True,
            # another rstudio speciality, without this, it gives
            # > system error 13 (Permission denied) [path: /opt/app-root/src/.cache/rstudio
            # equivalent podman command may include
            # > --mount type=tmpfs,dst=/opt/app-root/src,notmpcopyup
            # can't use mounts= because testcontainers already sets volumes=
            # > mounts=[docker.types.Mount(target="/opt/app-root/src/", source="", type="volume", no_copy=True)],
            # can use tmpfs=, keep in mind `notmpcopyup` opt is podman specific
            "tmpfs": {"/opt/app-root/src": "rw,notmpcopyup"},
        }
        if not kwargs.keys().isdisjoint(defaults.keys()):
            raise TypeError(f"Keyword arguments in {defaults.keys()=} are not allowed, for good reasons")
        super().__init__(**defaults, **kwargs)

        self.port = port
        self.with_exposed_ports(self.port)

    @testcontainers.core.waiting_utils.wait_container_is_ready(urllib.error.URLError)
    def _connect(
        self, container_host: str | None = None, container_port: int | None = None, base_url: str = ""
    ) -> None:
        """
        :param container_host: overrides the container host IP in connection check to use direct access
        :param container_port: overrides the container port
        :param base_url: needs to be with a leading /
        """
        # are we still alive?
        self.get_wrapped_container().reload()
        assert self.get_wrapped_container().status != "exited"

        # connect
        host = container_host or self.get_container_host_ip()
        port = container_port or self.get_exposed_port(self.port)
        try:
            # if we did not enable cookie support here, with RStudio we'd end up looping and getting
            # HTTP 302 (i.e. `except urllib.error.HTTPError as e: assert e.code == 302`) every time
            cookie_jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
            # host may be an ipv6 address, need to be careful with formatting this
            if ":" in host:
                host = f"[{host}]"
            result = opener.open(urllib.request.Request(f"http://{host}:{port}{base_url}"), timeout=1)
        except urllib.error.URLError as e:
            raise e

        # get /
        try:
            if result.status != 200:
                raise ConnectionError(f"Failed to connect to container, {result.status=}")
        finally:
            result.close()

    def start(self, wait_for_readiness: bool = True) -> WorkbenchContainer:
        super().start()
        container_id = self.get_wrapped_container().id
        docker_client = testcontainers.core.container.DockerClient().client
        logging.debug(docker_client.api.inspect_container(container_id)["HostConfig"])
        if wait_for_readiness:
            self._connect()
        return self


def grab_and_check_logs(subtests: pytest_subtests.SubTests, container: WorkbenchContainer) -> None:
    # Here is a list of blocked keywords we don't want to see in the log messages during the container/workbench
    # startup (e.g., log messages from Jupyter IDE, code-server IDE or RStudio IDE).
    blocked_keywords = [
        "Error",
        "error",
        "Warning",
        "warning",
        "Failed",
        "failed",
        "[W ",
        "[E ",
        # https://docs.nginx.com/nginx/admin-guide/monitoring/logging/
        "[warn] ",
        "[error] ",
        "[crit] ",
        "[alert] ",
        "[emerg] ",
        # https://docs.python.org/3/tutorial/errors.html#exceptions
        "Traceback",
    ]
    # Here is a list of allowed messages that match some block keyword from the list above, but we allow them
    # for some reason.
    allowed_messages = [
        # We don't touch this - it should be fixed in the future by the package upgrade.
        "JupyterEventsVersionWarning: The `version` property of an event schema must be a string. It has been type coerced, but in a future version of this library, it will fail to validate.",
        # This is a message from our reverse proxy nginx caused by the fact that we attempt to connect to the code-server before it's actually running (container.start(wait_for_readiness=True)).
        "connect() failed (111: Connection refused) while connecting to upstream, client",
        # We use oauth-proxy to give us authentication, and we use OpenShift route to get HTTPS
        "WARNING: The Jupyter server is listening on all IP addresses and not using encryption. This is not recommended.",
    ]

    # Let's wait a couple of seconds to give a chance to log eventual extra startup messages just to be sure we don't
    # miss anything important in this test.
    time.sleep(3)

    stdout, stderr = container.get_logs()
    full_logs = ""
    for line in stdout.splitlines() + stderr.splitlines():
        full_logs = f"{full_logs}\n{line.decode()}"
        logging.debug(line.decode())

    # let's check that logs don't contain any error or unexpected warning message
    with subtests.test("Checking the log in the workbench..."):
        failed_lines: list[str] = []
        for line in full_logs.splitlines():
            if any(keyword in line for keyword in blocked_keywords):
                if any(allowed in line for allowed in allowed_messages):
                    logging.debug(f"Waived message: '{line}'")
                else:
                    logging.error(f"Unexpected keyword in the following message: '{line}'")
                    failed_lines.append(line)
        if len(failed_lines) > 0:
            pytest.fail(
                f"Log message(s) ({len(failed_lines)}) that violate our checks occurred during the workbench startup:\n{'\n'.join(failed_lines)}"
            )
