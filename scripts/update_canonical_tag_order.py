#!/usr/bin/env python3
"""Insert the previous release into ``_BASE_CANONICAL_TAG_ORDER``.

``tests/test_main.py`` prepends the current release at runtime. The list itself
holds older tags, newest first. A bump from 3.7 to 3.8 has to record ``3.7``
there or ``make test`` rejects the rolled-out ImageStream tags.

The previous release is read from the Jupyter Universal ImageStream: its first
tag before rollout, and its second tag after rollout.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT = re.compile(r"^(_BASE_CANONICAL_TAG_ORDER = )(\[.*?\])", re.M | re.S)
RELEASE_TAG = re.compile(r"^\d+\.\d+$")
UNIVERSAL_IMAGESTREAM = "jupyter-universal-notebook-imagestream.yaml"


def release_tag(root: Path) -> str:
    full_version = yaml.safe_load((root / "versions_config.yml").read_text(encoding="utf-8"))["release"]["full_version"]
    major, minor, _patch = str(full_version).split(".")
    return f"{int(major)}.{int(minor)}"


def previous_release(root: Path, release: str) -> str:
    """N-1 from the ODH and RHOAI Jupyter Universal ImageStreams. They must agree."""
    found: set[str] = set()
    for variant in ("odh", "rhoai"):
        path = root / "manifests" / variant / "base" / UNIVERSAL_IMAGESTREAM
        names = [tag["name"] for tag in yaml.safe_load(path.read_text(encoding="utf-8"))["spec"]["tags"]]
        previous = names[1] if names[0] == release else names[0]
        if not isinstance(previous, str) or RELEASE_TAG.fullmatch(previous) is None:
            raise ValueError(f"{variant} N-1 tag is not a release tag: {previous!r}")
        found.add(previous)
    if len(found) != 1:
        raise ValueError(f"ODH and RHOAI disagree on the N-1 release: {sorted(found)}")
    return found.pop()


def update_canonical_tag_order(root: Path) -> None:
    release = release_tag(root)
    previous = previous_release(root, release)
    path = root / "tests" / "test_main.py"
    source = path.read_text(encoding="utf-8")
    match = ASSIGNMENT.search(source)
    if match is None:
        raise ValueError("_BASE_CANONICAL_TAG_ORDER assignment was not found")

    order = ast.literal_eval(match.group(2))
    if order[:1] == [previous]:
        print(f"_BASE_CANONICAL_TAG_ORDER already starts with {previous} (current release is {release})")
        return

    updated = [previous, *[tag for tag in order if tag != previous]]
    rendered = "[\n" + "".join(f"    {json.dumps(tag)},\n" for tag in updated) + "]"
    path.write_text(source[: match.start(2)] + rendered + source[match.end(2) :], encoding="utf-8")
    print(f"Recorded previous release {previous} in _BASE_CANONICAL_TAG_ORDER (current release is {release})")


def main() -> None:
    update_canonical_tag_order(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT)


if __name__ == "__main__":
    main()
