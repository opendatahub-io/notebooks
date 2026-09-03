"""Validate the summary artifact and emit a pass/fail report."""

from __future__ import annotations

import json

with open("summary") as input_file:
    summary = json.load(input_file)

checks = {
    "count_positive": summary["count"] > 0,
    "mean_in_range": 1 <= summary["mean"] <= 100,
    "min_le_max": summary["min"] <= summary["max"],
}
passed = all(checks.values())

report = {
    "status": "PASS" if passed else "FAIL",
    "checks": checks,
    "summary": summary,
}

with open("validation_report", "w") as output_file:
    json.dump(report, output_file, indent=2)

if not passed:
    raise SystemExit(1)
