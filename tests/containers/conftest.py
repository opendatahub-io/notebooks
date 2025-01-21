from __future__ import annotations

from typing import TYPE_CHECKING

import testcontainers.core.config
import testcontainers.core.container
import testcontainers.core.docker_client

import pytest

if TYPE_CHECKING:
    from pytest import ExitCode, Session, Parser, Metafunc

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


def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--image", action="append", default=[],
                     help="Image to use, can be specified multiple times")


def pytest_generate_tests(metafunc: Metafunc) -> None:
    if image.__name__ in metafunc.fixturenames:
        metafunc.parametrize(image.__name__, metafunc.config.getoption("--image"))


# https://docs.pytest.org/en/stable/how-to/fixtures.html#parametrizing-fixtures
# indirect parametrization https://stackoverflow.com/questions/18011902/how-to-pass-a-parameter-to-a-fixture-function-in-pytest
@pytest.fixture(scope="session")
def image(request):
    yield request.param


def pytest_sessionstart(session: Session) -> None:
    # first preflight check: ping the Docker API
    client = testcontainers.core.docker_client.DockerClient()
    assert client.client.ping(), "Failed to connect to Docker"

    # second preflight check: start the Reaper container
    assert testcontainers.core.container.Reaper.get_instance() is not None, "Failed to start Reaper container"


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_sessionfinish
def pytest_sessionfinish(session: Session, exitstatus: int | ExitCode) -> None:
    # resolves a shutdown resource leak warning that would be otherwise reported
    if SHUTDOWN_RYUK:
        testcontainers.core.container.Reaper.delete_instance()
