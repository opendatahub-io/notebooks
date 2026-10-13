"""À-la-carte AIPCC base-image repository names and publish tags."""

from __future__ import annotations

import re

AIPCC_BASE_IMAGES_PREFIX = "quay.io/aipcc/base-images/"
_OS_SUFFIX = r"(?:el|ubi)\d+(?:\.\d+)?"
CHANNEL_IMAGE_NAME_RE = re.compile(
    rf"^(?P<channel>(?:cuda|rocm)\d+\.\d+-torch\d+\.\d+-{_OS_SUFFIX}|cpu(?:-notorch|-torch\d+\.\d+)-{_OS_SUFFIX})$"
)
RHDS_CHANNEL_TAG_RE = re.compile(r"^(?P<build>\d+)$")


def normalize_stream_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 2:
        raise ValueError(f"Expected major.minor stream version, got '{version}'")
    return f"{int(parts[0])}.{int(parts[1])}"


def normalize_torch_version(version: str) -> str:
    if version.count(".") == 1:
        return version
    parts = version.split(".")
    if len(parts) == 3:
        return f"{parts[0]}.{parts[1]}"
    raise ValueError(f"Expected torch version major.minor, got '{version}'")


def parse_channel_image_name(image_name: str) -> str | None:
    match = CHANNEL_IMAGE_NAME_RE.fullmatch(image_name)
    if match is None:
        return None
    return match.group("channel")


def is_channel_repository(repository: str) -> bool:
    if not repository.startswith(AIPCC_BASE_IMAGES_PREFIX):
        return False
    image_name = repository.removeprefix(AIPCC_BASE_IMAGES_PREFIX)
    return parse_channel_image_name(image_name) is not None


def build_channel_repository(
    accelerator: str,
    acc_version: str | None,
    torch_version: str,
    os_base: str,
    *,
    cpu_variant: str = "torch",
) -> str:
    torch_token = normalize_torch_version(torch_version)
    if accelerator == "cpu":
        suffix = f"cpu-notorch-{os_base}" if cpu_variant == "notorch" else f"cpu-torch{torch_token}-{os_base}"
        return f"{AIPCC_BASE_IMAGES_PREFIX}{suffix}"
    if acc_version is None:
        raise ValueError(f"acc_version is required for accelerator '{accelerator}'")
    acc = normalize_stream_version(acc_version)
    return f"{AIPCC_BASE_IMAGES_PREFIX}{accelerator}{acc}-torch{torch_token}-{os_base}"


def channel_tag_build(tag: str) -> int:
    match = RHDS_CHANNEL_TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError(f"Unsupported RHDS channel tag: {tag}")
    return int(match.group("build"))


def select_latest_channel_tag(tags: tuple[str, ...] | list[str], candidate_tag: str) -> str | None:
    numeric_tags = [tag for tag in tags if RHDS_CHANNEL_TAG_RE.fullmatch(tag)]
    if not numeric_tags:
        return None
    candidate_match = RHDS_CHANNEL_TAG_RE.fullmatch(candidate_tag)
    candidate_build = int(candidate_match.group("build")) if candidate_match else -1
    at_or_above = [tag for tag in numeric_tags if channel_tag_build(tag) >= candidate_build]
    pool = at_or_above if at_or_above else numeric_tags
    return max(pool, key=channel_tag_build)
