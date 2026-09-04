from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

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
