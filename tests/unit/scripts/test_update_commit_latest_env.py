from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "update-commit-latest-env.py"
_SPEC = importlib.util.spec_from_file_location("update_commit_latest_env", _MODULE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


@pytest.mark.parametrize(
    ("cfg", "expected"),
    [
        ({"config": {"Labels": {"vcs-ref": "abc1234567890abcdef"}}}, "abc1234567890abcdef"),
        ({"config": {"Labels": None}}, None),
        ({"config": {}}, None),
        ({"config": None}, None),
        ({}, None),
    ],
)
def test_vcs_ref_from_config(cfg: dict, expected: str | None) -> None:
    assert mod.vcs_ref_from_config(cfg) == expected


def test_fetch_quay_json_timeout_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_timeout(*_args, **_kwargs):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(mod.urllib.request, "urlopen", raise_timeout)

    with pytest.raises(ValueError, match="Quay API request failed"):
        mod._fetch_quay_json("https://quay.io/api/v1/repository/opendatahub/foo/tag/")


def test_fetch_quay_json_urlerror_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_url_error(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(mod.urllib.request, "urlopen", raise_url_error)

    with pytest.raises(ValueError, match="Quay API request failed"):
        mod._fetch_quay_json("https://quay.io/api/v1/repository/opendatahub/foo/tag/")


def test_fetch_quay_json_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"tags": []}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert mod._fetch_quay_json("https://quay.io/api/v1/repository/opendatahub/foo/tag/") == payload


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("main-" + "a" * 40, "aaaaaaa"),
        ("main-not-a-sha", None),
        ("rhoai-3.5", None),
    ],
)
def test_vcs_ref_from_odh_main_tag(tag: str, expected: str | None) -> None:
    assert mod.vcs_ref_from_odh_main_tag(tag) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("rhoai-3.5", "rhoai-3.5"),
        ("rhoai-3.5.1", None),
        ("main-abc", None),
    ],
)
def test_normalize_rhoai_version_tag(value: str, expected: str | None) -> None:
    assert mod.normalize_rhoai_version_tag(value) == expected


def test_rhoai_image_base_maps_opendatahub_to_rhoai() -> None:
    odh_url = "quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9:2026.1"
    assert (
        mod.rhoai_image_base(odh_url)
        == "quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9"
    )


def test_resolve_rhoai_version_tag_invalid_explicit_tag() -> None:
    args = argparse.Namespace(rhoai_version_tag="not-a-rhoai-tag")
    semaphore = asyncio.Semaphore(1)

    assert asyncio.run(mod.resolve_rhoai_version_tag(args, semaphore)) is None


def test_resolve_odh_vcs_ref_uses_pinned_tag_vcs_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_inspect(image_url: str, _semaphore, log_failure=True):
        return image_url, {"config": {"Labels": {"vcs-ref": "deadbeef0123456789"}}}

    monkeypatch.setattr(mod, "skopeo_inspect_config", fake_inspect)

    result = asyncio.run(
        mod.resolve_odh_vcs_ref(
            "quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9",
            "2026.1",
            asyncio.Semaphore(1),
        )
    )

    assert result == "deadbee"


def test_resolve_odh_vcs_ref_falls_back_to_main_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    main_tag = "main-" + "b" * 40

    async def fake_inspect(image_url: str, _semaphore, log_failure=True):
        if image_url.endswith(":missing-tag"):
            return image_url, None
        return image_url, {"config": {"Labels": {"vcs-ref": "cafebabe0123456789"}}}

    async def fake_find_latest(_base: str, _semaphore):
        return main_tag

    monkeypatch.setattr(mod, "skopeo_inspect_config", fake_inspect)
    monkeypatch.setattr(mod, "find_latest_odh_main_tag", fake_find_latest)

    result = asyncio.run(
        mod.resolve_odh_vcs_ref(
            "quay.io/opendatahub/odh-workbench-jupyter-minimal-cpu-py312-ubi9",
            "missing-tag",
            asyncio.Semaphore(1),
        )
    )

    assert result == "bbbbbbb"
