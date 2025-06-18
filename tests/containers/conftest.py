from __future__ import annotations

import dataclasses
import logging
import os
import platform
from typing import TYPE_CHECKING, Any

import docker.errors
import docker.models.images
import docker.types
import pytest
import testcontainers.core.config
import testcontainers.core.container
import testcontainers.core.docker_client

from tests.containers import docker_utils, skopeo_utils, utils

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest import ExitCode, Metafunc, Parser, Session

SECURITY_OPTION_ROOTLESS = "name=rootless"
TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE = "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"

SHUTDOWN_RYUK = False

# NOTE: Configure Testcontainers through `testcontainers.core.config` and not through env variables.
# Importing `testcontainers` above has already read out env variables, and so at this point, setting
#  * DOCKER_HOST
#  * TESTCONTAINERS_RYUK_DISABLED
#  * TESTCONTAINERS_RYUK_PRIVILEGED
#  * TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE
# would have no effect.

# We'd get selinux violations with podman otherwise, so either ryuk must be privileged, or we need to disable selinux.
# https://github.com/testcontainers/testcontainers-java/issues/2088#issuecomment-1169830358
testcontainers.core.config.testcontainers_config.ryuk_privileged = True


@dataclasses.dataclass
class Image:
    # only pulled images have an id
    id: str | None
    name: str
    labels: dict[str, str]

    @classmethod
    def from_docker(cls, image: docker.models.images.Image, name: str):
        return Image(id=image.id, name=name, labels=image.labels)


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_addoption
def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--image", action="append", default=[], help="Image to use, can be specified multiple times")


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_generate_tests
def pytest_generate_tests(metafunc: Metafunc) -> None:
    if image.__name__ in metafunc.fixturenames:
        metafunc.parametrize(image.__name__, metafunc.config.getoption("--image"))


def get_image_metadata(image: str) -> Image:
    client = testcontainers.core.container.DockerClient()
    try:
        # docker inspect
        image_metadata = client.client.images.get(image)
    except docker.errors.ImageNotFound:
        # skopeo inspect
        labels = skopeo_utils.get_image_labels(image)
        if labels is not None:
            return Image(id=None, name=image, labels=labels)
        # pull & docker inspect
        image_metadata = client.client.images.pull(image)
        assert isinstance(image_metadata, docker.models.images.Image)

    return Image.from_docker(image_metadata, name=image)


def skip_if_not_workbench_image(image: str) -> Image:
    image_metadata = get_image_metadata(image)

    ide_server_label_fragments = ("-code-server-", "-jupyter-", "-rstudio-")
    if not any(ide in image_metadata.labels["name"] for ide in ide_server_label_fragments):
        pytest.skip(
            f"Image {image} does not have any of '{ide_server_label_fragments=} in {image_metadata.labels['name']=}'"
        )

    return image_metadata


def skip_if_not_cuda_image(image: str) -> Image:
    image_metadata = get_image_metadata(image)

    if "-cuda-" not in image_metadata.labels["name"]:
        pytest.skip(f"Image {image} does not have any of '-cuda-' in {image_metadata.labels['name']=}")

    return image_metadata


def skip_if_not_rocm_image(image: str) -> Image:
    image_metadata = get_image_metadata(image)
    if "-rocm-" not in image_metadata.labels["name"]:
        pytest.skip(f"Image {image} does not have any of '-rocm-' in {image_metadata.labels['name']=}")

    return image_metadata


# https://docs.pytest.org/en/stable/how-to/fixtures.html#parametrizing-fixtures
# indirect parametrization https://stackoverflow.com/questions/18011902/how-to-pass-a-parameter-to-a-fixture-function-in-pytest
@pytest.fixture(scope="session")
def image(request):
    yield request.param


@pytest.fixture(scope="session")
def runtime_image(image: str) -> Image:
    image_metadata = get_image_metadata(image)

    if not '-runtime-' in image_metadata.labels["name"]:
        pytest.skip(
            f"Image {image} does not have any of '-runtime-' in {image_metadata.labels['name']=}'"
        )

    return image_metadata


@pytest.fixture(scope="function")
def workbench_image(image: str):
    skip_if_not_workbench_image(image)
    yield image


@pytest.fixture(scope="function")
def cuda_workbench_image(workbench_image: str):
    skip_if_not_cuda_image(workbench_image)
    yield workbench_image


@pytest.fixture(scope="function")
def rocm_workbench_image(workbench_image: str):
    skip_if_not_rocm_image(workbench_image)
    yield workbench_image


