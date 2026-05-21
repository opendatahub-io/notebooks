"""Unit tests for scripts/update-commit-latest-env.py."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

# The script filename contains hyphens, so we import via importlib.
_spec = importlib.util.spec_from_file_location(
    "update_commit_latest_env",
    _REPO_ROOT / "scripts" / "update-commit-latest-env.py",
)
assert _spec is not None and _spec.loader is not None
ucle = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ucle
_spec.loader.exec_module(ucle)


# ---------------------------------------------------------------------------
# Helpers — fake subprocess for the Nullables pattern
# ---------------------------------------------------------------------------


def _make_fake_process(stdout: bytes, stderr: bytes = b"", returncode: int = 0):
    """Return an object that quacks like an asyncio.subprocess.Process."""
    proc = AsyncMock()
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    return proc


def _skopeo_config_json(vcs_ref: str | None) -> bytes:
    labels = {"vcs-ref": vcs_ref} if vcs_ref else {}
    return json.dumps({"config": {"Labels": labels}}).encode()


# ---------------------------------------------------------------------------
# Env-file parsing
# ---------------------------------------------------------------------------


class TestEnvFileParsing:
    def test_parse_basic_entries(self, tmp_path: Path) -> None:
        env = tmp_path / "params-latest.env"
        env.write_text("foo-n=quay.io/org/foo@sha256:aaa\nbar-n=quay.io/org/bar@sha256:bbb\n")
        parsed = ucle.parse_env_file(env)
        assert parsed == [
            ("foo-n", "quay.io/org/foo@sha256:aaa"),
            ("bar-n", "quay.io/org/bar@sha256:bbb"),
        ]

    def test_skip_comments_and_blanks(self, tmp_path: Path) -> None:
        env = tmp_path / "params-latest.env"
        env.write_text("# this is a comment\n\nfoo-n=quay.io/org/foo@sha256:aaa\n  # indented comment\n\n")
        parsed = ucle.parse_env_file(env)
        assert parsed == [("foo-n", "quay.io/org/foo@sha256:aaa")]

    def test_value_with_equals_sign(self, tmp_path: Path) -> None:
        env = tmp_path / "params-latest.env"
        env.write_text("foo-n=quay.io/org/foo@sha256:abc=def\n")
        parsed = ucle.parse_env_file(env)
        assert parsed == [("foo-n", "quay.io/org/foo@sha256:abc=def")]

    def test_rejects_malformed_line_without_equals(self, tmp_path: Path) -> None:
        env = tmp_path / "params-latest.env"
        env.write_text("good-n=value\nmalformed line\n")
        with pytest.raises(ValueError, match="invalid env entry at line 2"):
            ucle.parse_env_file(env)


# ---------------------------------------------------------------------------
# Variable-name transformation
# ---------------------------------------------------------------------------


class TestVariableNameTransformation:
    def test_suffix_n_becomes_commit_n(self) -> None:
        assert re.sub(r"-n$", "-commit-n", "foo-n") == "foo-commit-n"

    def test_no_suffix_n_unchanged(self) -> None:
        assert re.sub(r"-n$", "-commit-n", "foo-bar") == "foo-bar"

    def test_internal_n_not_replaced(self) -> None:
        assert re.sub(r"-n$", "-commit-n", "foo-n-bar") == "foo-n-bar"

    def test_real_variable_names(self) -> None:
        name = "odh-workbench-jupyter-minimal-cpu-py312-ubi9-n"
        assert re.sub(r"-n$", "-commit-n", name) == ("odh-workbench-jupyter-minimal-cpu-py312-ubi9-commit-n")


# ---------------------------------------------------------------------------
# get_image_vcs_ref — stubbing the subprocess boundary (Nullables)
# ---------------------------------------------------------------------------


class TestGetImageVcsRef:
    def test_extracts_vcs_ref(self) -> None:
        fake_proc = _make_fake_process(_skopeo_config_json("abc1234def5678"))
        sem = asyncio.Semaphore(1)

        with patch.object(asyncio, "create_subprocess_exec", return_value=fake_proc):
            url, ref = asyncio.run(ucle.get_image_vcs_ref("quay.io/org/img@sha256:aaa", sem))

        assert url == "quay.io/org/img@sha256:aaa"
        assert ref == "abc1234def5678"

    def test_returns_none_when_label_missing(self) -> None:
        fake_proc = _make_fake_process(_skopeo_config_json(None))
        sem = asyncio.Semaphore(1)

        with patch.object(asyncio, "create_subprocess_exec", return_value=fake_proc):
            _url, ref = asyncio.run(ucle.get_image_vcs_ref("quay.io/org/img@sha256:aaa", sem))

        assert ref is None

    def test_returns_none_on_nonzero_exit(self) -> None:
        fake_proc = _make_fake_process(b"", stderr=b"error", returncode=1)
        sem = asyncio.Semaphore(1)

        with patch.object(asyncio, "create_subprocess_exec", return_value=fake_proc):
            _url, ref = asyncio.run(ucle.get_image_vcs_ref("quay.io/org/img@sha256:aaa", sem))

        assert ref is None

    def test_returns_none_on_empty_stdout(self) -> None:
        fake_proc = _make_fake_process(b"", returncode=0)
        sem = asyncio.Semaphore(1)

        with patch.object(asyncio, "create_subprocess_exec", return_value=fake_proc):
            _url, ref = asyncio.run(ucle.get_image_vcs_ref("quay.io/org/img@sha256:aaa", sem))

        assert ref is None

    def test_returns_none_on_invalid_json(self) -> None:
        fake_proc = _make_fake_process(b"not json at all")
        sem = asyncio.Semaphore(1)

        with patch.object(asyncio, "create_subprocess_exec", return_value=fake_proc):
            _url, ref = asyncio.run(ucle.get_image_vcs_ref("quay.io/org/img@sha256:aaa", sem))

        assert ref is None

    def test_returns_none_when_skopeo_not_found(self) -> None:
        sem = asyncio.Semaphore(1)

        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError

        with patch.object(asyncio, "create_subprocess_exec", side_effect=raise_fnf):
            _url, ref = asyncio.run(ucle.get_image_vcs_ref("quay.io/org/img@sha256:aaa", sem))

        assert ref is None


# ---------------------------------------------------------------------------
# inspect — concurrent orchestration
# ---------------------------------------------------------------------------


class TestInspect:
    def test_gathers_results_for_multiple_images(self) -> None:
        calls = iter(
            [
                _make_fake_process(_skopeo_config_json("aaaaaaa")),
                _make_fake_process(_skopeo_config_json("bbbbbbb")),
            ]
        )

        with patch.object(asyncio, "create_subprocess_exec", side_effect=lambda *a, **kw: next(calls)):
            results = asyncio.run(ucle.inspect(["quay.io/org/a@sha256:aaa", "quay.io/org/b@sha256:bbb"]))

        assert len(results) == 2
        by_url = dict(results)
        assert by_url["quay.io/org/a@sha256:aaa"] == "aaaaaaa"
        assert by_url["quay.io/org/b@sha256:bbb"] == "bbbbbbb"

    def test_handles_empty_input(self) -> None:
        results = asyncio.run(ucle.inspect([]))
        assert results == []


# ---------------------------------------------------------------------------
# main — end-to-end with real temp files and stubbed subprocess
# ---------------------------------------------------------------------------


class TestMain:
    def test_end_to_end(self, tmp_path: Path) -> None:
        params = tmp_path / "params-latest.env"
        params.write_text("img-alpha-n=quay.io/org/alpha@sha256:aaa\nimg-beta-n=quay.io/org/beta@sha256:bbb\n")

        calls = iter(
            [
                _make_fake_process(_skopeo_config_json("1234567890abcdef")),
                _make_fake_process(_skopeo_config_json("fedcba0987654321")),
            ]
        )

        with (
            patch.object(ucle, "PROJECT_ROOT", tmp_path),
            patch.object(asyncio, "create_subprocess_exec", side_effect=lambda *a, **kw: next(calls)),
        ):
            (tmp_path / "manifests" / "odh" / "base").mkdir(parents=True)
            params_real = tmp_path / "manifests" / "odh" / "base" / "params-latest.env"
            commit_real = tmp_path / "manifests" / "odh" / "base" / "commit-latest.env"
            params_real.write_text("img-alpha-n=quay.io/org/alpha@sha256:aaa\nimg-beta-n=quay.io/org/beta@sha256:bbb\n")

            asyncio.run(ucle.main())

            output = commit_real.read_text()

        lines = output.strip().split("\n")
        assert len(lines) == 2
        assert lines == sorted(lines)
        for line in lines:
            var, val = line.split("=")
            assert "-commit-n" in var
            assert len(val) == 7

    def test_exits_on_failed_inspection(self, tmp_path: Path) -> None:
        (tmp_path / "manifests" / "odh" / "base").mkdir(parents=True)
        params = tmp_path / "manifests" / "odh" / "base" / "params-latest.env"
        params.write_text("img-n=quay.io/org/img@sha256:aaa\n")

        fake_proc = _make_fake_process(b"", stderr=b"fail", returncode=1)

        with (
            patch.object(ucle, "PROJECT_ROOT", tmp_path),
            patch.object(asyncio, "create_subprocess_exec", return_value=fake_proc),
            pytest.raises(SystemExit, match="1"),
        ):
            asyncio.run(ucle.main())

    def test_output_is_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "manifests" / "odh" / "base").mkdir(parents=True)
        params = tmp_path / "manifests" / "odh" / "base" / "params-latest.env"
        params.write_text(
            "zzz-n=quay.io/org/z@sha256:aaa\naaa-n=quay.io/org/a@sha256:bbb\nmmm-n=quay.io/org/m@sha256:ccc\n"
        )

        calls = iter(
            [
                _make_fake_process(_skopeo_config_json("1111111")),
                _make_fake_process(_skopeo_config_json("2222222")),
                _make_fake_process(_skopeo_config_json("3333333")),
            ]
        )

        with (
            patch.object(ucle, "PROJECT_ROOT", tmp_path),
            patch.object(asyncio, "create_subprocess_exec", side_effect=lambda *a, **kw: next(calls)),
        ):
            asyncio.run(ucle.main())

        output = (tmp_path / "manifests" / "odh" / "base" / "commit-latest.env").read_text()
        lines = output.strip().split("\n")
        assert lines == sorted(lines)
        assert lines[0].startswith("aaa-commit-n=")
        assert lines[1].startswith("mmm-commit-n=")
        assert lines[2].startswith("zzz-commit-n=")

    def test_commit_hash_truncated_to_7_chars(self, tmp_path: Path) -> None:
        (tmp_path / "manifests" / "odh" / "base").mkdir(parents=True)
        params = tmp_path / "manifests" / "odh" / "base" / "params-latest.env"
        params.write_text("img-n=quay.io/org/img@sha256:aaa\n")

        fake_proc = _make_fake_process(_skopeo_config_json("abcdef1234567890"))

        with (
            patch.object(ucle, "PROJECT_ROOT", tmp_path),
            patch.object(asyncio, "create_subprocess_exec", return_value=fake_proc),
        ):
            asyncio.run(ucle.main())

        output = (tmp_path / "manifests" / "odh" / "base" / "commit-latest.env").read_text()
        _, val = output.strip().split("=")
        assert val == "abcdef1"

    def test_skips_comments_in_params_file(self, tmp_path: Path) -> None:
        (tmp_path / "manifests" / "odh" / "base").mkdir(parents=True)
        params = tmp_path / "manifests" / "odh" / "base" / "params-latest.env"
        params.write_text("# a comment\n\nimg-n=quay.io/org/img@sha256:aaa\n")

        fake_proc = _make_fake_process(_skopeo_config_json("abcdef1234567890"))

        with (
            patch.object(ucle, "PROJECT_ROOT", tmp_path),
            patch.object(asyncio, "create_subprocess_exec", return_value=fake_proc),
        ):
            asyncio.run(ucle.main())

        output = (tmp_path / "manifests" / "odh" / "base" / "commit-latest.env").read_text()
        lines = output.strip().split("\n")
        assert len(lines) == 1
        assert lines[0] == "img-commit-n=abcdef1"
