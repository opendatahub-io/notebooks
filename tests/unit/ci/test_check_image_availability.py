"""Unit tests for ci/check-image-availability.py."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import textwrap
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

mod = importlib.import_module("ci.check-image-availability")


# ---------------------------------------------------------------------------
# Nullable subprocess layer (Nullables pattern)
#
# Instead of mocking asyncio internals we provide a thin fake for the only I/O
# boundary: ``asyncio.create_subprocess_exec``.  Each ``FakeProcess`` instance
# behaves like a real ``asyncio.subprocess.Process`` (stdout/stderr bytes,
# returncode) and ``communicate()`` returns immediately.
# ---------------------------------------------------------------------------


class FakeProcess:
    """Nullable replacement for asyncio.subprocess.Process."""

    def __init__(
        self,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        *,
        hang: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self._hang = hang
        self._killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._hang:
            await asyncio.sleep(3600)
        return self.stdout, self.stderr

    def kill(self) -> None:
        self._killed = True

    async def wait(self) -> int:
        return self.returncode


def make_create_subprocess_exec(
    process: FakeProcess,
) -> Any:
    """Return an async callable that ignores its arguments and yields *process*."""

    async def _create(*args: Any, **kwargs: Any) -> FakeProcess:  # noqa: RUF029
        return process

    return _create


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skopeo_ok_json(created: str = "2025-04-01T12:00:00Z") -> bytes:
    return json.dumps({"created": created}).encode()


# ---------------------------------------------------------------------------
# parse_env_file
# ---------------------------------------------------------------------------


class TestParseEnvFile:
    def test_basic_entries(self, tmp_path: Path) -> None:
        env = tmp_path / "params.env"
        env.write_text(
            textwrap.dedent("""\
                FOO=quay.io/org/img:tag1
                BAR=quay.io/org/img:tag2
            """),
        )
        result = mod.parse_env_file(env)
        assert result == [
            ("FOO", "quay.io/org/img:tag1"),
            ("BAR", "quay.io/org/img:tag2"),
        ]

    def test_skips_comments_and_blanks(self, tmp_path: Path) -> None:
        env = tmp_path / "params.env"
        env.write_text(
            textwrap.dedent("""\
                # this is a comment
                FOO=quay.io/org/img:tag1

                # another comment
                BAR=quay.io/org/img:tag2
            """),
        )
        result = mod.parse_env_file(env)
        assert len(result) == 2

    def test_skips_dummy_values(self, tmp_path: Path) -> None:
        env = tmp_path / "params.env"
        env.write_text("KEY=dummy\nOTHER=quay.io/org/img:v1\n")
        result = mod.parse_env_file(env)
        assert result == [("OTHER", "quay.io/org/img:v1")]

    def test_skips_empty_values(self, tmp_path: Path) -> None:
        env = tmp_path / "params.env"
        env.write_text("EMPTY=\nGOOD=quay.io/org/img:v1\n")
        result = mod.parse_env_file(env)
        assert result == [("GOOD", "quay.io/org/img:v1")]

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = mod.parse_env_file(tmp_path / "nonexistent.env")
        assert result == []


# ---------------------------------------------------------------------------
# Duplicate image URL detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """The main() function exits with 1 when the same image URL appears under two variables."""

    def test_duplicate_urls_detected(self, tmp_path: Path) -> None:
        env = tmp_path / "params.env"
        env.write_text(
            "VAR_A=quay.io/org/img:same\nVAR_B=quay.io/org/img:same\n",
        )
        entries = mod.parse_env_file(env)

        seen_urls: dict[str, str] = {}
        duplicates: list[tuple[str, str, str]] = []
        for variable, image_url in entries:
            if image_url in seen_urls:
                duplicates.append((image_url, seen_urls[image_url], variable))
            seen_urls[image_url] = variable

        assert len(duplicates) == 1
        assert duplicates[0] == ("quay.io/org/img:same", "VAR_A", "VAR_B")

    def test_no_duplicates_when_urls_differ(self, tmp_path: Path) -> None:
        env = tmp_path / "params.env"
        env.write_text(
            "A=quay.io/org/img:v1\nB=quay.io/org/img:v2\n",
        )
        entries = mod.parse_env_file(env)

        seen_urls: dict[str, str] = {}
        for variable, image_url in entries:
            assert image_url not in seen_urls
            seen_urls[image_url] = variable


# ---------------------------------------------------------------------------
# parse_created_timestamp
# ---------------------------------------------------------------------------


class TestParseCreatedTimestamp:
    def test_isoformat_utc(self) -> None:
        result = mod.parse_created_timestamp("2025-04-01T12:00:00Z")
        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2025

    def test_naive_gets_utc(self) -> None:
        result = mod.parse_created_timestamp("2025-04-01T12:00:00")
        assert result is not None
        assert result.tzinfo == UTC

    def test_none_returns_none(self) -> None:
        assert mod.parse_created_timestamp(None) is None

    def test_empty_returns_none(self) -> None:
        assert mod.parse_created_timestamp("") is None


# ---------------------------------------------------------------------------
# format_age
# ---------------------------------------------------------------------------


class TestFormatAge:
    def test_none_returns_dash(self) -> None:
        assert mod.format_age(None) == mod.SUMMARY_MISSING_VALUE

    def test_just_now(self) -> None:
        assert mod.format_age(datetime.now(UTC)) == "Just now"

    def test_minutes(self) -> None:
        t = datetime.now(UTC) - timedelta(minutes=5)
        assert mod.format_age(t) == "5m ago"

    def test_hours(self) -> None:
        t = datetime.now(UTC) - timedelta(hours=3)
        assert mod.format_age(t) == "3h ago"

    def test_days(self) -> None:
        t = datetime.now(UTC) - timedelta(days=2)
        assert mod.format_age(t) == "2d ago"

    def test_weeks(self) -> None:
        t = datetime.now(UTC) - timedelta(weeks=3)
        assert mod.format_age(t) == "3w ago"


# ---------------------------------------------------------------------------
# build_quay_url
# ---------------------------------------------------------------------------


class TestBuildQuayUrl:
    def test_tag_reference(self) -> None:
        url = mod.build_quay_url("quay.io/org/repo:v1.0")
        assert url == "https://quay.io/repository/org/repo?tab=tags&tag=v1.0"

    def test_digest_reference(self) -> None:
        url = mod.build_quay_url("quay.io/org/repo@sha256:abc123")
        assert url == "https://quay.io/repository/org/repo"

    def test_non_quay_returns_none(self) -> None:
        assert mod.build_quay_url("docker.io/library/nginx:latest") is None

    def test_no_slash_in_path_returns_none(self) -> None:
        assert mod.build_quay_url("quay.io/noslash") is None

    def test_no_tag_no_digest(self) -> None:
        url = mod.build_quay_url("quay.io/org/repo")
        assert url == "https://quay.io/repository/org/repo"


# ---------------------------------------------------------------------------
# _extract_skopeo_error
# ---------------------------------------------------------------------------


class TestExtractSkopeoError:
    def test_extracts_tail_reason(self) -> None:
        stderr = (
            'time="2025-04-01" level=fatal msg="Error parsing image name \\"docker://q.io/r:t\\": manifest unknown"'
        )
        assert mod._extract_skopeo_error(stderr) == "manifest unknown"

    def test_fallback_to_full_stderr(self) -> None:
        stderr = "something went wrong"
        assert mod._extract_skopeo_error(stderr) == "something went wrong"

    def test_msg_without_colon(self) -> None:
        stderr = 'msg="simple error message"'
        assert mod._extract_skopeo_error(stderr) == "simple error message"


# ---------------------------------------------------------------------------
# format_markdown_image
# ---------------------------------------------------------------------------


class TestFormatMarkdownImage:
    def test_basic(self) -> None:
        assert mod.format_markdown_image("quay.io/org/repo:v1") == "`quay.io/org/repo:v1`"

    def test_pipe_escaped(self) -> None:
        assert mod.format_markdown_image("quay.io/org/repo|foo") == r"`quay.io/org/repo\|foo`"


# ---------------------------------------------------------------------------
# terminal_supports_hyperlinks
# ---------------------------------------------------------------------------


class TestTerminalSupportsHyperlinks:
    def test_force_hyperlink_true(self) -> None:
        with patch.dict(os.environ, {"FORCE_HYPERLINK": "1"}, clear=True):
            assert mod.terminal_supports_hyperlinks() is True

    def test_force_hyperlink_false(self) -> None:
        with patch.dict(os.environ, {"FORCE_HYPERLINK": "0"}, clear=True):
            assert mod.terminal_supports_hyperlinks() is False

    def test_dumb_terminal(self) -> None:
        with patch.dict(os.environ, {"TERM": "dumb"}, clear=True):
            assert mod.terminal_supports_hyperlinks() is False

    def test_apple_terminal(self) -> None:
        with patch.dict(os.environ, {"TERM_PROGRAM": "Apple_Terminal"}, clear=True):
            assert mod.terminal_supports_hyperlinks() is False

    def test_iterm(self) -> None:
        with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}, clear=True):
            assert mod.terminal_supports_hyperlinks() is True


# ---------------------------------------------------------------------------
# check_image — async, using Nullable subprocess
# ---------------------------------------------------------------------------


class TestCheckImage:
    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def test_available_image(self) -> None:
        async def _test() -> None:
            semaphore = asyncio.Semaphore(1)
            fake = FakeProcess(stdout=_skopeo_ok_json("2025-04-01T12:00:00Z"), returncode=0)
            with patch("asyncio.create_subprocess_exec", make_create_subprocess_exec(fake)):
                result = await mod.check_image("VAR", "quay.io/org/img:v1", semaphore, emit_immediate_errors=False)

            assert result.available is True
            assert result.error is None
            assert result.created is not None
            assert result.created.year == 2025

        self._run(_test())

    def test_unavailable_image(self) -> None:
        async def _test() -> None:
            semaphore = asyncio.Semaphore(1)
            fake = FakeProcess(
                stderr=b'msg="manifest unknown"',
                returncode=1,
            )
            with patch("asyncio.create_subprocess_exec", make_create_subprocess_exec(fake)):
                result = await mod.check_image("VAR", "quay.io/org/img:v1", semaphore, emit_immediate_errors=False)

            assert result.available is False
            assert result.error == "manifest unknown"

        self._run(_test())

    def test_empty_stderr_on_failure(self) -> None:
        async def _test() -> None:
            semaphore = asyncio.Semaphore(1)
            fake = FakeProcess(returncode=1)
            with patch("asyncio.create_subprocess_exec", make_create_subprocess_exec(fake)):
                result = await mod.check_image("VAR", "quay.io/org/img:v1", semaphore, emit_immediate_errors=False)

            assert result.available is False
            assert result.error == "Image not found"

        self._run(_test())

    def test_timeout(self) -> None:
        async def _test() -> mod.ImageCheckResult:
            semaphore = asyncio.Semaphore(1)
            fake = FakeProcess(hang=True)
            with (
                patch("asyncio.create_subprocess_exec", make_create_subprocess_exec(fake)),
                patch.object(mod, "COMMAND_TIMEOUT_SECONDS", 0.01),
            ):
                result = await mod.check_image("VAR", "quay.io/org/img:v1", semaphore, emit_immediate_errors=False)

            assert result.available is False
            assert result.error == "Timeout checking image"
            assert fake._killed is True
            return result

        self._run(_test())

    def test_json_parse_error(self) -> None:
        async def _test() -> None:
            semaphore = asyncio.Semaphore(1)
            fake = FakeProcess(stdout=b"not json", returncode=0)
            with patch("asyncio.create_subprocess_exec", make_create_subprocess_exec(fake)):
                result = await mod.check_image("VAR", "quay.io/org/img:v1", semaphore, emit_immediate_errors=False)

            assert result.available is False
            assert result.error == "Unexpected error checking image"

        self._run(_test())


# ---------------------------------------------------------------------------
# run_checks — integration of check_image + progress
# ---------------------------------------------------------------------------


class TestRunChecks:
    def test_all_available(self) -> None:
        async def _test() -> None:
            entries = [
                ("A", "quay.io/org/img:v1"),
                ("B", "quay.io/org/img:v2"),
            ]
            fake = FakeProcess(stdout=_skopeo_ok_json(), returncode=0)
            with patch("asyncio.create_subprocess_exec", make_create_subprocess_exec(fake)):
                results = await mod.run_checks(entries, rich_table=None)

            assert len(results) == 2
            assert all(r.available for r in results)

        asyncio.run(_test())

    def test_mixed_results(self) -> None:
        async def _test() -> None:
            call_count = 0

            async def _create(*args: Any, **kwargs: Any) -> FakeProcess:  # noqa: RUF029
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return FakeProcess(stdout=_skopeo_ok_json(), returncode=0)
                return FakeProcess(stderr=b'msg="not found"', returncode=1)

            entries = [
                ("A", "quay.io/org/img:v1"),
                ("B", "quay.io/org/img:v2"),
            ]
            with patch("asyncio.create_subprocess_exec", _create):
                results = await mod.run_checks(entries, rich_table=None)

            assert len(results) == 2
            available = [r for r in results if r.available]
            missing = [r for r in results if not r.available]
            assert len(available) >= 1
            assert len(missing) >= 1

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# write_github_step_summary — Markdown summary generation
# ---------------------------------------------------------------------------


class TestWriteGithubStepSummary:
    def test_writes_summary_file(self, tmp_path: Path) -> None:
        summary_path = tmp_path / "summary.md"
        results = [
            mod.ImageCheckResult(variable="A", image_url="quay.io/org/img:v1", available=True),
            mod.ImageCheckResult(variable="B", image_url="quay.io/org/img:v2", available=False, error="not found"),
        ]
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
            mod.write_github_step_summary(results)

        content = summary_path.read_text()
        assert "## Image Availability Check" in content
        assert "**2** images" in content
        assert "**1 OK**" in content
        assert "**1 missing**" in content

    def test_summary_contains_missing_section(self, tmp_path: Path) -> None:
        summary_path = tmp_path / "summary.md"
        results = [
            mod.ImageCheckResult(variable="BROKEN", image_url="quay.io/org/broken:v1", available=False, error="gone"),
        ]
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
            mod.write_github_step_summary(results)

        content = summary_path.read_text()
        assert "### Missing Images" in content
        assert "`BROKEN`" in content

    def test_no_missing_section_when_all_ok(self, tmp_path: Path) -> None:
        summary_path = tmp_path / "summary.md"
        results = [
            mod.ImageCheckResult(variable="A", image_url="quay.io/org/img:v1", available=True),
        ]
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
            mod.write_github_step_summary(results)

        content = summary_path.read_text()
        assert "### Missing Images" not in content

    def test_no_op_without_env_var(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            mod.write_github_step_summary([])

    def test_summary_includes_quay_link(self, tmp_path: Path) -> None:
        summary_path = tmp_path / "summary.md"
        results = [
            mod.ImageCheckResult(variable="X", image_url="quay.io/org/repo:tag1", available=True),
        ]
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
            mod.write_github_step_summary(results)

        content = summary_path.read_text()
        assert "[Open in Quay]" in content
        assert "quay.io/repository/org/repo" in content

    def test_summary_with_age(self, tmp_path: Path) -> None:
        summary_path = tmp_path / "summary.md"
        results = [
            mod.ImageCheckResult(
                variable="X",
                image_url="quay.io/org/repo:tag1",
                available=True,
                created=datetime(2020, 1, 1, tzinfo=UTC),
            ),
        ]
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
            mod.write_github_step_summary(results)

        content = summary_path.read_text()
        assert "w ago" in content


# ---------------------------------------------------------------------------
# render_image_cell
# ---------------------------------------------------------------------------


class TestRenderImageCell:
    def test_non_quay_returns_plain_string(self) -> None:
        result = mod.render_image_cell("docker.io/library/nginx:latest", supports_hyperlinks=True)
        assert result == "docker.io/library/nginx:latest"

    def test_hyperlinks_disabled_returns_string(self) -> None:
        result = mod.render_image_cell("quay.io/org/repo:v1", supports_hyperlinks=False)
        assert result == "quay.io/org/repo:v1"


# ---------------------------------------------------------------------------
# should_use_rich_output
# ---------------------------------------------------------------------------


class TestShouldUseRichOutput:
    def test_ci_returns_false(self) -> None:
        with patch.dict(os.environ, {"CI": "true"}):
            assert mod.should_use_rich_output() is False
