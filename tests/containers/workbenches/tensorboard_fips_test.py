from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from tests.containers import docker_utils

if TYPE_CHECKING:
    from tests.containers.conftest import Image


def test_tensorboard_fips_fallback(jupyterlab_image: Image) -> None:
    """Verify TensorBoard works without its non-FIPS Rust data server."""
    with docker_utils.running_container(jupyterlab_image.name, user=1001) as container:
        ecode, output = container.exec(
            [
                "/opt/app-root/bin/python3",
                "-c",
                "import tensorboard",
            ]
        )
        if ecode != 0:
            pytest.skip(f"TensorBoard is not installed in {jupyterlab_image.name}: {output.decode(errors='replace')}")

        ecode, output = container.exec(
            [
                "/opt/app-root/bin/python3",
                "-c",
                textwrap.dedent(
                    """
                    import importlib.util
                    import pathlib
                    import subprocess
                    import tempfile
                    import time
                    import urllib.request

                    data_server = pathlib.Path(
                        importlib.util.find_spec("tensorboard_data_server").origin
                    ).parent / "bin" / "server"
                    assert not data_server.exists(), f"non-FIPS TensorBoard server remains installed: {data_server}"

                    with tempfile.TemporaryDirectory() as logdir:
                        process = subprocess.Popen(
                            [
                                "/opt/app-root/bin/tensorboard",
                                "--logdir",
                                logdir,
                                "--load_fast=auto",
                                "--host",
                                "127.0.0.1",
                                "--port",
                                "6006",
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        try:
                            for _ in range(50):
                                if process.poll() is not None:
                                    stdout, stderr = process.communicate()
                                    raise RuntimeError(
                                        f"TensorBoard exited with {process.returncode}: "
                                        f"stdout={stdout.decode(errors='replace')} "
                                        f"stderr={stderr.decode(errors='replace')}"
                                    )
                                try:
                                    with urllib.request.urlopen("http://127.0.0.1:6006", timeout=1) as response:
                                        assert response.status == 200
                                        break
                                except Exception:
                                    time.sleep(0.2)
                            else:
                                raise RuntimeError("TensorBoard did not become ready")
                        finally:
                            process.terminate()
                            process.wait(timeout=5)
                    """
                ),
            ]
        )
        decoded_output = output.decode(errors="replace")
        assert ecode == 0, decoded_output
