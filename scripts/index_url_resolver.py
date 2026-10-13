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

from scripts.aipcc_channel_images import parse_channel_image_name

RHAI_PYPI_API_ROOT = "https://packages.redhat.com/api/pypi/public-rhai"
_RHAI_PYPI_PATH_PREFIX = "/api/pypi/public-rhai/"
INDEX_CHECK_TIMEOUT_SECONDS = 5.0
INDEX_URL_LABEL = "com.redhat.aiplatform.index_url"
SKOPEO_TIMEOUT_SECONDS = 60

_RHOAI_CHANNEL_INDEX_PATH_RE = re.compile(
    r"/public-rhai/(?P<channel>[^/]+)/simple/?$",
)
# Accepts tag (:build), digest (@sha256:…), or tag+digest (:build@sha256:…).
_BASE_IMAGE_RE = re.compile(
    r"^quay\.io/aipcc/base-images/(?P<image>[^:@]+)(?::(?P<tag>[^@]+)(?:@sha256:[0-9a-f]+)?|@sha256:[0-9a-f]+)$",
)
_RELEASE_OVERRIDE_RE = re.compile(r"^(?P<minor>\d+\.\d+)(?:-EA(?P<ea>\d+))?$")

app = typer.Typer(add_completion=False, no_args_is_help=True)


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


def is_unexpanded_label_index_url(index_url: str) -> bool:
    """Return True when a label still contains build-time placeholders."""
    return "${" in index_url


def normalize_skopeo_image_reference(base_image: str) -> str:
    """Skopeo cannot inspect references that include both a tag and a digest."""
    digest_match = re.search(r"@sha256:[0-9a-f]+", base_image)
    if digest_match is None:
        return base_image
    prefix = base_image[: digest_match.start()]
    digest = base_image[digest_match.start() :]
    if ":" in prefix:
        return f"{prefix.rsplit(':', 1)[0]}{digest}"
    return base_image


def parse_accelerator(image_name: str, conf_file: Path) -> str:
    if channel := parse_channel_image_name(image_name):
        return channel
    raise IndexResolutionError(f"Unsupported à-la-carte BASE_IMAGE in {conf_file}: {image_name}")


def _format_release(minor: str, ea: str | None) -> str:
    return minor if ea is None else f"{minor}-EA{int(ea)}"


def parse_release_override(release: str, conf_file: Path) -> str:
    """Normalize RELEASE from a build-args conf (consuming product version)."""
    match = _RELEASE_OVERRIDE_RE.fullmatch(release)
    if match is None:
        raise IndexResolutionError(f"Unsupported RELEASE in {conf_file}: {release}")
    return _format_release(match.group("minor"), match.group("ea"))


def build_channel_index_url(channel: str, *, test: bool = False) -> str:
    segment = f"{channel}-test" if test else channel
    return f"{RHAI_PYPI_API_ROOT}/{segment}/simple/"


def channel_index_url_candidates(channel: str) -> tuple[str, str]:
    return (
        build_channel_index_url(channel, test=False),
        build_channel_index_url(channel, test=True),
    )


def inspect_base_image_index_url(base_image: str) -> str:
    """Extract the index URL from the base image's com.redhat.aiplatform.index_url label via skopeo."""
    skopeo_ref = normalize_skopeo_image_reference(base_image)
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
                f"docker://{skopeo_ref}",
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
    expected_prefix = urlparse(RHAI_PYPI_API_ROOT)
    if parsed.scheme != "https":
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unsupported scheme: {index_url}")
    if parsed.netloc != expected_prefix.netloc:
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unexpected host: {index_url}")
    match = _RHOAI_CHANNEL_INDEX_PATH_RE.search(parsed.path)
    if match is None:
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unexpected path: {index_url}")
    channel = match.group("channel")
    if channel == "rhoai" or channel.startswith("rhoai/"):
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has deprecated path: {index_url}")


def build_test_variant_url(index_url: str) -> str | None:
    """Derive the -test fallback URL from a production channel index URL."""
    parsed = urlparse(index_url)
    path = parsed.path
    channel_match = _RHOAI_CHANNEL_INDEX_PATH_RE.search(path)
    if channel_match is None:
        return None
    channel = channel_match.group("channel")
    if channel.endswith("-test"):
        return None
    test_path = path.replace(f"/{channel}/simple", f"/{channel}-test/simple", 1)
    if test_path == path:
        return None
    return urlunparse(parsed._replace(path=test_path))


