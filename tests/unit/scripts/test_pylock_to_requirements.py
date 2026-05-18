from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "lockfile-generators" / "helpers" / "pylock-to-requirements.py"
_SPEC = importlib.util.spec_from_file_location("pylock_to_requirements", _MODULE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
helper = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(helper)


def test_extract_default_index_from_pylock_strips_format_json(tmp_path: Path) -> None:
    pylock_path = tmp_path / "pylock.toml"
    pylock_path.write_text(
        "# uv pip compile --default-index=https://example.invalid/simple/?format=json\n",
        encoding="utf-8",
    )

    assert helper.extract_default_index_from_pylock(pylock_path) == "https://example.invalid/simple/"
