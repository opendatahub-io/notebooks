from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from tests.containers import docker_utils

if TYPE_CHECKING:
    from tests.containers.conftest import Image

# Printed by TensorBoard only after the Rust data server actually starts.
_FAST_LOADER_MARK = "Using experimental fast data loading logic"

_CHECK = textwrap.dedent(
    f"""\
    import importlib.util
    import pathlib
    import subprocess
    import tempfile
    import time
    import urllib.error
    import urllib.request

    if importlib.util.find_spec("tensorboard") is None:
        print("TENSORBOARD_ABSENT")
        raise SystemExit(0)

    data_server_spec = importlib.util.find_spec("tensorboard_data_server")
    if data_server_spec is None or data_server_spec.origin is None:
        raise SystemExit("tensorboard is installed but tensorboard_data_server is missing")
    data_server = pathlib.Path(data_server_spec.origin).parent / "bin" / "server"
    if data_server.exists():
        raise SystemExit(f"non-FIPS TensorBoard server remains installed: {{data_server}}")

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
        ready = False
        try:
            for _ in range(50):
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    raise SystemExit(
                        "TensorBoard exited with "
                        f"{{process.returncode}}: stdout={{stdout.decode(errors='replace')}} "
                        f"stderr={{stderr.decode(errors='replace')}}"
                    )
                try:
                    with urllib.request.urlopen("http://127.0.0.1:6006", timeout=1) as response:
                        if response.status != 200:
                            raise RuntimeError(f"unexpected status {{response.status}}")
                        ready = True
                        break
                except (OSError, TimeoutError, urllib.error.URLError, RuntimeError):
                    time.sleep(0.2)
            if not ready:
                raise SystemExit("TensorBoard did not become ready")
        finally:
            if process.poll() is None:
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
            else:
                stdout, stderr = process.communicate()
        decoded_stderr = stderr.decode(errors="replace")
        if "{_FAST_LOADER_MARK}" in decoded_stderr:
            raise SystemExit(
                "TensorBoard used the Rust data server instead of the Python fallback: "
                f"{{decoded_stderr}}"
            )
        if "TensorBoard" not in decoded_stderr:
            raise SystemExit(
                "TensorBoard did not report that it was listening: "
                f"stdout={{stdout.decode(errors='replace')}} stderr={{decoded_stderr}}"
            )
    print("TENSORBOARD_FIPS_FALLBACK_OK")
    """
)


def _assert_tensorboard_fips_fallback(image: Image) -> None:
    with docker_utils.running_container(image.name, user=1001) as container:
        exit_code, output_bytes = container.exec(["/opt/app-root/bin/python3", "-c", _CHECK])
    output = output_bytes.decode(errors="replace")
    if "TENSORBOARD_ABSENT" in output:
        pytest.skip(f"TensorBoard is not installed in {image.name}")
    assert exit_code == 0, output
    assert "TENSORBOARD_FIPS_FALLBACK_OK" in output


def test_tensorboard_fips_fallback_workbench(jupyterlab_image: Image) -> None:
    """Workbench images keep TensorBoard on the Python loader after the Rust server is removed."""
    _assert_tensorboard_fips_fallback(jupyterlab_image)


def test_tensorboard_fips_fallback_runtime(runtime_image: Image) -> None:
    """Runtime images keep TensorBoard on the Python loader after the Rust server is removed."""
    _assert_tensorboard_fips_fallback(runtime_image)