@pytest.fixture(scope="function")
def jupyterlab_image(image: str) -> Image:
    image_metadata = skip_if_not_workbench_image(image)
    if "-jupyter-" not in image_metadata.labels["name"]:
        pytest.skip(f"Image {image} does not have '-jupyter-' in {image_metadata.labels['name']=}'")

    return image_metadata


@pytest.fixture(scope="function")
def rstudio_image(image: str) -> Image:
    image_metadata = skip_if_not_workbench_image(image)
    if not utils.is_rstudio_image(image):
        pytest.skip(f"Image {image} does not have '-rstudio-' in {image_metadata.labels['name']=}'")

    return image_metadata


@pytest.fixture(scope="function")
def codeserver_image(image: str) -> Image:
    image_metadata = skip_if_not_workbench_image(image)
    if "-code-server-" not in image_metadata.labels["name"]:
        pytest.skip(f"Image {image} does not have '-code-server-' in {image_metadata.labels['name']=}'")

    return image_metadata


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_sessionstart
def pytest_sessionstart(session: Session) -> None:
    # first preflight check: ping the Docker API
    client = testcontainers.core.docker_client.DockerClient()
    assert client.client.ping(), "Failed to connect to Docker"

    # determine the local socket path
    # NOTE: this will not work for remote docker, but we will cross the bridge when we come to it
    socket_path = docker_utils.get_socket_path(client.client)

    # set that socket path for ryuk's use, unless user overrode that
    if TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE not in os.environ:
        logging.info("Env variable TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE not set, setting it now")
        if platform.system().lower() == "linux":
            logging.info(f"We are on Linux, setting {socket_path=} for TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE")
            testcontainers.core.config.testcontainers_config.ryuk_docker_socket = socket_path
        elif platform.system().lower() == "darwin":
            podman_machine_socket_path = docker_utils.get_podman_machine_socket_path(client.client)
            logging.info(
                f"We are on macOS, setting {podman_machine_socket_path=} for TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"
            )
            testcontainers.core.config.testcontainers_config.ryuk_docker_socket = podman_machine_socket_path
        else:
            raise RuntimeError(
                f"Unsupported platform {platform.system()=}, cannot set TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"
            )

    # second preflight check: start the Reaper container
    if not testcontainers.core.config.testcontainers_config.ryuk_disabled:
        # when running on rootless podman, ryuk fails to start and may need to be disabled
        # https://java.testcontainers.org/supported_docker_environment/#podman
        logging.warning("Ryuk is enabled. This may not work with rootless podman.")
        try:
            assert testcontainers.core.container.Reaper.get_instance() is not None, "Failed to start Reaper container"
        except Exception as e:
            logging.exception("Failed to start the Ryuk Reaper container", exc_info=e)
            logging.error("Set env variable 'export TESTCONTAINERS_RYUK_DISABLED=true' and try again.")
            raise RuntimeError("Consider disabling Ryuk as per the log messages above.") from e


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_sessionfinish
def pytest_sessionfinish(session: Session, exitstatus: int | ExitCode) -> None:
    # resolves a shutdown resource leak warning that would be otherwise reported
    if SHUTDOWN_RYUK:
        testcontainers.core.container.Reaper.delete_instance()


@pytest.fixture(scope="function")
def test_frame():
    class TestFrame:
        """Helper class to manage resources in tests.
        Example:
        >>> import subprocess
        >>> import testcontainers.core.network
        >>>
        >>> def test_something(test_frame: TestFrame):
        >>> # this will create/destroy the network as it enters/leaves the test_frame
        >>>    network = testcontainers.core.network.Network(...)
        >>>    test_frame.append(network)
        >>>
        >>> # some resources require additional cleanup function
        >>>    test_frame.append(subprocess.Popen(...), lambda p: p.kill())
        """

        def __init__(self):
            self.resources: list[tuple[Any, Callable]] = []

        def append[T](self, resource: T, cleanup_func: Callable[[T], None] | None = None) -> T:
            """Runs the Context manager lifecycle on the resource,
            without actually using the `with` structured resource management thing.

            For some resources, the __exit__ method does not force termination.
            subprocess.Popen is one such resource, its __exit__ only `wait()`s.
            Use the cleanup_func argument to terminate resources that need it.

            This is somewhat similar to Go's `defer`."""
            self.resources.append((resource, cleanup_func))
            return resource.__enter__()  # noqa: PLC2801 Unnecessary dunder call to `__enter__`

        def destroy(self):
            """Runs __exit__() on the registered resources as a cleanup."""
            for resource, cleanup_func in reversed(self.resources):
                if cleanup_func is not None:
                    cleanup_func(resource)
                resource.__exit__(None, None, None)  # don't use named args, there are inconsistencies

    t = TestFrame()
    yield t
    t.destroy()
