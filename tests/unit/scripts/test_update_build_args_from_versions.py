from __future__ import annotations

import importlib
import subprocess
import textwrap
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def load_updater():
    try:
        return importlib.import_module("scripts.update_build_args_from_versions")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Missing sync implementation module: {exc}")


def completed_process(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["skopeo"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


DEFAULT_GPU_MINIMAL_ACC_VERSION = {"cuda": "25.0", "rocm": "8.0"}
TEST_IMAGE_DIGEST = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
RHDS_CPU_EA2_IMAGE = "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771"
RHDS_CUDA_EA2_IMAGE = "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771"
RHDS_ROCM_EA2_IMAGE = "quay.io/aipcc/base-images/rocm-7.1-el9.6:3.5.0-ea.2-1777919771"


def pin_image_for_test(tagged_image: str) -> str:
    if "@" in tagged_image:
        return tagged_image
    return f"{tagged_image}@{TEST_IMAGE_DIGEST}"


def pinned_base_image(tagged_image: str) -> str:
    return f"BASE_IMAGE={pin_image_for_test(tagged_image)}"


def stub_image_digest_pinning(monkeypatch: pytest.MonkeyPatch, updater) -> None:
    monkeypatch.setattr(
        updater,
        "resolve_image_digest",
        lambda image, digest_cache=None, source_tag_by_digest=None: pin_image_for_test(image),
    )


_RESOLVE_IMAGE_DIGEST_TESTS = frozenset(
    {
        "test_resolve_image_digest_uses_skopeo_inspect",
        "test_resolve_image_digest_records_source_tag_for_digest_reference",
        "test_resolve_image_digest_keeps_already_pinned_reference",
    }
)


@pytest.fixture(autouse=True)
def _stub_image_digest_pinning(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.name in _RESOLVE_IMAGE_DIGEST_TESTS:
        return
    stub_image_digest_pinning(monkeypatch, load_updater())


def rhds_gpu_stable_image(
    accelerator: str,
    *,
    full_version: str = "3.5.0",
    build: str = "1780598175",
) -> str:
    return f"quay.io/aipcc/base-images/{accelerator}-stable:{full_version}-{build}"


def stub_published_rhds_gpu_stable_tags(
    monkeypatch: pytest.MonkeyPatch,
    updater,
    *,
    full_version: str = "3.5.0",
    cuda_build: str = "1780598175",
    rocm_build: str = "1780598175",
) -> None:
    tags_by_repository = {
        "quay.io/aipcc/base-images/cuda-stable": (f"{full_version}-{cuda_build}",),
        "quay.io/aipcc/base-images/rocm-stable": (f"{full_version}-{rocm_build}",),
    }
    monkeypatch.setattr(
        updater,
        "list_rhds_repository_tags",
        lambda repository, tag_cache=None: tags_by_repository.get(repository, ()),
    )


def stub_rhds_repository_tags(
    monkeypatch: pytest.MonkeyPatch,
    updater,
    tags_by_repository: dict[str, tuple[str, ...]],
) -> None:
    monkeypatch.setattr(
        updater,
        "list_rhds_repository_tags",
        lambda repository, tag_cache=None: tags_by_repository.get(repository, ()),
    )


def stub_empty_rhds_tag_listing(monkeypatch: pytest.MonkeyPatch, updater) -> None:
    monkeypatch.setattr(
        updater,
        "list_rhds_repository_tags",
        lambda repository, tag_cache=None: (),
    )


def stub_matching_rhds_stable_acc_version(monkeypatch: pytest.MonkeyPatch, updater) -> None:
    monkeypatch.setattr(
        updater,
        "inspect_rhds_stable_acc_version",
        lambda image, accelerator: {"cuda": "25.0", "rocm": "8.0"}.get(accelerator),
    )


def write_conf(path: Path, *lines: str) -> None:
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def gpu_minimal_policy_block(
    accelerator: str,
    *,
    acc_version: str | None = None,
    rhds_channel: str = "fast",
    odh_origin: str = "in-house",
    shared_acc_version: bool = False,
) -> str:
    resolved_acc_version = acc_version or DEFAULT_GPU_MINIMAL_ACC_VERSION[accelerator]
    if shared_acc_version:
        return (
            "      minimal:\n"
            f'        acc_version: "{resolved_acc_version}"\n'
            "        rhds:\n"
            f"          channel: {rhds_channel}\n"
            "        odh:\n"
            f"          origin: {odh_origin}"
        )
    rhds_acc_version = "" if rhds_channel == "stable" else f'          acc_version: "{resolved_acc_version}"\n'
    return (
        "      minimal:\n"
        "        rhds:\n"
        f"          channel: {rhds_channel}\n"
        f"{rhds_acc_version}"
        "        odh:\n"
        f"          origin: {odh_origin}\n"
        f'          acc_version: "{resolved_acc_version}"'
    )


def write_gpu_minimal_versions_config(
    path: Path,
    *,
    accelerator: str,
    full_version: str = "3.5.0",
    acc_version: str | None = None,
    rhds_channel: str = "fast",
    odh_origin: str = "in-house",
    shared_acc_version: bool = False,
) -> None:
    write_versions_config(
        path,
        full_version=full_version,
        replacements=[
            (
                gpu_minimal_policy_block(accelerator),
                gpu_minimal_policy_block(
                    accelerator,
                    acc_version=acc_version,
                    rhds_channel=rhds_channel,
                    odh_origin=odh_origin,
                    shared_acc_version=shared_acc_version,
                ),
            )
        ],
    )


def write_versions_config(
    path: Path,
    *,
    schema_version: int = 1,
    full_version: str = "3.6.0",
    rhds_os_base: str = "el9.6",
    python_version: str = "3.12",
    replacements: list[tuple[str, str]] | None = None,
) -> None:
    text = textwrap.dedent(
        f"""\
        schema_version: {schema_version}

        release:
          full_version: "{full_version}"
          rhds_os_base: "{rhds_os_base}"
          python_version: "{python_version}"

        artifacts:
          base_image:
            cpu:
              rhds:
                channel: fast
                version: "<full_version>"
              odh:
                origin: in-house
                version: "latest"

            cuda:
              minimal:
                rhds:
                  channel: fast
                  acc_version: "25.0"
                odh:
                  origin: in-house
                  acc_version: "25.0"
              pytorch:
                rhds:
                  channel: fast
                  acc_version: "25.0"
                odh:
                  origin: in-house
                  acc_version: "25.0"
              pytorch-llmcompressor:
                rhds:
                  channel: fast
                  acc_version: "25.0"
                odh:
                  origin: in-house
                  acc_version: "25.0"
              tensorflow:
                rhds:
                  channel: fast
                  acc_version: "24.9"
                odh:
                  origin: in-house
                  acc_version: "24.9"

            rocm:
              minimal:
                rhds:
                  channel: fast
                  acc_version: "8.0"
                odh:
                  origin: in-house
                  acc_version: "8.0"
              pytorch:
                rhds:
                  channel: fast
                  acc_version: "8.0"
                odh:
                  origin: in-house
                  acc_version: "8.0"
              tensorflow:
                rhds:
                  channel: fast
                  acc_version: "8.0"
                odh:
                  origin: in-house
                  acc_version: "8.0"
        """
    )

    for old, new in replacements or []:
        updated = text.replace(old, new)
        if updated == text:
            raise AssertionError(f"Replacement did not match config text: {old!r}")
        text = updated

    path.write_text(text, encoding="utf-8")


def test_load_versions_config_rejects_unexpected_keys(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    config.write_text(
        textwrap.dedent(
            """\
            schema_version: 1

            release:
              full_version: "3.5.0"
              rhds_os_base: "el9.6"
              python_version: "3.12"

            artifacts:
              base_image:
                cpu:
                  rhds:
                    channel: fast
                    version: "<full_version>"
                  odh:
                    origin: in-house
                    version: "latest"
                extra:
                  bogus: {}
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unexpected keys"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_missing_required_keys(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    config.write_text(
        textwrap.dedent(
            """\
            schema_version: 1

            release:
              full_version: "3.5.0"
              python_version: "3.12"

            artifacts:
              base_image:
                cpu:
                  rhds:
                    channel: fast
                    version: "<full_version>"
                  odh:
                    origin: in-house
                    version: "latest"
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing keys"):
        updater.load_versions_config(config)


def test_load_versions_config_accepts_schema_version_one(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(config)

    loaded = updater.load_versions_config(config)

    assert loaded.release.full_version == "3.6.0"
    assert loaded.release.python_version == "3.12"


def test_load_versions_config_accepts_shared_gpu_acc_version_layout(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        acc_version: "25.0"\n        rhds:\n          channel: fast\n        odh:\n          origin: in-house',
            )
        ],
    )

    loaded = updater.load_versions_config(config)

    assert loaded.policy("cuda", "rhds", "minimal").mode == "fast"
    assert loaded.policy("cuda", "rhds", "minimal").version == "25.0"
    assert loaded.policy("cuda", "odh", "minimal").mode == "in-house"
    assert loaded.policy("cuda", "odh", "minimal").version == "25.0"


def test_load_versions_config_rejects_mismatched_legacy_gpu_acc_versions(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "24.9"',
            )
        ],
    )

    with pytest.raises(ValueError, match="must match"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_schema_version_two(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(config, schema_version=2)

    with pytest.raises(ValueError, match="Unsupported schema_version"):
        updater.load_versions_config(config)


def test_resolve_version_uses_full_version_placeholder() -> None:
    updater = load_updater()
    release = updater.ReleaseConfig(full_version="3.6.0", rhds_os_base="el9.6", python_version="3.12")

    assert updater.resolve_version("<full_version>", release) == "3.6.0"


def test_load_versions_config_rejects_empty_rhds_os_base(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(config, rhds_os_base="")

    with pytest.raises(ValueError, match="rhds_os_base"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_invalid_python_version(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(config, python_version="3")

    with pytest.raises(ValueError, match="python_version"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_non_scalar_cpu_version(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    config.write_text(
        textwrap.dedent(
            """\
            schema_version: 1

            release:
              full_version: "3.5.0"
              rhds_os_base: "el9.6"
              python_version: "3.12"

            artifacts:
              base_image:
                cpu:
                  rhds:
                    channel: fast
                    version:
                      major: 3
                  odh:
                    origin: in-house
                    version: "latest"
                cuda:
                  minimal:
                    rhds:
                      channel: fast
                      acc_version: "25.0"
                    odh:
                      origin: in-house
                      acc_version: "25.0"
                  pytorch:
                    rhds:
                      channel: fast
                      acc_version: "25.0"
                    odh:
                      origin: in-house
                      acc_version: "25.0"
                  pytorch-llmcompressor:
                    rhds:
                      channel: fast
                      acc_version: "25.0"
                    odh:
                      origin: in-house
                      acc_version: "25.0"
                  tensorflow:
                    rhds:
                      channel: fast
                      acc_version: "24.9"
                    odh:
                      origin: in-house
                      acc_version: "24.9"
                rocm:
                  minimal:
                    rhds:
                      channel: fast
                      acc_version: "8.0"
                    odh:
                      origin: in-house
                      acc_version: "8.0"
                  pytorch:
                    rhds:
                      channel: fast
                      acc_version: "8.0"
                    odh:
                      origin: in-house
                      acc_version: "8.0"
                  tensorflow:
                    rhds:
                      channel: fast
                      acc_version: "8.0"
                    odh:
                      origin: in-house
                      acc_version: "8.0"
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="version"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_invalid_rhds_channel(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      rhds:\n        channel: fast\n        version: "<full_version>"',
                '      rhds:\n        channel: default\n        version: "<full_version>"',
            )
        ],
    )

    with pytest.raises(ValueError, match=r"rhds.*channel"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_missing_cpu_version_for_fast(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      rhds:\n        channel: fast\n        version: "<full_version>"',
                "      rhds:\n        channel: fast",
            )
        ],
    )

    with pytest.raises(ValueError, match="version"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_cpu_acc_version_key(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      rhds:\n        channel: fast\n        version: "<full_version>"',
                '      rhds:\n        channel: fast\n        acc_version: "<full_version>"',
            )
        ],
    )

    with pytest.raises(ValueError, match="Unexpected keys"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_acc_version_for_stable(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        rhds:\n          channel: stable\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
            )
        ],
    )

    with pytest.raises(ValueError, match="stable"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_invalid_odh_origin(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      odh:\n        origin: in-house\n        version: "latest"',
                '      odh:\n        origin: default\n        version: "latest"',
            )
        ],
    )

    with pytest.raises(ValueError, match=r"odh.*origin"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_non_latest_cpu_odh_version(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      odh:\n        origin: in-house\n        version: "latest"',
                '      odh:\n        origin: in-house\n        version: "3.12"',
            )
        ],
    )

    with pytest.raises(ValueError, match=r"cpu.*version.*latest"):
        updater.load_versions_config(config)


def test_load_versions_config_rejects_non_numeric_cuda_in_house_acc_version(tmp_path: Path) -> None:
    updater = load_updater()
    config = tmp_path / "versions_config.yml"
    write_versions_config(
        config,
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "latest"',
            )
        ],
    )

    with pytest.raises(ValueError, match="numeric acc_version"):
        updater.load_versions_config(config)


def test_collect_conf_targets_classifies_managed_paths(tmp_path: Path) -> None:
    updater = load_updater()
    managed = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    managed.parent.mkdir(parents=True)
    managed.write_text("BASE_IMAGE=example\n", encoding="utf-8")

    targets = updater.collect_conf_targets(tmp_path)

    assert len(targets) == 1
    assert targets[0].path == managed
    assert targets[0].distribution == "rhds"
    assert targets[0].accelerator == "cuda"
    assert targets[0].flavor == "minimal"


def test_collect_conf_targets_ignores_base_images_build_args(tmp_path: Path) -> None:
    updater = load_updater()
    managed = tmp_path / "base-images" / "build-args" / "cuda13.0.conf"
    managed.parent.mkdir(parents=True)
    managed.write_text("INDEX_URL=https://example.invalid\n", encoding="utf-8")

    targets = updater.collect_conf_targets(tmp_path)

    assert targets == []


def test_collect_conf_targets_rejects_unknown_build_args_filename(tmp_path: Path) -> None:
    updater = load_updater()
    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "gpu.conf"
    write_conf(conf, "BASE_IMAGE=example")

    with pytest.raises(ValueError, match="Unsupported build-args filename"):
        updater.collect_conf_targets(tmp_path)


def test_split_image_ref_accepts_tag_and_digest_references() -> None:
    updater = load_updater()

    assert updater.split_image_ref("quay.io/example/repo:3.5.0-ea.1-1") == (
        "quay.io/example/repo",
        "3.5.0-ea.1-1",
    )
    assert updater.split_image_ref(
        "quay.io/example/repo@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ) == (
        "quay.io/example/repo",
        "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )


def test_resolve_image_digest_uses_skopeo_inspect(monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()
    digest = "sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"

    inspect_calls: list[str] = []

    def fake_inspect(image: str, warning_color=None) -> dict[str, str]:
        inspect_calls.append(image)
        return {"Digest": digest}

    monkeypatch.setattr(updater, "inspect_image_manifest", fake_inspect)

    pinned = updater.resolve_image_digest("quay.io/aipcc/base-images/cpu:3.5.0-1782914735")

    assert inspect_calls == ["quay.io/aipcc/base-images/cpu:3.5.0-1782914735"]
    assert pinned == f"quay.io/aipcc/base-images/cpu:3.5.0-1782914735@{digest}"
    assert pinned != pin_image_for_test("quay.io/aipcc/base-images/cpu:3.5.0-1782914735")


def test_resolve_image_digest_records_source_tag_for_digest_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    source_tag_by_digest: dict[str, str] = {}

    monkeypatch.setattr(
        updater,
        "inspect_image_manifest",
        lambda image, warning_color=None: {"Digest": digest},
    )

    pinned = updater.resolve_image_digest(
        "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771",
        source_tag_by_digest=source_tag_by_digest,
    )

    assert pinned == f"quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771@{digest}"
    assert source_tag_by_digest[pinned] == "3.5.0-ea.2-1777919771"


def test_resolve_image_digest_keeps_already_pinned_reference() -> None:
    updater = load_updater()
    digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    image = f"quay.io/aipcc/base-images/cpu@{digest}"

    assert updater.resolve_image_digest(image) == image


def test_image_tag_from_reference_uses_source_tag_cache() -> None:
    updater = load_updater()
    digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    image = f"quay.io/aipcc/base-images/cpu@{digest}"

    assert (
        updater.image_tag_from_reference(
            image,
            source_tag_by_digest={image: "3.5.0-ea.2-1777919771"},
        )
        == "3.5.0-ea.2-1777919771"
    )


def test_image_tag_from_reference_returns_none_without_cached_tag_mapping() -> None:
    updater = load_updater()
    digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    image = f"quay.io/aipcc/base-images/cpu@{digest}"

    assert updater.image_tag_from_reference(image) is None


def test_image_tag_from_reference_matches_digest_from_digest_cache() -> None:
    updater = load_updater()
    digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    image = f"quay.io/aipcc/base-images/cpu@{digest}"

    assert (
        updater.image_tag_from_reference(
            image,
            digest_cache={
                "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771": digest,
                "quay.io/aipcc/base-images/cpu:3.5.0-1777921111": "sha256:deadbeef",
            },
        )
        == "3.5.0-ea.2-1777919771"
    )


def test_image_tag_from_reference_prefers_highest_semantic_match_from_digest_cache() -> None:
    updater = load_updater()
    digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    image = f"quay.io/aipcc/base-images/cpu@{digest}"

    assert (
        updater.image_tag_from_reference(
            image,
            digest_cache={
                "quay.io/aipcc/base-images/cpu:3.9.0-ea.1-1": digest,
                "quay.io/aipcc/base-images/cpu:3.10.0-ea.1-1": digest,
            },
        )
        == "3.10.0-ea.1-1"
    )


def test_image_tag_from_reference_reuses_digest_to_tag_repository_cache() -> None:
    updater = load_updater()
    digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    image = f"quay.io/aipcc/base-images/cpu@{digest}"
    digest_to_tag_by_repository = {
        "quay.io/aipcc/base-images/cpu": {digest: "3.5.0-ea.2-1777919771"},
    }

    assert (
        updater.image_tag_from_reference(
            image,
            digest_to_tag_by_repository=digest_to_tag_by_repository,
        )
        == "3.5.0-ea.2-1777919771"
    )


def test_select_best_matching_tag_prefers_higher_semantic_version() -> None:
    updater = load_updater()

    selected = updater.select_best_matching_tag(
        [
            "3.9.0-ea.1-1",
            "3.10.0-ea.1-1",
        ]
    )

    assert selected == "3.10.0-ea.1-1"


def test_select_best_matching_tag_prefers_higher_build_number() -> None:
    updater = load_updater()

    selected = updater.select_best_matching_tag(
        [
            "3.5.0-ea.2-9",
            "3.5.0-ea.2-10",
        ]
    )

    assert selected == "3.5.0-ea.2-10"


def test_select_latest_matching_rhds_tag_prefers_highest_build_in_same_family() -> None:
    updater = load_updater()

    latest = updater.select_latest_matching_rhds_tag(
        [
            "3.6.0-ea.1-1777919000",
            "3.6.0-ea.1-1777919999",
            "3.6.0-ea.2-1777920000",
            "3.6.0-1777921111",
        ],
        "3.6.0-ea.1-1777000000",
    )

    assert latest == "3.6.0-ea.1-1777919999"


def test_build_rhds_pinned_tag_targets_ga_family_on_rollback() -> None:
    updater = load_updater()
    release = updater.ReleaseConfig(full_version="3.4.0", rhds_os_base="el9.6", python_version="3.12")

    tag = updater.build_rhds_pinned_tag("3.5.0-ea.2-1777919771", release.full_version)

    assert tag == "3.4.0-1777919771"


def test_resolve_latest_published_rhds_image_uses_skopeo_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cuda-25.0-el9.6","Tags":'
                '["3.6.0-ea.1-1777919000","3.6.0-ea.1-1777919999","3.6.0-ea.2-1777920000"]}'
            )
        ),
    )

    latest = updater.resolve_latest_published_rhds_image(
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777000000"
    )

    assert latest == "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.2-1777920000"


def test_resolve_latest_published_rhds_image_progresses_ea1_to_ea2_without_ga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cuda-13.0-el9.6","Tags":'
                '["3.5.0-ea.1-1777919000","3.5.0-ea.2-1777919999"]}'
            )
        ),
    )

    latest = updater.resolve_latest_published_rhds_image(
        "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771"
    )

    assert latest == "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919999"


def test_resolve_latest_published_rhds_image_keeps_ea1_when_only_ea1_patches_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cuda-13.0-el9.6","Tags":'
                '["3.5.0-ea.1-1777919000","3.5.0-ea.1-1777919999"]}'
            )
        ),
    )

    latest = updater.resolve_latest_published_rhds_image(
        "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771"
    )

    assert latest == "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919999"


def test_resolve_latest_published_rhds_image_never_regresses_ea2_to_ea1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cuda-13.0-el9.6","Tags":'
                '["3.5.0-ea.1-1777919999","3.5.0-ea.2-1777919000"]}'
            )
        ),
    )

    latest = updater.resolve_latest_published_rhds_image(
        "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771"
    )

    assert latest == "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919000"


def test_resolve_latest_published_rhds_image_prefers_ga_over_ea_for_same_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cuda-13.0-el9.6","Tags":'
                '["3.5.0-ea.1-1777919000","3.5.0-ea.2-1780972037","3.5.0-1781269637"]}'
            )
        ),
    )

    latest = updater.resolve_latest_published_rhds_image(
        "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1780972037"
    )

    assert latest == "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-1781269637"


def test_resolve_latest_published_rhds_image_keeps_ea_family_when_ga_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cuda-13.0-el9.6","Tags":'
                '["3.5.0-ea.1-1777919000","3.5.0-ea.2-1777919999"]}'
            )
        ),
    )

    latest = updater.resolve_latest_published_rhds_image(
        "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771"
    )

    assert latest == "quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919999"


def test_resolve_latest_published_rhds_image_rollback_from_ea2_targets_ga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cpu","Tags":'
                '["3.4.0-ea.1-1777919000","3.4.0-ea.2-1777919999","3.4.0-1777921111"]}'
            )
        ),
    )

    latest = updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cpu:3.4.0-1777919771")

    assert latest == "quay.io/aipcc/base-images/cpu:3.4.0-1777921111"


def test_resolve_latest_published_rhds_image_rollback_from_ga_targets_latest_ga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=('{"Repository":"quay.io/aipcc/base-images/cpu","Tags":["3.4.0-1777919000","3.4.0-1777921111"]}')
        ),
    )

    latest = updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cpu:3.4.0-1777919771")

    assert latest == "quay.io/aipcc/base-images/cpu:3.4.0-1777921111"


def test_resolve_latest_published_rhds_image_rollback_falls_back_to_highest_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cpu","Tags":'
                '["3.4.0-ea.1-1777919000","3.4.0-ea.2-1777919999","3.5.0-1777921111"]}'
            )
        ),
    )

    latest = updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cpu:3.4.0-0")

    assert latest == "quay.io/aipcc/base-images/cpu:3.4.0-ea.2-1777919999"


def test_resolve_latest_published_rhds_image_rollback_raises_when_release_is_unpublished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout='{"Repository":"quay.io/aipcc/base-images/cpu","Tags":["3.5.0-ea.2-1777919999"]}'
        ),
    )

    with pytest.raises(ValueError, match=r"release '3.4.0'"):
        updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cpu:3.4.0-0")


def test_resolve_latest_published_rhds_image_raises_on_skopeo_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(returncode=1, stderr="manifest unknown"),
    )

    with pytest.raises(ValueError, match="skopeo list-tags failed"):
        updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777000000")


def test_resolve_latest_published_rhds_image_raises_when_skopeo_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("skopeo")

    monkeypatch.setattr(updater.subprocess, "run", raise_missing)

    with pytest.raises(ValueError, match="skopeo is required"):
        updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777000000")


def test_resolve_latest_published_rhds_image_raises_when_skopeo_list_tags_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(["skopeo", "list-tags"], timeout=60)

    monkeypatch.setattr(updater.subprocess, "run", raise_timeout)

    with pytest.raises(ValueError, match="skopeo list-tags timed out"):
        updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777000000")


def test_plan_updates_caches_rhds_tag_listing_per_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    first = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    second = tmp_path / "runtimes" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    base_image = "quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1777919771"
    write_conf(first, f"BASE_IMAGE={base_image}")
    write_conf(second, f"BASE_IMAGE={base_image}")

    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[-1])
        return completed_process(stdout='{"Tags":["3.6.0-ea.1-1777919999"]}')

    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert calls == ["docker://quay.io/aipcc/base-images/cpu"]


def test_plan_updates_infers_bundle_phase_for_stable_to_fast_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    target_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    peer_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(target_conf, "BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5")
    write_conf(peer_conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        if image == "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-0":
            return "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780000000"
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert seen == [
        "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-0",
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1777919771",
    ]
    assert rendered[target_conf] == pinned_base_image("quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780000000")
    assert rendered[peer_conf] == pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001")


def test_plan_updates_infers_ga_phase_for_stable_to_fast_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    target_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    peer_conf = tmp_path / "jupyter" / "pytorch" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(target_conf, f"BASE_IMAGE={rhds_gpu_stable_image('cuda')}")
    write_conf(peer_conf, "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-1777919771")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        if image.endswith(":3.5.0-0"):
            return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1780000000"
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1780000001"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert seen == [
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-0",
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1777919771",
    ]
    assert rendered[target_conf] == pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1780000000")
    assert rendered[peer_conf] == pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1780000001")


def test_plan_updates_falls_back_to_ea1_without_any_bundle_fast_style_peers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    first_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    second_conf = tmp_path / "runtimes" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    write_conf(first_conf, "BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5")
    write_conf(second_conf, "BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert seen == [
        "quay.io/aipcc/base-images/cpu:3.5.0-ea.1-0",
        "quay.io/aipcc/base-images/cpu:3.5.0-ea.1-0",
    ]
    assert rendered[first_conf] == pinned_base_image("quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780000000")
    assert rendered[second_conf] == pinned_base_image("quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780000000")


def test_plan_updates_uses_highest_observed_bundle_phase_for_existing_fast_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    cpu_conf = tmp_path / "runtimes" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    cuda_conf = tmp_path / "jupyter" / "pytorch" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(cpu_conf, "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780600064")
    write_conf(cuda_conf, "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771")
    rocm_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.rocm.conf"
    write_conf(rocm_conf, "BASE_IMAGE=quay.io/aipcc/base-images/rocm-8.0-el9.6:3.5.0-ea.2-1777919771")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        if image == "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780600064":
            return "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780609999"
        if image == "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1777919771":
            return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001"
        return "quay.io/aipcc/base-images/rocm-8.0-el9.6:3.5.0-ea.2-1780000002"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert seen == [
        "quay.io/aipcc/base-images/rocm-8.0-el9.6:3.5.0-ea.2-1777919771",
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1777919771",
        "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780600064",
    ]
    assert rendered[rocm_conf] == pinned_base_image("quay.io/aipcc/base-images/rocm-8.0-el9.6:3.5.0-ea.2-1780000002")
    assert rendered[cuda_conf] == pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001")
    assert rendered[cpu_conf] == pinned_base_image("quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780609999")


def test_plan_updates_uses_forward_discovery_not_bundle_phase_for_lagging_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    cpu_conf = tmp_path / "runtimes" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    cuda_conf = tmp_path / "jupyter" / "pytorch" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(cpu_conf, "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.4.0-ea.2-1780600064")
    write_conf(cuda_conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    def fake_list_tags(repository: str, tag_cache=None) -> tuple[str, ...]:
        if repository == "quay.io/aipcc/base-images/cpu":
            return ("3.5.0-ea.1-1777919000",)
        return ()

    monkeypatch.setattr(updater, "list_rhds_repository_tags", fake_list_tags)

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        if image == "quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780600064":
            return "quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780609999"
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert "quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780600064" in seen
    assert "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780600064" not in seen
    assert rendered[cpu_conf] == pinned_base_image("quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780609999")
    assert rendered[cuda_conf] == pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001")


def test_plan_updates_starts_new_release_at_ea1_when_peers_are_older_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.6.0")

    target_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    peer_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(target_conf, "BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5")
    write_conf(peer_conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        if image == "quay.io/aipcc/base-images/cpu:3.6.0-ea.1-0":
            return "quay.io/aipcc/base-images/cpu:3.6.0-ea.1-1780000000"
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1780000001"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)
    stub_empty_rhds_tag_listing(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert seen == [
        "quay.io/aipcc/base-images/cpu:3.6.0-ea.1-0",
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777919771",
    ]
    assert rendered[target_conf] == pinned_base_image("quay.io/aipcc/base-images/cpu:3.6.0-ea.1-1780000000")
    assert rendered[peer_conf] == pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1780000001")


def test_plan_updates_uses_published_ga_for_new_release_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.4.0-ea.2-1777919771")

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cuda-25.0-el9.6","Tags":'
                '["3.5.0-ea.1-1777919000","3.5.0-ea.2-1777919999","3.5.0-1777921111"]}'
            )
        ),
    )

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image(
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1777921111"
    )


def test_plan_updates_uses_highest_published_phase_for_new_release_when_ga_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.4.0-ea.2-1777919771")

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cuda-25.0-el9.6","Tags":'
                '["3.5.0-ea.1-1777919000","3.5.0-ea.2-1777919999"]}'
            )
        ),
    )

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image(
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1777919999"
    )


def test_plan_updates_stable_to_fast_forward_uses_highest_published_phase_for_new_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.4")

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cpu","Tags":'
                '["3.5.0-ea.1-1777919000","3.5.0-ea.2-1777919999"]}'
            )
        ),
    )

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image("quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919999")


def test_plan_updates_new_release_without_published_tags_keeps_strict_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.4.0-ea.2-1777919771")

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout='{"Repository":"quay.io/aipcc/base-images/cuda-25.0-el9.6","Tags":["3.4.0-ea.2-1777919771"]}'
        ),
    )

    with pytest.raises(ValueError, match="No matching published RHDS tag found"):
        updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))


def test_plan_updates_builds_fast_rhds_candidate_before_latest_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)
    stub_empty_rhds_tag_listing(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert seen == ["quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777919771"]
    assert updates[0].updated_text.strip() == pinned_base_image(
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999"
    )


def test_plan_updates_rollback_targets_ga_family_for_older_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0")

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    write_conf(conf, f"BASE_IMAGE={RHDS_CPU_EA2_IMAGE}")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cpu:3.4.0-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert seen == ["quay.io/aipcc/base-images/cpu:3.4.0-1777919771"]
    assert updates[0].updated_text.strip() == pinned_base_image("quay.io/aipcc/base-images/cpu:3.4.0-1780000000")


def test_plan_updates_uses_hard_coded_rhds_cpu_version_for_fast_channel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        full_version="3.5.0",
        replacements=[
            (
                '      rhds:\n        channel: fast\n        version: "<full_version>"',
                '      rhds:\n        channel: fast\n        version: "3.4.0"',
            )
        ],
    )

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    write_conf(conf, f"BASE_IMAGE={RHDS_CPU_EA2_IMAGE}")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cpu:3.4.0-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert seen == ["quay.io/aipcc/base-images/cpu:3.4.0-1777919771"]
    assert updates[0].updated_text.strip() == pinned_base_image("quay.io/aipcc/base-images/cpu:3.4.0-1780000000")


def test_plan_updates_rollback_ignores_newer_fast_peers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0")

    cpu_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    cuda_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(cpu_conf, "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780600064")
    write_conf(cuda_conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        if image == "quay.io/aipcc/base-images/cpu:3.4.0-1780600064":
            return "quay.io/aipcc/base-images/cpu:3.4.0-1780609999"
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.4.0-1780000001"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert seen == [
        "quay.io/aipcc/base-images/cpu:3.4.0-1780600064",
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.4.0-1777919771",
    ]
    assert rendered[cpu_conf] == pinned_base_image("quay.io/aipcc/base-images/cpu:3.4.0-1780609999")
    assert rendered[cuda_conf] == pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.4.0-1780000001")


def test_plan_updates_rollback_falls_back_to_highest_published_phase_when_ga_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0")

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    write_conf(conf, f"BASE_IMAGE={RHDS_CPU_EA2_IMAGE}")

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            stdout=(
                '{"Repository":"quay.io/aipcc/base-images/cpu","Tags":'
                '["3.4.0-ea.1-1777919000","3.4.0-ea.2-1777919999","3.5.0-ea.2-1777921111"]}'
            )
        ),
    )

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image("quay.io/aipcc/base-images/cpu:3.4.0-ea.2-1777919999")


def test_plan_updates_rollback_from_stable_target_uses_ga_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0")

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cpu:3.4.0-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert seen == ["quay.io/aipcc/base-images/cpu:3.4.0-0"]
    assert updates[0].updated_text.strip() == pinned_base_image("quay.io/aipcc/base-images/cpu:3.4.0-1780000000")


def test_plan_updates_allows_independent_mixed_rhds_channels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        full_version="3.5.0",
        replacements=[
            (
                gpu_minimal_policy_block("cuda"),
                gpu_minimal_policy_block("cuda", rhds_channel="stable"),
            )
        ],
    )

    cpu_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    cuda_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(cpu_conf, f"BASE_IMAGE={RHDS_CPU_EA2_IMAGE}")
    write_conf(cuda_conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)
    stub_published_rhds_gpu_stable_tags(monkeypatch, updater)
    stub_matching_rhds_stable_acc_version(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path.name: update.updated_text.strip() for update in updates}

    assert seen == ["quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771"]
    assert rendered["konflux.cpu.conf"] == pinned_base_image("quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780000000")
    assert rendered["konflux.cuda.conf"] == pinned_base_image(rhds_gpu_stable_image("cuda"))


def test_plan_updates_allows_cuda_minimal_stable_and_pytorch_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_gpu_minimal_versions_config(
        tmp_path / "versions_config.yml",
        accelerator="cuda",
        full_version="3.5.0",
        rhds_channel="stable",
    )

    minimal_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    pytorch_conf = tmp_path / "jupyter" / "pytorch" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(minimal_conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")
    write_conf(pytorch_conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)
    stub_published_rhds_gpu_stable_tags(monkeypatch, updater)
    stub_matching_rhds_stable_acc_version(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert seen == ["quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1777919771"]
    assert rendered[minimal_conf] == pinned_base_image(rhds_gpu_stable_image("cuda"))
    assert rendered[pytorch_conf] == pinned_base_image(
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000000"
    )


@pytest.mark.parametrize(
    ("accelerator", "current_image", "acc_version"),
    [
        ("cuda", RHDS_CUDA_EA2_IMAGE, "25.0"),
        ("rocm", RHDS_ROCM_EA2_IMAGE, "8.0"),
    ],
)
def test_plan_updates_uses_rhds_gpu_stable_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    accelerator: str,
    current_image: str,
    acc_version: str,
) -> None:
    updater = load_updater()
    write_gpu_minimal_versions_config(
        tmp_path / "versions_config.yml",
        accelerator=accelerator,
        full_version="3.5.0",
        acc_version=acc_version,
        rhds_channel="stable",
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / f"konflux.{accelerator}.conf"
    write_conf(conf, f"BASE_IMAGE={current_image}")

    stub_published_rhds_gpu_stable_tags(monkeypatch, updater)
    stub_matching_rhds_stable_acc_version(monkeypatch, updater)
    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image(rhds_gpu_stable_image(accelerator))


def test_plan_updates_uses_rhds_cpu_stable_repo(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        full_version="3.5.0",
        replacements=[
            (
                '      rhds:\n        channel: fast\n        version: "<full_version>"',
                "      rhds:\n        channel: stable",
            )
        ],
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    write_conf(conf, f"BASE_IMAGE={RHDS_CPU_EA2_IMAGE}")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image("quay.io/aipcc/base-image-cpu-stable-ubi9:3.5")


def test_plan_updates_uses_odh_midstream_rocm_repo(tmp_path: Path) -> None:
    updater = load_updater()
    write_gpu_minimal_versions_config(
        tmp_path / "versions_config.yml",
        accelerator="rocm",
        acc_version="8.0",
        odh_origin="midstream",
        shared_acc_version=True,
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "rocm.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/opendatahub/odh-base-image-rocm-py312-c9s:v8.0")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image(
        "quay.io/opendatahub/odh-midstream-rocm-base-8-0:latest"
    )


def test_plan_updates_picks_rhds_stable_tag_matching_shared_acc_version_over_newer_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_gpu_minimal_versions_config(
        tmp_path / "versions_config.yml",
        accelerator="cuda",
        full_version="3.5.0",
        acc_version="24.9",
        rhds_channel="stable",
        shared_acc_version=True,
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    stub_rhds_repository_tags(
        monkeypatch,
        updater,
        {
            "quay.io/aipcc/base-images/cuda-stable": (
                "3.5.0-1780598175",
                "3.5.0-1780598176",
            )
        },
    )
    monkeypatch.setattr(
        updater,
        "inspect_rhds_stable_acc_version",
        lambda image, accelerator: {
            rhds_gpu_stable_image("cuda", build="1780598175"): "24.9",
            rhds_gpu_stable_image("cuda", build="1780598176"): "25.0",
        }[image],
    )

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image(rhds_gpu_stable_image("cuda", build="1780598175"))


def test_inspect_image_config_warns_in_red_on_skopeo_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(returncode=1, stderr="fatal auth error"),
    )

    with caplog.at_level("WARNING"):
        payload = updater.inspect_image_config(rhds_gpu_stable_image("cuda"), warning_color="red")

    assert payload is None
    assert caplog.records[-1].msg.startswith(f"{updater.ANSI_RED}WARNING:")
    assert f"skopeo inspect --config failed for {rhds_gpu_stable_image('cuda')}: fatal auth error" in caplog.text


def test_plan_updates_raises_in_red_when_rhds_stable_candidates_cannot_be_inspected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    updater = load_updater()
    write_gpu_minimal_versions_config(
        tmp_path / "versions_config.yml",
        accelerator="cuda",
        full_version="3.5.0",
        acc_version="25.0",
        rhds_channel="stable",
        shared_acc_version=True,
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    stub_published_rhds_gpu_stable_tags(monkeypatch, updater)
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(returncode=1, stderr="fatal auth error"),
    )

    with caplog.at_level("WARNING"), pytest.raises(ValueError, match=r"matches configured shared acc_version 25\.0"):
        updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert len(caplog.records) == 1
    assert caplog.records[-1].msg.startswith(f"{updater.ANSI_RED}WARNING:")
    assert "fatal auth error" in caplog.text


def test_plan_updates_raises_when_rhds_stable_acc_version_cannot_be_determined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_gpu_minimal_versions_config(
        tmp_path / "versions_config.yml",
        accelerator="cuda",
        full_version="3.5.0",
        acc_version="25.0",
        rhds_channel="stable",
        shared_acc_version=True,
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    stub_published_rhds_gpu_stable_tags(monkeypatch, updater)
    monkeypatch.setattr(updater, "inspect_rhds_stable_acc_version", lambda image, accelerator: None)

    with pytest.raises(ValueError, match=r"matches configured shared acc_version 25\.0"):
        updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))


def test_plan_updates_raises_when_no_rhds_stable_image_matches_shared_acc_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_gpu_minimal_versions_config(
        tmp_path / "versions_config.yml",
        accelerator="cuda",
        full_version="3.5.0",
        acc_version="25.0",
        rhds_channel="stable",
        shared_acc_version=True,
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, f"BASE_IMAGE={RHDS_CUDA_EA2_IMAGE}")

    stub_rhds_repository_tags(
        monkeypatch,
        updater,
        {"quay.io/aipcc/base-images/cuda-stable": ("3.5.0-1780598175",)},
    )
    monkeypatch.setattr(updater, "inspect_rhds_stable_acc_version", lambda image, accelerator: "24.9")

    with pytest.raises(ValueError, match=r"matches configured shared acc_version 25\.0") as exc_info:
        updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert "older acc_version 24.9" in str(exc_info.value)


def test_plan_updates_uses_odh_midstream_cpu_repo(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        python_version="3.11",
        replacements=[
            (
                '      odh:\n        origin: in-house\n        version: "latest"',
                '      odh:\n        origin: midstream\n        version: "latest"',
            )
        ],
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "cpu.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image(
        "quay.io/opendatahub/odh-midstream-python-base-3-11:latest"
    )


def test_plan_updates_uses_odh_in_house_cpu_repo_from_release_python_version(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", python_version="3.11")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "cpu.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image(
        "quay.io/opendatahub/odh-base-image-cpu-py311-c9s:latest"
    )


def test_plan_updates_can_switch_odh_rocm_back_to_in_house_repo(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "rocm.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/opendatahub/odh-midstream-rocm-base-7-1:latest")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == pinned_base_image(
        "quay.io/opendatahub/odh-base-image-rocm-py312-c9s:v8.0"
    )


def test_plan_updates_rewrites_release_to_minor_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.6.0")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(
        conf,
        textwrap.dedent(
            """\
            BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771
            PYLOCK_FLAVOR=cuda
            RELEASE=3.5
            """
        ).rstrip(),
    )

    monkeypatch.setattr(
        updater,
        "resolve_latest_published_rhds_image",
        lambda image, tag_cache=None: "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999",
    )
    stub_empty_rhds_tag_listing(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.splitlines() == [
        pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999"),
        "PYLOCK_FLAVOR=cuda",
        "RELEASE=3.6",
    ]


def test_main_updates_base_image_and_release_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(
        conf,
        textwrap.dedent(
            """\
            INDEX_URL=unchanged
            BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771
            PYLOCK_FLAVOR=cuda
            RELEASE=3.5
            """
        ).rstrip(),
    )

    monkeypatch.setattr(
        updater,
        "resolve_latest_published_rhds_image",
        lambda image, tag_cache=None: "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999",
    )
    stub_empty_rhds_tag_listing(monkeypatch, updater)

    assert updater.main(["--root", str(tmp_path), "--config", str(tmp_path / "versions_config.yml")]) == 0
    assert conf.read_text(encoding="utf-8").splitlines() == [
        "INDEX_URL=unchanged",
        pinned_base_image("quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999"),
        "PYLOCK_FLAVOR=cuda",
        "RELEASE=3.6",
    ]


def test_plan_updates_rewrites_root_makefile_release_defaults(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0", python_version="3.11")

    makefile = tmp_path / "Makefile"
    makefile.write_text(
        textwrap.dedent(
            """\
            IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images
            RELEASE          ?= 3.5
            RELEASE_PYTHON_VERSION ?= 3.12
            PRODUCT ?= odh
            """
        ),
        encoding="utf-8",
    )

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    updates_by_path = {update.path if hasattr(update, "path") else update.target.path: update for update in updates}

    assert updates_by_path[makefile].updated_text.splitlines() == [
        "IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images",
        "RELEASE          ?= 3.4",
        "RELEASE_PYTHON_VERSION ?= 3.11",
        "PRODUCT ?= odh",
    ]


def test_main_updates_root_makefile_release_defaults(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0", python_version="3.11")

    makefile = tmp_path / "Makefile"
    makefile.write_text(
        textwrap.dedent(
            """\
            IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images
            RELEASE          ?= 3.5
            RELEASE_PYTHON_VERSION ?= 3.12
            PRODUCT ?= odh
            """
        ),
        encoding="utf-8",
    )

    assert updater.main(["--root", str(tmp_path), "--config", str(tmp_path / "versions_config.yml")]) == 0
    assert makefile.read_text(encoding="utf-8").splitlines() == [
        "IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images",
        "RELEASE          ?= 3.4",
        "RELEASE_PYTHON_VERSION ?= 3.11",
        "PRODUCT ?= odh",
    ]


def test_main_dry_run_does_not_write_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    original = "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771\n"
    write_conf(conf, original.rstrip())

    monkeypatch.setattr(
        updater,
        "resolve_latest_published_rhds_image",
        lambda image, tag_cache=None: "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999",
    )
    stub_empty_rhds_tag_listing(monkeypatch, updater)

    assert updater.main(["--root", str(tmp_path), "--config", str(tmp_path / "versions_config.yml"), "--dry-run"]) == 0
    assert conf.read_text(encoding="utf-8") == original


def test_main_check_returns_nonzero_when_files_need_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(conf, "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771")

    monkeypatch.setattr(
        updater,
        "resolve_latest_published_rhds_image",
        lambda image, tag_cache=None: "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999",
    )
    stub_empty_rhds_tag_listing(monkeypatch, updater)

    assert updater.main(["--root", str(tmp_path), "--config", str(tmp_path / "versions_config.yml"), "--check"]) == 1
    assert conf.read_text(encoding="utf-8").strip() == (
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771"
    )


def test_main_updates_cuda_stable_with_rhds_stable_repo_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_gpu_minimal_versions_config(
        tmp_path / "versions_config.yml",
        accelerator="cuda",
        full_version="3.5.0",
        acc_version="12.9",
        rhds_channel="stable",
        shared_acc_version=True,
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    write_conf(
        conf,
        textwrap.dedent(
            """\
            INDEX_URL=unchanged
            BASE_IMAGE=quay.io/aipcc/base-images/cuda-12.9-el9.6:3.5.0-ea.2-1777919771
            PYLOCK_FLAVOR=cuda
            RELEASE=3.5
            """
        ).rstrip(),
    )

    seen: list[str] = []

    def fake_list(repository: str, tag_cache=None) -> tuple[str, ...]:
        seen.append(repository)
        if repository == "quay.io/example/testing/cuda-stable":
            return ("3.5.0-9999999999",)
        return ()

    monkeypatch.setattr(updater, "list_rhds_repository_tags", fake_list)
    monkeypatch.setattr(updater, "inspect_rhds_stable_acc_version", lambda image, accelerator: "12.9")

    assert (
        updater.main(
            [
                "--root",
                str(tmp_path),
                "--config",
                str(tmp_path / "versions_config.yml"),
                "--rhds-stable-repo-override=cuda=quay.io/example/testing/cuda-stable",
            ]
        )
        == 0
    )
    assert seen == ["quay.io/example/testing/cuda-stable"]
    assert conf.read_text(encoding="utf-8").splitlines() == [
        "INDEX_URL=unchanged",
        pinned_base_image("quay.io/example/testing/cuda-stable:3.5.0-9999999999"),
        "PYLOCK_FLAVOR=cuda",
        "RELEASE=3.5",
    ]
