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


def make_skopeo_inspect_fail_stub():
    """Stub inspect_base_image_index_url to force the tag/digest fallback path."""

    def stub(base_image: str) -> str:
        raise resolver.IndexResolutionError(f"skopeo inspect failed for {base_image}")

    return stub


DIGEST_PINNED_CPU = (
    "quay.io/aipcc/base-images/cpu@sha256:2f93df7e0b1b823bb63311f38b91cb8e0dc305d588813815dd4f77061fd15585"
)
DIGEST_PINNED_CUDA = (
    "quay.io/aipcc/base-images/cuda-13.0-el9.6@sha256:1620d9ade9a2a196b9d9bcca7842918dbf911273957abdd064a25e5f9d3f027c"
)


def assert_skopeo_inspect_cmd(cmd: list[str], base_image: str) -> None:
    assert cmd[:3] == ["skopeo", "inspect", "--retry-times"], f"unexpected skopeo prefix: {cmd}"
    assert cmd[-1] == f"docker://{base_image}", f"expected docker://{base_image}, got {cmd[-1]!r}"


def test_build_test_variant_url_from_production() -> None:
    prod = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/"
    expected = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    result = resolver.build_test_variant_url(prod)
    assert result == expected, f"expected {expected}, got {result}"


def test_build_test_variant_url_returns_none_for_test_url() -> None:
    test = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    result = resolver.build_test_variant_url(test)
    assert result is None, f"expected None for test URL, got {result}"


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

    assert resolved.product == "rhoai", f"expected product rhoai, got {resolved.product}"
    assert resolved.index_profile == "rhoai", f"expected index_profile rhoai, got {resolved.index_profile}"
    assert resolved.flavor == "cpu", f"expected flavor cpu, got {resolved.flavor}"
    assert resolved.accelerator == "cpu", f"expected accelerator cpu, got {resolved.accelerator}"
    assert resolved.release == "3.5-EA2", f"expected release 3.5-EA2, got {resolved.release}"
    assert resolved.index_url == label_url, f"expected index_url {label_url}, got {resolved.index_url}"


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

    assert resolved.flavor == "cuda", f"expected flavor cuda, got {resolved.flavor}"
    assert resolved.accelerator == "cuda13.0", f"expected accelerator cuda13.0, got {resolved.accelerator}"
    assert resolved.release == "3.5-EA2", f"expected release 3.5-EA2, got {resolved.release}"
    assert resolved.index_url == label_url, f"expected index_url {label_url}, got {resolved.index_url}"


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

    assert resolved.flavor == "rocm", f"expected flavor rocm, got {resolved.flavor}"
    assert resolved.accelerator == "rocm7.1", f"expected accelerator rocm7.1, got {resolved.accelerator}"
    assert resolved.release == "3.5-EA2", f"expected release 3.5-EA2, got {resolved.release}"
    assert resolved.index_url == label_url, f"expected index_url {label_url}, got {resolved.index_url}"


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

    expected = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/"
    assert resolved.index_url == expected, f"expected fallback test index {expected}, got {resolved.index_url}"
    assert checked_urls == [
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/",
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9-test/simple/",
    ], f"unexpected probe order: {checked_urls}"


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

    expected = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/"
    assert resolved.index_url == expected, f"expected prod index {expected}, got {resolved.index_url}"
    assert checked_urls == [
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cpu-ubi9/simple/",
    ], f"unexpected probe order: {checked_urls}"


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
    assert resolved.index_url == label_url, f"expected label URL {label_url}, got {resolved.index_url}"


def test_error_when_label_url_invalid_host_falls_back_to_tag(
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
    monkeypatch.setattr(
        resolver,
        "inspect_base_image_index_url",
        make_skopeo_label_stub("https://evil.example.com/api/pypi/rhoai/3.5/cpu-ubi9/simple/"),
    )
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.index_url == label_url, f"expected tag-derived index {label_url}, got {resolved.index_url}"
    assert resolved.release == "3.5-EA2", f"expected release 3.5-EA2, got {resolved.release}"
    assert resolved.accelerator == "cpu", f"expected accelerator cpu, got {resolved.accelerator}"


def test_resolve_falls_back_to_tag_when_label_has_template_placeholders(
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
    template_url = (
        "https://packages.redhat.com/api/pypi/public-rhai/rhoai/${INDEX_VERSION}/${INDEX_VARIANT}-test/simple/"
    )
    label_url = prod_index_url(release="3.5-EA2", accelerator="cpu")
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_label_stub(template_url))
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.index_url == label_url, f"expected tag-derived index {label_url}, got {resolved.index_url}"


def test_resolve_falls_back_to_tag_when_label_missing(
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

    def stub_no_label(base_image: str) -> str:
        raise resolver.IndexResolutionError(f"{resolver.INDEX_URL_LABEL} label is missing from {base_image}")

    monkeypatch.setattr(resolver, "inspect_base_image_index_url", stub_no_label)
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.index_url == label_url, f"expected tag-derived index {label_url}, got {resolved.index_url}"


@pytest.mark.parametrize(
    ("conf_name", "base_image", "flavor", "accelerator"),
    [
        ("konflux.cpu.conf", DIGEST_PINNED_CPU, "cpu", "cpu"),
        ("konflux.cuda.conf", DIGEST_PINNED_CUDA, "cuda", "cuda13.0"),
    ],
)
def test_resolve_digest_pinned_base_image_uses_release_when_label_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    conf_name: str,
    base_image: str,
    flavor: str,
    accelerator: str,
) -> None:
    """Digest pins (no tag) must fall back via RELEASE, not misparse image as cpu@sha256."""
    conf_file = write_conf(
        tmp_path,
        conf_name,
        [
            f"BASE_IMAGE={base_image}",
            f"PYLOCK_FLAVOR={flavor}",
            "PRODUCT=rhoai",
            "RELEASE=3.5",
        ],
    )
    label_url = prod_index_url(release="3.5", accelerator=accelerator)
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_inspect_fail_stub())
    monkeypatch.setattr(resolver, "index_url_exists", lambda url: url == label_url)

    resolved = resolver.resolve_index_config(conf_file)

    assert resolved.accelerator == accelerator, f"expected accelerator {accelerator}, got {resolved.accelerator}"
    assert resolved.release == "3.5", f"expected release 3.5, got {resolved.release}"
    assert resolved.index_url == label_url, f"expected index {label_url}, got {resolved.index_url}"


