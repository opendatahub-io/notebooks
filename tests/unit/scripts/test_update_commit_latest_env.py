from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, call

import pytest

if TYPE_CHECKING:
    from pytest import MonkeyPatch

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "update-commit-latest-env.py"
_SPEC = importlib.util.spec_from_file_location("update_commit_latest_env", _MODULE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
update_env = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(update_env)


def test_find_latest_tag_selects_newest_matching_tag_and_forwards_logging(monkeypatch: MonkeyPatch) -> None:
    tags = ["not-a-main-tag", f"main-{'a' * 40}", f"main-{'b' * 40}"]
    inspected: list[tuple[str, bool]] = []

    def inspect_config(
        image_url: str,
        semaphore: asyncio.Semaphore,
        *,
        log_failure: bool,
    ) -> tuple[str, dict[str, str]]:
        inspected.append((image_url, log_failure))
        created = "2026-01-02T00:00:00Z" if image_url.endswith("a" * 40) else "2026-01-03T00:00:00Z"
        return image_url, {"created": created}

    monkeypatch.setattr(update_env, "skopeo_list_tags", AsyncMock(return_value=tags))
    monkeypatch.setattr(update_env, "skopeo_inspect_config", AsyncMock(side_effect=inspect_config))

    result = asyncio.run(
        update_env.find_latest_tag_by_skopeo_created(
            "quay.io/example/image", update_env.ODH_TAG_PATTERN, asyncio.Semaphore(1), log_failure=False
        )
    )

    assert result == f"main-{'b' * 40}"
    assert inspected == [
        (f"quay.io/example/image:main-{'a' * 40}", False),
        (f"quay.io/example/image:main-{'b' * 40}", False),
    ]


def test_find_latest_tag_returns_none_without_matching_tags(monkeypatch: MonkeyPatch) -> None:
    inspect_config = AsyncMock()

    monkeypatch.setattr(update_env, "skopeo_list_tags", AsyncMock(return_value=["rhoai-3.6", "latest"]))
    monkeypatch.setattr(update_env, "skopeo_inspect_config", inspect_config)

    result = asyncio.run(
        update_env.find_latest_tag_by_skopeo_created(
            "quay.io/example/image", update_env.ODH_TAG_PATTERN, asyncio.Semaphore(1)
        )
    )

    assert result is None
    inspect_config.assert_not_awaited()


def test_find_latest_tag_returns_none_when_all_inspects_fail(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        update_env,
        "skopeo_list_tags",
        AsyncMock(return_value=[f"main-{'a' * 40}", f"main-{'b' * 40}"]),
    )
    monkeypatch.setattr(update_env, "skopeo_inspect_config", AsyncMock(return_value=("unused", None)))

    result = asyncio.run(
        update_env.find_latest_tag_by_skopeo_created(
            "quay.io/example/image", update_env.ODH_TAG_PATTERN, asyncio.Semaphore(1)
        )
    )

    assert result is None


def test_find_latest_rhoai_tag_enables_failure_logging_explicitly(monkeypatch: MonkeyPatch) -> None:
    semaphore = asyncio.Semaphore(1)
    helper = AsyncMock(return_value="rhoai-3.6")

    monkeypatch.setattr(update_env, "find_latest_tag_by_skopeo_created", helper)

    result = asyncio.run(update_env.find_latest_rhoai_tag_by_created("quay.io/example/image", semaphore))

    assert result == "rhoai-3.6"
    helper.assert_awaited_once_with("quay.io/example/image", update_env.RHOAI_TAG_PATTERN, semaphore, log_failure=True)


def test_find_latest_odh_main_tag_disables_failure_logging_on_fallback(monkeypatch: MonkeyPatch) -> None:
    semaphore = asyncio.Semaphore(1)
    helper = AsyncMock(return_value=f"main-{'a' * 40}")

    monkeypatch.setattr(update_env, "quay_list_matching_tags", AsyncMock(return_value=[]))
    monkeypatch.setattr(update_env, "find_latest_tag_by_skopeo_created", helper)

    result = asyncio.run(update_env.find_latest_odh_main_tag("quay.io/example/image", semaphore))

    assert result == f"main-{'a' * 40}"
    helper.assert_awaited_once_with("quay.io/example/image", update_env.ODH_TAG_PATTERN, semaphore, log_failure=False)


def test_load_workbench_images_filters_comments_and_non_workbench_entries(tmp_path: Path) -> None:
    params = tmp_path / "params.env"
    params.write_text(
        "# comment\n"
        "odh-workbench-jupyter-minimal-cpu-py312-ubi9-n=quay.io/opendatahub/image:tag\n"
        "pipeline-runtime-n=dummy\n"
        "odh-workbench-rstudio-n=quay.io/opendatahub/rstudio:tag\n",
        encoding="utf-8",
    )

    assert update_env.load_workbench_images(params) == [
        ("odh-workbench-jupyter-minimal-cpu-py312-ubi9-n", "quay.io/opendatahub/image:tag"),
        ("odh-workbench-rstudio-n", "quay.io/opendatahub/rstudio:tag"),
    ]


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("quay.io/opendatahub/image:tag", ("quay.io/opendatahub/image", "tag")),
        ("quay.io/opendatahub/image", ("quay.io/opendatahub/image", "")),
    ],
)
def test_parse_image_ref(image: str, expected: tuple[str, str]) -> None:
    assert update_env.parse_image_ref(image) == expected


