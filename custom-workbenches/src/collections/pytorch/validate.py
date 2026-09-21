#!/usr/bin/env python3
"""Validate PyTorch collection imports."""
from __future__ import annotations

import importlib
import sys

REQUIRED = ("torch", "torchvision")


def main() -> int:
    failed: list[str] = []
    for name in REQUIRED:
        try:
            mod = importlib.import_module(name)
            version = getattr(mod, "__version__", "unknown")
            print(f"OK  {name} ({version})")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {exc}", file=sys.stderr)
            failed.append(name)
    if failed:
        print(f"Validation failed for: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("PyTorch collection validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
