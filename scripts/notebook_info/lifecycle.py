"""Red Hat product lifecycle dates for the Notebook status report."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

PRODUCT_NAME = "Red Hat OpenShift AI Self-Managed"
LIFECYCLE_API = "https://access.redhat.com/product-life-cycles/api/v1/products"
FULL_SUPPORT = "Full support"
EXTENDED_SUPPORT = "Extended update support"


@dataclass(frozen=True)
class SupportWindow:
    full_support_end: str | None
    extended_support_end: str | None


def _phase_end(phase: dict) -> str | None:
    if phase.get("end_date_format") != "date":
        return None
    end_date = phase.get("end_date")
    if not isinstance(end_date, str) or len(end_date) < 10:
        return None
    return end_date[:10]


def support_windows_from_payload(payload: dict, versions: set[str]) -> dict[str, SupportWindow | None]:
    published: dict[str, SupportWindow] = {}
    for product in payload.get("data", []):
        if not isinstance(product, dict) or product.get("name") != PRODUCT_NAME:
            continue
        for version in product.get("versions", []):
            if not isinstance(version, dict):
                continue
            name = str(version.get("name", ""))
            if name not in versions:
                continue
            full_end = None
            extended_end = None
            for phase in version.get("phases", []):
                if not isinstance(phase, dict):
                    continue
                if phase.get("name") == FULL_SUPPORT:
                    full_end = _phase_end(phase)
                elif phase.get("name") == EXTENDED_SUPPORT:
                    extended_end = _phase_end(phase)
            published[name] = SupportWindow(full_end, extended_end)
    return {version: published.get(version) for version in versions}


def fetch_support_windows(versions: set[str]) -> dict[str, SupportWindow | None]:
    request = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage]
        f"{LIFECYCLE_API}?{urllib.parse.urlencode({'name': PRODUCT_NAME})}",
        headers={"Accept": "application/json", "User-Agent": "notebook-info"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage]
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("Expected a JSON object from the product lifecycle API")
    return support_windows_from_payload(payload, versions)
