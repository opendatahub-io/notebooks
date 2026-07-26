from __future__ import annotations

import copy
import json

import pytest
import yaml
from pydantic import ValidationError

from ci.versions_config_schema import (
    ACC_VERSION_PATTERN,
    PYTHON_VERSION_PATTERN,
    RHDS_FAST_CPU_VERSION_PATTERN,
    RHDS_OS_BASE_PATTERN,
    SEMVER_PATTERN,
    VersionsConfig,
    build_json_schema,
)
from tests import PROJECT_ROOT

_GPU_FLAVOR = {
    "acc_version": "13.0",
    "rhds": {"channel": "fast"},
    "odh": {"origin": "in-house"},
}


def _minimal_valid_config() -> dict:
    return {
        "schema_version": 1,
        "release": {
            "full_version": "3.5.0",
            "rhds_os_base": "el9.6",
            "python_version": "3.12",
        },
        "artifacts": {
            "base_image": {
                "cpu": {
                    "rhds": {"channel": "fast", "version": "3.5.0"},
                    "odh": {"origin": "in-house", "version": "latest"},
                },
                "cuda": {
                    "minimal": copy.deepcopy(_GPU_FLAVOR),
                },
                "rocm": {
                    "minimal": {
                        "acc_version": "7.14",
                        "rhds": {"channel": "fast"},
                        "odh": {"origin": "in-house"},
                    },
                },
            }
        },
    }


def test_repo_versions_config_validates() -> None:
    data = yaml.safe_load((PROJECT_ROOT / "versions_config.yml").read_text(encoding="utf-8"))
    config = VersionsConfig.model_validate(data)
    assert config.schema_version == 1
    assert config.release.full_version == "3.5.0"
    assert config.artifacts.base_image.cuda["minimal"].acc_version == "13.0"
    assert "pytorch-llmcompressor" in config.artifacts.base_image.cuda


def test_rejects_unexpected_top_level_key() -> None:
    data = _minimal_valid_config()
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        VersionsConfig.model_validate(data)


def test_rejects_unknown_cpu_distribution_key() -> None:
    data = _minimal_valid_config()
    data["artifacts"]["base_image"]["cpu"]["extra"] = {"channel": "fast", "version": "3.5.0"}
    with pytest.raises(ValidationError):
        VersionsConfig.model_validate(data)


def test_rejects_cpu_odh_non_latest_version() -> None:
    data = _minimal_valid_config()
    data["artifacts"]["base_image"]["cpu"]["odh"]["version"] = "3.5.0"
    with pytest.raises(ValidationError):
        VersionsConfig.model_validate(data)


def test_accepts_experimental_cuda_flavor_key() -> None:
    data = _minimal_valid_config()
    data["artifacts"]["base_image"]["cuda"]["my-experimental-flavor"] = copy.deepcopy(_GPU_FLAVOR)
    data["artifacts"]["base_image"]["cuda"]["pytorch+llmcompressor"] = copy.deepcopy(_GPU_FLAVOR)
    config = VersionsConfig.model_validate(data)
    assert "my-experimental-flavor" in config.artifacts.base_image.cuda
    assert "pytorch+llmcompressor" in config.artifacts.base_image.cuda


def test_rejects_rhds_os_base_without_el_prefix() -> None:
    data = _minimal_valid_config()
    data["release"]["rhds_os_base"] = "9.6"
    with pytest.raises(ValidationError) as exc_info:
        VersionsConfig.model_validate(data)
    assert any(err["type"] == "string_pattern_mismatch" for err in exc_info.value.errors())


def test_rejects_nested_gpu_acc_version() -> None:
    data = _minimal_valid_config()
    data["artifacts"]["base_image"]["cuda"]["minimal"]["odh"]["acc_version"] = "13.0"
    with pytest.raises(ValidationError) as exc_info:
        VersionsConfig.model_validate(data)
    assert any(err["type"] == "extra_forbidden" for err in exc_info.value.errors())


def test_json_schema_includes_string_patterns() -> None:
    schema = build_json_schema()
    release = schema["$defs"]["Release"]["properties"]
    assert release["full_version"]["pattern"] == SEMVER_PATTERN
    assert release["rhds_os_base"]["pattern"] == RHDS_OS_BASE_PATTERN
    assert release["python_version"]["pattern"] == PYTHON_VERSION_PATTERN
    assert schema["$defs"]["GpuFlavor"]["properties"]["acc_version"]["pattern"] == ACC_VERSION_PATTERN
    assert schema["$defs"]["RhdsFastCpuPolicy"]["properties"]["version"]["pattern"] == RHDS_FAST_CPU_VERSION_PATTERN


def test_committed_json_schema_matches_generator() -> None:
    committed = json.loads((PROJECT_ROOT / "ci" / "versions_config.schema.json").read_text(encoding="utf-8"))
    assert committed == build_json_schema()
    assert committed["$id"] == "versions_config.schema.json"
    assert committed["examples"]
