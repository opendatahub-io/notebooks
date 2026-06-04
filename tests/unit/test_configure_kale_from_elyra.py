"""Unit tests for configure_kale_from_elyra.py - Elyra to Kale config transformation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Import the module under test
_REPO_ROOT = Path(__file__).resolve().parents[2]
_UTILS_PATH = _REPO_ROOT / "jupyter/datascience/ubi9-python-3.12/utils"
if str(_UTILS_PATH) not in sys.path:
    sys.path.insert(0, str(_UTILS_PATH))

import configure_kale_from_elyra as kale_config


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


# =============================================================================
# Auth Type Tests
# =============================================================================


def test_kubernetes_service_account_token_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test KUBERNETES_SERVICE_ACCOUNT_TOKEN auth type transformation."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "KUBERNETES_SERVICE_ACCOUNT_TOKEN",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["host"] == "http://ml-pipeline:8080"
    assert mock_kale_module["config"]["namespace"] == "test-namespace"
    assert mock_kale_module["config"]["auth_type"] == "kubernetes_service_account_token"
    assert mock_kale_module["config"]["auth_config"]["token_path"] == (
        "/var/run/secrets/kubernetes.io/serviceaccount/token"
    )
    assert mock_kale_module["config"]["ssl_ca_cert"] == (
        "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    )


def test_no_authentication_auth_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test NO_AUTHENTICATION auth type transformation."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "NO_AUTHENTICATION",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["host"] == "http://ml-pipeline:8080"
    assert mock_kale_module["config"]["namespace"] == "test-namespace"
    assert mock_kale_module["config"]["auth_type"] is None
    assert mock_kale_module["config"]["auth_config"] == {}


def test_existing_bearer_token_with_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test EXISTING_BEARER_TOKEN auth type with api_password."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "EXISTING_BEARER_TOKEN",
            "api_password": "secret-token",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["auth_type"] == "existing_bearer_token"
    assert mock_kale_module["config"]["auth_config"]["env_var"] == "KF_PIPELINES_TOKEN"
    # Verify the actual token value is NOT stored in the config
    config_str = json.dumps(mock_kale_module["config"])
    assert "secret-token" not in config_str, "Sensitive token should not be stored in config"


def test_existing_bearer_token_without_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test EXISTING_BEARER_TOKEN auth type without api_password."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "EXISTING_BEARER_TOKEN",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["auth_type"] == "existing_bearer_token"
    assert mock_kale_module["config"]["auth_config"] == {}


def test_dex_static_passwords_with_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test DEX_STATIC_PASSWORDS auth type with credentials."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "DEX_STATIC_PASSWORDS",
            "api_username": "admin",
            "api_password": "password123",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["auth_type"] == "dex"
    assert mock_kale_module["config"]["auth_config"]["env_var_username"] == "KF_PIPELINES_USERNAME"
    assert mock_kale_module["config"]["auth_config"]["env_var_password"] == "KF_PIPELINES_PASSWORD"
    # Verify the actual credentials are NOT stored in the config
    config_str = json.dumps(mock_kale_module["config"])
    assert "admin" not in config_str, "Sensitive username should not be stored in config"
    assert "password123" not in config_str, "Sensitive password should not be stored in config"


def test_dex_ldap_and_legacy_auth_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test DEX_LDAP and DEX_LEGACY map to same Kale auth_type."""
    for dex_type in ["DEX_LDAP", "DEX_LEGACY"]:
        # Create separate directory for each iteration to ensure isolation
        test_dir = tmp_path / dex_type.lower()
        test_dir.mkdir()

        elyra_config = write_elyra_config(
            test_dir,
            {
                "api_endpoint": "http://ml-pipeline:8080",
                "user_namespace": "test-namespace",
                "auth_type": dex_type,
                "api_username": "user",
                "api_password": "pass",
            },
        )

        monkeypatch.setattr("os.path.exists", lambda path: True)

        result = kale_config.configure_kale_from_elyra(str(elyra_config))

        assert result is True
        assert mock_kale_module["config"] is not None
        assert mock_kale_module["config"]["auth_type"] == "dex"
        assert "env_var_username" in mock_kale_module["config"]["auth_config"]
        assert "env_var_password" in mock_kale_module["config"]["auth_config"]


