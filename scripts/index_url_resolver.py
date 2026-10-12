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

PUBLIC_RHAI_ROOT = "https://packages.redhat.com/api/pypi/public-rhai"
RHOAI_INDEX_ROOT = f"{PUBLIC_RHAI_ROOT}/rhoai"
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


# Legacy product-stream indexes: .../rhoai/{release}/{accelerator}-ubi9(-test)?/simple/
_RHOAI_INDEX_PATH_RE = re.compile(
    r"/rhoai/(?P<release>[^/]+)/(?P<accelerator>[^/]+)-ubi9(?:-test)?/simple/?$",
)
# À-la-carte channel indexes: .../public-rhai/{channel}(-test)?/simple/
# Channel tokens look like cpu-torch2.13-el9.8 / cuda13.0-torch2.13-el9.8 (not the legacy
# /rhoai/... tree, which has more path segments and is handled above).
_CHANNEL_INDEX_PATH_RE = re.compile(
    r"/public-rhai/(?P<channel>(?!rhoai(?:/|$))[^/]+?)(?:-test)?/simple/?$",
)
# Quay repo name for torch-channel bases (ADR-0016).
_CHANNEL_IMAGE_RE = re.compile(
    r"^(?P<accelerator>cpu|cuda\d+\.\d+|rocm\d+\.\d+|spyre)"
    r"(?:-torch[\d.]+|-notorch)?"
    r"(?:-el\d+(?:\.\d+)?)?$"
)
# Accepts tag (:3.5.0-…), digest (@sha256:…), or tag+digest (:3.5.0-…@sha256:…).
# Image name stops at : or @.
_BASE_IMAGE_RE = re.compile(
    r"^quay\.io/aipcc/base-images/(?P<image>[^:@]+)(?::(?P<tag>[^@]+)(?:@sha256:[0-9a-f]+)?|@sha256:[0-9a-f]+)$",
)
_RELEASE_OVERRIDE_RE = re.compile(r"^(?P<minor>\d+\.\d+)(?:-EA(?P<ea>\d+))?$")
# Legacy OS-suffixed repos (pre-torch-channel): cpu-el9.8, cuda-13.0-el9.8, rocm-7.14-el9.8
_LEGACY_ACCELERATOR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^cpu(?:-el\d+(?:\.\d+)?)?$"), "cpu"),
    (re.compile(r"^cuda-(?P<version>\d+\.\d+)-el\d+(?:\.\d+)?$"), "cuda"),
    (re.compile(r"^rocm-(?P<version>\d+\.\d+)-el\d+(?:\.\d+)?$"), "rocm"),
)
_TAG_RE = re.compile(r"^(?P<minor>\d+\.\d+)\.\d+(?:-ea\.(?P<ea>\d+))?(?:[-.].+)?$")
# Torch-channel image tags are build timestamps, optionally prefixed with the channel stem.
_CHANNEL_TAG_RE = re.compile(
    r"^(?:(?P<stem>[a-z0-9.]+(?:-torch[\d.]+)?)-)?(?P<build>\d+)$",
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


def is_unexpanded_label_index_url(index_url: str) -> bool:
    """Return True when a label still contains build-time placeholders."""
    return "${" in index_url


def is_channel_image(image_name: str) -> bool:
    """Return True for à-la-carte torch/notorch channel base-image repository names."""
    match = _CHANNEL_IMAGE_RE.fullmatch(image_name)
    if match is None:
        return False
    # Require torch/notorch token so bare legacy names like cpu / cpu-el9.8 stay legacy.
    return "-torch" in image_name or "-notorch" in image_name


def parse_accelerator(image_name: str, conf_file: Path) -> str:
    channel_match = _CHANNEL_IMAGE_RE.fullmatch(image_name)
    if channel_match is not None and is_channel_image(image_name):
        return channel_match.group("accelerator")

    for pattern, prefix in _LEGACY_ACCELERATOR_PATTERNS:
        match = pattern.fullmatch(image_name)
        if not match:
            continue
        version = match.groupdict().get("version")
        return prefix if version is None else f"{prefix}{version}"
    raise IndexResolutionError(f"Unsupported BASE_IMAGE accelerator in {conf_file}: {image_name}")


def accelerator_from_channel(channel: str) -> str:
    """Derive the accelerator token from an à-la-carte channel name."""
    match = _CHANNEL_IMAGE_RE.fullmatch(channel)
    if match is None:
        raise IndexResolutionError(f"Unsupported à-la-carte channel name: {channel}")
    return match.group("accelerator")


def _format_release(minor: str, ea: str | None) -> str:
    return minor if ea is None else f"{minor}-EA{int(ea)}"


def parse_release(tag: str, conf_file: Path) -> str:
    match = _TAG_RE.fullmatch(tag)
    if match is None:
        raise IndexResolutionError(f"Unsupported BASE_IMAGE tag in {conf_file}: {tag}")
    return _format_release(match.group("minor"), match.group("ea"))


def parse_release_override(release: str, conf_file: Path) -> str:
    """Normalize RELEASE from a build-args conf (used for digest-pinned BASE_IMAGE)."""
    match = _RELEASE_OVERRIDE_RE.fullmatch(release)
    if match is None:
        raise IndexResolutionError(f"Unsupported RELEASE in {conf_file}: {release}")
    return _format_release(match.group("minor"), match.group("ea"))


def build_rhoai_index_url(*, release: str, accelerator: str) -> str:
    return f"{RHOAI_INDEX_ROOT}/{release}/{accelerator}-ubi9/simple/"


def stable_rhoai_release(release: str) -> str:
    """Drop EA suffix when resolving ROCm indexes from stable 3.5 profiles."""
    return release.split("-EA", maxsplit=1)[0]


def build_rhoai_test_index_url(*, release: str, accelerator: str) -> str:
    return f"{RHOAI_INDEX_ROOT}/{release}/{accelerator}-ubi9-test/simple/"


def build_channel_index_url(*, channel: str) -> str:
    return f"{PUBLIC_RHAI_ROOT}/{channel}/simple/"


def build_channel_test_index_url(*, channel: str) -> str:
    return f"{PUBLIC_RHAI_ROOT}/{channel}-test/simple/"


def index_url_candidates(*, release: str, accelerator: str) -> tuple[str, str]:
    return (
        build_rhoai_index_url(release=release, accelerator=accelerator),
        build_rhoai_test_index_url(release=release, accelerator=accelerator),
    )


def channel_index_url_candidates(*, channel: str) -> tuple[str, str]:
    return (
        build_channel_index_url(channel=channel),
        build_channel_test_index_url(channel=channel),
    )


def skopeo_image_reference(base_image: str) -> str:
    """Normalize BASE_IMAGE for skopeo.

    Skopeo rejects references that include both a tag and a digest. When both are
    present, prefer the digest-only form so label inspection still works.
    """
    match = _BASE_IMAGE_RE.fullmatch(base_image)
    if match is None:
        return base_image
    digest_match = re.search(r"@(sha256:[0-9a-f]+)$", base_image)
    if digest_match is None or match.group("tag") is None:
        return base_image
    return f"quay.io/aipcc/base-images/{match.group('image')}@{digest_match.group(1)}"


def inspect_base_image_index_url(base_image: str) -> str:
    """Extract the index URL from the base image's com.redhat.aiplatform.index_url label via skopeo."""
    skopeo_ref = skopeo_image_reference(base_image)
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
    expected_prefix = urlparse(PUBLIC_RHAI_ROOT)
    if parsed.scheme != "https":
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unsupported scheme: {index_url}")
    if parsed.netloc != expected_prefix.netloc:
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unexpected host: {index_url}")
    if not parsed.path.startswith(expected_prefix.path + "/") and parsed.path != expected_prefix.path:
        raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unexpected path: {index_url}")
    if _RHOAI_INDEX_PATH_RE.search(parsed.path) is not None:
        return
    if _CHANNEL_INDEX_PATH_RE.search(parsed.path) is not None:
        return
    raise IndexResolutionError(f"{INDEX_URL_LABEL} label in {base_image} has unexpected path: {index_url}")


def build_test_variant_url(index_url: str) -> str | None:
    """Derive the -test fallback URL from a production index URL.

    Legacy production: .../rhoai/{release}/{accelerator}-ubi9/simple/
    Legacy test:       .../rhoai/{release}/{accelerator}-ubi9-test/simple/
    Channel production: .../public-rhai/{channel}/simple/
    Channel test:       .../public-rhai/{channel}-test/simple/
    """
    parsed = urlparse(index_url)
    path = parsed.path
    if "-ubi9-test/simple" in path:
        return None
    replaced = re.sub(r"-ubi9/simple(/?)$", r"-ubi9-test/simple\1", path)
    if replaced != path:
        return urlunparse(parsed._replace(path=replaced))

    channel_match = _CHANNEL_INDEX_PATH_RE.search(path)
    if channel_match is None:
        return None
    # Already a -test channel URL when the path segment ends with -test before /simple/
    channel = channel_match.group("channel")
    # If original path contains `{channel}-test/simple`, the regex strips -test into channel.
    # Detect already-test by seeing whether the matched segment in the path ends with -test.
    segment = path[channel_match.start("channel") : path.index("/simple")]
    if segment.endswith("-test"):
        return None
    return urlunparse(parsed._replace(path=path.replace(f"/{channel}/simple", f"/{channel}-test/simple", 1)))


def parse_release_and_accelerator_from_url(index_url: str) -> tuple[str, str]:
    """Extract release and accelerator from a validated RHOAI index URL path.

    For legacy indexes, release is the product stream (e.g. ``3.5-EA2``).
    For à-la-carte channel indexes, release is the channel token
    (e.g. ``cpu-torch2.13-el9.8``).
    """
    parsed = urlparse(index_url)
    legacy = _RHOAI_INDEX_PATH_RE.search(parsed.path)
    if legacy is not None:
        return (legacy.group("release"), legacy.group("accelerator"))

    channel_match = _CHANNEL_INDEX_PATH_RE.search(parsed.path)
    if channel_match is None:
        raise IndexResolutionError(f"Cannot extract release/accelerator from index URL: {index_url}")
    channel = channel_match.group("channel")
    return (channel, accelerator_from_channel(channel))


def ensure_json_format_param(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["format"] = ["json"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def validated_index_probe_url(index_url: str) -> str:
    probe_url = ensure_json_format_param(index_url)
    parsed = urlparse(probe_url)
    expected_prefix = urlparse(PUBLIC_RHAI_ROOT)
    if parsed.scheme != "https":
        raise IndexResolutionError(f"Unsupported index URL scheme for availability probe: {index_url}")
    if parsed.netloc != expected_prefix.netloc:
        raise IndexResolutionError(f"Unsupported index URL host for availability probe: {index_url}")
    if not parsed.path.startswith(expected_prefix.path):
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
) -> ResolvedIndexConfig | None:
    try:
        label_url = inspect_base_image_index_url(base_image)
        if is_unexpanded_label_index_url(label_url):
            return None
        validate_label_index_url(label_url, base_image)
    except IndexResolutionError:
        return None

    selected_index_url = _select_index_url_from_label(label_url, conf_file)
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


def _resolve_channel_from_base_image_ref(
    *,
    image_name: str,
    conf_file: Path,
    flavor: str,
    product: str,
    base_image: str,
) -> ResolvedIndexConfig:
    """Resolve index URL when BASE_IMAGE is an à-la-carte torch-channel repository."""
    channel = image_name
    accelerator = parse_accelerator(image_name, conf_file)
    selected_index_url: str | None = None
    checked_urls: list[str] = []
    for candidate_url in channel_index_url_candidates(channel=channel):
        checked_urls.append(candidate_url)
        if index_url_exists(candidate_url):
            selected_index_url = candidate_url
            break

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
        accelerator=accelerator,
        release=channel,
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
    if is_channel_image(image_name):
        tag = match.group("tag")
        if tag is not None and _CHANNEL_TAG_RE.fullmatch(tag) is None and _TAG_RE.fullmatch(tag) is None:
            raise IndexResolutionError(f"Unsupported BASE_IMAGE tag in {conf_file}: {tag}")
        return _resolve_channel_from_base_image_ref(
            image_name=image_name,
            conf_file=conf_file,
            flavor=flavor,
            product=product,
            base_image=base_image,
        )

    accelerator = parse_accelerator(image_name, conf_file)
    tag = match.group("tag")
    if tag is not None:
        release = parse_release(tag, conf_file)
    elif release_override:
        release = parse_release_override(release_override, conf_file)
    else:
        raise IndexResolutionError(
            f"Digest-pinned BASE_IMAGE in {conf_file} requires RELEASE for index resolution fallback: {base_image}"
        )
    release_candidates = [release]
    if accelerator.startswith("rocm"):
        stable = stable_rhoai_release(release)
        if stable != release:
            release_candidates.insert(0, stable)

    selected_index_url: str | None = None
    checked_urls: list[str] = []
    for release_candidate in release_candidates:
        production_url, test_url = index_url_candidates(
            release=release_candidate,
            accelerator=accelerator,
        )
        for candidate_url in (production_url, test_url):
            checked_urls.append(candidate_url)
            if index_url_exists(candidate_url):
                selected_index_url = candidate_url
                break
        if selected_index_url is not None:
            break

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
        accelerator=accelerator,
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

    if resolved := _resolve_from_label(
        base_image,
        conf_file,
        flavor=flavor,
        product=product,
    ):
        return resolved

    return _resolve_from_base_image_ref(
        base_image,
        conf_file,
        flavor=flavor,
        product=product,
        release_override=entries.get("RELEASE"),
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
