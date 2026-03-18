# Jira Authentication — Product Requirements Document

## Overview

This document specifies the authentication behaviour for the CVE Jira scripts
that interact with `https://redhat.atlassian.net` (Atlassian Cloud).  It
follows a spec-driven development approach: the implementation in
`scripts/cve/jira_auth.py` must satisfy every requirement stated here.

The default Jira URL is `https://redhat.atlassian.net`, replacing the
previous `https://issues.redhat.com` (legacy self-hosted).  All scripts use
API v3 (`/rest/api/3/`).

---

## Goals

- Support non-interactive (CI/automation) use via API token (env vars).
- Support developer workstations via API token stored in the OS keychain
  (one-time `store-token` command) or OAuth 2.0 browser flow with PKCE.
- Maintain backwards compatibility with the legacy `JIRA_TOKEN` bearer-token
  approach used against `https://issues.redhat.com`.  Note: the legacy token
  is passed through as-is (`Authorization: Bearer`); no v2 endpoint paths are
  used — all scripts use API v3 exclusively.  This works because Jira
  Server/Data Center PATs authenticate at the HTTP level, independent of the
  REST API version in the URL path.
- Store API tokens and OAuth tokens securely using the OS keychain.
- Provide a single, well-tested entry point (`get_auth_headers`) consumed by
  all CVE scripts, and a `JiraClient.from_env()` factory that encapsulates
  auth and base-URL resolution.

---

## Definitions

| Term | Meaning |
|------|---------|
| **API token** | An opaque token created at id.atlassian.com, used for Basic auth |
| **PAT** | Personal Access Token — used with the legacy self-hosted Jira |
| **OAuth access token** | Short-lived token returned by the Atlassian OAuth 2.0 token endpoint |
| **Refresh token** | Long-lived token used to obtain new access tokens without re-authorizing |
| **PKCE** | Proof Key for Code Exchange — prevents authorization code interception |
| **Cloud ID** | UUID identifying an Atlassian Cloud site, needed to route API requests through `api.atlassian.com` |
| **Keyring** | OS-level secret store (macOS Keychain, GNOME Keyring, KWallet) |
| **ADF** | Atlassian Document Format — JSON-based rich-text format used by API v3 |

---

## Auth Methods

### 1. API Token (Basic Auth) — preferred

**When**: `JIRA_EMAIL` and `JIRA_API_TOKEN` environment variables are both set,
OR an API token has been stored in the OS keychain.

**Mechanism**: `Authorization: Basic base64("{email}:{api_token}")`

Create a token at https://id.atlassian.com/manage-profile/security/api-tokens.

**Base URL**: Uses `JIRA_URL` directly (e.g. `https://redhat.atlassian.net`).

**Sources (checked in order)**:
1. **Env vars** `JIRA_EMAIL` + `JIRA_API_TOKEN` — for CI/automation.
2. **OS keychain** — for developer workstations.  Store once with:
   `python -m scripts.cve.jira_auth store-token`

**Keychain storage**:
- Service name: `"jira-cve-scripts"`, username key: `"api-token"`
- Stored value: JSON `{"email": "...", "api_token": "..."}`

**Requirements**:
- REQ-A1: If env vars are present, they MUST take precedence over the keychain.
- REQ-A2: If env vars are absent, the keychain MUST be checked before falling
  through to other auth methods.
- REQ-A3: The credential string MUST be UTF-8 encoded before base64 encoding.
- REQ-A4: Keychain read failures MUST be silently ignored (fall through).
- REQ-A5: If exactly one of `JIRA_EMAIL`/`JIRA_API_TOKEN` is set, MUST raise
  `JiraAuthError` (fail fast on half-configured credentials).

---

### 2. Legacy Bearer Token — backwards compatibility

**When**: `JIRA_TOKEN` is set (and `JIRA_EMAIL`/`JIRA_API_TOKEN` are not).

**Mechanism**: `Authorization: Bearer {JIRA_TOKEN}`

**Base URL**: Uses `JIRA_URL` directly.

**Requirements**:
- REQ-B1: If `JIRA_TOKEN` is present (and method 1 conditions are not met),
  this method MUST be chosen.
- REQ-B2: No transformation is applied to the token value.
- REQ-B3: A deprecation warning MUST be printed to stderr when the resolved
  `JIRA_URL` contains `atlassian.net`.

---

### 3. OAuth 2.0 Browser Redirect Flow with PKCE — interactive

**When**: `JIRA_OAUTH_CLIENT_SECRET` is set, and methods 1 and 2 do not apply.

**Client ID**: Hardcoded as `Vy2kiBP7sPj6HfgxCXam8iGutRps5Xsu` in the source.
Overridable via `JIRA_OAUTH_CLIENT_ID` env var.