def test_dex_without_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test DEX auth type without credentials."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "DEX_STATIC_PASSWORDS",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["auth_type"] == "dex"
    assert mock_kale_module["config"]["auth_config"] == {}


def test_missing_auth_type_defaults_to_kubernetes_sa_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test missing auth_type defaults to KUBERNETES_SERVICE_ACCOUNT_TOKEN."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["auth_type"] == "kubernetes_service_account_token"
    assert mock_kale_module["config"]["auth_config"]["token_path"] == (
        "/var/run/secrets/kubernetes.io/serviceaccount/token"
    )


def test_unknown_auth_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test unknown/unsupported auth type results in no auth_type/auth_config."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "CUSTOM_UNKNOWN_AUTH",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["host"] == "http://ml-pipeline:8080"
    assert mock_kale_module["config"]["namespace"] == "test-namespace"
    # Unknown auth types are not handled, so auth_type and auth_config are not set
    assert "auth_type" not in mock_kale_module["config"]
    assert "auth_config" not in mock_kale_module["config"]


# =============================================================================
# Field Mapping Tests
# =============================================================================


def test_namespace_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test user_namespace field mapping to namespace."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "my-custom-namespace",
            "auth_type": "NO_AUTHENTICATION",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: False)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["namespace"] == "my-custom-namespace"


def test_namespace_optional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test namespace field is optional."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "auth_type": "NO_AUTHENTICATION",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: False)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert "namespace" not in mock_kale_module["config"]


def test_ssl_cert_from_environment_variable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test SSL certificate path from KF_PIPELINES_SSL_SA_CERTS env var."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "auth_type": "NO_AUTHENTICATION",
        },
    )

    # Create a mock cert file
    cert_file = tmp_path / "ca.crt"
    cert_file.write_text("FAKE CERT", encoding="utf-8")

    def mock_exists(path):
        return path == str(cert_file)

    monkeypatch.setenv("KF_PIPELINES_SSL_SA_CERTS", str(cert_file))
    monkeypatch.setattr("os.path.exists", mock_exists)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert mock_kale_module["config"]["ssl_ca_cert"] == str(cert_file)


def test_ssl_cert_default_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test SSL certificate uses default path when env var not set."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "auth_type": "NO_AUTHENTICATION",
        },
    )

    def mock_exists(path):
        return path == "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    monkeypatch.setattr("os.path.exists", mock_exists)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert (
        mock_kale_module["config"]["ssl_ca_cert"]
        == "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    )


def test_ssl_cert_omitted_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_kale_module,
) -> None:
    """Test SSL certificate is omitted when cert file doesn't exist."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "auth_type": "NO_AUTHENTICATION",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: False)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
    assert "ssl_ca_cert" not in mock_kale_module["config"]


# =============================================================================
# Edge Case Tests
# =============================================================================


def test_missing_api_endpoint(
    tmp_path: Path,
    mock_kale_module,
) -> None:
    """Test missing api_endpoint (required field) returns False."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "user_namespace": "test-namespace",
            "auth_type": "NO_AUTHENTICATION",
        },
    )

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is False
    assert mock_kale_module["config"] is None


def test_empty_api_endpoint(
    tmp_path: Path,
    mock_kale_module,
) -> None:
    """Test empty api_endpoint returns False."""
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "",
            "user_namespace": "test-namespace",
            "auth_type": "NO_AUTHENTICATION",
        },
    )

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
    elyra_config = write_elyra_config(
        tmp_path,
        {
            "api_endpoint": "http://ml-pipeline:8080",
            "user_namespace": "test-namespace",
            "auth_type": "KUBERNETES_SERVICE_ACCOUNT_TOKEN",
        },
    )

    monkeypatch.setattr("os.path.exists", lambda path: True)

    result = kale_config.configure_kale_from_elyra(str(elyra_config))

    assert result is True
    assert mock_kale_module["config"] is not None
