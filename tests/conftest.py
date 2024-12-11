from __future__ import annotations

from typing import TYPE_CHECKING

import testcontainers.core.container
import testcontainers.core.config

if TYPE_CHECKING:
    from pytest import ExitCode, Session

# We'd get selinux violations with podman otherwise, so either ryuk must be privileged, or we need to disable selinux.
# https://github.com/testcontainers/testcontainers-java/issues/2088#issuecomment-1169830358
testcontainers.core.config.testcontainers_config.ryuk_privileged = True


# https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_sessionfinish
def pytest_sessionfinish(session: Session, exitstatus: int | ExitCode) -> None:
    testcontainers.core.container.Reaper.delete_instance()