def test_parse_quay_repository_rejects_other_hosts() -> None:
    with pytest.raises(ValueError, match=r"not a quay\.io repository"):
        update_env.parse_quay_repository("registry.example/image")


def test_skopeo_list_tags_handles_invalid_payload(monkeypatch: MonkeyPatch) -> None:
    process = AsyncMock(returncode=0)
    process.communicate.return_value = (b'{"Tags": "not-a-list"}', b"")
    monkeypatch.setattr(update_env.asyncio, "create_subprocess_exec", AsyncMock(return_value=process))

    result = asyncio.run(update_env.skopeo_list_tags("quay.io/example/image", asyncio.Semaphore(1)))

    assert result == []


def test_skopeo_inspect_config_uses_argument_list_and_extracts_config(monkeypatch: MonkeyPatch) -> None:
    process = AsyncMock(returncode=0)
    config = {"config": {"Labels": {"vcs-ref": "abcdef1234567"}}}
    process.communicate.return_value = (json.dumps(config).encode(), b"")
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(update_env.asyncio, "create_subprocess_exec", create_process)

    result = asyncio.run(update_env.skopeo_inspect_config("quay.io/example/image:tag", asyncio.Semaphore(1)))

    assert result == ("quay.io/example/image:tag", config)
    assert create_process.await_args == call(
        "skopeo",
        "inspect",
        "--override-os=linux",
        "--override-arch=amd64",
        "--retry-times=3",
        "--config",
        "docker://quay.io/example/image:tag",
        stdout=update_env.asyncio.subprocess.PIPE,
        stderr=update_env.asyncio.subprocess.PIPE,
    )


def test_skopeo_inspect_config_handles_missing_skopeo(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(update_env.asyncio, "create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError))

    result = asyncio.run(update_env.skopeo_inspect_config("quay.io/example/image:tag", asyncio.Semaphore(1)))

    assert result == ("quay.io/example/image:tag", None)


def test_communicate_kills_process_after_timeout(monkeypatch: MonkeyPatch) -> None:
    process = AsyncMock()
    process.kill = Mock()

    async def communicate_forever() -> tuple[bytes, bytes]:
        await asyncio.sleep(1)
        return b"", b""

    process.communicate.side_effect = communicate_forever
    monkeypatch.setattr(update_env, "SKOPEO_TIMEOUT_SEC", 0.001)

    with pytest.raises(TimeoutError):
        asyncio.run(update_env._communicate(process))

    process.kill.assert_called_once_with()
    process.wait.assert_awaited_once_with()


def test_write_commit_env_sorts_and_uses_utf8(tmp_path: Path) -> None:
    destination = tmp_path / "commit-latest.env"

    update_env.write_commit_env([("z-key", "last"), ("a-key", "first")], destination)

    assert destination.read_text(encoding="utf-8") == "a-key=first\nz-key=last\n"
