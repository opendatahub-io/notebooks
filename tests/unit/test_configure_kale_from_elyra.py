"""Unit tests for configure_kale_from_elyra.py - Elyra to Kale config transformation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Import the module under test
_REPO_ROOT = Path(__file__).resolve().parents[2]
_UTILS_PATH = _REPO_ROOT / "jupyter/datascience/ubi9-python-3.12/utils"
if str(_UTILS_PATH) not in sys.path:
    sys.path.insert(0, str(_UTILS_PATH))

import configure_kale_from_elyra as kale_config  # noqa: E402  # pyright: ignore[reportMissingImports]


def write_elyra_config(tmp_path: Path, metadata: dict) -> Path:
    """Helper to create Elyra runtime config JSON file."""
    config_file = tmp_path / "Pipeline.json"
    config_data = {"metadata": metadata}
    config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    return config_file


@pytest.fixture
def mock_kale_module(monkeypatch: pytest.MonkeyPatch):
    """
    Fixture to mock the kale.config module.

    Returns a dict containing saved_config that gets populated by save_config calls.
    """
    saved = {"config": None}

    def mock_save_config(config):
        saved["config"] = config

    # Create mock modules
    mock_kfp_server_config = MagicMock()
    mock_kfp_server_config.save_config = mock_save_config

    mock_kale_config = MagicMock()
    mock_kale_config.kfp_server_config = mock_kfp_server_config

    # Install mocks in sys.modules
    sys.modules["kale"] = MagicMock()
    sys.modules["kale.config"] = mock_kale_config

    # Suppress print output
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    yield saved

    # Cleanup
    if "kale" in sys.modules:
        del sys.modules["kale"]
    if "kale.config" in sys.modules:
        del sys.modules["kale.config"]


def assert_config_matches(actual: dict | None, expected: dict | None, test_name: str) -> None:
    """
    Custom assertion that prints formatted JSON diff on failure.

    Args:
        actual: The actual Kale config produced
        expected: The expected Kale config
        test_name: Name of the test for error messages
    """
    if actual != expected:
        actual_json = json.dumps(actual, indent=2, sort_keys=True) if actual else "None"
        expected_json = json.dumps(expected, indent=2, sort_keys=True) if expected else "None"

        error_msg = (
            f"\n{'=' * 80}\n"
            f"Test: {test_name}\n"
            f"{'=' * 80}\n\n"
            f"EXPECTED OUTPUT:\n"
            f"{expected_json}\n\n"
            f"ACTUAL OUTPUT:\n"
            f"{actual_json}\n"
            f"{'=' * 80}\n"
        )
        pytest.fail(error_msg)


# =============================================================================
# Auth Type Tests (Parametrized)
# =============================================================================

AUTH_TEST_CASES = [
    {
        "test_name": "kubernetes_service_account_token_auth",
        "description": "KUBERNETES_SERVICE_ACCOUNT_TOKEN auth type transformation",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "KUBERNETES_SERVICE_ACCOUNT_TOKEN",
        },
        "expected_output": {
            "host": "http://ml-pipeline:8080",
            "namespace": "test-namespace",
            "auth_type": "kubernetes_service_account_token",
            "auth_config": {
                "token_path": "/var/run/secrets/kubernetes.io/serviceaccount/token"
            },
            "ssl_ca_cert": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        },
        "expected_success": True,
        "mock_paths_exist": True,
    },
    {
        "test_name": "no_authentication_auth_type",
        "description": "NO_AUTHENTICATION auth type transformation",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "NO_AUTHENTICATION",
        },
        "expected_output": {
            "host": "http://ml-pipeline:8080",
            "namespace": "test-namespace",
            "auth_type": None,
            "auth_config": {},
            "ssl_ca_cert": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        },
        "expected_success": True,
        "mock_paths_exist": True,
    },
    {
        "test_name": "existing_bearer_token_with_password",
        "description": "EXISTING_BEARER_TOKEN auth type with api_password",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "EXISTING_BEARER_TOKEN",
            "api_password": "secret-token",
        },
        "expected_output": {
            "host": "http://ml-pipeline:8080",
            "namespace": "test-namespace",
            "auth_type": "existing_bearer_token",
            "auth_config": {"env_var": "KF_PIPELINES_TOKEN"},
            "ssl_ca_cert": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        },
        "expected_success": True,
        "mock_paths_exist": True,
        "verify_env_var": ("KF_PIPELINES_TOKEN", "secret-token"),
        "verify_token_not_in_config": "secret-token",
    },
    {
        "test_name": "existing_bearer_token_without_password",
        "description": "EXISTING_BEARER_TOKEN auth type without api_password",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "EXISTING_BEARER_TOKEN",
        },
        "expected_output": {
            "host": "http://ml-pipeline:8080",
            "namespace": "test-namespace",
            "auth_type": "existing_bearer_token",
            "auth_config": {},
            "ssl_ca_cert": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        },
        "expected_success": True,
        "mock_paths_exist": True,
    },
    {
        "test_name": "missing_auth_type_defaults_to_kubernetes_sa_token",
        "description": "Missing auth_type defaults to KUBERNETES_SERVICE_ACCOUNT_TOKEN",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
        },
        "expected_output": {
            "host": "http://ml-pipeline:8080",
            "namespace": "test-namespace",
            "auth_type": "kubernetes_service_account_token",
            "auth_config": {
                "token_path": "/var/run/secrets/kubernetes.io/serviceaccount/token"
            },
            "ssl_ca_cert": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        },
        "expected_success": True,
        "mock_paths_exist": True,
    },
    {
        "test_name": "unknown_auth_type",
        "description": "Unknown/unsupported auth type results in no auth_type/auth_config",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "CUSTOM_UNKNOWN_AUTH",
        },
        "expected_output": {
            "host": "http://ml-pipeline:8080",
            "namespace": "test-namespace",
            "ssl_ca_cert": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        },
        "expected_success": True,
        "mock_paths_exist": True,
    },
]


@pytest.mark.parametrize("test_case", AUTH_TEST_CASES, ids=lambda tc: tc["test_name"])
def test_auth_transformation(
    test_case: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Parametrized test for authentication type transformations."""
    # Print test case for visibility
    print(f"\n{'=' * 80}")
    print(f"Test: {test_case['test_name']}")
    print(f"Description: {test_case['description']}")
    print(f"\nInput Elyra Config:")
    print(json.dumps(test_case['elyra_input'], indent=2))
    print(f"\nExpected Kale Config:")
    print(json.dumps(test_case['expected_output'], indent=2))
    print(f"{'=' * 80}\n")

    # Write Elyra config file
    elyra_config = write_elyra_config(tmp_path, test_case["elyra_input"])

    # Mock file existence if specified
    if test_case.get("mock_paths_exist"):
        monkeypatch.setattr("os.path.exists", lambda path: True)

    # Run the function
    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    # Verify return value
    assert result == test_case["expected_success"], (
        f"Expected success={test_case['expected_success']}, got {result}"
    )

    # Verify config output
    assert_config_matches(
        mock_kale_module["config"],
        test_case.get("expected_output"),
        test_case["test_name"],
    )

    # Additional verifications
    if "verify_env_var" in test_case:
        env_var, expected_value = test_case["verify_env_var"]
        assert os.environ.get(env_var) == expected_value, (
            f"Expected env var {env_var}={expected_value}, got {os.environ.get(env_var)}"
        )

    if "verify_token_not_in_config" in test_case:
        token = test_case["verify_token_not_in_config"]
        config_str = json.dumps(mock_kale_module["config"])
        assert token not in config_str, (
            f"Sensitive token '{token}' should not be stored in config"
        )


