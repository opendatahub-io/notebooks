from __future__ import annotations

import os
import re

TAG_ENCODED_IMAGE_REPOSITORIES = {"workbench-images"}
PUBLIC_INDEX_IMAGE_NAME_PATTERN = re.compile(
    r"^(?:(?:codeserver|jupyter|runtime)-baseline|jupyter-universal)-ubi9-python-\d+\.\d+$"
)
PUBLIC_INDEX_IMAGE_TAG_PATTERN = re.compile(
    r"^(?:(?:codeserver|jupyter|runtime)-baseline|jupyter-universal)-ubi9-python-\d+\.\d+(?:[-_].*|$)"
)
# Hybrid: ODH public-index + RHOAI RH-index. Match make-target and published names.
_HYBRID_UNIVERSAL_RE = re.compile(r"jupyter-universal|workbench-jupyter-universal", re.IGNORECASE)


def _image_name_and_tag(image: str) -> tuple[str, str | None]:
    image_ref = image.split("@", maxsplit=1)[0]
    last_segment = image_ref.rsplit("/", maxsplit=1)[-1]
    image_name, separator, image_tag = last_segment.partition(":")
    if not separator:
        return image_name, None
    return image_name, image_tag


def _looks_like_rhoai_universal(image: str) -> bool:
    """RHOAI universal builds use RH-index, not the ODH public-index contract.

    Detect published names (``/rhoai/``, ``rhel9``) and GHA ``workbench-images``
    tags that encode the product matrix as ``_rhoai_`` (hybrid only — baseline
    images keep PyPI on both matrix legs and never reach this helper).
    """
    if not _HYBRID_UNIVERSAL_RE.search(image):
        return False
    lowered = image.lower()
    if "/rhoai/" in lowered or "rhel9" in lowered:
        return True
    # GHA tag: …-4741_merge_<sha>_rhoai_linux_amd64
    if "_rhoai_" in lowered:
        return True
    return os.environ.get("PRODUCT", "odh") == "rhoai"


def is_public_index_image(image: str) -> bool:
    """Return True if the image uses the phase-1 public-index / PyPI-backed contract.

    ``jupyter-universal`` is hybrid: ODH → public-index, RHOAI → RH-index (no PyPI).
    """
    if _looks_like_rhoai_universal(image):
        return False
    image_name, image_tag = _image_name_and_tag(image)
    if PUBLIC_INDEX_IMAGE_NAME_PATTERN.fullmatch(image_name):
        return True
    if image_name in TAG_ENCODED_IMAGE_REPOSITORIES and image_tag is not None:
        return PUBLIC_INDEX_IMAGE_TAG_PATTERN.fullmatch(image_tag) is not None
    return False
