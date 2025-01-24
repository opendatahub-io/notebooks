from __future__ import annotations

import logging
import os
from typing import Iterable, TYPE_CHECKING

import testcontainers.core.config
import testcontainers.core.container
import testcontainers.core.docker_client

import pytest

if TYPE_CHECKING:
    from pytest import ExitCode, Session, Parser, Metafunc

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


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_addoption
def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--image", action="append", default=[],
                     help="Image to use, can be specified multiple times")


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_generate_tests
def pytest_generate_tests(metafunc: Metafunc) -> None:
    if image.__name__ in metafunc.fixturenames:
        metafunc.parametrize(image.__name__, metafunc.config.getoption("--image"))


# https://docs.pytest.org/en/stable/how-to/fixtures.html#parametrizing-fixtures
# indirect parametrization https://stackoverflow.com/questions/18011902/how-to-pass-a-parameter-to-a-fixture-function-in-pytest
@pytest.fixture(scope="session")
def image(request):
    yield request.param


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_sessionstart
def pytest_sessionstart(session: Session) -> None:
    # first preflight check: ping the Docker API
    client = testcontainers.core.docker_client.DockerClient()
    assert client.client.ping(), "Failed to connect to Docker"

    # determine the local socket path
    # NOTE: this will not work for remote docker, but we will cross the bridge when we come to it
    socket_path = the_one(adapter.socket_path for adapter in client.client.api.adapters.values())

    # set that socket path for ryuk's use, unless user overrode that
    if TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE not in os.environ:
        testcontainers.core.config.testcontainers_config.ryuk_docker_socket = socket_path

    # second preflight check: start the Reaper container
    if not testcontainers.core.config.testcontainers_config.ryuk_disabled:
        # when running on rootless podman, ryuk fails to start and may need to be disabled
        # https://java.testcontainers.org/supported_docker_environment/#podman
        logging.warning("Ryuk is enabled. This may not work with rootless podman.")
        try:
            assert testcontainers.core.container.Reaper.get_instance() is not None, "Failed to start Reaper container"
        except Exception as e:
            logging.exception("Failed to start the Ryuk Reaper container", exc_info=e)
            logging.error(f"Set env variable 'export TESTCONTAINERS_RYUK_DISABLED=true' and try again.")
            raise RuntimeError("Consider disabling Ryuk as per the log messages above.") from e


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_sessionfinish
def pytest_sessionfinish(session: Session, exitstatus: int | ExitCode) -> None:
    # resolves a shutdown resource leak warning that would be otherwise reported
    if SHUTDOWN_RYUK:
        testcontainers.core.container.Reaper.delete_instance()


# https://docs.python.org/3/library/functions.html#iter
def the_one[T](iterable: Iterable[T]) -> T:
    """Checks that there is exactly one element in the iterable, and returns it."""
    it = iter(iterable)
    try:
        v = next(it)
    except StopIteration:
        raise ValueError("No elements in iterable")
    try:
        next(it)
    except StopIteration:
        return v
    raise ValueError("More than one element in iterable")
