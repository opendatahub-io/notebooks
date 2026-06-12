#!/usr/bin/env python3
"""Fix Gitleaks SARIF so GitHub code scanning upload accepts it.

Gitleaks 8.30.x sometimes emits endColumn=0. upload-sarif requires endColumn >= 1
(SARIF 2.1.0).

Alternative: ``npx -y @microsoft/sarif-multitool rewrite INPUT.sarif
--normalize-for-ghas --output OUTPUT.sarif`` also normalizes SARIF for GitHub
Advanced Security ingestion (see docs/sarif.md). We use this small script instead:
the multitool is a .NET application (pulled in via npm) and we avoid that runtime
dependency in CI. The multitool typically *removes* invalid column properties rather
than clamping them to valid values.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def sanitize_sarif(data: dict) -> tuple[dict, int]:
    """Clamp invalid ``endColumn`` values in result regions to satisfy upload-sarif."""
    fixed = 0
    for run in data.get("runs", []):
        for result in run.get("results", []):
            for location in result.get("locations", []):
                region = location.get("physicalLocation", {}).get("region")
                if not region:
                    continue
                end_col = region.get("endColumn")
                if end_col is None or end_col < 1:
                    start_col = region.get("startColumn", 1) or 1
                    region["endColumn"] = max(start_col, 1)
                    fixed += 1
    return data, fixed


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "gitleaks.sarif")
    data = json.loads(path.read_text(encoding="utf-8"))
    data, fixed = sanitize_sarif(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if fixed:
        print(f"Sanitized {fixed} SARIF region(s) with invalid endColumn in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
