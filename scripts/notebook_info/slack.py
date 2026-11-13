"""Slack client for the Notebook status report."""

from __future__ import annotations

import json
import os
import urllib.request


def post_report(report: str, channel: str) -> None:
    if "SLACK_APP_TOKEN" not in os.environ:
        raise SystemExit("Missing environment variable: SLACK_APP_TOKEN")
    request = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(
            {
                "channel": channel,
                "text": report,
                "mrkdwn": True,
                "unfurl_links": False,
                "unfurl_media": False,
            }
        ).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['SLACK_APP_TOKEN']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage]
        body = json.load(response)
    if not body.get("ok"):
        raise RuntimeError(f"Slack chat.postMessage failed: {body.get('error')}")
