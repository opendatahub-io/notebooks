from __future__ import annotations

from tests.public_index_image_utils import is_public_index_image


def test_codeserver_baseline_ubi9_python_is_public_index() -> None:
    assert is_public_index_image(
        "quay.io/example/codeserver-baseline-ubi9-python-3.12:on-pr-deadbeef",
    )


def test_standard_codeserver_is_not_public_index() -> None:
    assert not is_public_index_image(
        "quay.io/example/codeserver-ubi9-python-3.12:on-pr-deadbeef",
    )

