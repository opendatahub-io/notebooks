from __future__ import annotations

PUBLIC_INDEX_IMAGE_NAME_FRAGMENTS = ("codeserver-baseline-ubi9-python-",)


def is_public_index_image(image: str) -> bool:
    """Return True if the image uses the phase-1 public-index / PyPI-backed contract."""
    return any(fragment in image for fragment in PUBLIC_INDEX_IMAGE_NAME_FRAGMENTS)

