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
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=example\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported build-args filename"):
        updater.collect_conf_targets(tmp_path)


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

    tag = updater.build_rhds_pinned_tag("3.5.0-ea.2-1777919771", release)

    assert tag == "3.4.0-1777919771"


def test_resolve_latest_published_rhds_image_uses_skopeo_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()

    class Completed:
        returncode = 0
        stdout = (
            '{"Repository":"quay.io/aipcc/base-images/cuda-25.0-el9.6","Tags":'
            '["3.6.0-ea.1-1777919000","3.6.0-ea.1-1777919999","3.6.0-ea.2-1777920000"]}'
        )
        stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

    latest = updater.resolve_latest_published_rhds_image(
        "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777000000"
    )

    assert latest == "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777919999"


def test_resolve_latest_published_rhds_image_rollback_falls_back_to_highest_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    class Completed:
        returncode = 0
        stdout = (
            '{"Repository":"quay.io/aipcc/base-images/cpu","Tags":'
            '["3.4.0-ea.1-1777919000","3.4.0-ea.2-1777919999","3.5.0-1777921111"]}'
        )
        stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

    latest = updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cpu:3.4.0-0")

    assert latest == "quay.io/aipcc/base-images/cpu:3.4.0-ea.2-1777919999"


def test_resolve_latest_published_rhds_image_rollback_raises_when_release_is_unpublished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    class Completed:
        returncode = 0
        stdout = '{"Repository":"quay.io/aipcc/base-images/cpu","Tags":["3.5.0-ea.2-1777919999"]}'
        stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

    with pytest.raises(ValueError, match=r"release '3.4.0'"):
        updater.resolve_latest_published_rhds_image("quay.io/aipcc/base-images/cpu:3.4.0-0")


def test_resolve_latest_published_rhds_image_raises_on_skopeo_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()

    class Completed:
        returncode = 1
        stdout = ""
        stderr = "manifest unknown"

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

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


