from __future__ import annotations

import base64
import hashlib
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from scripts.cve.jira_auth import (
    JiraAuthConfig,
    JiraAuthError,
    JiraConnectionConfig,
    _basic_auth_header,  # ruff: ignore[import-private-name]
    _cli,  # ruff: ignore[import-private-name]
    _not_expired,  # ruff: ignore[import-private-name]
    _parse_expires_at,  # ruff: ignore[import-private-name]
    _pkce_pair,  # ruff: ignore[import-private-name]
    get_auth_headers,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch, Subtests


# ── _basic_auth_header ─────────────────────────────────────────────────


def test_basic_auth_header() -> None:
    headers = _basic_auth_header("user@example.com", "my-token")
    expected_raw = base64.b64encode(b"user@example.com:my-token").decode("ascii")
    assert headers == {"Authorization": f"Basic {expected_raw}"}


# ── _pkce_pair ─────────────────────────────────────────────────────────


def test_pkce_pair_returns_two_strings() -> None:
    verifier, challenge = _pkce_pair()
    assert isinstance(verifier, str)
    assert isinstance(challenge, str)
    assert len(verifier) > 0
    assert len(challenge) > 0


def test_pkce_pair_challenge_differs_from_verifier() -> None:
    verifier, challenge = _pkce_pair()
    assert verifier != challenge


def test_pkce_pair_is_unique() -> None:
    pair1 = _pkce_pair()
    pair2 = _pkce_pair()
    assert pair1[0] != pair2[0]
    assert pair1[1] != pair2[1]


def test_pkce_pair_verifier_is_url_safe() -> None:
    verifier, _ = _pkce_pair()
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert set(verifier).issubset(allowed)


def test_pkce_pair_uses_s256_challenge() -> None:
    verifier, challenge = _pkce_pair()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert challenge == expected


# ── _parse_expires_at ──────────────────────────────────────────────────


def test_parse_expires_at_valid_iso(subtests: Subtests) -> None:
    cases = [
        ("2025-06-15T12:00:00+00:00", datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)),
        ("2025-06-15T12:00:00", datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)),
    ]
    for value, expected in cases:
        with subtests.test(msg=f"_parse_expires_at({value!r})"):
            result = _parse_expires_at(value)
            assert result == expected


def test_parse_expires_at_empty_returns_none() -> None:
    assert _parse_expires_at("") is None


def test_parse_expires_at_invalid_returns_none() -> None:
    assert _parse_expires_at("not-a-date") is None


# ── _not_expired ───────────────────────────────────────────────────────


def test_not_expired_future_token() -> None:
    future = datetime.now(tz=UTC) + timedelta(hours=1)
    assert _not_expired(future) is True


def test_not_expired_past_token() -> None:
    past = datetime.now(tz=UTC) - timedelta(hours=1)
    assert _not_expired(past) is False


def test_not_expired_within_buffer() -> None:
    almost_expired = datetime.now(tz=UTC) + timedelta(seconds=30)
    assert _not_expired(almost_expired) is False


def test_not_expired_just_outside_buffer() -> None:
    safe = datetime.now(tz=UTC) + timedelta(seconds=120)
    assert _not_expired(safe) is True


# ── get_auth_headers (env-var paths only, no OAuth flow) ──────────────


def test_get_auth_headers_basic_auth() -> None:
    config = JiraAuthConfig(email="user@redhat.com", api_token="my-api-token")  # ruff: ignore[hardcoded-password-func-arg]
    assert "my-api-token" not in repr(config)
    headers = get_auth_headers(config, "https://redhat.atlassian.net")
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")
    decoded = base64.b64decode(headers["Authorization"].split(" ", 1)[1]).decode("utf-8")
    assert decoded == "user@redhat.com:my-api-token"


def test_get_auth_headers_basic_auth_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_EMAIL", "user@redhat.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "my-api-token")

    config = JiraAuthConfig.from_env(os.environ)
    headers = get_auth_headers(config, "https://redhat.atlassian.net")
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")
    decoded = base64.b64decode(headers["Authorization"].split(" ", 1)[1]).decode("utf-8")
    assert decoded == "user@redhat.com:my-api-token"


def test_get_auth_headers_bearer(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.cve.jira_auth._load_api_token", lambda: None)

    config = JiraAuthConfig(legacy_token="legacy-bearer-token")  # ruff: ignore[hardcoded-password-func-arg]
    headers = get_auth_headers(config, "https://issues.redhat.com")
    assert headers == {"Authorization": "Bearer legacy-bearer-token"}


def test_get_auth_headers_bearer_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_TOKEN", "legacy-bearer-token")
    monkeypatch.setattr("scripts.cve.jira_auth._load_api_token", lambda: None)

    config = JiraAuthConfig.from_env(os.environ)
    headers = get_auth_headers(config, "https://issues.redhat.com")
    assert headers == {"Authorization": "Bearer legacy-bearer-token"}


def test_get_auth_headers_raises_when_only_email() -> None:
    with pytest.raises(JiraAuthError, match=r"JIRA_EMAIL.*JIRA_API_TOKEN"):
        JiraAuthConfig(email="user@redhat.com")


def test_get_auth_headers_raises_when_only_email_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_EMAIL", "user@redhat.com")

    with pytest.raises(JiraAuthError, match=r"JIRA_EMAIL.*JIRA_API_TOKEN"):
        JiraAuthConfig.from_env(os.environ)


def test_get_auth_headers_raises_when_only_token(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.cve.jira_auth._load_api_token", lambda: None)

    with pytest.raises(JiraAuthError, match="JIRA_EMAIL"):
        JiraAuthConfig(api_token="my-api-token")  # ruff: ignore[hardcoded-password-func-arg]


def test_get_auth_headers_raises_when_only_token_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_API_TOKEN", "my-api-token")
    monkeypatch.setattr("scripts.cve.jira_auth._load_api_token", lambda: None)

    with pytest.raises(JiraAuthError, match="JIRA_EMAIL"):
        JiraAuthConfig.from_env(os.environ)


def test_get_auth_headers_raises_when_no_creds(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.cve.jira_auth._load_api_token", lambda: None)

    with pytest.raises(JiraAuthError, match="No Jira authentication credentials found"):
        get_auth_headers(JiraAuthConfig(), "https://redhat.atlassian.net")


def test_jira_config_from_env_reads_explicit_mapping() -> None:
    config = JiraConnectionConfig.from_env(
        {
            "JIRA_URL": " https://jira.example.com ",
            "JIRA_EMAIL": " user@example.com ",
            "JIRA_API_TOKEN": " api-token ",
        }
    )

    assert config.url == "https://jira.example.com"
    assert config.auth.email == "user@example.com"
    assert config.auth.api_token == "api-token"  # ruff: ignore[hardcoded-password-string]


def test_jira_config_from_env_uses_defaults() -> None:
    config = JiraConnectionConfig.from_env({})

    assert config.url == "https://redhat.atlassian.net"
    assert config.auth.email == ""


def test_cli_status_reports_auth_error(monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fail_config(_environ: object) -> JiraConnectionConfig:
        raise JiraAuthError("invalid Jira configuration")

    monkeypatch.setattr(JiraConnectionConfig, "from_env", fail_config)
    monkeypatch.setattr(sys, "argv", ["jira_auth", "status"])

    with pytest.raises(SystemExit) as exc_info:
        _cli()

    assert exc_info.value.code == 1
    assert "invalid Jira configuration" in capsys.readouterr().err
