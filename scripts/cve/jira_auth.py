"""Jira authentication for CVE scripts.

Supports three auth methods (in priority order):

1. API token (Basic auth) — stored in OS keychain or env vars
   - One-time setup:  ./uv run python -m scripts.cve.jira_auth store-token
   - Or env vars:     JIRA_EMAIL + JIRA_API_TOKEN
2. Legacy Bearer token  — set JIRA_TOKEN
3. OAuth 2.0 browser flow — set JIRA_OAUTH_CLIENT_SECRET
   (client_id is hardcoded; override with JIRA_OAUTH_CLIENT_ID)

CLI commands:
    ./uv run python -m scripts.cve.jira_auth store-token   # save API token to keychain
    ./uv run python -m scripts.cve.jira_auth clear-token   # remove stored token
    ./uv run python -m scripts.cve.jira_auth status        # show current auth config

See jira_auth.spec.md for the full requirements document.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import keyring
import keyring.errors

_KEYRING_SERVICE = "jira-cve-scripts"
_OAUTH_TIMEOUT_S = 120
_TOKEN_EXPIRY_BUFFER_S = 60
# Use "localhost" not "127.0.0.1" — Atlassian's OAuth redirect fails to
# deliver the callback when the redirect_uri uses a bare IP address.
_CALLBACK_PORT = 8080

# Atlassian OAuth 2.0 endpoints and defaults
_ATLASSIAN_AUTH_URL = "https://auth.atlassian.com/authorize"
_ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
_ATLASSIAN_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
_ATLASSIAN_SCOPES = "read:jira-work write:jira-work read:me offline_access"
_DEFAULT_CLIENT_ID = "Vy2kiBP7sPj6HfgxCXam8iGutRps5Xsu"


class JiraAuthError(RuntimeError):
    """Raised when no authentication method can be configured."""


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def get_auth_headers(jira_url: str) -> dict[str, str]:
    """Return HTTP headers sufficient to authenticate against *jira_url*.

    Auth method priority:
      1a. JIRA_EMAIL + JIRA_API_TOKEN env vars -> Basic auth
      1b. API token from OS keychain           -> Basic auth
      2.  JIRA_TOKEN                           -> Bearer auth (legacy)
      3.  JIRA_OAUTH_CLIENT_SECRET             -> OAuth 2.0 flow (PKCE)
      4.  None set                             -> raises JiraAuthError
    """
    email = os.environ.get("JIRA_EMAIL", "").strip()
    api_token = os.environ.get("JIRA_API_TOKEN", "").strip()
    legacy_token = os.environ.get("JIRA_TOKEN", "").strip()
    client_secret = os.environ.get("JIRA_OAUTH_CLIENT_SECRET", "").strip()

    # --- Method 1a: API token from env vars ---
    if email or api_token:
        if not (email and api_token):
            raise JiraAuthError(
                "Set both JIRA_EMAIL and JIRA_API_TOKEN together, or unset both to use keyring/OAuth."
            )
        return _basic_auth_header(email, api_token)

    # --- Method 1b: API token from keyring ---
    if not email and not api_token:
        stored = _load_api_token()
        if stored:
            return _basic_auth_header(stored["email"], stored["api_token"])

    # --- Method 2: Legacy Bearer token ---
    if legacy_token:
        if "atlassian.net" in jira_url:
            print(
                "WARNING: JIRA_TOKEN (Bearer) may not work on Atlassian Cloud "
                f"({jira_url}). Consider using JIRA_EMAIL + JIRA_API_TOKEN instead.",
                file=sys.stderr,
            )
        return {"Authorization": f"Bearer {legacy_token}"}

    # --- Method 3: OAuth 2.0 browser redirect with PKCE ---
    if client_secret:
        client_id = os.environ.get("JIRA_OAUTH_CLIENT_ID", _DEFAULT_CLIENT_ID).strip()
        access_token = _get_oauth_token(client_id, client_secret, jira_url)
        return {"Authorization": f"Bearer {access_token}"}

    # --- No method available ---
    raise JiraAuthError(
        "No Jira authentication credentials found.\n\n"
        "Set one of the following:\n"
        "  Option 1 — API token (recommended):\n"
        "    ./uv run python -m scripts.cve.jira_auth store-token\n"
        "    (stores email + API token in your OS keychain — one-time setup)\n\n"
        "  Option 1b — API token via env vars (CI/automation):\n"
        "    export JIRA_EMAIL='you@redhat.com'\n"
        "    export JIRA_API_TOKEN='your-atlassian-api-token'\n"
        "    (Create at https://id.atlassian.com/manage-profile/security/api-tokens)\n\n"
        "  Option 2 — OAuth 2.0 (interactive browser flow):\n"
        "    export JIRA_OAUTH_CLIENT_SECRET='your-client-secret'\n"
        "    (Get the secret from the team Bitwarden vault)\n\n"
        "  Option 3 — Legacy PAT (issues.redhat.com only):\n"
        "    export JIRA_TOKEN='your-personal-access-token'\n"
    )


def _basic_auth_header(email: str, api_token: str) -> dict[str, str]:
    """Build a Basic auth header from email and API token."""
    raw = f"{email}:{api_token}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def _load_api_token() -> dict[str, str] | None:
    """Load stored API token from keyring, returning None if unavailable."""
    try:
        raw = keyring.get_password(_KEYRING_SERVICE, "api-token")
        if raw:
            data = json.loads(raw)
            if data.get("email") and data.get("api_token"):
                return data
    except Exception:
        pass
    return None


def store_api_token(email: str, api_token: str) -> None:
    """Store an API token in the OS keychain for future use.

    Call this from the CLI: ``python -m scripts.cve.jira_auth store-token``
    """
    raw = json.dumps({"email": email, "api_token": api_token})
    try:
        keyring.set_password(_KEYRING_SERVICE, "api-token", raw)
        print(f"API token stored in keychain for {email}")
    except Exception as exc:
        raise JiraAuthError(f"Failed to store token in keychain: {exc}") from exc


def clear_api_token() -> None:
    """Remove stored API token from the OS keychain."""
    try:
        keyring.delete_password(_KEYRING_SERVICE, "api-token")
        print("API token removed from keychain")
    except keyring.errors.PasswordDeleteError:
        print("No stored API token found")
    except Exception as exc:
        print(f"Failed to clear API token: {exc}", file=sys.stderr)


def resolve_cloud_base_url(access_token: str, jira_url: str) -> str:
    """Resolve the Atlassian API gateway URL for the given Jira Cloud site.

    Calls the accessible-resources endpoint, finds the site matching
    *jira_url*, and returns ``https://api.atlassian.com/ex/jira/{cloud_id}``.

    Raises ``JiraAuthError`` if no site matches *jira_url*.
    """
    req = urllib.request.Request(
        _ATLASSIAN_RESOURCES_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            sites = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise JiraAuthError(
            f"Failed to resolve cloud ID: HTTP {e.code} from {_ATLASSIAN_RESOURCES_URL}"
        ) from e
    except Exception as e:
        raise JiraAuthError(
            f"Failed to resolve cloud ID from {_ATLASSIAN_RESOURCES_URL}: {e}"
        ) from e

    if not sites:
        raise JiraAuthError(
            "No accessible Atlassian sites found. "
            "Ensure your OAuth app has site access granted."
        )

    jira_url_stripped = jira_url.rstrip("/")
    cloud_id = None
    for site in sites:
        site_url = site.get("url", "").rstrip("/")
        if jira_url_stripped == site_url:
            cloud_id = site["id"]
            break

    if not cloud_id:
        available = ", ".join(s.get("url", "?") for s in sites)
        raise JiraAuthError(
            f"No Atlassian site matching {jira_url} found. "
            f"Available sites: {available}"
        )

    return f"https://api.atlassian.com/ex/jira/{cloud_id}"


# ---------------------------------------------------------------------------
# OAuth 2.0 browser redirect flow with PKCE
# ---------------------------------------------------------------------------

def _get_oauth_token(client_id: str, client_secret: str, jira_url: str) -> str:
    """Return a valid OAuth access token, using cache if possible."""
    cached = _load_token(jira_url)
    if cached:
        expires_at = _parse_expires_at(cached.get("expires_at", ""))
        if expires_at and _not_expired(expires_at):
            return cached["access_token"]

        refresh_token = cached.get("refresh_token")
        if refresh_token:
            try:
                token_data = _refresh_oauth_token(client_id, client_secret, refresh_token)
                # Preserve cached cloud_id/api_base_url
                token_data.setdefault("cloud_id", cached.get("cloud_id", ""))
                token_data.setdefault("api_base_url", cached.get("api_base_url", ""))
                _save_token(jira_url, token_data)
                return token_data["access_token"]
            except Exception:
                _save_token(jira_url, {})

    token_data = _do_oauth_flow(client_id, client_secret)

    # Resolve and cache cloud ID — mandatory for Atlassian Cloud URLs
    try:
        api_base_url = resolve_cloud_base_url(token_data["access_token"], jira_url)
        token_data["api_base_url"] = api_base_url
    except JiraAuthError:
        if "atlassian.net" in jira_url:
            raise
        print(f"WARNING: Could not resolve cloud ID for {jira_url}, continuing without it.", file=sys.stderr)

    _save_token(jira_url, token_data)
    return token_data["access_token"]


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _do_oauth_flow(client_id: str, client_secret: str) -> dict[str, Any]:
    """Run the OAuth 2.0 browser redirect flow with PKCE and return token data."""
    state = base64.urlsafe_b64encode(secrets.token_bytes(16)).decode("ascii")
    verifier, challenge = _pkce_pair()
    redirect_uri = f"http://localhost:{_CALLBACK_PORT}/callback"

    params = {
        "audience": "api.atlassian.com",
        "client_id": client_id,
        "scope": _ATLASSIAN_SCOPES,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "consent",
    }
    auth_url = f"{_ATLASSIAN_AUTH_URL}?{urllib.parse.urlencode(params)}"

    result: dict[str, Any] = {}
    event = threading.Event()

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            qs = urllib.parse.parse_qs(parsed.query)
            result["code"] = qs.get("code", [None])[0]
            result["state"] = qs.get("state", [None])[0]
            result["error"] = qs.get("error", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authentication complete.</h2>"
                b"<p>You can close this tab and return to the terminal.</p></body></html>"
            )
            event.set()

        def log_message(self, *args):
            pass

    server: HTTPServer | None = None
    try:
        server = HTTPServer(("localhost", _CALLBACK_PORT), _CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
    except (OSError, RuntimeError) as exc:
        if server is not None:
            server.server_close()
        raise JiraAuthError(
            f"Cannot start OAuth callback server on localhost:{_CALLBACK_PORT} ({exc}). "
            "Ensure the port is free and retry."
        ) from exc

    try:
        opened = webbrowser.open(auth_url)
        if not opened:
            print(
                "\nCould not open browser automatically. Visit this URL to authenticate:\n"
                f"  {auth_url}\n",
                flush=True,
            )
        else:
            print("Opening browser for Jira authentication...", flush=True)

        if not event.wait(timeout=_OAUTH_TIMEOUT_S):
            raise JiraAuthError(
                f"OAuth flow timed out after {_OAUTH_TIMEOUT_S} seconds. "
                "Please try again."
            )
    finally:
        server.shutdown()
        server.server_close()

    if result.get("error"):
        raise JiraAuthError(f"OAuth authorization error: {result['error']}")

    if result.get("state") != state:
        raise JiraAuthError("OAuth state mismatch — possible CSRF attack, aborting.")

    code = result.get("code")
    if not code:
        raise JiraAuthError("OAuth callback received no authorization code.")

    return _exchange_code(client_id, client_secret, code, redirect_uri, verifier)


def _exchange_code(
    client_id: str, client_secret: str, code: str, redirect_uri: str, code_verifier: str,
) -> dict[str, Any]:
    """Exchange an authorization code for tokens."""
    payload = json.dumps({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }).encode("utf-8")
    return _post_token_endpoint(payload)


def _refresh_oauth_token(client_id: str, client_secret: str, refresh_token: str) -> dict[str, Any]:
    """Exchange a refresh token for a new access token."""
    payload = json.dumps({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }).encode("utf-8")
    return _post_token_endpoint(payload)


def _post_token_endpoint(payload: bytes) -> dict[str, Any]:
    req = urllib.request.Request(
        _ATLASSIAN_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise JiraAuthError(f"Token exchange failed HTTP {e.code}: {body}") from e
    except Exception as e:
        raise JiraAuthError(f"Token exchange failed: {e}") from e

    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise JiraAuthError("Token exchange failed: response missing access_token")

    try:
        expires_in = int(data.get("expires_in", 3600))
    except (TypeError, ValueError) as e:
        raise JiraAuthError(f"Token exchange failed: invalid expires_in={data.get('expires_in')!r}") from e

    expires_at = datetime.now(tz=timezone.utc).replace(microsecond=0) + timedelta(seconds=expires_in)

    return {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": expires_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Token storage — keyring with file fallback
# ---------------------------------------------------------------------------

def _load_token(jira_url: str) -> dict[str, Any] | None:
    """Load cached OAuth token data, returning None if unavailable/invalid."""
    raw: str | None = None

    try:
        raw = keyring.get_password(_KEYRING_SERVICE, jira_url)
    except Exception:
        raw = None

    if not raw:
        raw = _read_token_file(jira_url)

    if not raw:
        return None

    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or "access_token" not in data:
            return None
        return data
    except (json.JSONDecodeError, ValueError):
        return None


def _save_token(jira_url: str, token_data: dict[str, Any]) -> None:
    """Persist OAuth token data to keyring or fallback file."""
    raw = json.dumps(token_data)

    try:
        keyring.set_password(_KEYRING_SERVICE, jira_url, raw)
        return
    except keyring.errors.NoKeyringError:
        pass
    except Exception as exc:
        print(f"WARNING: keyring write failed ({exc}), falling back to file storage.", file=sys.stderr)

    try:
        _write_token_file(jira_url, raw)
    except OSError as exc:
        print(f"WARNING: token cache write failed ({exc}), continuing without cached OAuth token.", file=sys.stderr)


def _token_file_path(jira_url: str) -> Path:
    config_dir = Path.home() / ".config" / "jira"
    digest = hashlib.sha256(jira_url.rstrip("/").encode("utf-8")).hexdigest()[:16]
    return config_dir / f"oauth-token-{digest}.json"


def _read_token_file(jira_url: str) -> str | None:
    path = _token_file_path(jira_url)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _write_token_file(jira_url: str, raw: str) -> None:
    """Atomically write token file with 0600 permissions."""
    path = _token_file_path(jira_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".jira-token-")
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_expires_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _not_expired(expires_at: datetime) -> bool:
    """Return True if the token is still valid with the expiry buffer."""
    now = datetime.now(tz=timezone.utc)
    return expires_at > now + timedelta(seconds=_TOKEN_EXPIRY_BUFFER_S)


def get_cached_api_base_url(jira_url: str) -> str | None:
    """Return the cached API base URL from a previous OAuth flow, if available."""
    cached = _load_token(jira_url)
    if cached:
        return cached.get("api_base_url")
    return None


# ---------------------------------------------------------------------------
# CLI entry point: python -m scripts.cve.jira_auth store-token
# ---------------------------------------------------------------------------

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m scripts.cve.jira_auth",
        description="Manage Jira API tokens in the OS keychain",
    )
    sub = parser.add_subparsers(dest="command")

    store = sub.add_parser("store-token", help="Store email + API token in the keychain")
    store.add_argument("--email", help="Atlassian account email")
    store.add_argument("--token", help="API token (omit to be prompted)")

    sub.add_parser("clear-token", help="Remove stored API token from the keychain")
    sub.add_parser("status", help="Show which auth method would be used")

    args = parser.parse_args()

    if args.command == "store-token":
        email = args.email or input("Email: ").strip()
        if args.token:
            api_token = args.token
        else:
            import getpass
            api_token = getpass.getpass("API token (from https://id.atlassian.com/manage-profile/security/api-tokens): ")
        store_api_token(email, api_token.strip())

    elif args.command == "clear-token":
        clear_api_token()

    elif args.command == "status":
        jira_url = os.environ.get("JIRA_URL", "https://redhat.atlassian.net")
        print(f"JIRA_URL: {jira_url}")

        if os.environ.get("JIRA_EMAIL") and os.environ.get("JIRA_API_TOKEN"):
            print("Auth: API token (from env vars JIRA_EMAIL + JIRA_API_TOKEN)")
        elif (stored := _load_api_token()):
            print(f"Auth: API token (from keychain, email={stored['email']})")
        elif os.environ.get("JIRA_TOKEN"):
            print("Auth: Legacy Bearer token (from env var JIRA_TOKEN)")
        elif os.environ.get("JIRA_OAUTH_CLIENT_SECRET"):
            print("Auth: OAuth 2.0 browser flow")
        else:
            print("Auth: NOT CONFIGURED — run: python -m scripts.cve.jira_auth store-token")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
