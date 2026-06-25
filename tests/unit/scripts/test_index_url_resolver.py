from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import scripts.index_url_resolver as resolver


def write_conf(
    tmp_path: Path,
    name: str,
    lines: list[str],
) -> Path:
    conf_file = Path(tmp_path) / name
    conf_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return conf_file


def prod_index_url(*, release: str, accelerator: str) -> str:
    return f"https://packages.redhat.com/api/pypi/public-rhai/rhoai/{release}/{accelerator}-ubi9/simple/"


def test_index_url_candidates_use_prod_then_test_suffix() -> None:
    assert resolver.index_url_candidates(release="3.5-EA2", accelerator="cpu") == (
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/",
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/",
    )


def test_resolve_rhoai_cpu_index_from_konflux_conf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cpu.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1778762488",
            "PYLOCK_FLAVOR=cpu",
            "PRODUCT=rhoai",
        ],
    )
    monkeypatch.setattr(
        resolver,
        "index_url_exists",
        lambda url: url == prod_index_url(release="3.5-EA2", accelerator="cpu"),
    )

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.product == "rhoai"
    assert resolved.index_profile == "rhoai"
    assert resolved.flavor == "cpu"
    assert resolved.accelerator == "cpu"
    assert resolved.release == "3.5-EA2"
    assert resolved.index_url == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/"


def test_resolve_rhoai_cuda_index_from_konflux_conf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cuda.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1778760737",
            "PYLOCK_FLAVOR=cuda",
            "PRODUCT=rhoai",
        ],
    )
    monkeypatch.setattr(
        resolver,
        "index_url_exists",
        lambda url: url == prod_index_url(release="3.5-EA2", accelerator="cuda13.0"),
    )

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.flavor == "cuda"
    assert resolved.accelerator == "cuda13.0"
    assert resolved.release == "3.5-EA2"
    assert resolved.index_url == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cuda13.0-ubi9/simple/"


def test_resolve_rhoai_rocm_index_from_konflux_conf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.rocm.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/rocm-7.1-el9.6:3.5.0-ea.2-1778760581",
            "PYLOCK_FLAVOR=rocm",
            "PRODUCT=rhoai",
        ],
    )
    monkeypatch.setattr(
        resolver,
        "index_url_exists",
        lambda url: url == prod_index_url(release="3.5-EA2", accelerator="rocm7.1"),
    )

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.flavor == "rocm"
    assert resolved.accelerator == "rocm7.1"
    assert resolved.release == "3.5-EA2"
    assert resolved.index_url == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/rocm7.1-ubi9/simple/"


def test_reject_non_konflux_conf_when_required(tmp_path: Path) -> None:
    conf_file = write_conf(
        tmp_path,
        "cpu.conf",
        [
            "BASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest",
            "PYLOCK_FLAVOR=cpu",
            "PRODUCT=odh",
        ],
    )

    with pytest.raises(resolver.IndexResolutionError, match="konflux"):
        resolver.resolve_index_config(conf_file, require_konflux=True)


def test_resolve_rhoai_falls_back_to_test_index_when_prod_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cpu.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1778762488",
            "PYLOCK_FLAVOR=cpu",
            "PRODUCT=rhoai",
        ],
    )

    checked_urls: list[str] = []

    def fake_index_url_exists(url: str) -> bool:
        checked_urls.append(url)
        return url.endswith("/cpu-ubi9-test/simple/")

    monkeypatch.setattr(resolver, "index_url_exists", fake_index_url_exists)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.index_url == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    assert checked_urls == [
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/",
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/",
    ]


def test_resolve_rhoai_does_not_check_test_when_prod_is_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cpu.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1778762488",
            "PYLOCK_FLAVOR=cpu",
            "PRODUCT=rhoai",
        ],
    )

    checked_urls: list[str] = []

    def fake_index_url_exists(url: str) -> bool:
        checked_urls.append(url)
        return url.endswith("/cpu-ubi9/simple/")

    monkeypatch.setattr(resolver, "index_url_exists", fake_index_url_exists)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.index_url == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/"
    assert checked_urls == [
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/",
    ]


def test_resolve_pandoc_index_url_cuda_uses_matching_accelerator() -> None:
    resolved = resolver.ResolvedIndexConfig(
        conf_file=Path("konflux.cuda.conf"),
        product="rhoai",
        index_profile="rhoai",
        flavor="cuda",
        base_image="quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-1782270034",
        accelerator="cuda13.0",
        release="3.5",
        index_url=prod_index_url(release="3.5", accelerator="cuda13.0"),
    )

    assert resolver.resolve_pandoc_index_url(resolved) == prod_index_url(
        release="3.5",
        accelerator="cuda13.0",
    )


def test_resolve_pandoc_index_url_rocm_uses_rocm714_production_index() -> None:
    resolved = resolver.ResolvedIndexConfig(
        conf_file=Path("konflux.rocm.conf"),
        product="rhoai",
        index_profile="rhoai",
        flavor="rocm",
        base_image="quay.io/aipcc/base-images/rocm-7.1-el9.6:3.5.0-ea.2-1780597719",
        accelerator="rocm7.1",
        release="3.5-EA2",
        index_url="https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/rocm7.1-ubi9-test/simple/",
    )

    assert resolver.resolve_pandoc_index_url(resolved) == prod_index_url(
        release="3.5",
        accelerator="rocm7.14",
    )


def test_cli_prints_plain_index_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.rocm.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/rocm-7.1-el9.6:3.5.0-ea.2-1778760581",
            "PYLOCK_FLAVOR=rocm",
            "PRODUCT=rhoai",
        ],
    )
    monkeypatch.setattr(
        resolver,
        "index_url_exists",
        lambda url: url == prod_index_url(release="3.5-EA2", accelerator="rocm7.1"),
    )

    runner = CliRunner()
    result = runner.invoke(resolver.app, ["index-url", str(conf_file)])

    assert result.exit_code == 0
    assert (
        result.stdout.strip() == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/rocm7.1-ubi9/simple/"
    )
