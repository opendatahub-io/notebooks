from __future__ import annotations

import pathlib
import pytest

from scripts.get_playwright_version import extract_playwright_version, strip_json5_comments


def test_strip_json5_comments():
    content = """
    // comment with @playwright/test
    {
      '@playwright/test': '=1.61.1', /* block comment
      with @playwright/test */
    }
    """
    cleaned = strip_json5_comments(content)
    assert "@playwright/test" in cleaned
    assert "comment with" not in cleaned
    assert "block comment" not in cleaned


@pytest.mark.parametrize(
    "manifest_content,expected_version",
    [
        ('{"@playwright/test": "=1.61.1"}', "1.61.1"),
        ('{"@playwright/test": "1.61.1"}', "1.61.1"),
        ("{\n  // @playwright/test: '=1.0.0'\n  '@playwright/test': '=2.0.5',\n}", "2.0.5"),
    ],
)
def test_extract_playwright_version_valid(tmp_path: pathlib.Path, manifest_content: str, expected_version: str):
    manifest = tmp_path / "package.json5"
    manifest.write_text(manifest_content, encoding="utf-8")
    assert extract_playwright_version(manifest) == expected_version


@pytest.mark.parametrize(
    "manifest_content",
    [
        '{"@playwright/test": "=1.61.1-beta"}',
        '{"@playwright/test": "=1.61.1extra"}',
        '{"@playwright/test": "1.61"}',
        '{"other-pkg": "1.61.1"}',
        '{"@playwright/test": "=1.61.1", "@playwright/test": "=1.62.0"}',
    ],
)
def test_extract_playwright_version_invalid(tmp_path: pathlib.Path, manifest_content: str):
    manifest = tmp_path / "package.json5"
    manifest.write_text(manifest_content, encoding="utf-8")
    with pytest.raises(ValueError):
        extract_playwright_version(manifest)
