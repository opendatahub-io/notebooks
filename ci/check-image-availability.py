#!/usr/bin/env python3
"""Check that all image references in params env files exist in their container registries.

This is a focused availability check.
It verifies that images can be fetched and, for successful checks,
reads the image config timestamp so CI and local runs can show a richer summary with image age.

Usage:
    python ci/check-image-availability.py manifests/odh/base/params-latest.env manifests/odh/base/params.env
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import shutil
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Self
from urllib.parse import quote

import structlog
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from ci.logging_config import configure_logging, make_pretty_log

log = structlog.get_logger()


COMMAND_TIMEOUT_SECONDS = 120
MAX_CONCURRENT_CHECKS = 22
SUMMARY_MISSING_VALUE = "—"


@dataclass(slots=True)
class ImageCheckResult:
    variable: str
    image_url: str
    available: bool
    created: datetime | None = None
    error: str | None = None


@dataclass(slots=True)
class ProgressState:
    total: int
    completed: int = 0
    ok_count: int = 0
    missing_count: int = 0


class RichProgressTable(AbstractContextManager["RichProgressTable"]):
    """Render a stable live table for local TTY runs."""

    def __init__(self, entries: list[tuple[str, str]]) -> None:
        self._console = Console(stderr=True)
        self._supports_hyperlinks = terminal_supports_hyperlinks()
        self._order = [image_url for _, image_url in entries]
        self._rows = {
            image_url: {
                "status": "Pending",
                "quay_url": None,
                "age": SUMMARY_MISSING_VALUE,
            }
            for _, image_url in entries
        }
        self._live = Live(
            self._render_table(),
            console=self._console,
            auto_refresh=False,
            transient=True,
        )

    def __enter__(self) -> Self:
        self._live.start()
        self._live.refresh()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._live.stop()

    def update_result(self, result: ImageCheckResult, state: ProgressState) -> None:
        self._rows[result.image_url] = {
            "status": "OK" if result.available else "Missing",
            "quay_url": build_quay_url(result.image_url),
            "age": format_age(result.created),
        }
        self._console.print(self._render_progress_line(result, state))
        self._live.update(self._render_table(), refresh=False)
        self._live.refresh()

    def print_final_table(self) -> None:
        self._console.print(self._render_table())

    def _render_progress_line(self, result: ImageCheckResult, state: ProgressState) -> Text:
        progress_line = Text()
        progress_line.append(f"[{state.completed}/{state.total}] ", style="dim")
        progress_line.append("OK" if result.available else "Missing", style="green" if result.available else "red")
        progress_line.append(f" {result.image_url}")
        age = format_age(result.created)
        if age != SUMMARY_MISSING_VALUE:
            progress_line.append(f" ({age})", style="dim")
        return progress_line

    def _render_table(self) -> Table:
        table = Table(title="Image Availability Check")
        table.add_column("Image", overflow="fold")
        table.add_column("Status", no_wrap=True)
        table.add_column("Age", no_wrap=True)

        for image_url in self._order:
            row = self._rows[image_url]
            status = row["status"]
            status_style = {
                "Pending": "yellow",
                "OK": "green",
                "Missing": "red",
            }[status]

            image_cell = render_image_cell(image_url, self._supports_hyperlinks)

            table.add_row(
                image_cell,
                f"[{status_style}]{status}[/{status_style}]",
                row["age"],
            )

        return table


def parse_created_timestamp(created: str | None) -> datetime | None:
    if not created:
        return None

    parsed = datetime.fromisoformat(created)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_age(created: datetime | None) -> str:
    if created is None:
        return SUMMARY_MISSING_VALUE

    delta = datetime.now(UTC) - created
    total_seconds = max(0, int(delta.total_seconds()))

    if total_seconds < 60:
        return "Just now"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m ago"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h ago"
    if total_seconds < 604800:
        return f"{total_seconds // 86400}d ago"
    return f"{total_seconds // 604800}w ago"


def build_quay_url(image_url: str) -> str | None:
    prefix = "quay.io/"
    if not image_url.startswith(prefix):
        return None

    repository_ref = image_url.removeprefix(prefix)
    if "/" not in repository_ref:
        return None

    namespace, repository_with_ref = repository_ref.split("/", maxsplit=1)
    repository = repository_with_ref
    tag: str | None = None

    if "@sha256:" in repository_with_ref:
        repository = repository_with_ref.split("@", maxsplit=1)[0]
    elif ":" in repository_with_ref:
        repository, tag = repository_with_ref.rsplit(":", maxsplit=1)

    base_url = f"https://quay.io/repository/{quote(namespace)}/{quote(repository, safe='')}"
    if tag:
        return f"{base_url}?tab=tags&tag={quote(tag, safe='')}"
    return base_url


def build_image_http_url(image_url: str) -> str | None:
    if image_url.startswith(("http://", "https://")):
        return image_url
    return build_quay_url(image_url)


def render_image_cell(image_url: str, supports_hyperlinks: bool) -> Text | str:
    http_url = build_image_http_url(image_url)
    if http_url is None:
        return image_url

    if not supports_hyperlinks:
        return image_url

    image_cell = Text(image_url, style="cyan")
    image_cell.stylize(f"link {http_url}")
    return image_cell


def format_markdown_image(image_url: str) -> str:
    return f"`{image_url.replace('|', '\\|')}`"


def write_github_step_summary(results: list[ImageCheckResult]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    ok_count = sum(1 for result in results if result.available)
    missing = [result for result in results if not result.available]

    lines = [
        "## Image Availability Check",
        "",
        f"Checked **{len(results)}** images: **{ok_count} OK**, **{len(missing)} missing**.",
        "",
        "| Image | Status | Quay link | Age |",
        "| --- | --- | --- | --- |",
    ]

    for result in sorted(results, key=lambda item: item.image_url):
        quay_url = build_quay_url(result.image_url)
        link_cell = f"[Open in Quay]({quay_url})" if quay_url else SUMMARY_MISSING_VALUE
        lines.append(
            f"| {format_markdown_image(result.image_url)} | "
            f"{'OK' if result.available else 'Missing'} | "
            f"{link_cell} | {format_age(result.created)} |"
        )

    if missing:
        lines.extend(
            [
                "",
                "### Missing Images",
                "",
                "| Variable | Image |",
                "| --- | --- |",
            ]
        )
        for result in sorted(missing, key=lambda item: item.variable):
            lines.append(f"| `{result.variable}` | {format_markdown_image(result.image_url)} |")

    lines.append("")

    try:
        with open(summary_path, "a", encoding="utf-8") as summary_file:
            summary_file.write("\n".join(lines))
    except OSError:
        log.exception("Failed to write GitHub step summary", path=summary_path)


def terminal_supports_hyperlinks() -> bool:
    """Best-effort OSC 8 hyperlink support detection.

    Terminals expose support via a mix of environment variables rather than a
    single standard capability flag. This keeps the local Rich table readable in
    terminals like macOS Terminal.app that do not support OSC 8 hyperlinks.
    """
    force = os.environ.get("FORCE_HYPERLINK")
    if force is not None:
        return force not in {"0", "false", "False", ""}

    if os.environ.get("TERM") == "dumb":
        return False

    if os.environ.get("TERM_PROGRAM") == "Apple_Terminal":
        return False

    if os.environ.get("TERM_PROGRAM") in {"iTerm.app", "WezTerm", "vscode"}:
        return True

    if any(
        os.environ.get(key)
        for key in (
            "KITTY_WINDOW_ID",
            "GHOSTTY_RESOURCES_DIR",
            "WT_SESSION",
            "KONSOLE_VERSION",
            "ITERM_SESSION_ID",
            "WEZTERM_EXECUTABLE",
        )
    ):
        return True

    if os.environ.get("VTE_VERSION"):
        return True

    return False


def should_use_rich_output() -> bool:
    return not os.environ.get("CI") and sys.stderr.isatty()


_SKOPEO_MSG_RE = re.compile(r'msg="(.*)"')


def _extract_skopeo_error(stderr_text: str) -> str:
    """Extract a concise error reason from skopeo's logfmt stderr.

    Skopeo emits lines like:
        time="..." level=fatal msg="Error parsing image name \"docker://REG/REPO:TAG\": ... : manifest unknown"

    This extracts just the tail reason (e.g. "manifest unknown") for readable logging.
    Falls back to the full stderr if parsing fails.
    """
    match = _SKOPEO_MSG_RE.search(stderr_text)
    if not match:
        return stderr_text
    msg = match.group(1).replace('\\"', '"')
    # The reason is typically after the last ": "
    last_colon = msg.rfind(": ")
    if last_colon != -1:
        return msg[last_colon + 2 :]
    return msg


async def check_image(
    variable: str,
    image_url: str,
    semaphore: asyncio.Semaphore,
    *,
    emit_immediate_errors: bool,
) -> ImageCheckResult:
    """Check whether a container image exists in the registry."""
    full_image_url = f"docker://{image_url}"
    command = [
        "skopeo",
        "inspect",
        "--config",
        "--override-os=linux",
        "--override-arch=amd64",
        "--retry-times=3",
        full_image_url,
    ]

    try:
        async with semaphore:
            log.debug("Checking image availability", image_url=image_url)
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=COMMAND_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                if emit_immediate_errors:
                    log.error("Timeout checking image", image_url=image_url)
                return ImageCheckResult(
                    variable=variable,
                    image_url=image_url,
                    available=False,
                    error="Timeout checking image",
                )

        if process.returncode != 0:
            stderr_text = stderr.decode().strip() if stderr else ""
            error = _extract_skopeo_error(stderr_text) if stderr_text else "Image not found"
            if emit_immediate_errors:
                log.error("Image check failed", image_url=image_url, error=error)
            return ImageCheckResult(
                variable=variable,
                image_url=image_url,
                available=False,
                error=error,
            )

        inspect_data = json.loads(stdout.decode())
        created = parse_created_timestamp(inspect_data.get("created"))
        log.debug("Image exists", image_url=image_url, created=created.isoformat() if created else None)
        return ImageCheckResult(
            variable=variable,
            image_url=image_url,
            available=True,
            created=created,
        )

    except Exception:
        log.exception("Unexpected error checking image", image_url=image_url)
        return ImageCheckResult(
            variable=variable,
            image_url=image_url,
            available=False,
            error="Unexpected error checking image",
        )


async def check_image_with_progress(
    variable: str,
    image_url: str,
    semaphore: asyncio.Semaphore,
    state: ProgressState,
    state_lock: asyncio.Lock,
    rich_table: RichProgressTable | None,
) -> ImageCheckResult:
    result = await check_image(
        variable,
        image_url,
        semaphore,
        emit_immediate_errors=rich_table is None,
    )
    quay_url = build_quay_url(result.image_url)
    age = format_age(result.created)

    async with state_lock:
        state.completed += 1
        if result.available:
            state.ok_count += 1
        else:
            state.missing_count += 1

        if rich_table is not None:
            rich_table.update_result(result, state)
        else:
            log.info(
                "Image check progress",
                completed=state.completed,
                total=state.total,
                ok_so_far=state.ok_count,
                missing_so_far=state.missing_count,
                image_url=result.image_url,
                available=result.available,
                age=None if age == SUMMARY_MISSING_VALUE else age,
                quay_url=quay_url,
            )

    return result


def parse_env_file(path: pathlib.Path) -> list[tuple[str, str]]:
    """Parse a params env file into (variable, image_url) pairs.

    Skips empty lines, comments, and dummy values.
    """
    entries: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            variable, _, image_url = line.partition("=")
            if not image_url or image_url == "dummy":
                continue
            entries.append((variable, image_url))
    return entries


async def run_checks(
    all_entries: list[tuple[str, str]],
    rich_table: RichProgressTable | None,
) -> list[ImageCheckResult]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
    state = ProgressState(total=len(all_entries))
    state_lock = asyncio.Lock()
    tasks = [
        check_image_with_progress(variable, image_url, semaphore, state, state_lock, rich_table)
        for variable, image_url in all_entries
    ]
    return await asyncio.gather(*tasks)


async def main() -> int:
    pretty_log = make_pretty_log()

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <env-file> [<env-file> ...]", file=sys.stderr)
        return 2

    if shutil.which("skopeo") is None:
        log.error("The 'skopeo' command was not found. Please ensure it is installed and in your PATH.")
        return 2

    all_entries: list[tuple[str, str]] = []
    for arg in sys.argv[1:]:
        path = pathlib.Path(arg)
        if not path.exists():
            log.error("File not found", path=str(path))
            return 2
        entries = parse_env_file(path)
        log.info("Parsed env file", path=str(path), count=len(entries))
        all_entries.extend(entries)

    # Detect duplicate image URLs — two variables pointing to the same image is a bug
    seen_urls: dict[str, str] = {}
    for variable, image_url in all_entries:
        if image_url in seen_urls:
            log.error(
                "Duplicate image URL detected",
                image_url=image_url,
                variable_1=seen_urls[image_url],
                variable_2=variable,
            )
            return 1
        seen_urls[image_url] = variable

    rich_table: RichProgressTable | None = None
    if should_use_rich_output():
        rich_table = RichProgressTable(all_entries)
        with rich_table:
            results = await run_checks(all_entries, rich_table)
    else:
        results = await run_checks(all_entries, rich_table)

    write_github_step_summary(results)

    failed = [result for result in results if not result.available]

    log.info("Check complete", total=len(results), failed=len(failed))

    if failed:
        pretty_log.error(
            "The following images were NOT found in their registries",
            failures=[{"variable": r.variable, "image_url": r.image_url, "error": r.error} for r in failed],
        )
        if rich_table is not None:
            rich_table.print_final_table()
        return 1

    log.info("All images are available in their registries.")
    if rich_table is not None:
        rich_table.print_final_table()
    return 0


if __name__ == "__main__":
    configure_logging()
    sys.exit(asyncio.run(main()))
