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


def test_workbench_images_tag_encoded_baseline_is_public_index() -> None:
    assert is_public_index_image(
        "ghcr.io/opendatahub-io/notebooks/workbench-images:"
        "codeserver-baseline-ubi9-python-3.12-4304_merge_9b9123b_rhoai_linux_amd64",
    )


def test_workbench_images_tag_encoded_standard_codeserver_is_not_public_index() -> None:
    assert not is_public_index_image(
        "ghcr.io/opendatahub-io/notebooks/workbench-images:"
        "codeserver-ubi9-python-3.12-4304_merge_9b9123b_rhoai_linux_amd64",
    )