def test_plan_updates_caches_rhds_tag_listing_per_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    first = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    second = tmp_path / "runtimes" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    base_image = "quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1777919771\n"
    first.write_text(f"BASE_IMAGE={base_image}", encoding="utf-8")
    second.write_text(f"BASE_IMAGE={base_image}", encoding="utf-8")

    calls: list[str] = []

    class Completed:
        returncode = 0
        stdout = '{"Tags":["3.6.0-ea.1-1777919999"]}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd[-1])
        return Completed()

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
    target_conf.parent.mkdir(parents=True)
    peer_conf.parent.mkdir(parents=True)
    target_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5\n", encoding="utf-8")
    peer_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

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
    assert rendered[target_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780000000"
    assert rendered[peer_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001"


def test_plan_updates_infers_ga_phase_for_stable_to_fast_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    target_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    peer_conf = tmp_path / "jupyter" / "pytorch" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    target_conf.parent.mkdir(parents=True)
    peer_conf.parent.mkdir(parents=True)
    target_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-image-cuda-stable-ubi9:3.5\n", encoding="utf-8")
    peer_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-1777919771\n",
        encoding="utf-8",
    )

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
    assert rendered[target_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1780000000"
    assert rendered[peer_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1780000001"


def test_plan_updates_falls_back_to_ea1_without_any_bundle_fast_style_peers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    first_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    second_conf = tmp_path / "runtimes" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    first_conf.parent.mkdir(parents=True)
    second_conf.parent.mkdir(parents=True)
    first_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5\n", encoding="utf-8")
    second_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5\n", encoding="utf-8")

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
    assert rendered[first_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780000000"
    assert rendered[second_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780000000"


def test_plan_updates_uses_highest_observed_bundle_phase_for_existing_fast_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    cpu_conf = tmp_path / "runtimes" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    cuda_conf = tmp_path / "jupyter" / "pytorch" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    cpu_conf.parent.mkdir(parents=True)
    cuda_conf.parent.mkdir(parents=True)
    cpu_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780600064\n", encoding="utf-8")
    cuda_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771\n",
        encoding="utf-8",
    )
    rocm_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.rocm.conf"
    rocm_conf.parent.mkdir(parents=True)
    rocm_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/rocm-8.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

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
    assert rendered[rocm_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/rocm-8.0-el9.6:3.5.0-ea.2-1780000002"
    assert rendered[cuda_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001"
    assert rendered[cpu_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780609999"


def test_plan_updates_uses_forward_discovery_not_bundle_phase_for_lagging_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    cpu_conf = tmp_path / "runtimes" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    cuda_conf = tmp_path / "jupyter" / "pytorch" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    cpu_conf.parent.mkdir(parents=True)
    cuda_conf.parent.mkdir(parents=True)
    cpu_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.4.0-ea.2-1780600064\n", encoding="utf-8")
    cuda_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

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
    assert rendered[cpu_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.1-1780609999"
    assert rendered[cuda_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000001"


def test_plan_updates_starts_new_release_at_ea1_when_peers_are_older_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.6.0")

    target_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    peer_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    target_conf.parent.mkdir(parents=True)
    peer_conf.parent.mkdir(parents=True)
    target_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5\n", encoding="utf-8")
    peer_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

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
    assert rendered[target_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.6.0-ea.1-1780000000"
    assert rendered[peer_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1780000001"


def test_plan_updates_uses_published_ga_for_new_release_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.4.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    class Completed:
        returncode = 0
        stdout = (
            '{"Repository":"quay.io/aipcc/base-images/cuda-25.0-el9.6","Tags":'
            '["3.5.0-ea.1-1777919000","3.5.0-ea.2-1777919999","3.5.0-1777921111"]}'
        )
        stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-1777921111"


def test_plan_updates_uses_highest_published_phase_for_new_release_when_ga_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.4.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    class Completed:
        returncode = 0
        stdout = (
            '{"Repository":"quay.io/aipcc/base-images/cuda-25.0-el9.6","Tags":'
            '["3.5.0-ea.1-1777919000","3.5.0-ea.2-1777919999"]}'
        )
        stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert (
        updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1777919999"
    )


def test_plan_updates_stable_to_fast_forward_uses_highest_published_phase_for_new_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.4\n", encoding="utf-8")

    class Completed:
        returncode = 0
        stdout = (
            '{"Repository":"quay.io/aipcc/base-images/cpu","Tags":["3.5.0-ea.1-1777919000","3.5.0-ea.2-1777919999"]}'
        )
        stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919999"


def test_plan_updates_new_release_without_published_tags_keeps_strict_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.5.0")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.4.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    class Completed:
        returncode = 0
        stdout = '{"Repository":"quay.io/aipcc/base-images/cuda-25.0-el9.6","Tags":["3.4.0-ea.2-1777919771"]}'
        stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

    with pytest.raises(ValueError, match="No matching published RHDS tag found"):
        updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))


def test_plan_updates_builds_fast_rhds_candidate_before_latest_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771\n",
        encoding="utf-8",
    )

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)
    stub_empty_rhds_tag_listing(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert seen == ["quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777919771"]
    assert (
        updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999"
    )


def test_plan_updates_rollback_targets_ga_family_for_older_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0")

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771\n", encoding="utf-8")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cpu:3.4.0-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert seen == ["quay.io/aipcc/base-images/cpu:3.4.0-1777919771"]
    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.4.0-1780000000"


def test_plan_updates_rollback_ignores_newer_fast_peers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0")

    cpu_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    cuda_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    cpu_conf.parent.mkdir(parents=True)
    cuda_conf.parent.mkdir(parents=True)
    cpu_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780600064\n", encoding="utf-8")
    cuda_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

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
    assert rendered[cpu_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.4.0-1780609999"
    assert rendered[cuda_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.4.0-1780000001"


def test_plan_updates_rollback_falls_back_to_highest_published_phase_when_ga_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0")

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771\n", encoding="utf-8")

    class Completed:
        returncode = 0
        stdout = (
            '{"Repository":"quay.io/aipcc/base-images/cpu","Tags":'
            '["3.4.0-ea.1-1777919000","3.4.0-ea.2-1777919999","3.5.0-ea.2-1777921111"]}'
        )
        stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda *args, **kwargs: Completed())

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.4.0-ea.2-1777919999"


def test_plan_updates_rollback_from_stable_target_uses_ga_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.4.0")

    conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5\n", encoding="utf-8")

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cpu:3.4.0-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert seen == ["quay.io/aipcc/base-images/cpu:3.4.0-0"]
    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.4.0-1780000000"


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
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        rhds:\n          channel: stable\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
            )
        ],
    )

    cpu_conf = tmp_path / "jupyter" / "datascience" / "ubi9-python-3.12" / "build-args" / "konflux.cpu.conf"
    cuda_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    cpu_conf.parent.mkdir(parents=True)
    cuda_conf.parent.mkdir(parents=True)
    cpu_conf.write_text("BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771\n", encoding="utf-8")
    cuda_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)
    stub_matching_rhds_stable_acc_version(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path.name: update.updated_text.strip() for update in updates}

    assert seen == ["quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771"]
    assert rendered["konflux.cpu.conf"] == "BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1780000000"
    assert rendered["konflux.cuda.conf"] == "BASE_IMAGE=quay.io/aipcc/base-image-cuda-stable-ubi9:3.5"


def test_plan_updates_allows_cuda_minimal_stable_and_pytorch_fast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        full_version="3.5.0",
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        rhds:\n          channel: stable\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
            )
        ],
    )

    minimal_conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    pytorch_conf = tmp_path / "jupyter" / "pytorch" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    minimal_conf.parent.mkdir(parents=True)
    pytorch_conf.parent.mkdir(parents=True)
    minimal_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )
    pytorch_conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    seen: list[str] = []

    def fake_resolve(image: str, tag_cache=None) -> str:
        seen.append(image)
        return "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000000"

    monkeypatch.setattr(updater, "resolve_latest_published_rhds_image", fake_resolve)
    stub_matching_rhds_stable_acc_version(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))
    rendered = {update.target.path: update.updated_text.strip() for update in updates}

    assert seen == ["quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1777919771"]
    assert rendered[minimal_conf] == "BASE_IMAGE=quay.io/aipcc/base-image-cuda-stable-ubi9:3.5"
    assert rendered[pytorch_conf] == "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.5.0-ea.2-1780000000"


