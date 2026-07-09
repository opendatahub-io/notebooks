from __future__ import annotations

import allure

from tests.containers import base_image_test, conftest, docker_utils


class TestCodeServerImage:
    """Tests for Code Server workbench images in this repository."""

    @allure.issue("RHAIENG-6157")
    @allure.description(
        "Check that the packages the VS Code Jupyter extension requires before it will run a notebook "
        "cell ('jupyter', 'notebook', and a working 'jupyter kernelspec') are present in the image. "
        "Without them, the extension falls back to `pip install -U notebook 'jupyter-client<8' 'pyzmq<25'`, "
        "which fails to build on architectures lacking prebuilt wheels for the pinned pyzmq version (e.g. s390x)."
    )
    def test_jupyter_extension_dependencies_present(self, codeserver_image: conftest.Image) -> None:
        def check_jupyter_extension_dependencies():
            # ruff: noqa: PLC0415 `import` should be at the top-level of a file
            import subprocess

            import notebook  # pyright: ignore[reportMissingImports]  # noqa: F401

            # mirrors JupyterInterpreterDependencyService.getDependenciesNotInstalled()
            import jupyter  # noqa: F401

            # mirrors JupyterInterpreterDependencyService.isKernelSpecAvailable()
            subprocess.run(["jupyter", "kernelspec", "--version"], check=True)
            print("jupyter extension dependencies OK")

        with docker_utils.running_container(codeserver_image.name) as container:
            exit_code, output_bytes = container.exec(
                base_image_test.encode_python_function_execution_command_interpreter(
                    "python3", check_jupyter_extension_dependencies
                )
            )

        assert exit_code == 0, f"Python script execution failed. Output: {output_bytes}"
        assert b"jupyter extension dependencies OK" in output_bytes, (
            f"Expected success message not found in output. Output: {output_bytes}"
        )

    @allure.issue("RHAIENG-6157")
    @allure.description(
        "End-to-end check that a real Jupyter kernel can be started and can execute code, "
        "exercising the same pyzmq-based ZMQ transport the VS Code extension's kernel connection uses."
    )
    def test_jupyter_kernel_starts_and_executes(self, codeserver_image: conftest.Image) -> None:
        def start_kernel_and_execute():
            # ruff: noqa: PLC0415 `import` should be at the top-level of a file
            from jupyter_client.manager import KernelManager  # pyright: ignore[reportMissingImports]

            km = KernelManager(kernel_name="python3")
            km.start_kernel()
            try:
                kc = km.client()
                kc.start_channels()
                try:
                    kc.wait_for_ready(timeout=30)
                    msg_id = kc.execute("print('kernel executed ok')")
                    while True:
                        msg = kc.get_iopub_msg(timeout=10)
                        if msg["parent_header"].get("msg_id") != msg_id:
                            continue
                        if msg["msg_type"] == "stream":
                            print(msg["content"]["text"].strip())
                        if msg["msg_type"] == "status" and msg["content"]["execution_state"] == "idle":
                            break
                finally:
                    kc.stop_channels()
            finally:
                km.shutdown_kernel()

        with docker_utils.running_container(codeserver_image.name) as container:
            exit_code, output_bytes = container.exec(
                base_image_test.encode_python_function_execution_command_interpreter(
                    "python3", start_kernel_and_execute
                )
            )

        assert exit_code == 0, f"Python script execution failed. Output: {output_bytes}"
        assert b"kernel executed ok" in output_bytes, f"Expected kernel output not found. Output: {output_bytes}"
