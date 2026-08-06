from __future__ import annotations

from tests.public_index_image_utils import is_public_index_image


def test_codeserver_baseline_ubi9_python_is_public_index() -> None:
    assert is_public_index_image(
        "quay.io/example/codeserver-baseline-ubi9-python-3.12:on-pr-deadbeef",
    )


def test_codeserver_baseline_ubi9_python_with_digest_is_public_index() -> None:
    assert is_public_index_image(
        "quay.io/example/codeserver-baseline-ubi9-python-3.12:on-pr-deadbeef@sha256:deadbeef",
    )


def test_standard_codeserver_is_not_public_index() -> None:
    assert not is_public_index_image(
        "quay.io/example/codeserver-ubi9-python-3.12:on-pr-deadbeef",
    )


def test_standard_codeserver_tag_named_like_baseline_is_not_public_index() -> None:
    assert not is_public_index_image(
        "quay.io/example/codeserver-ubi9-python-3.12:codeserver-baseline-ubi9-python-3.12",
    )


def test_registry_path_named_like_baseline_is_not_public_index() -> None:
    assert not is_public_index_image(
        "quay.io/example/codeserver-baseline-ubi9-python-3.12/codeserver-ubi9-python-3.12:latest",
    )


def test_lookalike_baseline_name_is_not_public_index() -> None:
    assert not is_public_index_image(
        "quay.io/example/codeserver-baseline-ubi9-python-3.12-extra:latest",
    )
