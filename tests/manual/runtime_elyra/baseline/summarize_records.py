"""Read the upstream CSV artifact and write summary statistics as JSON."""

from __future__ import annotations

import csv
import json
import statistics

values: list[int] = []

with open("raw_records") as input_file:
    reader = csv.DictReader(input_file)
    for row in reader:
        values.append(int(row["value"]))

if values:
    summary = {
        "count": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }
else:
    summary = {
        "count": 0,
        "mean": 0.0,
        "median": 0.0,
        "stdev": 0.0,
        "min": 0,
        "max": 0,
    }

with open("summary", "w") as output_file:
    json.dump(summary, output_file, indent=2)
