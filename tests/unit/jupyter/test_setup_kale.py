"""Sourced setup-kale.sh configures Kale without leaking shell state."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tests import PROJECT_ROOT

_RUNTIME_MARKER = "/opt/app-root/runtimes/..data"
_BASELINE = PROJECT_ROOT / "jupyter/baseline/ubi9-python-3.12/setup-kale.sh"
_DATASCIENCE = PROJECT_ROOT / "jupyter/datascience/ubi9-python-3.12/setup-kale.sh"
_UNIVERSAL = PROJECT_ROOT / "jupyter/universal/ubi9-python-3.12/setup-kale.sh"
_SCRIPTS = (_BASELINE, _DATASCIENCE, _UNIVERSAL)
_SCRIPT_IDS = ("baseline", "datascience", "universal")


def test_setup_kale_scripts_stay_in_sync() -> None:
    baseline = _BASELINE.read_text(encoding="utf-8")
    datascience = _DATASCIENCE.read_text(encoding="utf-8")
    assert baseline == datascience
    for script in (_BASELINE, _DATASCIENCE, _UNIVERSAL):
        text = script.read_text(encoding="utf-8")
        assert "eval " not in text
        assert "shopt -u nullglob" not in text
        assert "set -Eeuxo pipefail" not in text


def test_universal_exports_bearer_without_word_splitting() -> None:
    text = _UNIVERSAL.read_text(encoding="utf-8")
    assert "printf -v KF_PIPELINES_TOKEN '%s'" in text
    assert 'KF_PIPELINES_TOKEN="' not in text


def test_configure_kale_helpers_stay_in_sync() -> None:
    baseline = PROJECT_ROOT / "jupyter/baseline/ubi9-python-3.12/utils/configure_kale_from_elyra.py"
    datascience = PROJECT_ROOT / "jupyter/datascience/ubi9-python-3.12/utils/configure_kale_from_elyra.py"
    assert baseline.read_text(encoding="utf-8") == datascience.read_text(encoding="utf-8")


def _source_setup_kale(
    script: Path,
    tmp_path: Path,
    *,
    runtime_files: dict[str, str],
    caller: str,
    python_exit: int = 0,
    python_stdout: str = "",
    python_stderr: str = "",
    preset_ssl_cert: str | None = None,
    existing_settings: str | None = None,
) -> dict[str, str]:
    runtime_dir = tmp_path / "runtimes"
    runtime_dir.mkdir()
    for name, body in runtime_files.items():
        (runtime_dir / name).write_text(body, encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "python-invoked.txt"
    stdout_payload = tmp_path / "python-stdout"
    stderr_payload = tmp_path / "python-stderr"
    bearer_file = tmp_path / "bearer"
    stdout_payload.write_text(python_stdout, encoding="utf-8")
    stderr_payload.write_text(python_stderr, encoding="utf-8")
    stub = bin_dir / "python3"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'%s\\t%s\\n\' "$ELYRA_RUNTIME_CONFIG" "$*" > "{record}"\n'
        f'cat "{stdout_payload}"\n'
        f'cat "{stderr_payload}" >&2\n'
        f"exit {python_exit}\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    home = tmp_path / "home"
    settings = home / ".jupyter/lab/user-settings/jupyterlab-kubeflow-kale/kale-settings.jupyterlab-settings"
    if existing_settings is not None:
        settings.parent.mkdir(parents=True)
        settings.write_text(existing_settings, encoding="utf-8")

    target = tmp_path / "setup-kale.sh"
    target.write_text(
        script.read_text(encoding="utf-8").replace(_RUNTIME_MARKER, runtime_dir.as_posix()),
        encoding="utf-8",
    )

    preset = ""
    if preset_ssl_cert is not None:
        preset = f'export KF_PIPELINES_SSL_SA_CERTS="{preset_ssl_cert}"\n'
    else:
        preset = "unset KF_PIPELINES_SSL_SA_CERTS\n"

    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "export LC_ALL=C\n"
        f"{caller}\n"
        f"{preset}"
        "unset KF_PIPELINES_TOKEN\n"
        f'export HOME="{home}"\n'
        f'export PATH="{bin_dir}{os.pathsep}$PATH"\n'
        f'source "{target}"\n'
        "rc=$?\n"
        "printf 'rc=%s\\n' \"$rc\"\n"
        "printf 'errexit=%s\\n' \"$([ -o errexit ] && printf 1 || printf 0)\"\n"
        "printf 'nounset=%s\\n' \"$([ -o nounset ] && printf 1 || printf 0)\"\n"
        "printf 'xtrace=%s\\n' \"$([ -o xtrace ] && printf 1 || printf 0)\"\n"
        "printf 'pipefail=%s\\n' \"$([ -o pipefail ] && printf 1 || printf 0)\"\n"
        "printf 'nullglob=%s\\n' \"$(shopt -q nullglob && printf 1 || printf 0)\"\n"
        'printf \'runtime_dir_leaked=%s\\n\' "$([ -n "${_KALE_RUNTIME_DIR+x}" ] && printf 1 || printf 0)"\n'
        'printf \'xtrace_state_leaked=%s\\n\' "$([ -n "${__kale_had_xtrace+x}" ] && printf 1 || printf 0)"\n'
        "printf 'image=%s\\n' \"${KALE_DEFAULT_BASE_IMAGE-}\"\n"
        "printf 'security=%s\\n' \"${KALE_SECURITY_CONTEXT_ENABLED-}\"\n"
        "printf 'sa_file=%s\\n' \"${KF_PIPELINES_SA_TOKEN_PATH-}\"\n"
        "printf 'ssl_cert=%s\\n' \"${KF_PIPELINES_SSL_SA_CERTS-}\"\n"
        "printf 'elyra=%s\\n' \"${ELYRA_RUNTIME_CONFIG-}\"\n"
        f'printf "settings=%s\\n" "$(cat "{settings}" 2>/dev/null || true)"\n'
        f'if [ -f "{record}" ]; then printf "python=%s\\n" "$(cat "{record}")"; fi\n'
        "set +x\n"
        f'printf \'%s\' "${{KF_PIPELINES_TOKEN-}}" > "{bearer_file}"\n'
        "if [ -n \"${KF_PIPELINES_TOKEN+x}\" ]; then printf 'bearer_set=1\\n'; "
        "else printf 'bearer_set=0\\n'; fi\n"
        'printf \'auth_leaked=%s\\n\' "$([ -n "${_kale_auth+x}" ] && printf 1 || printf 0)"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    result = subprocess.run(
        [str(wrapper)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    parsed: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            parsed[key] = value
    parsed["bearer"] = bearer_file.read_text(encoding="utf-8")
    parsed["stderr"] = result.stderr
    return parsed


@pytest.mark.parametrize("script", _SCRIPTS, ids=_SCRIPT_IDS)
def test_pipeline_json_is_preferred(script: Path, tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        script,
        tmp_path,
        runtime_files={"Pipeline.json": "{}", "a.json": "{}"},
        caller="shopt -u nullglob\nset +o xtrace\n",
    )
    runtime_dir = tmp_path / "runtimes"
    assert parsed["elyra"] == (runtime_dir / "Pipeline.json").as_posix()
    chosen, invoked = parsed["python"].split("\t", 1)
    assert chosen == parsed["elyra"]
    assert invoked.endswith("configure_kale_from_elyra.py")


@pytest.mark.parametrize("script", _SCRIPTS, ids=_SCRIPT_IDS)
def test_falls_back_to_first_runtime_json(script: Path, tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        script,
        tmp_path,
        runtime_files={"b.json": "{}", "a.json": "{}"},
        caller="shopt -u nullglob\nset +o xtrace\n",
    )
    chosen = (tmp_path / "runtimes" / "a.json").as_posix()
    assert parsed["elyra"] == chosen
    assert parsed["python"].split("\t", 1)[0] == chosen


@pytest.mark.parametrize("script", _SCRIPTS, ids=_SCRIPT_IDS)
def test_missing_runtime_still_configures_kale_defaults(script: Path, tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        script,
        tmp_path,
        runtime_files={},
        caller="shopt -u nullglob\nset +o xtrace\n",
    )
    assert "python" not in parsed
    assert parsed["image"] == "ubi9/python-312"
    assert parsed["security"] == "false"
    assert parsed["sa_file"] == "/var/run/secrets/kubernetes.io/serviceaccount/token"
    assert parsed["ssl_cert"] == "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    assert parsed["settings"] == '{"outputPath": "_kale"}'
    assert parsed["rc"] == "0"
    assert parsed["bearer_set"] == "0"
    assert parsed["bearer"] == ""
    assert parsed["auth_leaked"] == "0"


@pytest.mark.parametrize("script", _SCRIPTS, ids=_SCRIPT_IDS)
def test_helper_failure_does_not_abort_startup(script: Path, tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        script,
        tmp_path,
        runtime_files={"Pipeline.json": "{}"},
        caller="shopt -u nullglob\nset +o xtrace\nset +o errexit\n",
        python_exit=1,
    )
    assert parsed["rc"] == "0"
    assert parsed["errexit"] == "0"
    assert parsed["settings"] == '{"outputPath": "_kale"}'
    assert "python" in parsed


@pytest.mark.parametrize("script", _SCRIPTS, ids=_SCRIPT_IDS)
def test_existing_output_directory_setting_is_preserved(script: Path, tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        script,
        tmp_path,
        runtime_files={},
        caller="set +o xtrace\n",
        existing_settings='{"outputPath": "custom"}',
    )
    assert parsed["settings"] == '{"outputPath": "custom"}'


@pytest.mark.parametrize("script", _SCRIPTS, ids=_SCRIPT_IDS)
def test_preset_ssl_cert_is_preserved(script: Path, tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        script,
        tmp_path,
        runtime_files={},
        caller="set +o xtrace\n",
        preset_ssl_cert="/custom/ca.crt",
    )
    assert parsed["ssl_cert"] == "/custom/ca.crt"


@pytest.mark.parametrize(
    ("caller", "nullglob", "xtrace", "pipefail"),
    [
        ("shopt -u nullglob\nset +o xtrace\nset +o pipefail\nset +o errexit\nset +o nounset\n", "0", "0", "0"),
        ("shopt -s nullglob\nset -o xtrace\nset -o pipefail\nset +o errexit\nset +o nounset\n", "1", "1", "1"),
    ],
    ids=["caller-defaults-off", "caller-state-on"],
)
@pytest.mark.parametrize("script", _SCRIPTS, ids=_SCRIPT_IDS)
def test_caller_shell_state_is_restored(
    script: Path,
    tmp_path: Path,
    caller: str,
    nullglob: str,
    xtrace: str,
    pipefail: str,
) -> None:
    # Pipeline.json is absent so runtime discovery actually enables nullglob.
    parsed = _source_setup_kale(
        script,
        tmp_path,
        runtime_files={"a.json": "{}"},
        caller=caller,
    )
    assert parsed["nullglob"] == nullglob
    assert parsed["xtrace"] == xtrace
    assert parsed["pipefail"] == pipefail
    assert parsed["errexit"] == "0"
    assert parsed["nounset"] == "0"
    assert parsed["rc"] == "0"
    assert parsed["runtime_dir_leaked"] == "0"
    assert parsed["xtrace_state_leaked"] == "0"
    assert parsed["auth_leaked"] == "0"
    assert parsed["bearer_set"] == "0"


_RUNTIME_BEARER = "runtime-bearer-marker $*"


def test_universal_exports_runtime_bearer_without_tracing_it(tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        _UNIVERSAL,
        tmp_path,
        runtime_files={"Pipeline.json": "{}"},
        caller="shopt -s nullglob\nset -o xtrace\nset +o errexit\nset +o nounset\n",
        python_stdout=_RUNTIME_BEARER,
        python_stderr="kale-helper-status\n",
    )
    assert parsed["bearer"] == _RUNTIME_BEARER
    assert parsed["bearer_set"] == "1"
    assert parsed["auth_leaked"] == "0"
    assert parsed["xtrace"] == "1"
    assert parsed["nullglob"] == "1"
    assert parsed["rc"] == "0"
    assert parsed["settings"] == '{"outputPath": "_kale"}'
    assert _RUNTIME_BEARER not in parsed["stderr"]
    assert "kale-helper-status" in parsed["stderr"]


def test_universal_ignores_helper_stderr_when_stdout_is_empty(tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        _UNIVERSAL,
        tmp_path,
        runtime_files={"Pipeline.json": "{}"},
        caller="set -o xtrace\n",
        python_stderr="kale-helper-status\n",
        python_exit=1,
    )
    assert parsed["rc"] == "0"
    assert parsed["bearer_set"] == "0"
    assert parsed["bearer"] == ""
    assert parsed["errexit"] == "0"
    assert parsed["settings"] == '{"outputPath": "_kale"}'
    assert "kale-helper-status" in parsed["stderr"]


def test_universal_keeps_bearer_when_helper_exits_nonzero(tmp_path: Path) -> None:
    parsed = _source_setup_kale(
        _UNIVERSAL,
        tmp_path,
        runtime_files={"a.json": "{}"},
        caller="shopt -u nullglob\nset +o xtrace\n",
        python_stdout=_RUNTIME_BEARER,
        python_exit=1,
    )
    assert parsed["rc"] == "0"
    assert parsed["bearer"] == _RUNTIME_BEARER
    assert parsed["bearer_set"] == "1"
    assert parsed["elyra"].endswith("/a.json")
    assert parsed["nullglob"] == "0"
    assert parsed["xtrace"] == "0"
    assert parsed["auth_leaked"] == "0"
    assert _RUNTIME_BEARER not in parsed["stderr"]