def test_plan_updates_uses_rhds_cuda_stable_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        full_version="3.5.0",
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        rhds:\n          channel: stable\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
            )
        ],
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    stub_matching_rhds_stable_acc_version(monkeypatch, updater)
    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-image-cuda-stable-ubi9:3.5"


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
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/aipcc/base-images/cpu:3.5.0-ea.2-1777919771\n", encoding="utf-8")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-image-cpu-stable-ubi9:3.5"


def test_plan_updates_uses_rhds_rocm_stable_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        full_version="3.5.0",
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "8.0"\n        odh:\n          origin: in-house\n          acc_version: "8.0"',
                '      minimal:\n        rhds:\n          channel: stable\n        odh:\n          origin: in-house\n          acc_version: "8.0"',
            )
        ],
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.rocm.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/rocm-7.1-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    stub_matching_rhds_stable_acc_version(monkeypatch, updater)
    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-image-rocm-stable-ubi9:3.5"


def test_plan_updates_uses_odh_midstream_rocm_repo(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "8.0"\n        odh:\n          origin: in-house\n          acc_version: "8.0"',
                '      minimal:\n        acc_version: "8.0"\n        rhds:\n          channel: fast\n        odh:\n          origin: midstream',
            )
        ],
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "rocm.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/opendatahub/odh-base-image-rocm-py312-c9s:v8.0\n", encoding="utf-8")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/opendatahub/odh-midstream-rocm-base-8-0:latest"


def test_plan_updates_warns_when_rhds_stable_image_acc_version_differs_from_shared_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        full_version="3.5.0",
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        acc_version: "25.0"\n        rhds:\n          channel: stable\n        odh:\n          origin: in-house',
            )
        ],
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(updater, "inspect_rhds_stable_acc_version", lambda image, accelerator: "24.9")

    with caplog.at_level("WARNING"):
        updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-image-cuda-stable-ubi9:3.5"
    assert caplog.records[-1].msg.startswith("\x1b[32mWARNING:")
    assert "Configured shared cuda acc_version 25.0" in caplog.text
    assert "use acc_version 24.9" in caplog.text


