#!/usr/bin/env python3
"""Patch pylock packages with RH wheel-only entries for hermetic offline builds.

Two strategies:
  replace   — swap the entire [[packages]] block from the reference lock (all arches).
              Use for Rust-backed packages (uv, ripgrep) where PyPI sdists break hermeto.
  merge-be  — keep PyPI wheels for x86_64/aarch64; add RH wheels for ppc64le/s390x only;
              drop sdists. Aligns rhoai-2.25 with public PyPI on LE while BE stays offline.

Usage:
    patch-rh-wheel-only-packages.py replace <pylock.toml> <reference.toml> pkg [pkg ...]
    patch-rh-wheel-only-packages.py merge-be <pylock.toml> <reference.toml> pkg [pkg ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BE_ARCHES = frozenset({"ppc64le", "s390x"})
RH_HOST = "packages.redhat.com"
PYPI_HOSTS = frozenset({"files.pythonhosted.org", "pypi.org"})

_WHEEL_ARCH_RE = re.compile(
    r"linux_(?P<arch>x86_64|aarch64|ppc64le|s390x)(?:\.|/|$)",
    re.IGNORECASE,
)
_RH_BUILD_REV_RE = re.compile(r"-(\d+)-(?:cp\d|abi3|py3)", re.IGNORECASE)
_WHEEL_LINE_RE = re.compile(r"(\{\s*url = \"[^\"]+\"[^}]+\})")  # unused; kept for reference


def extract_wheel_dicts(wheels_array_text: str) -> list[str]:
    """Extract top-level inline-table dicts from a wheels = [ ... ] array."""
    entries: list[str] = []
    i = 0
    text = wheels_array_text
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        depth = 0
        for pos in range(start, len(text)):
            ch = text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    entries.append(text[start : pos + 1])
                    i = pos + 1
                    break
        else:
            break
    return entries


def split_packages(text: str) -> tuple[str, list[str]]:
    match = re.match(r"^(#.*(?:\n|$))+", text)
    header = match.group(0) if match else ""
    body = text[len(header) :]
    blocks = [block for block in re.split(r"(?=^\[\[packages\]\]\n)", body, flags=re.MULTILINE) if block.strip()]
    return header, blocks


def package_name(block: str) -> str | None:
    match = re.search(r'^name = "([^"]+)"', block, re.MULTILINE)
    return match.group(1) if match else None


def load_package_map(path: Path) -> dict[str, str]:
    _, blocks = split_packages(path.read_text(encoding="utf-8"))
    return {name: block for block in blocks if (name := package_name(block))}


def wheel_arch_key(wheel_url: str) -> str:
    match = _WHEEL_ARCH_RE.search(wheel_url)
    if match is not None:
        return match.group("arch").lower()
    if wheel_url.endswith("py3-none-any.whl") or wheel_url.endswith("py2.py3-none-any.whl"):
        return "any"
    return "unknown"


def rh_build_revision(wheel_url: str) -> int:
    filename = wheel_url.rsplit("/", 1)[-1]
    match = _RH_BUILD_REV_RE.search(filename)
    return int(match.group(1)) if match else 0


def is_rh_url(url: str) -> bool:
    return RH_HOST in url


def is_pypi_url(url: str) -> bool:
    return any(host in url for host in PYPI_HOSTS)


def is_wheel_url(url: str) -> bool:
    return url.rsplit("/", 1)[-1].endswith(".whl")


def is_py312_compatible_wheel(url: str) -> bool:
    filename = url.rsplit("/", 1)[-1]
    return "-cp314" not in filename and "-cp313" not in filename


def parse_wheels_section(block: str) -> tuple[str, list[str], str]:
    """Return (header_before_wheels, wheel_dict_lines, trailing_after_wheels)."""
    match = re.search(r"^wheels = \[", block, re.MULTILINE)
    if match is None:
        return block.rstrip(), [], ""

    header = block[: match.start()].rstrip()
    rest = block[match.end() - 1 :]  # starts with [
    depth = 0
    end_idx = 0
    for idx, ch in enumerate(rest):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end_idx = idx + 1
                break
    wheels_array = rest[:end_idx]
    trailing = rest[end_idx:].lstrip("\n")
    wheel_lines = extract_wheel_dicts(wheels_array)
    return header, wheel_lines, trailing


def url_from_wheel_line(wheel_line: str) -> str:
    match = re.search(r'url = "([^"]+)"', wheel_line)
    if match is None:
        raise ValueError(f"no url in wheel line: {wheel_line[:80]}")
    return match.group(1)


def dedupe_rh_wheels(urls: list[str]) -> list[str]:
    best: dict[str, tuple[int, str]] = {}
    for url in urls:
        if not is_rh_url(url):
            continue
        key = wheel_arch_key(url)
        rev = rh_build_revision(url)
        if key not in best or rev > best[key][0]:
            best[key] = (rev, url)
    return [url for _, url in sorted(best.values(), key=lambda item: item[0])]


def format_wheels_array(wheel_lines: list[str]) -> str:
    if not wheel_lines:
        return ""
    inner = ",\n".join(f"    {line.strip().rstrip(',')}" for line in wheel_lines)
    return f"wheels = [\n{inner},\n]"


def strip_sdist(header: str) -> str:
    marker = "\nsdist = {"
    idx = header.find(marker)
    if idx == -1:
        return header.rstrip()
    start = idx
    brace_start = header.index("{", start)
    depth = 0
    for pos in range(brace_start, len(header)):
        ch = header[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return (header[:start] + header[pos + 1 :]).rstrip()
    return header.rstrip()


def patch_replace(target: Path, reference: Path, names: list[str]) -> None:
    ref_map = load_package_map(reference)
    missing = [name for name in names if name not in ref_map]
    if missing:
        raise SystemExit(f"Reference lock missing packages: {', '.join(missing)}")

    header, blocks = split_packages(target.read_text(encoding="utf-8"))
    updated: list[str] = []
    replaced: set[str] = set()
    for block in blocks:
        name = package_name(block)
        if name in names:
            updated.append(ref_map[name].rstrip() + "\n")
            replaced.add(name)
        else:
            updated.append(block.rstrip() + "\n")

    if replaced != set(names):
        raise SystemExit(f"Target lock missing packages to patch: {', '.join(sorted(set(names) - replaced))}")

    target.write_text(header + "\n".join(updated), encoding="utf-8")
    print(f"  Replaced RH wheel-only entries for: {', '.join(names)}")


def patch_merge_be(target: Path, reference: Path, names: list[str]) -> None:
    ref_map = load_package_map(reference)
    missing = [name for name in names if name not in ref_map]
    if missing:
        raise SystemExit(f"Reference lock missing packages: {', '.join(missing)}")

    header, blocks = split_packages(target.read_text(encoding="utf-8"))
    updated: list[str] = []
    merged: set[str] = set()

    for block in blocks:
        name = package_name(block)
        if name not in names:
            updated.append(block.rstrip() + "\n")
            continue

        ref_header, ref_wheel_lines, _ = parse_wheels_section(ref_map[name])
        ref_urls = [url_from_wheel_line(line) for line in ref_wheel_lines]
        ref_be_urls = dedupe_rh_wheels([u for u in ref_urls if wheel_arch_key(u) in BE_ARCHES])

        target_header, target_wheel_lines, trailing = parse_wheels_section(block)
        keep_lines = [
            line
            for line in target_wheel_lines
            if is_pypi_url(url := url_from_wheel_line(line))
            and is_wheel_url(url)
            and is_py312_compatible_wheel(url)
            and wheel_arch_key(url) not in BE_ARCHES
        ]

        if not ref_be_urls:
            raise SystemExit(f"Reference lock has no ppc64le/s390x RH wheels for {name}")

        ref_be_lines = [_find_wheel_line(ref_map[name], url) for url in ref_be_urls]
        merged_lines = keep_lines + ref_be_lines

        new_block = strip_sdist(target_header)
        new_block += "\n" + format_wheels_array(merged_lines)
        if trailing:
            new_block += "\n" + trailing.rstrip()
        updated.append(new_block.rstrip() + "\n")
        merged.add(name)

    if merged != set(names):
        raise SystemExit(f"Target lock missing packages to merge: {', '.join(sorted(set(names) - merged))}")

    target.write_text(header + "\n".join(updated), encoding="utf-8")
    print(f"  Merged BE RH wheels for: {', '.join(names)}")


def _find_wheel_line(block: str, url: str) -> str:
    _, wheel_lines, _ = parse_wheels_section(block)
    for line in wheel_lines:
        if url_from_wheel_line(line) == url:
            return line
    raise SystemExit(f"Could not find wheel metadata for URL: {url}")


def main() -> None:
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    target = Path(sys.argv[2])
    reference = Path(sys.argv[3])
    names = sys.argv[4:]

    if mode == "replace":
        patch_replace(target, reference, names)
    elif mode == "merge-be":
        patch_merge_be(target, reference, names)
    else:
        raise SystemExit(f"Unknown mode: {mode!r} (use replace or merge-be)")


if __name__ == "__main__":
    main()
