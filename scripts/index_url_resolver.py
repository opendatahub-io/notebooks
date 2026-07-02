#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import typer

RHOAI_INDEX_ROOT = "https://packages.redhat.com/api/pypi/public-rhai/rhoai"
INDEX_CHECK_TIMEOUT_SECONDS = 5.0
INDEX_URL_LABEL = "com.redhat.aiplatform.index_url"
SKOPEO_TIMEOUT_SECONDS = 60


class IndexResolutionError(ValueError):
    """Raised when a build-args config cannot be resolved into an index URL."""


@dataclass(frozen=True)
class ResolvedIndexConfig:
    conf_file: Path
    product: str
    index_profile: str
    flavor: str
    base_image: str
    accelerator: str
    release: str
    index_url: str


_RHOAI_INDEX_PATH_RE = re.compile(
    r"/rhoai/(?P<release>[^/]+)/(?P<accelerator>[^/]+)-ubi9(?:-test)?/simple/?$",
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def read_conf_file(conf_file: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in conf_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        entries[key.strip()] = value.strip()
    return entries


def is_konflux_conf(conf_file: Path) -> bool:
    return conf_file.name.startswith("konflux.")


def resolve_product(conf_file: Path, entries: dict[str, str]) -> str:
    product = entries.get("PRODUCT")
    if product:
        return product
    if is_konflux_conf(conf_file):
        return "rhoai"
    raise IndexResolutionError(f"PRODUCT is missing in {conf_file}")


def resolve_flavor(conf_file: Path, entries: dict[str, str]) -> str:
    if flavor := entries.get("PYLOCK_FLAVOR"):
        return flavor

    stem = conf_file.stem
    if stem.startswith("konflux."):
        return stem.removeprefix("konflux.")
    return stem


def inspect_base_image_index_url(base_image: str) -> str:
    """Extract the index URL from the base image's com.redhat.aiplatform.index_url label via skopeo."""
    try:
        result = subprocess.run(
            [
                "skopeo",
                "inspect",
                "--retry-times",
                "3",
                "--override-arch",
                "amd64",
                "--override-os",
                "linux",
                "--config",
                f"docker://{base_image}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=SKOPEO_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise IndexResolutionError(f"skopeo is not available; cannot inspect {base_image} for index URL label") from exc
    except subprocess.TimeoutExpired as exc:
        raise IndexResolutionError(f"skopeo inspect timed out for {base_image}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
        raise IndexResolutionError(f"skopeo inspect failed for {base_image}: {detail}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise IndexResolutionError(f"skopeo inspect returned invalid JSON for {base_image}: {exc}") from exc

    labels: dict[str, str] = {}
    for raw_labels in (
        payload.get("config", {}).get("Labels"),
        payload.get("Labels"),
    ):
        if isinstance(raw_labels, dict):
            labels.update({k: v for k, v in raw_labels.items() if isinstance(k, str) and isinstance(v, str)})

    index_url = labels.get(INDEX_URL_LABEL)
    if not index_url:
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label is missing from {base_image}")

    return index_url


def validate_label_index_url(index_url: str, base_image: str) -> None:
    """Validate that a label-provided index URL is well-formed and points to the expected host."""
    parsed = urlparse(index_url)
    expected_prefix = urlparse(RHOAI_INDEX_ROOT)
    if parsed.scheme != "https":
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unsupported scheme: {index_url}")
    if parsed.netloc != expected_prefix.netloc:
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unexpected host: {index_url}")
    if not parsed.path.startswith(expected_prefix.path):
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unexpected path: {index_url}")


def build_test_variant_url(index_url: str) -> str | None:
    """Derive the -test fallback URL from a production index URL.

    Production: .../rhoai/{release}/{accelerator}-ubi9/simple/
    Test:       .../rhoai/{release}/{accelerator}-ubi9-test/simple/
    """
    parsed = urlparse(index_url)
    path = parsed.path
    if "-ubi9-test/simple" in path:
        return None
    replaced = re.sub(r"-ubi9/simple(/?)$", r"-ubi9-test/simple\1", path)
    if replaced == path:
        return None
    return urlunparse(parsed._replace(path=replaced))


def parse_release_and_accelerator_from_url(index_url: str) -> tuple[str, str]:
    """Extract release and accelerator from a validated RHOAI index URL path."""
    parsed = urlparse(index_url)
    match = _RHOAI_INDEX_PATH_RE.search(parsed.path)
    if match is None:
        return ("", "")
    return (match.group("release"), match.group("accelerator"))


def ensure_json_format_param(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["format"] = ["json"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def validated_index_probe_url(index_url: str) -> str:
    probe_url = ensure_json_format_param(index_url)
    parsed = urlparse(probe_url)
    expected_prefix = urlparse(RHOAI_INDEX_ROOT)
    if parsed.scheme != "https":
        raise IndexResolutionError(f"Unsupported index URL scheme for availability probe: {index_url}")
    if parsed.netloc != expected_prefix.netloc:
        raise IndexResolutionError(f"Unsupported index URL host for availability probe: {index_url}")
    if not parsed.path.startswith(expected_prefix.path):
        raise IndexResolutionError(f"Unsupported index URL path for availability probe: {index_url}")
    return probe_url


@cache
def index_url_exists(index_url: str) -> bool:
    request = Request(validated_index_probe_url(index_url), method="HEAD")  # noqa: S310
    try:
        with urlopen(request, timeout=INDEX_CHECK_TIMEOUT_SECONDS) as response:  # noqa: S310
            return 200 <= response.status < 400
    except HTTPError:
        return False
    except URLError:
        return False


def resolve_index_config(
    conf_file: Path,
    *,
    require_konflux: bool = False,
) -> ResolvedIndexConfig:
    if not conf_file.is_file():
        raise IndexResolutionError(f"Config file not found: {conf_file}")
    if require_konflux and not is_konflux_conf(conf_file):
        raise IndexResolutionError(f"RH index resolution currently supports only konflux.*.conf files: {conf_file}")

    entries = read_conf_file(conf_file)
    product = resolve_product(conf_file, entries)
    if product != "rhoai":
        raise IndexResolutionError(f"Unsupported PRODUCT for dynamic RH index resolution in {conf_file}: {product}")

    base_image = entries.get("BASE_IMAGE")
    if not base_image:
        raise IndexResolutionError(f"BASE_IMAGE is missing in {conf_file}")

    label_url = inspect_base_image_index_url(base_image)
    validate_label_index_url(label_url, base_image)

    flavor = resolve_flavor(conf_file, entries)

    selected_index_url: str | None = None
    checked_urls: list[str] = []

    checked_urls.append(label_url)
    if index_url_exists(label_url):
        selected_index_url = label_url
    else:
        test_url = build_test_variant_url(label_url)
        if test_url is not None:
            checked_urls.append(test_url)
            if index_url_exists(test_url):
                selected_index_url = test_url

    if selected_index_url is None:
        raise IndexResolutionError(
            f"No production or -test RH index is available for {conf_file}: " + " / ".join(checked_urls)
        )

    release, accelerator = parse_release_and_accelerator_from_url(selected_index_url)

    return ResolvedIndexConfig(
        conf_file=conf_file,
        product=product,
        index_profile="rhoai",
        flavor=flavor,
        base_image=base_image,
        accelerator=accelerator,
        release=release,
        index_url=selected_index_url,
    )


@app.command("index-url")
def print_index_url(
    conf_file: Annotated[str, typer.Argument(help="Path to build-args config file")],
) -> None:
    typer.echo(resolve_index_config(Path(conf_file)).index_url)


@app.callback()
def main() -> None:
    """Resolve dynamic index URLs from build-args config files."""


if __name__ == "__main__":
    app()