def parse_channel_from_index_url(index_url: str) -> str:
    """Return the channel id from an à-la-carte index URL (production or -test)."""
    parsed = urlparse(index_url)
    match = _RHOAI_CHANNEL_INDEX_PATH_RE.search(parsed.path)
    if match is None:
        raise IndexResolutionError(f"Cannot extract channel from index URL: {index_url}")
    channel = match.group("channel")
    if channel.endswith("-test"):
        return channel.removesuffix("-test")
    return channel


def ensure_json_format_param(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["format"] = ["json"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def validated_index_probe_url(index_url: str) -> str:
    probe_url = ensure_json_format_param(index_url)
    parsed = urlparse(probe_url)
    expected_prefix = urlparse(RHAI_PYPI_API_ROOT)
    if parsed.scheme != "https":
        raise IndexResolutionError(f"Unsupported index URL scheme for availability probe: {index_url}")
    if parsed.netloc != expected_prefix.netloc:
        raise IndexResolutionError(f"Unsupported index URL host for availability probe: {index_url}")
    if not parsed.path.startswith(_RHAI_PYPI_PATH_PREFIX):
        raise IndexResolutionError(f"Unsupported index URL path for availability probe: {index_url}")
    return probe_url


@cache
def index_url_exists(index_url: str) -> bool:
    request = Request(validated_index_probe_url(index_url), method="HEAD")  # ruff: ignore[suspicious-url-open-usage]
    try:
        with urlopen(request, timeout=INDEX_CHECK_TIMEOUT_SECONDS) as response:  # ruff: ignore[suspicious-url-open-usage]
            return 200 <= response.status < 400
    except HTTPError:
        return False
    except URLError:
        return False


def _select_index_url_from_label(label_url: str, conf_file: Path) -> str:
    checked_urls: list[str] = [label_url]
    if index_url_exists(label_url):
        return label_url

    test_url = build_test_variant_url(label_url)
    if test_url is not None:
        checked_urls.append(test_url)
        if index_url_exists(test_url):
            return test_url

    raise IndexResolutionError(
        f"No production or -test RH index is available for {conf_file}: " + " / ".join(checked_urls)
    )


def _resolve_from_label(
    base_image: str,
    conf_file: Path,
    *,
    flavor: str,
    product: str,
    release_override: str | None = None,
) -> ResolvedIndexConfig | None:
    try:
        label_url = inspect_base_image_index_url(base_image)
        if is_unexpanded_label_index_url(label_url):
            return None
        validate_label_index_url(label_url, base_image)
    except IndexResolutionError:
        return None

    if not release_override:
        return None

    selected_index_url = _select_index_url_from_label(label_url, conf_file)
    release = parse_release_override(release_override, conf_file)
    channel = parse_channel_from_index_url(selected_index_url)

    return ResolvedIndexConfig(
        conf_file=conf_file,
        product=product,
        index_profile="rhoai",
        flavor=flavor,
        base_image=base_image,
        accelerator=channel,
        release=release,
        index_url=selected_index_url,
    )


def _resolve_from_base_image_ref(
    base_image: str,
    conf_file: Path,
    *,
    flavor: str,
    product: str,
    release_override: str | None = None,
) -> ResolvedIndexConfig:
    match = _BASE_IMAGE_RE.fullmatch(base_image)
    if match is None:
        raise IndexResolutionError(f"Unsupported BASE_IMAGE format in {conf_file}: {base_image}")

    image_name = match.group("image")
    channel = parse_channel_image_name(image_name)
    if channel is None:
        raise IndexResolutionError(f"Unsupported à-la-carte BASE_IMAGE in {conf_file}: {image_name}")
    if not release_override:
        raise IndexResolutionError(
            f"Channel BASE_IMAGE in {conf_file} requires RELEASE for index resolution: {base_image}"
        )
    release = parse_release_override(release_override, conf_file)
    production_url, test_url = channel_index_url_candidates(channel)
    checked_urls = [production_url, test_url]
    selected_index_url = next((url for url in checked_urls if index_url_exists(url)), None)
    if selected_index_url is None:
        raise IndexResolutionError(
            f"No production or -test RH index is available for {conf_file}: " + " / ".join(checked_urls)
        )
    return ResolvedIndexConfig(
        conf_file=conf_file,
        product=product,
        index_profile="rhoai",
        flavor=flavor,
        base_image=base_image,
        accelerator=channel,
        release=release,
        index_url=selected_index_url,
    )


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

    flavor = resolve_flavor(conf_file, entries)
    release_override = entries.get("RELEASE")

    if resolved := _resolve_from_label(
        base_image,
        conf_file,
        flavor=flavor,
        product=product,
        release_override=release_override,
    ):
        return resolved

    return _resolve_from_base_image_ref(
        base_image,
        conf_file,
        flavor=flavor,
        product=product,
        release_override=release_override,
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
