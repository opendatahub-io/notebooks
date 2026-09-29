from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import allure
import pytest

from tests import PROJECT_ROOT


@pytest.mark.parametrize("image", ["baseline", "datascience"])
@allure.issue("RHOAIENG-82538")
def test_kale_frontend_requires_configured_kfp_host(image: str, tmp_path: Path) -> None:
    script = PROJECT_ROOT / f"jupyter/{image}/ubi9-python-3.12/setup-kale.sh"
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    jupyter = binary_dir / "jupyter"
    jupyter.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$KALE_CALLS"\n')
    jupyter.chmod(0o755)

    config_path = tmp_path / ".config/kale/kfp_server_config.json"
    calls = tmp_path / "calls"
    env = os.environ.copy()
    env.update(
        HOME=str(tmp_path),
        PATH=f"{binary_dir}:{env['PATH']}",
        KALE_CALLS=str(calls),
        KALE_SCRIPT=str(script),
    )
    env.pop("KALE_CONFIG_PATH", None)

    def run_setup(expected_action: str) -> None:
        result = subprocess.run(
            ["bash", "-c", 'source "$KALE_SCRIPT"'],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert calls.read_text().splitlines()[-1] == (
            f"labextension {expected_action} --level=user jupyterlab-kubeflow-kale"
        )

    run_setup("disable")
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"host": "https://pipelines.example.test"}))
    run_setup("enable")
    assert json.loads(
        (tmp_path / ".jupyter/lab/user-settings/jupyterlab-kubeflow-kale/kale-settings.jupyterlab-settings").read_text()
    ) == {"outputPath": "_kale"}

    env["KALE_CONFIG_PATH"] = str(tmp_path / "standalone.json")
    run_setup("disable")
    Path(env["KALE_CONFIG_PATH"]).write_text(json.dumps({"host": "https://standalone.example.test"}))
    run_setup("enable")
    Path(env["KALE_CONFIG_PATH"]).write_text("{invalid json")
    run_setup("disable")
    Path(env["KALE_CONFIG_PATH"]).write_text(json.dumps({"host": "  "}))
    run_setup("disable")


@pytest.mark.parametrize("image", ["baseline", "datascience"])
@allure.issue("RHOAIENG-82538")
def test_kale_disables_stale_elyra_config_after_runtime_removed(image: str, tmp_path: Path) -> None:
    original = PROJECT_ROOT / f"jupyter/{image}/ubi9-python-3.12/setup-kale.sh"
    runtime_dir = tmp_path / "runtimes"
    script = tmp_path / "setup-kale.sh"
    script.write_text(original.read_text().replace("/opt/app-root/runtimes/", f"{runtime_dir}/"))

    bridge = tmp_path / "configure_kale_from_elyra.py"
    bridge.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "if os.environ.get('KALE_TEST_BRIDGE_FAILURE'):\n"
        "    raise SystemExit(1)\n"
        "Path(os.environ['KALE_CONFIG_PATH']).write_text(os.environ['KALE_TEST_CONFIG'])\n"
    )
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    jupyter = binary_dir / "jupyter"
    jupyter.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$KALE_CALLS"\n')
    jupyter.chmod(0o755)

    config_path = tmp_path / ".config/kale/kfp_server_config.json"
    config_path.parent.mkdir(parents=True)
    calls = tmp_path / "calls"
    env = os.environ.copy()
    env.update(
        HOME=str(tmp_path),
        PATH=f"{binary_dir}:{env['PATH']}",
        KALE_CONFIG_PATH=str(config_path),
        KALE_CALLS=str(calls),
        KALE_TEST_CONFIG=json.dumps({"host": "https://pipelines.example.test"}),
        KALE_SCRIPT=str(script),
    )

    def run_setup(expected_action: str) -> None:
        result = subprocess.run(
            ["bash", "-c", 'source "$KALE_SCRIPT"'],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert calls.read_text().splitlines()[-1] == (
            f"labextension {expected_action} --level=user jupyterlab-kubeflow-kale"
        )

    (runtime_dir / "..data").mkdir(parents=True)
    (runtime_dir / "..data/Pipeline.json").write_text("{}")
    run_setup("enable")
    generated_config = config_path.read_bytes()
    marker = Path(f"{config_path}.elyra-sha256")
    assert marker.read_text() == hashlib.sha256(generated_config).hexdigest()

    env["KALE_TEST_BRIDGE_FAILURE"] = "1"
    run_setup("disable")
    env.pop("KALE_TEST_BRIDGE_FAILURE")

    shutil.rmtree(runtime_dir)
    run_setup("disable")
    assert config_path.read_bytes() == generated_config

    standalone_path = tmp_path / "standalone.json"
    standalone_path.write_text(json.dumps({"host": "https://standalone.example.test"}))
    env["KALE_CONFIG_PATH"] = str(standalone_path)
    run_setup("enable")

    env["KALE_CONFIG_PATH"] = str(config_path)
    config_path.write_text(json.dumps({"host": "https://independent.example.test"}))
    run_setup("enable")

    config_path.write_bytes(generated_config)
    (runtime_dir / "..data").mkdir(parents=True)
    (runtime_dir / "..data/Pipeline.json").write_text("{}")
    run_setup("enable")
    shutil.rmtree(runtime_dir)
    run_setup("disable")
