#!/usr/bin/env python3
"""Merge pip-style constraint lines. Fail if the same package has two different specs."""
from __future__ import annotations

import re
import sys
from pathlib import Path

_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def pkg_name(spec: str) -> str:
    spec = spec.strip()
    if not spec or spec.startswith("#"):
        return ""
    m = _NAME.match(spec)
    if not m:
        return spec.lower()
    return m.group(1).replace("_", "-").lower()


def merge(paths: list[Path], dest: Path) -> None:
    by_name: dict[str, tuple[str, str]] = {}
    for path in paths:
        if not path.is_file():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            name = pkg_name(line)
            if not name:
                continue
            prev = by_name.get(name)
            if prev and prev[0] != line:
                src_a, src_b = prev[1], str(path)
                raise SystemExit(
                    f"Incompatible constraints for '{name}':\n"
                    f"  {src_a}: {prev[0]}\n"
                    f"  {src_b}: {line}\n"
                    "Do not mix these collections in one image. "
                    "Build two images, or install the second collection in an isolated venv."
                )
            by_name[name] = (line, str(path))

    lines = [
        "# Merged collection constraints — pip/uv -c",
        "# One ABI per image. Conflicting collections must not share site-packages.",
        "",
    ]
    for name in sorted(by_name):
        lines.append(by_name[name][0])
    dest.write_text("\n".join(lines) + "\n")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: merge-constraints.py DEST [CONSTRAINT_FILE ...]", file=sys.stderr)
        return 2
    dest = Path(sys.argv[1])
    merge([Path(p) for p in sys.argv[2:]], dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
