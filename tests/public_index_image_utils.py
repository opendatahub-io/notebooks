from __future__ import annotations

import re

PUBLIC_INDEX_IMAGE_NAME_PATTERNS = (r"codeserver-baseline-ubi9-python-\d+\.\d+",)


def _normalized_image_name(image: str) -> str:
    image_name = image.rsplit("/", maxsplit=1)[-1]
    image_name = image_name.split("@", maxsplit=1)[0]
    return image_name.rsplit(":", maxsplit=1)[0]


def is_public_index_image(image: str) -> bool:
    """Return True if the image uses the phase-1 public-index / PyPI-backed contract."""
    image_name = _normalized_image_name(image)
    return any(re.fullmatch(pattern, image_name) for pattern in PUBLIC_INDEX_IMAGE_NAME_PATTERNS)
