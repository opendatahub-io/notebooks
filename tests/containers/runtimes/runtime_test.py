from __future__ import annotations

import allure

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
            try:
                _socket = context.socket(zmq.PAIR)
                print("pyzmq imported and socket created successfully")
            finally:
                _socket.close(0)  # linger=0
                context.term()

        try:
            container.start(wait_for_readiness=False)  # readiness is not needed for exec
            exit_code, output_str = container.exec(
                base_image_test.encode_python_function_execution_command_interpreter("/usr/bin/python3", check_zmq)
            )

            assert exit_code == 0, f"Python script execution failed. Output: {output_str}"
            assert "pyzmq imported and socket created successfully" in output_str, (
                f"Expected success message not found in output. Output: {output_str}"
            )
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)