def test_digest_pinned_base_image_requires_release_when_label_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conf_file = write_conf(
        tmp_path,
        "konflux.cpu.conf",
        [
            f"BASE_IMAGE={DIGEST_PINNED_CPU}",
            "PYLOCK_FLAVOR=cpu",
            "PRODUCT=rhoai",
        ],
    )
    monkeypatch.setattr(resolver, "inspect_base_image_index_url", make_skopeo_inspect_fail_stub())

    with pytest.raises(resolver.IndexResolutionError, match="requires RELEASE"):
        resolver.resolve_index_config(conf_file)


def test_error_when_label_missing_and_tag_unusable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr(resolver, "index_url_exists", lambda _url: False)

    with pytest.raises(resolver.IndexResolutionError, match="No production or -test RH index is available"):
        resolver.resolve_index_config(conf_file)


def test_inspect_base_image_index_url_parses_config_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that inspect_base_image_index_url correctly extracts the label from skopeo output."""
    base_image = "quay.io/aipcc/base-images/cpu:3.5.0-1782914735"
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
        assert_skopeo_inspect_cmd(cmd, base_image)

        class FakeResult:
            returncode = 0
            stdout = skopeo_output
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = resolver.inspect_base_image_index_url(base_image)
    assert result == expected_url, f"expected label URL {expected_url}, got {result}"


def test_inspect_base_image_index_url_error_on_missing_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_image = "quay.io/aipcc/base-images/cpu:3.5.0-1782914735"
    skopeo_output = json.dumps({"config": {"Labels": {"other.label": "value"}}})

    def fake_run(cmd, **kwargs):
        assert_skopeo_inspect_cmd(cmd, base_image)

        class FakeResult:
            returncode = 0
            stdout = skopeo_output
            stderr = ""

        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(resolver.IndexResolutionError, match="label is missing"):
        resolver.inspect_base_image_index_url(base_image)


def test_inspect_base_image_index_url_error_on_skopeo_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_image = "quay.io/aipcc/base-images/cpu:3.5.0-1782914735"

    def fake_run(cmd, **kwargs):
        assert_skopeo_inspect_cmd(cmd, base_image)

        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "unauthorized: access denied"

        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(resolver.IndexResolutionError, match="skopeo inspect failed"):
        resolver.inspect_base_image_index_url(base_image)


def test_inspect_base_image_index_url_error_on_skopeo_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_image = "quay.io/aipcc/base-images/cpu:3.5.0-1782914735"

    def fake_run(cmd, **kwargs):
        assert_skopeo_inspect_cmd(cmd, base_image)
        raise FileNotFoundError("skopeo")

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(resolver.IndexResolutionError, match="skopeo is not available"):
        resolver.inspect_base_image_index_url(base_image)


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

    assert result.exit_code == 0, f"CLI failed: {result.stdout} {result.exception}"
    expected_stdout = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/rocm7.1-ubi9/simple/"
    assert result.stdout.strip() == expected_stdout, f"expected {expected_stdout}, got {result.stdout.strip()!r}"


def test_parse_release_and_accelerator_from_url() -> None:
    url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5-EA2/cuda13.0-ubi9/simple/"
    release, accelerator = resolver.parse_release_and_accelerator_from_url(url)
    assert release == "3.5-EA2", f"expected release 3.5-EA2, got {release}"
    assert accelerator == "cuda13.0", f"expected accelerator cuda13.0, got {accelerator}"


def test_parse_release_and_accelerator_from_test_url() -> None:
    url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5/rocm7.1-ubi9-test/simple/"
    release, accelerator = resolver.parse_release_and_accelerator_from_url(url)
    assert release == "3.5", f"expected release 3.5, got {release}"
    assert accelerator == "rocm7.1", f"expected accelerator rocm7.1, got {accelerator}"


def test_validate_label_index_url_rejects_malformed_path() -> None:
    base_image = "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1778762488"
    malformed_url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5/simple/"
    with pytest.raises(resolver.IndexResolutionError, match="unexpected path"):
        resolver.validate_label_index_url(malformed_url, base_image)


def test_parse_release_and_accelerator_from_url_rejects_malformed_path() -> None:
    malformed_url = "https://packages.redhat.com/api/pypi/public-rhai/rhoai/3.5/simple/"
    with pytest.raises(resolver.IndexResolutionError, match="Cannot extract release/accelerator"):
        resolver.parse_release_and_accelerator_from_url(malformed_url)
