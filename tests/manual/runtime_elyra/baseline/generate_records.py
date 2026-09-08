"""Generate a small CSV dataset using only the Python standard library."""

from __future__ import annotations

import csv
import os
import random

record_count = int(os.getenv("record_count", "10"))
rng = random.Random(int(os.getenv("random_seed", "42")))  # ruff: ignore[suspicious-non-cryptographic-random-usage]

with open("raw_records", "w", newline="") as output_file:
    writer = csv.writer(output_file)
    writer.writerow(["id", "value"])
    for record_id in range(record_count):
        random_num = rng.randint(1, 100)
        writer.writerow([record_id, random_num])
