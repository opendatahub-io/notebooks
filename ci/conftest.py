from __future__ import annotations

import ast
import pathlib
import sys

import pytest

_ci_dir = pathlib.Path(__file__).parent

# ci/ and ci/cached-builds/ scripts use bare imports
# (e.g. `import gha_pr_changed_files`, `import package_versions_selftestdata`)
sys.path.insert(0, str(_ci_dir))
sys.path.insert(0, str(_ci_dir / "cached-builds"))

# Paths that cannot be imported as Python modules (hyphens in names)
collect_ignore_glob = ["check-image-availability.py"]
collect_ignore = ["security-scan", "cached_builds"]


def pytest_collect_file(parent: pytest.Collector, file_path: pathlib.Path):
    """Collect .py files in ci/ that contain unittest.TestCase but don't match python_files."""
    if not file_path.is_relative_to(_ci_dir):
        return None
    if file_path.suffix != ".py" or file_path.name.startswith("_"):
        return None

    ini_patterns = parent.config.getini("python_files")
    if any(file_path.match(p) for p in ini_patterns):
        return None

    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
    except OSError, SyntaxError:
        return None

    def _is_testcase_base(base: ast.expr) -> bool:
        return (
            isinstance(base, ast.Attribute)
            and isinstance(base.value, ast.Name)
            and base.value.id == "unittest"
            and base.attr == "TestCase"
        ) or (isinstance(base, ast.Name) and base.id == "TestCase")

    has_unittest_case = any(
        isinstance(node, ast.ClassDef) and any(_is_testcase_base(base) for base in node.bases)
        for node in ast.walk(tree)
    )
    if has_unittest_case:
        return pytest.Module.from_parent(parent, path=file_path)
    return None
