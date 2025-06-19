from __future__ import annotations

import contextlib

import allure
import pytest
import testcontainers.core.container

from tests.containers import base_image_test, conftest, docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer


class TestRuntimeImage:
    """Tests for runtime images in this repository."""

    @allure.description("Check that pyzmq library works correctly, important to check especially on s390x.")
    def test_pyzmq_import(self, runtime_image: conftest.Image) -> None:
        container = WorkbenchContainer(image=runtime_image.name, user=4321, group_add=[0])

        def check_zmq():
            # ruff: noqa: PLC0415 `import` should be at the top-level of a file
            import zmq  # pyright: ignore reportMissingImports

            context = zmq.Context()
            socket = None
            try:
                socket = context.socket(zmq.PAIR)
                print("pyzmq imported and socket created successfully")
            finally:
                if socket is not None:
                    socket.close(0)  # linger=0
                context.term()

        with running_image(runtime_image.name) as container:
            exit_code, output_str = container.exec(
                # NOTE: /usr/bin/python3 would not find zmq, we need python3 in user's venv
                base_image_test.encode_python_function_execution_command_interpreter("python3", check_zmq)
            )

            assert exit_code == 0, f"Python script execution failed. Output: {output_str}"
            assert "pyzmq imported and socket created successfully" in output_str, (
                f"Expected success message not found in output. Output: {output_str}"
            )


@contextlib.contextmanager
def running_image(image: str):
    """Usage: with running_image("quay.io/...") as container:"""
    container = testcontainers.core.container.DockerContainer(image=image, user=23456, group_add=[0])
    container.with_command("/bin/sh -c 'sleep infinity'")
    try:
        container.start()
        yield container
    except Exception as e:
        pytest.fail(f"Unexpected exception in test: {e}")
    finally:
        docker_utils.NotebookContainer(container).stop(timeout=0)

    # If the return doesn't happen in the try block, fail the test
    pytest.fail("The test did not pass as expected.")