**Client secret**: Distributed to the team via the Bitwarden vault.
Set as `JIRA_OAUTH_CLIENT_SECRET` env var.

**Prerequisites**: The OAuth app is registered at `developer.atlassian.com`
with:
- Redirect URIs: `http://localhost:8080/callback` and `http://127.0.0.1:8080/callback`
- Scopes: `read:jira-work write:jira-work read:me offline_access`

**Base URL**: OAuth tokens are scoped to `api.atlassian.com`, NOT directly to
the Jira instance.  After obtaining a token, the script resolves the Cloud ID
via `GET https://api.atlassian.com/oauth/token/accessible-resources` and uses
`https://api.atlassian.com/ex/jira/{cloud_id}` as the effective base URL.

**Flow**:
1. Check the token store for a cached, non-expired access token → use it.
2. Check the token store for a valid refresh token → exchange for new access
   token; update store.
3. Generate PKCE code verifier (32 random bytes, base64url) and code challenge
   (SHA-256 of verifier, base64url).
4. Start a temporary HTTP server on `localhost:8080`.
5. Construct the Atlassian authorization URL with `audience=api.atlassian.com`,
   `code_challenge`, `code_challenge_method=S256`, and open in the browser.
6. Wait (max 120 s) for the callback containing `code` and `state`.
7. Verify `state` matches (CSRF protection).
8. Exchange `code` + `code_verifier` + `client_secret` for tokens.
9. Resolve Cloud ID and cache `api_base_url` alongside the token.
10. Return `Authorization: Bearer {access_token}`.

**Requirements**:
- REQ-C1: `state` MUST be generated with `secrets.token_bytes(16)` (≥ 128 bits).
- REQ-C2: The local HTTP server MUST bind to `localhost` only (Atlassian's
  OAuth redirect does not deliver callbacks to bare IP addresses like `127.0.0.1`).
- REQ-C3: If the browser cannot be opened, the URL MUST be printed to stdout.
- REQ-C4: Timeout after 120 seconds → raise `JiraAuthError`.
- REQ-C5: Token values MUST NOT be printed to stdout or stderr.
- REQ-C6: The local server MUST be shut down after callback or timeout.
- REQ-C7: If token refresh fails, discard cached token and re-run full flow.
- REQ-C8: PKCE code verifier MUST be 32+ bytes of `secrets.token_bytes`,
  base64url-encoded without padding.
- REQ-C9: PKCE code challenge MUST use S256 (SHA-256 of verifier, base64url).

---

## Cloud ID Resolution

OAuth tokens access the Jira REST API through the Atlassian API gateway:

```http
GET https://api.atlassian.com/oauth/token/accessible-resources
Authorization: Bearer {access_token}
```

Returns a list of sites.  The script matches the configured `JIRA_URL` against
site URLs and extracts the `id` (Cloud ID).  The effective API base URL is:

```text
https://api.atlassian.com/ex/jira/{cloud_id}
```

The Cloud ID is cached in the token store (`cloud_id` and `api_base_url`
fields) to avoid re-resolving on every invocation.

---

## Token Storage

**Primary**: `keyring` library (mandatory dev dependency, installed via `uv sync`).
- Service name: `"jira-cve-scripts"`
- Username key: the Jira base URL (e.g., `https://redhat.atlassian.net`)
- Stored value: JSON string with fields:
  - `access_token`, `refresh_token`, `expires_at` (ISO-8601 UTC)
  - `cloud_id`, `api_base_url` (cached Cloud ID resolution)

**Fallback** (when no keyring backend is available, i.e. `NoKeyringError` — e.g.
headless CI containers, SSH sessions without a desktop keyring service):
- File: `~/.config/jira/oauth-token-{hash}.json` where `{hash}` is the first 16
  hex chars of `SHA-256(jira_url)`, namespaced per Jira site.
- Written atomically (temp file → chmod 0600 → rename).
- File cache write failures are logged as warnings (best-effort), not fatal.

**Requirements**:
- REQ-D1: File MUST be created with mode `0600` atomically.
- REQ-D2: `expires_at` MUST be ISO-8601 UTC.
- REQ-D3: Token is expired if `expires_at` is within 60 seconds of now.
- REQ-D4: Unparseable stored tokens MUST be silently discarded.
- REQ-D5: Non-`NoKeyringError` keyring failures → warning to stderr, file
  fallback.

---

## Public API

