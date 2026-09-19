from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.get_playwright_version import extract_playwright_version

if TYPE_CHECKING:
    from pathlib import Path


def test_extract_playwright_version_with_url_before_dependency(tmp_path: Path) -> None:
    manifest = tmp_path / "package.json5"
    manifest.write_text(
        "{ repository: { url: 'https://example.test/repo' },\n"
        "  devDependencies: { '@playwright/test': '=1.63.0' } }\n",
        encoding="utf-8",
    )

    assert extract_playwright_version(manifest) == "1.63.0"
