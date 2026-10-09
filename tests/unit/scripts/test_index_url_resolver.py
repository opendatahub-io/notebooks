from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import scripts.index_url_resolver as resolver

CHANNEL_CUDA_IMAGE = (
    "quay.io/aipcc/base-images/cuda13.0-torch2.13-el9.8:1791476595"
    "@sha256:c4b7da6cd0b49ce7a62be010986c6cf745983e68cd408ec054edc74b11b26045"
)
CHANNEL_INDEX_URL = "https://packages.redhat.com/api/pypi/public-rhai/cuda13.0-torch2.13-el9.8-test/simple/"


def write_conf(
    tmp_path: Path,
    name: str,
    lines: list[str],
) -> Path:
    conf_file = Path(tmp_path) / name
    conf_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return conf_file


def make_skopeo_label_stub(label_url: str):
    def stub(base_image: str) -> str:
        return label_url

    return stub


def make_skopeo_inspect_fail_stub():
    def stub(base_image: str) -> str:
        raise resolver.IndexResolutionError(f"skopeo inspect failed for {base_image}")

    return stub


def assert_skopeo_inspect_cmd(cmd: list[str], base_image: str) -> None:
    assert cmd[:3] == ["skopeo", "inspect", "--retry-times"], f"unexpected skopeo prefix: {cmd}"
    digest_only = resolver.normalize_skopeo_image_reference(base_image)
    assert cmd[-1] == f"docker://{digest_only}", f"expected docker://{digest_only}, got {cmd[-1]!r}"


def test_normalize_skopeo_image_reference_strips_tag_when_digest_present() -> None:
    assert resolver.normalize_skopeo_image_reference(CHANNEL_CUDA_IMAGE) == (
        "quay.io/aipcc/base-images/cuda13.0-torch2.13-el9.8"
        "@sha256:c4b7da6cd0b49ce7a62be010986c6cf745983e68cd408ec054edc74b11b26045"
    )


def test_build_test_variant_url_for_channel_index() -> None:
    prod = "https://packages.redhat.com/api/pypi/public-rhai/cuda13.0-torch2.13-el9.8/simple/"
    expected = "https://packages.redhat.com/api/pypi/public-rhai/cuda13.0-torch2.13-el9.8-test/simple/"
    assert resolver.build_test_variant_url(prod) == expected


def test_validate_label_index_url_accepts_channel_path() -> None:
    resolver.validate_label_index_url(CHANNEL_INDEX_URL, CHANNEL_CUDA_IMAGE)


def test_validate_label_index_url_rejects_legacy_rhoai_path() -> None:
    legacy = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/"
    with pytest.raises(resolver.IndexResolutionError, match="unexpected path"):
        resolver.validate_label_index_url(legacy, CHANNEL_CUDA_IMAGE)


def test_parse_accelerator_accepts_channel_image_name() -> None:
    assert (
        resolver.parse_accelerator("cuda13.0-torch2.13-el9.8", Path("konflux.cuda.conf"))
        == "cuda13.0-torch2.13-el9.8"
    )


def test_resolve_cuda_channel_index_from_label(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cuda.conf",
        [
            f"BASE_IMAGE={CHANNEL_CUDA_IMAGE}",
            "PYLOCK_FLAVOR=cuda",
            "PRODUCT=rhoai",
            "RELEASE=3.6",
        ],
    )
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(CHANNEL_INDEX_URL))
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == CHANNEL_INDEX_URL)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.flavor == "cuda"
    assert resolved.accelerator == "cuda13.0-torch2.13-el9.8"
    assert resolved.release == "3.6"
    assert resolved.index_url == CHANNEL_INDEX_URL


def test_resolve_channel_base_image_fallback_uses_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cuda.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/cuda13.0-torch2.13-el9.8:1791476595",
            "PYLOCK_FLAVOR=cuda",
            "PRODUCT=rhoai",
            "RELEASE=3.6",
        ],
    )
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_inspect_fail_stub())
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == CHANNEL_INDEX_URL)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.index_url == CHANNEL_INDEX_URL
    assert resolved.release == "3.6"


def test_reject_legacy_cuda_repository_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cuda.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.8:3.6.0-1791476877",
            "PYLOCK_FLAVOR=cuda",
            "PRODUCT=rhoai",
            "RELEASE=3.6",
        ],
    )
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_inspect_fail_stub())

    with pytest.raises(resolver.IndexResolutionError, match="Unsupported à-la-carte"):
        resolver.resolve_index_config(conf_file)


def test_inspect_base_image_index_url_parses_config_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    skopeo_output = json.dumps(
        {
            "config": {
                "Labels": {
                    "com.redhat.aiplatform.index_url": CHANNEL_INDEX_URL,
                }
            }
        }
    )

    def fake_run(cmd, **kwargs):
        assert_skopeo_inspect_cmd(cmd, CHANNEL_CUDA_IMAGE)

        class FakeResult:
            returncode = 0
            stdout = skopeo_output
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = resolver.inspect_base_image_index_url(CHANNEL_CUDA_IMAGE)
    assert result == CHANNEL_INDEX_URL


def test_cli_prints_plain_index_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cuda.conf",
        [
            f"BASE_IMAGE={CHANNEL_CUDA_IMAGE}",
            "PYLOCK_FLAVOR=cuda",
            "PRODUCT=rhoai",
            "RELEASE=3.6",
        ],
    )
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(CHANNEL_INDEX_URL))
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == CHANNEL_INDEX_URL)

    runner = CliRunner()
    result = runner.invoke(resolver.app, ["index-url", str(conf_file)])

    assert result.exit_code == 0, f"CLI failed: {result.stdout} {result.exception}"
    assert result.stdout.strip() == CHANNEL_INDEX_URL
