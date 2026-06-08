from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest

from scripts.cve.jira_auth import (
    JiraAuthError,
    _basic_auth_header,
    _not_expired,
    _parse_expires_at,
    _pkce_pair,
    get_auth_headers,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch
    from pytest_subtests import SubTests


def test_basic_auth_header() -> None:
    headers = _basic_auth_header("user@example.com", "my-token")
    expected_raw = base64.b64encode(b"user@example.com:my-token").decode("ascii")
    assert headers == {"Authorization": f"Basic {expected_raw}"}


def test_pkce_pair_produces_valid_values() -> None:
    verifier, challenge = _pkce_pair()
    assert len(verifier) > 20
    assert len(challenge) > 20
    assert verifier != challenge


def test_pkce_pair_is_unique() -> None:
    v1, c1 = _pkce_pair()
    v2, c2 = _pkce_pair()
    assert v1 != v2
    assert c1 != c2


def test_parse_expires_at_valid_iso(subtests: SubTests) -> None:
    cases = [
        ("2026-06-15T10:00:00+00:00", datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)),
        ("2026-01-01T00:00:00", datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)),
    ]
    for value, expected in cases:
        with subtests.test(msg=value):
            result = _parse_expires_at(value)
            assert result is not None
            assert result == expected


def test_parse_expires_at_invalid() -> None:
    assert _parse_expires_at("") is None
    assert _parse_expires_at("not-a-date") is None


def test_not_expired_true() -> None:
    future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    assert _not_expired(future) is True


def test_not_expired_false_when_past() -> None:
    past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    assert _not_expired(past) is False


def test_not_expired_false_within_buffer() -> None:
    almost_expired = datetime.now(tz=timezone.utc) + timedelta(seconds=30)
    assert _not_expired(almost_expired) is False


def test_get_auth_headers_with_env_api_token(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "my-api-token")
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_OAUTH_CLIENT_SECRET", raising=False)

    headers = get_auth_headers("https://redhat.atlassian.net")
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")


def test_get_auth_headers_incomplete_api_token(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_OAUTH_CLIENT_SECRET", raising=False)

    with pytest.raises(JiraAuthError, match="Set both JIRA_EMAIL and JIRA_API_TOKEN"):
        get_auth_headers("https://redhat.atlassian.net")


def test_get_auth_headers_legacy_bearer(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setenv("JIRA_TOKEN", "legacy-pat")
    monkeypatch.delenv("JIRA_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("scripts.cve.jira_auth._load_api_token", lambda: None)

    headers = get_auth_headers("https://issues.redhat.com")
    assert headers == {"Authorization": "Bearer legacy-pat"}


def test_get_auth_headers_no_creds_raises(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("scripts.cve.jira_auth._load_api_token", lambda: None)

    with pytest.raises(JiraAuthError, match="No Jira authentication credentials found"):
        get_auth_headers("https://redhat.atlassian.net")