```python
# scripts/cve/jira_auth.py

def get_auth_headers(jira_url: str) -> dict[str, str]:
    """Return HTTP headers sufficient to authenticate against jira_url.

    Auth method priority:
      1a. JIRA_EMAIL + JIRA_API_TOKEN env vars -> Basic auth
      1b. API token from OS keychain           -> Basic auth
      2.  JIRA_TOKEN                           -> Bearer auth (legacy)
      3.  JIRA_OAUTH_CLIENT_SECRET             -> OAuth 2.0 flow (PKCE)
      4.  None set                             -> raises JiraAuthError
    """

def resolve_cloud_base_url(access_token: str, jira_url: str) -> str:
    """Resolve the Atlassian API gateway URL for the given Jira Cloud site."""

def get_cached_api_base_url(jira_url: str) -> str | None:
    """Return the cached API base URL from a previous OAuth flow."""

def store_api_token(email: str, api_token: str) -> None:
    """Store an API token in the OS keychain for future use."""

def clear_api_token() -> None:
    """Remove stored API token from the OS keychain."""

class JiraAuthError(RuntimeError):
    """Raised when no authentication method can be configured."""
```

```python
# scripts/cve/jira_client.py

class JiraClient:
    def __init__(self, base_url: str, auth_headers: dict | None = None):
        """Direct constructor — testable, no env var dependencies."""

    @classmethod
    def from_env(cls) -> JiraClient:
        """Factory: reads env vars, resolves auth + base URL.

        For OAuth: resolves Cloud ID → uses api.atlassian.com gateway.
        For API token / Bearer: uses JIRA_URL directly.
        """
```

---

## JiraClient.from_env() Logic

```text
1. jira_url = JIRA_URL env var (default: https://redhat.atlassian.net)
2. auth_headers = get_auth_headers(jira_url)
3. If auth is Bearer AND JIRA_TOKEN is not set (i.e. OAuth):
   a. Check cached api_base_url → use if available
   b. Else call resolve_cloud_base_url() → get gateway URL
4. Else: base_url = jira_url
5. Return JiraClient(base_url, auth_headers)
```

---

## API Version

All scripts use **Jira REST API v3**.  Key endpoint changes from v2:

| Operation | v2 (removed) | v3 |
|-----------|-------------|-----|
| Search | `GET /rest/api/2/search` | `GET /rest/api/3/search/jql` |
| Get issue | `GET /rest/api/2/issue/{key}` | `GET /rest/api/3/issue/{key}` |
| Create issue | `POST /rest/api/2/issue` | `POST /rest/api/3/issue` |
| Issue link | `POST /rest/api/2/issueLink` | `POST /rest/api/3/issueLink` |

Issue descriptions use **ADF** (Atlassian Document Format) — a JSON structure
instead of wiki markup strings.

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| No auth env vars set | Raise `JiraAuthError` with instructions |
| Half-configured API token (one of JIRA_EMAIL/JIRA_API_TOKEN) | Raise `JiraAuthError` |
| OAuth flow times out | Raise `JiraAuthError` |
| OAuth state mismatch | Raise `JiraAuthError` ("possible CSRF") |
| Token exchange HTTP error | Raise `JiraAuthError` with response body |
| Token refresh fails | Discard cached token, re-run full browser flow |
| Cloud ID resolution fails (Atlassian Cloud URL) | Raise `JiraAuthError` — cloud ID is mandatory for `atlassian.net` |
| Cloud ID resolution fails (non-Cloud URL) | Warning to stderr, continue without cached cloud ID |
| Keyring write fails (non-NoKeyringError) | Warning to stderr, file fallback |
| File cache write fails (OSError) | Warning to stderr, continue without cache |
| Stored token unparseable | Silently discard, re-run auth |

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `JIRA_URL` | Jira server URL (default: `https://redhat.atlassian.net`) |
| `JIRA_EMAIL` | User email for Basic auth with API token |
| `JIRA_API_TOKEN` | Atlassian API token (paired with `JIRA_EMAIL`) |
| `JIRA_TOKEN` | Legacy Bearer token (PAT for `issues.redhat.com`) |
| `JIRA_OAUTH_CLIENT_ID` | Override hardcoded OAuth client ID (optional) |
| `JIRA_OAUTH_CLIENT_SECRET` | OAuth client secret (from team Bitwarden vault) |

---

## CLI Commands

The module can be run directly to manage stored credentials:

```bash
python -m scripts.cve.jira_auth store-token   # prompt for email + API token, save to keychain
python -m scripts.cve.jira_auth clear-token   # remove stored API token from keychain
python -m scripts.cve.jira_auth status        # show which auth method would be used
```

`store-token` accepts `--email` and `--token` flags for non-interactive use
(e.g. `--token "$(bw get password jira-api-token)"`).  When `--token` is
omitted, the token is read via `getpass` (not echoed to the terminal).

---

## Out of Scope

- Atlassian MCP server (`mcp.atlassian.com`) — rejects third-party OAuth
  tokens with HTTP 403; only Atlassian-approved MCP clients are accepted.
- Dynamic Client Registration (DCR) — Atlassian does not support it for
  third-party apps.
- Storing `JIRA_TOKEN` (legacy Bearer) in the keyring.
- Kerberos, NTLM, or certificate-based auth.
- Multi-account support.
