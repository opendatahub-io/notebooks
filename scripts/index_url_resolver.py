#!/usr/bin/env python3

from __future__ import annotations

import re
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


_BASE_IMAGE_RE = re.compile(
    r"^quay\.io/aipcc/base-images/(?P<image>[^:]+):(?P<tag>[^:]+)$",
)
_ACCELERATOR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^cpu$"), "cpu"),
    (re.compile(r"^cuda-(?P<version>\d+\.\d+)-el\d+(?:\.\d+)?$"), "cuda"),
    (re.compile(r"^rocm-(?P<version>\d+\.\d+)-el\d+(?:\.\d+)?$"), "rocm"),
)
_TAG_RE = re.compile(r"^(?P<minor>\d+\.\d+)\.\d+(?:-ea\.(?P<ea>\d+))?(?:[-.].+)?$")

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


def parse_accelerator(image_name: str, conf_file: Path) -> str:
    for pattern, prefix in _ACCELERATOR_PATTERNS:
        match = pattern.fullmatch(image_name)
        if not match:
            continue
        version = match.groupdict().get("version")
        return prefix if version is None else f"{prefix}{version}"
    raise IndexResolutionError(f"Unsupported BASE_IMAGE accelerator in {conf_file}: {image_name}")


def parse_release(tag: str, conf_file: Path) -> str:
    match = _TAG_RE.fullmatch(tag)
    if match is None:
        raise IndexResolutionError(f"Unsupported BASE_IMAGE tag in {conf_file}: {tag}")
    release = match.group("minor")
    ea = match.group("ea")
    return release if ea is None else f"{release}-EA{int(ea)}"


def build_rhoai_index_url(*, release: str, accelerator: str) -> str:
    return f"{RHOAI_INDEX_ROOT}/{release}/{accelerator}-ubi9/simple/"


# ROCm workbench locks stay on EA2 rocm7.1 until tensorflow_rocm lands on rocm7.14,
# but pandoc-rhai wheels are published on the stable rocm7.14 production index.
PANDOC_ROCM_ACCELERATOR = "rocm7.14"


def stable_rhoai_release(release: str) -> str:
    """Drop EA suffix so pandoc resolves from stable 3.5 profiles, not 3.5-EA2."""
    return release.split("-EA", maxsplit=1)[0]


def resolve_pandoc_index_url(resolved: ResolvedIndexConfig) -> str:
    """RHAI index URL for pandoc-rhai (may differ from the lock default index)."""
    if resolved.accelerator.startswith("rocm"):
        return build_rhoai_index_url(
            release=stable_rhoai_release(resolved.release),
            accelerator=PANDOC_ROCM_ACCELERATOR,
        )
    return build_rhoai_index_url(
        release=stable_rhoai_release(resolved.release),
        accelerator=resolved.accelerator,
    )


def build_rhoai_test_index_url(*, release: str, accelerator: str) -> str:
    return f"{RHOAI_INDEX_ROOT}/{release}/{accelerator}-ubi9-test/simple/"


def index_url_candidates(*, release: str, accelerator: str) -> tuple[str, str]:
    return (
        build_rhoai_index_url(release=release, accelerator=accelerator),
        build_rhoai_test_index_url(release=release, accelerator=accelerator),
    )


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

    match = _BASE_IMAGE_RE.fullmatch(base_image)
    if match is None:
        raise IndexResolutionError(f"Unsupported BASE_IMAGE format in {conf_file}: {base_image}")

    accelerator = parse_accelerator(match.group("image"), conf_file)
    release = parse_release(match.group("tag"), conf_file)
    flavor = resolve_flavor(conf_file, entries)
    production_url, test_url = index_url_candidates(release=release, accelerator=accelerator)

    if index_url_exists(production_url):
        selected_index_url = production_url
    elif index_url_exists(test_url):
        selected_index_url = test_url
    else:
        raise IndexResolutionError(
            f"Neither production nor -test RH index is available for {conf_file}: "
            f"{production_url} / {test_url}"
        )

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
