from __future__ import annotations

import contextlib

import allure
import pytest
import testcontainers.core.container

from tests.containers import base_image_test, conftest, docker_utils


class TestRuntimeImage:
    """Tests for runtime images in this repository."""

    @allure.description("Check that pyzmq library works correctly, important to check especially on s390x.")
    def test_pyzmq_import(self, runtime_image: conftest.Image) -> None:
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
            exit_code, output_bytes = container.exec(
                # NOTE: /usr/bin/python3 would not find zmq, we need python3 in user's venv
                base_image_test.encode_python_function_execution_command_interpreter("python3", check_zmq)
            )

        assert exit_code == 0, f"Python script execution failed. Output: {output_bytes}"
        assert b"pyzmq imported and socket created successfully" in output_bytes, (
            f"Expected success message not found in output. Output: {output_bytes}"
        )

    @allure.description("Check that feast CLI works correctly (imports pyarrow._s3fs transitively).")
    def test_feast_version(self, runtime_image: conftest.Image) -> None:
        if "-minimal-" in runtime_image.labels["name"]:
            pytest.skip("Feast is not installed in minimal runtime images.")

        with running_image(runtime_image.name) as container:
            exit_code, arch_output = container.exec(["uname", "-m"])
            arch = arch_output.decode().strip()
            if exit_code == 0 and arch == "s390x":
                pytest.skip(
                    "Feast CLI check skipped for s390x images (PyArrow/Feast native stack unreliable under CI QEMU)."
                )
            exit_code, output_bytes = container.exec(["/bin/sh", "-c", "feast version"])

        output = output_bytes.decode()
        assert exit_code == 0, f"'feast version' failed: {output}"

    @allure.description("Check that MLflow module imports and core functions are available.")
    def test_mlflow_import(self, runtime_image: conftest.Image) -> None:
        if "-minimal-" in runtime_image.labels["name"]:
            pytest.skip("MLflow is not installed in minimal runtime images.")

        def check_mlflow():
            # ruff: noqa: PLC0415 `import` should be at the top-level of a file
            import mlflow  # pyright: ignore reportMissingImports

            assert hasattr(mlflow, "start_run"), "MLflow does not have start_run function"
            assert hasattr(mlflow, "log_param"), "MLflow does not have log_param function"
            print(f"MLflow imported successfully (version: {mlflow.__version__})")

        with running_image(runtime_image.name) as container:
            exit_code, output_bytes = container.exec(
                base_image_test.encode_python_function_execution_command_interpreter("python3", check_mlflow)
            )

        assert exit_code == 0, f"Python script execution failed. Output: {output_bytes}"
        assert b"MLflow imported successfully" in output_bytes, (
            f"Expected success message not found in output. Output: {output_bytes}"
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