# =============================================================================
# DEX Auth Tests (Not Supported)
# =============================================================================

DEX_TEST_CASES = [
    {
        "test_name": "dex_static_passwords_with_credentials",
        "description": "DEX_STATIC_PASSWORDS auth type is not supported",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "DEX_STATIC_PASSWORDS",
            "api_username": "admin",
            "api_password": "password123",
        },
        "expected_output": None,
        "expected_success": False,
    },
    {
        "test_name": "dex_ldap_not_supported",
        "description": "DEX_LDAP auth type is not supported",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "DEX_LDAP",
            "api_username": "user",
            "api_password": "pass",
        },
        "expected_output": None,
        "expected_success": False,
    },
    {
        "test_name": "dex_legacy_not_supported",
        "description": "DEX_LEGACY auth type is not supported",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "DEX_LEGACY",
            "api_username": "user",
            "api_password": "pass",
        },
        "expected_output": None,
        "expected_success": False,
    },
    {
        "test_name": "dex_without_credentials",
        "description": "DEX auth type without credentials is not supported",
        "elyra_input": {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "DEX_STATIC_PASSWORDS",
        },
        "expected_output": None,
        "expected_success": False,
    },
]


@pytest.mark.parametrize("test_case", DEX_TEST_CASES, ids=lambda tc: tc["test_name"])
def test_dex_auth_not_supported(
    test_case: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Parametrized test for DEX authentication (not supported)."""
    # Print test case for visibility
    print(f"\n{'=' * 80}")
    print(f"Test: {test_case['test_name']}")
    print(f"Description: {test_case['description']}")
    print(f"\nInput Elyra Config:")
    print(json.dumps(test_case['elyra_input'], indent=2))
    print(f"\nExpected: Returns False, no config saved")
    print(f"{'=' * 80}\n")

    # Write Elyra config file
    elyra_config = write_elyra_config(tmp_path, test_case["elyra_input"])

    # Mock file existence
    monkeypatch.setattr("os.path.exists", lambda path: True)

    # Run the function
    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    # DEX auth should fail
    assert result is False, f"{test_case['test_name']}: DEX auth should not be supported"
    assert mock_kale_module["config"] is None, "No config should be saved for DEX auth"


# =============================================================================
# Field Mapping Tests
# =============================================================================


def test_namespace_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test user_namespace field mapping to namespace."""
    elyra_input = {
        "api_endpoint": "http://ml-pipeline:8080",
        "user_namespace": "my-custom-namespace",
        "auth_type": "NO_AUTHENTICATION",
    }
    expected_output = {
        "host": "http://ml-pipeline:8080",
        "namespace": "my-custom-namespace",
        "auth_type": None,
        "auth_config": {},
    }

    elyra_config = write_elyra_config(tmp_path, elyra_input)
    monkeypatch.setattr("os.path.exists", lambda path: False)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert_config_matches(mock_kale_module["config"], expected_output, "namespace_mapping")


def test_namespace_optional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test namespace field is optional."""
    elyra_input = {
        "api_endpoint": "http://ml-pipeline:8080",
        "auth_type": "NO_AUTHENTICATION",
    }
    expected_output = {
        "host": "http://ml-pipeline:8080",
        "auth_type": None,
        "auth_config": {},
    }

    elyra_config = write_elyra_config(tmp_path, elyra_input)
    monkeypatch.setattr("os.path.exists", lambda path: False)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert_config_matches(mock_kale_module["config"], expected_output, "namespace_optional")


def test_ssl_cert_from_environment_variable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test SSL certificate path from KF_PIPELINES_SSL_SA_CERTS env var."""
    # Create a mock cert file
    cert_file = tmp_path / "ca.crt"
    cert_file.write_text("FAKE CERT", encoding="utf-8")

    elyra_input = {
        "api_endpoint": "http://ml-pipeline:8080",
        "auth_type": "NO_AUTHENTICATION",
    }
    expected_output = {
        "host": "http://ml-pipeline:8080",
        "auth_type": None,
        "auth_config": {},
        "ssl_ca_cert": str(cert_file),
    }

    def mock_exists(path):
        return path == str(cert_file)

    monkeypatch.setenv("KF_PIPELINES_SSL_SA_CERTS", str(cert_file))
    monkeypatch.setattr("os.path.exists", mock_exists)

    elyra_config = write_elyra_config(tmp_path, elyra_input)
    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert_config_matches(
        mock_kale_module["config"],
        expected_output,
        "ssl_cert_from_environment_variable",
    )


def test_ssl_cert_default_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test SSL certificate uses default path when env var not set."""
    elyra_input = {
        "api_endpoint": "http://ml-pipeline:8080",
        "auth_type": "NO_AUTHENTICATION",
    }
    expected_output = {
        "host": "http://ml-pipeline:8080",
        "auth_type": None,
        "auth_config": {},
        "ssl_ca_cert": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
    }

    def mock_exists(path):
        return path == "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    monkeypatch.setattr("os.path.exists", mock_exists)

    elyra_config = write_elyra_config(tmp_path, elyra_input)
    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert_config_matches(mock_kale_module["config"], expected_output, "ssl_cert_default_path")


def test_ssl_cert_omitted_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test SSL certificate is omitted when cert file doesn't exist."""
    elyra_input = {
        "api_endpoint": "http://ml-pipeline:8080",
        "auth_type": "NO_AUTHENTICATION",
    }
    expected_output = {
        "host": "http://ml-pipeline:8080",
        "auth_type": None,
        "auth_config": {},
    }

    monkeypatch.setattr("os.path.exists", lambda path: False)

    elyra_config = write_elyra_config(tmp_path, elyra_input)
    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert_config_matches(
        mock_kale_module["config"],
        expected_output,
        "ssl_cert_omitted_when_file_missing",
    )


# =============================================================================
# Edge Case Tests
# =============================================================================


def test_missing_api_endpoint(
    tmp_path: Path,
    mock_kale_module,
) -> None:
    """Test missing api_endpoint (required field) returns False."""
    elyra_input = {
        "user_namespace": "test-namespace",
        "auth_type": "NO_AUTHENTICATION",
    }

    elyra_config = write_elyra_config(tmp_path, elyra_input)
    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is False
    assert mock_kale_module["config"] is None


def test_empty_api_endpoint(
    tmp_path: Path,
    mock_kale_module,
) -> None:
    """Test empty api_endpoint returns False."""
    elyra_input = {
        "api_endpoint": "",
        "user_namespace": "test-namespace",
        "auth_type": "NO_AUTHENTICATION",
    }

    elyra_config = write_elyra_config(tmp_path, elyra_input)
    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is False
    assert mock_kale_module["config"] is None


def test_missing_config_file_path() -> None:
    """Test None config path returns False."""
    result = kale_config.configure_kale_from_elyra(None)
    assert result is False


def test_non_existent_config_file(tmp_path: Path) -> None:
    """Test non-existent config file handles exception gracefully."""
    non_existent = str(tmp_path / "does_not_exist.json")
    result = kale_config.configure_kale_from_elyra(non_existent)
    assert result is False


def test_malformed_json_in_config_file(tmp_path: Path) -> None:
    """Test malformed JSON handles exception gracefully."""
    config_file = tmp_path / "bad.json"
    config_file.write_text("{ this is not valid json }", encoding="utf-8")

    result = kale_config.configure_kale_from_elyra(str(config_file))
    assert result is False


def test_successful_return_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test function returns True on successful config save."""
    elyra_input = {
        "api_endpoint": "http://ml-pipeline:8080",
        "user_namespace": "test-namespace",
        "auth_type": "KUBERNETES_SERVICE_ACCOUNT_TOKEN",
    }
    expected_output = {
        "host": "http://ml-pipeline:8080",
        "namespace": "test-namespace",
        "auth_type": "kubernetes_service_account_token",
        "auth_config": {
            "token_path": "/var/run/secrets/kubernetes.io/serviceaccount/token"
        },
        "ssl_ca_cert": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
    }

    elyra_config = write_elyra_config(tmp_path, elyra_input)
    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert_config_matches(mock_kale_module["config"], expected_output, "successful_return_value")
