from __future__ import annotations

from scripts.aipcc_channel_images import (
    build_channel_repository,
    parse_channel_image_name,
    select_latest_channel_tag,
)


def test_build_channel_repository_cuda() -> None:
    repo = build_channel_repository("cuda", "13.0", "2.13", "el9.8")
    assert repo == "quay.io/aipcc/base-images/cuda13.0-torch2.13-el9.8"


def test_parse_channel_image_name_round_trip() -> None:
    name = "cuda12.9-torch2.13-el9.8"
    assert parse_channel_image_name(name) == name


def test_select_latest_channel_tag_prefers_higher_build() -> None:
    latest = select_latest_channel_tag(("1777919000", "1777920000"), "1777919771")
    assert latest == "1777920000"
