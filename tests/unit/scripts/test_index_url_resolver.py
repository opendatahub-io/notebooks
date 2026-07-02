from __future__ import annotations

import json
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


def _test_index_url(*, release: str, accelerator: str) -> str:
    return f"https://packages.redhat.com/api/pypi/public-rhai/rhoai/{release}/{accelerator}-ubi9-test/simple/"


def make_skopeo_label_stub(label_url: str):
    """Return a function that replaces inspect_base_image_index_url and returns the given URL."""

    def stub(base_image: str) -> str:
        return label_url

    return stub


def test_build_test_variant_url_from_production() -> None:
    prod = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/"
    expected = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    assert resolver.build_test_variant_url(prod) == expected


def test_build_test_variant_url_returns_none_for_test_url() -> None:
    test = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    assert resolver.build_test_variant_url(test) is None


def test_resolve_rhoai_cpu_index_from_label(
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
    label_url = prod_index_url(release="3.5-EA2", accelerator="cpu")
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(label_url))
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.product == "rhoai"
    assert resolved.index_profile == "rhoai"
    assert resolved.flavor == "cpu"
    assert resolved.accelerator == "cpu"
    assert resolved.release == "3.5-EA2"
    assert resolved.index_url == label_url


def test_resolve_rhoai_cuda_index_from_label(
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
    label_url = prod_index_url(release="3.5-EA2", accelerator="cuda13.0")
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(label_url))
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.flavor == "cuda"
    assert resolved.accelerator == "cuda13.0"
    assert resolved.release == "3.5-EA2"
    assert resolved.index_url == label_url


def test_resolve_rhoai_rocm_index_from_label(
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
    label_url = prod_index_url(release="3.5-EA2", accelerator="rocm7.1")
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(label_url))
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.flavor == "rocm"
    assert resolved.accelerator == "rocm7.1"
    assert resolved.release == "3.5-EA2"
    assert resolved.index_url == label_url


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
    label_url = prod_index_url(release="3.5-EA2", accelerator="cpu")
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(label_url))

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
    label_url = prod_index_url(release="3.5-EA2", accelerator="cpu")
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(label_url))

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


def test_no_test_fallback_when_label_already_points_to_test_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the label URL already has -test, no further fallback is attempted."""
    conf_file = write_conf(
        tmp_path,
        "konflux.cpu.conf",
        [
            "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1778762488",
            "PYLOCK_FLAVOR=cpu",
            "PRODUCT=rhoai",
        ],
    )
    label_url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(label_url))
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    resolved = resolver.resolve_index_config(conf_file)
    assert resolved.index_url == label_url


def test_error_when_label_missing(
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

    def stub_no_label(base_image: str) -> str:
        raise resolver.IndexResolutionError(f"{resolver.INDEX_URL_LABEL} label is missing from {base_image}")

    monkeypatch.setattr(resolver, "inspect_base_image_index_url", stub_no_label)

    with pytest.raises(resolver.IndexResolutionError, match="label is missing"):
        resolver.resolve_index_config(conf_file)


def test_error_when_label_url_invalid_host(
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
        "inspect_base_image_index_url",
        make_skopeo_label_stub("https://evil.example.com/api/pypi/rhoai/3.5/cpu-ubi9/simple/"),
    )

    with pytest.raises(resolver.IndexResolutionError, match="unexpected host"):
        resolver.resolve_index_config(conf_file)


def test_inspect_base_image_index_url_parses_config_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that inspect_base_image_index_url correctly extracts the label from skopeo output."""
    expected_url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/"
    skopeo_output = json.dumps(
        {
            "config": {
                "Labels": {
                    "com.redhat.aiplatform.index_url": expected_url,
                    "other.label": "ignored",
                }
            }
        }
    )

    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = skopeo_output
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = resolver.inspect_base_image_index_url("quay.io/aipcc/base-images/cpu:3.5.0-1782914735")
    assert result == expected_url


def test_inspect_base_image_index_url_error_on_missing_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skopeo_output = json.dumps({"config": {"Labels": {"other.label": "value"}}})

    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = skopeo_output
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(resolver.IndexResolutionError, match="label is missing"):
        resolver.inspect_base_image_index_url("quay.io/aipcc/base-images/cpu:3.5.0-1782914735")


def test_inspect_base_image_index_url_error_on_skopeo_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd, **kwargs):
        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "unauthorized: access denied"

        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(resolver.IndexResolutionError, match="skopeo inspect failed"):
        resolver.inspect_base_image_index_url("quay.io/aipcc/base-images/cpu:3.5.0-1782914735")


def test_inspect_base_image_index_url_error_on_skopeo_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("skopeo")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(resolver.IndexResolutionError, match="skopeo is not available"):
        resolver.inspect_base_image_index_url("quay.io/aipcc/base-images/cpu:3.5.0-1782914735")


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
    label_url = prod_index_url(release="3.5-EA2", accelerator="rocm7.1")
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(label_url))
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    runner = CliRunner()
    result = runner.invoke(resolver.app, ["index-url", str(conf_file)])

    assert result.exit_code == 0
    assert (
        result.stdout.strip() == "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/rocm7.1-ubi9/simple/"
    )


def test_parse_release_and_accelerator_from_url() -> None:
    url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cuda13.0-ubi9/simple/"
    release, accelerator = resolver.parse_release_and_accelerator_from_url(url)
    assert release == "3.5-EA2"
    assert accelerator == "cuda13.0"


def test_parse_release_and_accelerator_from_test_url() -> None:
    url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5/rocm7.1-ubi9-test/simple/"
    release, accelerator = resolver.parse_release_and_accelerator_from_url(url)
    assert release == "3.5"
    assert accelerator == "rocm7.1"
