"""Shared Jira REST API v3 client for CVE scripts."""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

from scripts.cve import create_ssl_context
from scripts.cve.jira_auth import (
    get_auth_headers,
    get_cached_api_base_url,
    resolve_cloud_base_url,
)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request

    HAS_REQUESTS = False


_SSL_CONTEXT = create_ssl_context() if not HAS_REQUESTS else None

JIRA_DEFAULT_URL = "https://redhat.atlassian.net"

# Keys set explicitly by create_issue(); extra_fields may not override these.
_CREATE_ISSUE_PROTECTED_FIELD_KEYS = frozenset({
    "project", "summary", "issuetype", "description", "labels", "components", "security",
})


class JiraClient:
    """Simple Jira REST API v3 client.

    Supports both the ``requests`` library (preferred) and stdlib ``urllib``
    as a fallback for environments without ``requests`` installed.
    """

    def __init__(self, base_url: str, auth_headers: dict | None = None):
        """Direct constructor — testable, no env var dependencies."""
        self.base_url = base_url.rstrip("/")
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        if auth_headers:
            self.headers.update(auth_headers)

    @classmethod
    def from_env(cls) -> JiraClient:
        """Factory that reads env vars, resolves auth and base URL.

        For OAuth tokens the Jira REST API must be accessed through the
        Atlassian API gateway (``api.atlassian.com/ex/jira/{cloudId}``).
        For API-token (Basic) or legacy Bearer auth the configured
        ``JIRA_URL`` is used directly.
        """
        jira_url = os.environ.get("JIRA_URL", JIRA_DEFAULT_URL)
        auth_headers = get_auth_headers(jira_url)

        base_url = jira_url
        auth_value = auth_headers.get("Authorization", "")

        # OAuth tokens go through the API gateway — resolve cloud ID
        if auth_value.startswith("Bearer ") and not os.environ.get("JIRA_TOKEN", "").strip():
            cached_base = get_cached_api_base_url(jira_url)
            if cached_base:
                base_url = cached_base
            else:
                token = auth_value.removeprefix("Bearer ")
                base_url = resolve_cloud_base_url(token, jira_url)

        return cls(base_url, auth_headers)

    def _request(self, method: str, endpoint: str, params: dict | None = None, data: dict | None = None) -> dict:
        """Make a request to the Jira API."""
        url = f"{self.base_url}{endpoint}"

        if HAS_REQUESTS:
            response = requests.request(
                method,
                url,
                params=params,
                json=data,
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            if response.text:
                return response.json()
            return {}

        if params:
            query_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
            url = f"{url}?{query_string}"

        req = urllib.request.Request(url, headers=self.headers, method=method)
        if data:
            req.data = json.dumps(data).encode("utf-8")

        with urllib.request.urlopen(req, context=_SSL_CONTEXT, timeout=30) as resp:
            content = resp.read().decode()
            if content:
                return json.loads(content)
            return {}

    def search_issues(self, jql: str, fields: str,
                      max_results: int = 500) -> list[dict]:
        """Search for issues using JQL (API v3, token-based pagination)."""
        all_issues: list[dict] = []
        next_page_token: str | None = None

        while len(all_issues) < max_results:
            params: dict[str, str | int] = {
                "jql": jql,
                "maxResults": min(100, max_results - len(all_issues)),
                "fields": fields,
            }
            if next_page_token:
                params["nextPageToken"] = next_page_token

            data = self._request("GET", "/rest/api/3/search/jql", params=params)
            issues = data.get("issues", [])
            all_issues.extend(issues)

            if data.get("isLast", True) or not issues:
                break

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        return all_issues

    def get_issue(self, issue_key: str, fields: str) -> dict:
        """Get a single issue."""
        params = {"fields": fields}
        return self._request("GET", f"/rest/api/3/issue/{issue_key}", params=params)

    def create_issue(self, project_key: str, summary: str, issue_type: str,
                     description: dict | None = None, labels: list[str] | None = None,
                     components: list[str] | None = None,
                     security_level: str | None = None,
                     extra_fields: dict[str, Any] | None = None) -> dict:
        """Create a new Jira issue (API v3, ADF description).

        ``extra_fields`` are merged into the REST ``fields`` object for custom
        fields (e.g. Team). Keys in ``_CREATE_ISSUE_PROTECTED_FIELD_KEYS`` are
        ignored so callers cannot override project, summary, labels, etc.
        """
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        if description:
            fields["description"] = description

        if labels:
            fields["labels"] = labels

        if components:
            fields["components"] = [{"name": c} for c in components]

        if security_level:
            fields["security"] = {"name": security_level}

        if extra_fields:
            fields.update({
                k: v
                for k, v in extra_fields.items()
                if k not in _CREATE_ISSUE_PROTECTED_FIELD_KEYS
            })

        data = {"fields": fields}
        return self._request("POST", "/rest/api/3/issue", data=data)

    def create_issue_link(self, link_type: str, inward_key: str, outward_key: str) -> None:
        """Create a link between two issues."""
        data = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        }
        self._request("POST", "/rest/api/3/issueLink", data=data)

    def update_issue(self, issue_key: str, fields: dict) -> None:
        """Update fields on an existing issue."""
        self._request("PUT", f"/rest/api/3/issue/{issue_key}", data={"fields": fields})
