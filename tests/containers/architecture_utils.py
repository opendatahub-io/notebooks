"""Architecture detection utilities for container tests."""

import pytest

from tests.containers import docker_utils
from tests.containers.architecture_support import ARCHITECTURE_LIMITATIONS
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer


@pytest.fixture(scope="function")
def container_architecture(jupyterlab_image):
    """Cache architecture detection per test function."""
    container = WorkbenchContainer(image=jupyterlab_image.name, user=4321, group_add=[0])
    container.start(wait_for_readiness=False)
    try:
        exit_code, arch_output = container.exec(["uname", "-m"])
        if exit_code == 0:
            return arch_output.decode().strip()
        return None
    finally:
        docker_utils.NotebookContainer(container).stop(timeout=0)


def is_feature_supported(architecture: str, feature: str) -> bool:
    """Check if a feature is supported on the given architecture."""
    return ARCHITECTURE_LIMITATIONS.get(architecture, {}).get(feature, True)


def get_architecture_limitation_reason(architecture: str, feature: str) -> str:
    """Get the reason why a feature is not supported on the given architecture."""
    return ARCHITECTURE_LIMITATIONS.get(architecture, {}).get(f"{feature}_reason", "Unknown limitation")
