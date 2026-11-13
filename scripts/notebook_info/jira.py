"""Jira client used by the Notebook status report."""

from __future__ import annotations

import base64
import json
import os
import urllib.request


class JiraClient:
    def __init__(self, base_url: str, email: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.authorization = base64.b64encode(f"{email}:{token}".encode()).decode()

    def count(self, jql: str) -> int:
        count = 0
        next_page_token = None
        while True:
            payload = {"jql": jql, "maxResults": 5000, "fields": ["key"]}
            if next_page_token is not None:
                payload["nextPageToken"] = next_page_token
            request = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage]
                f"{self.base_url}/rest/api/3/search/jql",
                data=json.dumps(payload).encode(),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {self.authorization}",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage]
                body = json.load(response)
            count += len(body.get("issues", []))
            if body.get("isLast", True):
                return count
            next_page_token = body.get("nextPageToken")
            if not next_page_token:
                raise RuntimeError("Jira pagination did not provide nextPageToken")


def jira_client_from_env() -> JiraClient:
    try:
        return JiraClient(
            os.environ["JIRA_URL"],
            os.environ["JIRA_EMAIL"],
            os.environ["JIRA_API_TOKEN"],
        )
    except KeyError as error:
        raise SystemExit(f"Missing environment variable: {error.args[0]}") from error
