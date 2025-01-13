import functools
import http.cookiejar
import logging
import urllib.error
import urllib.request

import docker.errors
import docker.models.images

import testcontainers.core.container
import testcontainers.core.waiting_utils

import pytest

from tests.containers import docker_utils


class TestWorkbenchImage:
    """Tests for workbench images in this repository.
    A workbench image is an image running a web IDE that listens on port 8888."""

    @pytest.mark.parametrize('sysctls', [
        {},
        # disable ipv6 https://danwalsh.livejournal.com/47118.html
        {"net.ipv6.conf.all.disable_ipv6": "1"}
    ])
    def test_image_entrypoint_starts(self, image: str, sysctls) -> None:
        skip_if_not_workbench_image(image)

        container = WorkbenchContainer(image=image, user=1000, group_add=[0],
                                       sysctls=sysctls,
                                       # because rstudio only prints out errors when TTY is present
                                       # > TTY detected. Printing informational message about logging configuration.
                                       tty=True,
                                       # another rstudio speciality, without this, it gives
                                       # > system error 13 (Permission denied) [path: /opt/app-root/src/.cache/rstudio
                                       # equivalent podman command may include
                                       # > --mount type=tmpfs,dst=/opt/app-root/src,notmpcopyup
                                       # can't use mounts= because testcontainers already sets volumes=
                                       # > mounts=[docker.types.Mount(target="/opt/app-root/src/", source="", type="volume", no_copy=True)],
                                       # can use tmpfs=, keep in mind `notmpcopyup` opt is podman specific
                                       tmpfs={"/opt/app-root/src": "rw,notmpcopyup"},
                                       )
        try:
            try:
                container.start()
                # check explicitly that we can connect to the ide running in the workbench
                container._connect()
            finally:
                # try to grab logs regardless of whether container started or not
                stdout, stderr = container.get_logs()
                for line in stdout.splitlines() + stderr.splitlines():
                    logging.debug(line)
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)


class WorkbenchContainer(testcontainers.core.container.DockerContainer):
    @functools.wraps(testcontainers.core.container.DockerContainer.__init__)
    def __init__(
            self,
            port: int = 8888,
            **kwargs,
    ) -> None:
        super().__init__(**kwargs)

        self.port = port
        self.with_exposed_ports(self.port)

    @testcontainers.core.waiting_utils.wait_container_is_ready(urllib.error.URLError)
    def _connect(self) -> None:
        # are we still alive?
        self.get_wrapped_container().reload()
        assert self.get_wrapped_container().status != "exited"

        # connect
        try:
            # if we did not enable cookies support here, with RStudio we'd end up looping and getting
            # HTTP 302 (i.e. `except urllib.error.HTTPError as e: assert e.code == 302`) every time
            cookie_jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
            result = opener.open(
                urllib.request.Request(f"http://{self.get_container_host_ip()}:{self.get_exposed_port(self.port)}"),
                timeout=1)
        except urllib.error.URLError as e:
            raise e

        # get /
        try:
            if result.status != 200:
                raise ConnectionError(f"Failed to connect to container, {result.status=}")
        finally:
            result.close()

    def start(self):
        super().start()
        container_id = self.get_wrapped_container().id
        docker_client = testcontainers.core.container.DockerClient().client
        logging.debug(docker_client.api.inspect_container(container_id)['HostConfig'])
        self._connect()
        return self


def skip_if_not_workbench_image(image: str) -> docker.models.images.Image:
    client = testcontainers.core.container.DockerClient()
    try:
        image_metadata = client.client.images.get(image)
    except docker.errors.ImageNotFound:
        image_metadata = client.client.images.pull(image)
        assert isinstance(image_metadata, docker.models.images.Image)

    ide_server_label_fragments = ('-code-server-', '-jupyter-', '-rstudio-')
    if not any(ide in image_metadata.labels['name'] for ide in ide_server_label_fragments):
        pytest.skip(
            f"Image {image} does not have any of '{ide_server_label_fragments=} in {image_metadata.labels['name']=}'")

    return image_metadata