def test_inspect_image_config_warns_in_red_on_skopeo_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    updater = load_updater()

    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["skopeo"],
            returncode=1,
            stdout="",
            stderr="fatal auth error",
        ),
    )

    with caplog.at_level("WARNING"):
        payload = updater.inspect_image_config("quay.io/aipcc/base-image-cuda-stable-ubi9:3.5", warning_color="red")

    assert payload is None
    assert caplog.records[-1].msg.startswith("\x1b[31mWARNING:")
    assert (
        "skopeo inspect --config failed for quay.io/aipcc/base-image-cuda-stable-ubi9:3.5: fatal auth error"
        in caplog.text
    )


def test_plan_updates_warns_in_yellow_when_rhds_stable_acc_version_cannot_be_determined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    updater = load_updater()
    write_versions_config(
        tmp_path / "versions_config.yml",
        full_version="3.5.0",
        replacements=[
            (
                '      minimal:\n        rhds:\n          channel: fast\n          acc_version: "25.0"\n        odh:\n          origin: in-house\n          acc_version: "25.0"',
                '      minimal:\n        acc_version: "25.0"\n        rhds:\n          channel: stable\n        odh:\n          origin: in-house',
            )
        ],
    )

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.2-1777919771\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(updater, "inspect_rhds_stable_acc_version", lambda image, accelerator: None)

    with caplog.at_level("WARNING"):
        updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/aipcc/base-image-cuda-stable-ubi9:3.5"
    assert caplog.records[-1].msg.startswith("\x1b[33mWARNING:")
    assert "Could not determine RHDS stable cuda acc_version" in caplog.text


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
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest\n", encoding="utf-8")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/opendatahub/odh-midstream-python-base-3-11:latest"


def test_plan_updates_uses_odh_in_house_cpu_repo_from_release_python_version(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", python_version="3.11")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "cpu.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest\n", encoding="utf-8")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/opendatahub/odh-base-image-cpu-py311-c9s:latest"


def test_plan_updates_can_switch_odh_rocm_back_to_in_house_repo(tmp_path: Path) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "rocm.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("BASE_IMAGE=quay.io/opendatahub/odh-midstream-rocm-base-7-1:latest\n", encoding="utf-8")

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.strip() == "BASE_IMAGE=quay.io/opendatahub/odh-base-image-rocm-py312-c9s:v8.0"


def test_plan_updates_rewrites_release_to_minor_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml", full_version="3.6.0")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        textwrap.dedent(
            """\
            BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771
            PYLOCK_FLAVOR=cuda
            RELEASE=3.5
            """
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        updater,
        "resolve_latest_published_rhds_image",
        lambda image, tag_cache=None: "quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999",
    )
    stub_empty_rhds_tag_listing(monkeypatch, updater)

    updates = updater.plan_updates(tmp_path, updater.load_versions_config(tmp_path / "versions_config.yml"))

    assert updates[0].updated_text.splitlines() == [
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999",
        "PYLOCK_FLAVOR=cuda",
        "RELEASE=3.6",
    ]


def test_main_updates_base_image_and_release_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        textwrap.dedent(
            """\
            INDEX_URL=unchanged
            BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771
            PYLOCK_FLAVOR=cuda
            RELEASE=3.5
            """
        ),
        encoding="utf-8",
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
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-25.0-el9.6:3.6.0-ea.1-1777929999",
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
            KONFLUX ?= no
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
        "KONFLUX ?= no",
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
            KONFLUX ?= no
            """
        ),
        encoding="utf-8",
    )

    assert updater.main(["--root", str(tmp_path), "--config", str(tmp_path / "versions_config.yml")]) == 0
    assert makefile.read_text(encoding="utf-8").splitlines() == [
        "IMAGE_REGISTRY   ?= quay.io/opendatahub/workbench-images",
        "RELEASE          ?= 3.4",
        "RELEASE_PYTHON_VERSION ?= 3.11",
        "KONFLUX ?= no",
    ]


def test_main_dry_run_does_not_write_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    updater = load_updater()
    write_versions_config(tmp_path / "versions_config.yml")

    conf = tmp_path / "jupyter" / "minimal" / "ubi9-python-3.12" / "build-args" / "konflux.cuda.conf"
    conf.parent.mkdir(parents=True)
    original = "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771\n"
    conf.write_text(original, encoding="utf-8")

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
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "BASE_IMAGE=quay.io/aipcc/base-images/cuda-13.0-el9.6:3.5.0-ea.1-1777919771\n",
        encoding="utf-8",
    )

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
