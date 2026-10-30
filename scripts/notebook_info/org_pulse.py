"""Org Pulse API client for the Notebook status report."""

from __future__ import annotations

import json
import os
import ssl
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .config import ReleaseConfig

REGISTRY_PATH = "/api/modules/releases/registry"
CHI_HIERARCHY_PATH = "/api/modules/releases/chi-hierarchy/data"
NOTEBOOK_COMPONENT_NAME = "Notebooks Images"


class OrgPulseClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get_json(self, path: str) -> dict:
        request = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage]
            f"{self.base_url}{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(  # ruff: ignore[suspicious-url-open-usage]
            request, timeout=30, context=ssl.create_default_context()
        ) as response:
            body = json.load(response)
        if not isinstance(body, dict):
            raise RuntimeError(f"Expected a JSON object from Org Pulse path: {path}")
        return body

    def release_registry(self) -> dict:
        return self.get_json(REGISTRY_PATH)

    def chi_hierarchy(self) -> dict:
        return self.get_json(CHI_HIERARCHY_PATH)

    def code_freezes(self, releases: Mapping[str, ReleaseConfig]) -> dict[str, str | None]:
        registry = self.release_registry()
        by_id = {
            str(release.get("id")): release for release in registry.get("releases", []) if isinstance(release, dict)
        }
        result: dict[str, str | None] = {}
        for release, config in releases.items():
            milestones = (by_id.get(f"rhoai-{release}") or {}).get("milestones", {})
            result[release] = milestones.get("codeFreeze") or config.code_freeze
        return result

    def chi_grades(self, releases: Mapping[str, ReleaseConfig]) -> dict[str, dict[str, int]]:
        hierarchy = self.chi_hierarchy()
        versions = hierarchy.get("environments", {}).get("latest", {}).get("versions", [])
        result = {release: {} for release in releases}
        for version in versions:
            release = str(version.get("id", "")).removeprefix("rhoai-")
            if release not in result:
                continue
            for component in version.get("components", []):
                if component.get("name") != NOTEBOOK_COMPONENT_NAME:
                    continue
                for image in component.get("images", []):
                    grade = image.get("grade") or "Unknown"
                    result[release][grade] = result[release].get(grade, 0) + 1
        return result


def org_pulse_client_from_env() -> OrgPulseClient:
    try:
        return OrgPulseClient(
            os.environ["ORG_PULSE_API_BASE"],
            os.environ["ORG_PULSE_TOKEN"],
        )
    except KeyError as error:
        raise SystemExit(f"Missing environment variable: {error.args[0]}") from error
