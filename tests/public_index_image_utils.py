from __future__ import annotations

import re

TAG_ENCODED_IMAGE_REPOSITORIES = {"workbench-images"}
PUBLIC_INDEX_IMAGE_NAME_PATTERN = re.compile(r"^(codeserver|jupyter)-baseline-ubi9-python-\d+\.\d+$")
PUBLIC_INDEX_IMAGE_TAG_PATTERN = re.compile(r"^(codeserver|jupyter)-baseline-ubi9-python-\d+\.\d+(?:[-_].*|$)")


def _image_name_and_tag(image: str) -> tuple[str, str | None]:
    image_ref = image.split("@", maxsplit=1)[0]
    last_segment = image_ref.rsplit("/", maxsplit=1)[-1]
    image_name, separator, image_tag = last_segment.partition(":")
    if not separator:
        return image_name, None
    return image_name, image_tag


def is_public_index_image(image: str) -> bool:
    """Return True if the image uses the phase-1 public-index / PyPI-backed contract."""
    image_name, image_tag = _image_name_and_tag(image)
    if PUBLIC_INDEX_IMAGE_NAME_PATTERN.fullmatch(image_name):
        return True
    if image_name in TAG_ENCODED_IMAGE_REPOSITORIES and image_tag is not None:
        return PUBLIC_INDEX_IMAGE_TAG_PATTERN.fullmatch(image_tag) is not None
    return False
