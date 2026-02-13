#!/usr/bin/env python3
"""generate-rhoai-requirements.py — RHOAI wheel discovery and hash merging.

Why this script exists
======================
Public PyPI does not ship pre-built manylinux wheels for ppc64le and s390x
for many data-science packages (numpy, scipy, pandas, pyarrow, scikit-learn,
pillow, pyzmq, etc.).  Without pre-built wheels the Dockerfile must compile
them from source, which is slow, fragile, and requires a full build toolchain
(gcc, gfortran, cmake, OpenBLAS-devel, …) inside the image.

Red Hat OpenShift AI (RHOAI) maintains an internal PyPI index that publishes
pre-built wheels for these packages on ppc64le and s390x.  By using RHOAI
wheels we can:
  • eliminate most source compilations in the whl-cache Dockerfile stage,
  • remove the corresponding -devel RPMs and build tools from rpms.in.yaml,
  • significantly reduce image build time and image size.

However, the Konflux/cachi2 build system does NOT support --extra-index-url
inside a single requirements.txt.  To work around this we maintain *two*
requirements files:
  • requirements.txt        — packages from public PyPI (default index)
  • requirements-rhoai.txt  — same packages available on the RHOAI index,
                              with --index-url pointing to the RHOAI mirror

cachi2 prefetches both files into /cachi2/output/deps/pip/.  At install time
the Dockerfile runs:
    uv pip install --no-index --find-links /cachi2/output/deps/pip \
        --verify-hashes --requirements=./requirements.txt
Since /cachi2/output/deps/pip/ contains wheels from *both* sources, uv picks
whichever wheel matches the platform.  For --verify-hashes to accept RHOAI
wheels, their sha256 hashes must also appear in requirements.txt — that is
what the --merge-hashes flag does.

What this script does
=====================
  1. Parse requirements.txt → (name, version) for every pinned package.
  2. Fetch the RHOAI simple-index root → list of available packages.
  3. For each overlap, fetch the package page, collect wheel hashes that
     match the pinned version and the requested Python tag (default: cp312).
     With --prefer-rhoai-version: if the exact version is not on RHOAI but
     a different version is, use the latest RHOAI version and update the
     version pin and hashes in requirements.txt automatically.
  4. Write requirements-rhoai.txt  (consumed by cachi2 as a second pip source).
  5. (--merge-hashes) Append RHOAI hashes into requirements.txt so that
     `uv pip install --verify-hashes` accepts both PyPI and RHOAI wheels.

Usage
-----
  python3 scripts/lockfile-generators/generate-rhoai-requirements.py \\
    --requirements codeserver/ubi9-python-3.12/requirements.txt \\
    --output       codeserver/ubi9-python-3.12/requirements-rhoai.txt \\
    [--rhoai-index URL] [--merge-hashes] [--prefer-rhoai-version] \\
    [--python-tag cp312]
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

DEFAULT_RHOAI_INDEX = (
    "https://console.redhat.com/api/pypi/public-rhai/rhoai/3.3/cpu-ubi9/simple/"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """PEP 503 canonical package name: lowercase, [-_.] → hyphen."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(req_path: Path):
    """Yield (original_name, version, set_of_sha256) for every pinned package."""
    text = req_path.read_text()
    # Join backslash-continuation lines into single logical lines
    text = re.sub(r"\s*\\\n\s*", " ", text)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)==([^\s;]+)", line)
        if m:
            name, version = m.group(1), m.group(2)
            hashes = set(re.findall(r"--hash=sha256:([a-f0-9]+)", line))
            yield name, version, hashes


def fetch_html(url: str) -> str:
    """GET *url* and return the decoded body."""
    req = urllib.request.Request(url, headers={"Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode()


def fetch_rhoai_package_list(index_url: str) -> dict:
    """Return {normalized_name: raw_name} for every package on the RHOAI index."""
    html = fetch_html(index_url.rstrip("/") + "/")
    raw_names = re.findall(r'<a\s+href="[^"]*">([^<]+)</a>', html)
    return {normalize_name(n): n for n in raw_names}


def fetch_rhoai_wheels(index_url: str, raw_name: str):
    """Yield (filename, sha256, download_url) for every wheel of *raw_name*."""
    url = f"{index_url.rstrip('/')}/{raw_name}/"
    try:
        html = fetch_html(url)
    except Exception as exc:
        print(f"    Warning: could not fetch {url}: {exc}", file=sys.stderr)
        return
    for m in re.finditer(
        r'<a\s+href="([^"]*?)#sha256=([a-f0-9]+)"[^>]*>([^<]+)</a>', html
    ):
        yield m.group(3).strip(), m.group(2), m.group(1)


def parse_wheel_version(filename: str):
    """Return (normalized_name, version) extracted from a .whl filename.

    Handles optional build tags, e.g.
    ``numpy-2.3.5-2-cp312-cp312-linux_ppc64le.whl`` → (numpy, 2.3.5)
    """
    if not filename.endswith(".whl"):
        return None, None
    parts = filename[:-4].split("-")
    # Wheel format: name-ver[-build]-pytag-abitag-plattag  →  5 or 6 parts
    if len(parts) == 6:
        name, ver = parts[0], parts[1]
    elif len(parts) == 5:
        name, ver = parts[0], parts[1]
    else:
        return None, None
    return normalize_name(name), ver


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def version_sort_key(v: str):
    """Return a tuple for sorting PEP 440-ish version strings (e.g. '23.0.0')."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _parse_cpython_tag(tag: str):
    """Parse a CPython tag like 'cp312' into a (major, minor) tuple.

    The tag format is ``cp<major><minor>`` where minor may be 1 or 2 digits
    (e.g. cp36 → (3, 6), cp312 → (3, 12)).
    """
    m = re.match(r"cp(\d)(\d+)$", tag)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def is_wheel_compatible(whl_name: str, python_tag: str) -> bool:
    """Check whether *whl_name* is compatible with *python_tag* (e.g. 'cp312').

    Handles three cases:
      1. Exact tag match — ``cp312`` appears in the filename.
      2. Stable ABI (abi3) — a wheel tagged ``cp36-abi3`` is compatible with
         any CPython >= 3.6, so it works for cp312.
      3. Pure-Python — ``py3-none`` / ``py2.py3-none`` wheels are always ok.
    """
    if not python_tag:
        return True
    # Case 1: exact substring match (covers cp312-cp312 and cp312-abi3)
    if python_tag in whl_name:
        return True
    # Case 3: pure-Python wheels
    if "-py3-none-" in whl_name or "-py2.py3-none-" in whl_name:
        return True
    # Case 2: abi3 stable ABI — the wheel's minimum CPython version may be
    # lower than the requested tag (e.g. cp36-abi3 is compatible with cp312).
    if "-abi3-" not in whl_name:
        return False
    # Parse the wheel's python tag (3rd field from the end in the filename):
    #   name-ver[-build]-pytag-abitag-plattag.whl
    parts = whl_name.rsplit(".whl", 1)[0].split("-")
    if len(parts) < 5:
        return False
    whl_pytag = parts[-3]
    whl_ver = _parse_cpython_tag(whl_pytag)
    req_ver = _parse_cpython_tag(python_tag)
    if whl_ver and req_ver:
        return req_ver >= whl_ver
    return False


# ---------------------------------------------------------------------------
# Update versions in requirements.txt (for RHOAI version overrides)
# ---------------------------------------------------------------------------

def update_versions_in_requirements(req_path: Path, version_overrides: dict):
    """Replace version pins and hashes for packages where RHOAI provides a
    different version than what was originally in requirements.txt.

    *version_overrides*: {normalized_name: {"name": str, "old_ver": str,
                          "new_ver": str, "hashes": set_of_sha256}}
    """
    lines = req_path.read_text().splitlines()
    output = []
    i = 0

    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z0-9._-]+)==([^\s;]+)", line.strip())
        if not m:
            output.append(line)
            i += 1
            continue

        pkg_key = normalize_name(m.group(1))

        # Gather entire continuation block
        block = [line]
        j = i + 1
        while j < len(lines) and block[-1].rstrip().endswith("\\"):
            block.append(lines[j])
            j += 1

        if pkg_key not in version_overrides:
            output.extend(block)
            i = j
            continue

        ov = version_overrides[pkg_key]

        # Extract the first line: strip trailing backslash and any --hash entries.
        # Preserves the package name, version, and environment markers.
        first = re.sub(r"\s*\\$", "", block[0])       # strip trailing \
        first = re.sub(r"\s+--hash=\S+", "", first)   # strip inline hashes
        first = first.rstrip()

        # Replace the version pin
        first = first.replace(f"=={ov['old_ver']}", f"=={ov['new_ver']}", 1)

        # Rebuild block with RHOAI hashes only
        new_hashes = sorted(ov["hashes"])
        rebuilt = [f"{first} \\"]
        for k, h in enumerate(new_hashes):
            suffix = " \\" if k < len(new_hashes) - 1 else ""
            rebuilt.append(f"    --hash=sha256:{h}{suffix}")

        output.extend(rebuilt)
        i = j

    req_path.write_text("\n".join(output) + "\n")


# ---------------------------------------------------------------------------
# Merge RHOAI hashes into requirements.txt
# ---------------------------------------------------------------------------

def merge_hashes_into_requirements(req_path: Path, rhoai_hashes: dict):
    """Append RHOAI hashes to matching package blocks in *req_path*.

    *rhoai_hashes*: {normalized_name: set_of_sha256_hex_strings}
    """
    lines = req_path.read_text().splitlines()
    output = []
    i = 0

    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z0-9._-]+)==", line.strip())
        if not m:
            output.append(line)
            i += 1
            continue

        pkg_key = normalize_name(m.group(1))

        # Gather entire continuation block
        block = [line]
        j = i + 1
        while j < len(lines) and block[-1].rstrip().endswith("\\"):
            block.append(lines[j])
            j += 1

        if pkg_key in rhoai_hashes:
            existing = set(re.findall(r"--hash=sha256:([a-f0-9]+)", "\n".join(block)))
            new = sorted(rhoai_hashes[pkg_key] - existing)
            if new:
                # Ensure last existing line ends with continuation backslash
                last = block[-1].rstrip()
                if not last.endswith("\\"):
                    block[-1] = last + " \\"
                for k, h in enumerate(new):
                    suffix = " \\" if k < len(new) - 1 else ""
                    block.append(f"    --hash=sha256:{h}{suffix}")

        output.extend(block)
        i = j

    req_path.write_text("\n".join(output) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--requirements", type=Path, required=True,
        help="Path to requirements.txt (input & merge target)",
    )
    ap.add_argument(
        "--output", type=Path, required=True,
        help="Output path for requirements-rhoai.txt",
    )
    ap.add_argument(
        "--rhoai-index", default=DEFAULT_RHOAI_INDEX,
        help="RHOAI simple-index URL (default: %(default)s)",
    )
    ap.add_argument(
        "--merge-hashes", action="store_true",
        help="Also merge RHOAI hashes into requirements.txt",
    )
    ap.add_argument(
        "--prefer-rhoai-version", action="store_true",
        help="When RHOAI provides a package at a different version than "
             "requirements.txt, use the latest RHOAI version and update "
             "the version pin and hashes in requirements.txt. This avoids "
             "source builds on ppc64le/s390x when RHOAI ships a newer "
             "pre-built wheel.",
    )
    ap.add_argument(
        "--python-tag", default="cp312",
        help="Python version tag to filter wheels (default: cp312)",
    )
    args = ap.parse_args()

    if not args.requirements.is_file():
        print(f"Error: {args.requirements} not found", file=sys.stderr)
        sys.exit(1)

    # ---- 1. Parse requirements.txt ----------------------------------------
    print(f"Parsing {args.requirements} ...")
    req_pkgs = {}
    for name, version, hashes in parse_requirements(args.requirements):
        key = normalize_name(name)
        req_pkgs[key] = {"name": name, "version": version, "hashes": hashes}
    print(f"  {len(req_pkgs)} packages")

    # ---- 2. Fetch RHOAI package list --------------------------------------
    print(f"Fetching RHOAI index: {args.rhoai_index}")
    rhoai_pkgs = fetch_rhoai_package_list(args.rhoai_index)
    print(f"  {len(rhoai_pkgs)} packages available")

    # ---- 3. Collect matching wheel hashes ---------------------------------
    overlap = sorted(set(req_pkgs) & set(rhoai_pkgs))
    print(f"  {len(overlap)} packages overlap with requirements.txt")

    rhoai_entries = []
    rhoai_hash_map = {}
    version_overrides = {}  # packages where RHOAI version differs

    for key in overlap:
        info = req_pkgs[key]
        raw_name = rhoai_pkgs[key]
        target_ver = info["version"]
        print(f"  {info['name']}=={target_ver} ... ", end="", flush=True)

        # Collect all RHOAI wheels grouped by version
        wheels_by_ver = {}  # {version_str: [sha256, ...]}
        for whl_name, sha, _url in fetch_rhoai_wheels(args.rhoai_index, raw_name):
            if not is_wheel_compatible(whl_name, args.python_tag):
                continue
            _, whl_ver = parse_wheel_version(whl_name)
            if whl_ver is None:
                continue
            wheels_by_ver.setdefault(whl_ver, []).append(sha)

        # Select which version to use:
        #   1. Exact match with requirements.txt → preferred
        #   2. --prefer-rhoai-version → pick the latest RHOAI version
        #   3. Otherwise → no match
        if target_ver in wheels_by_ver:
            use_ver = target_ver
            hashes = wheels_by_ver[target_ver]
        elif args.prefer_rhoai_version and wheels_by_ver:
            use_ver = max(wheels_by_ver, key=version_sort_key)
            hashes = wheels_by_ver[use_ver]
        else:
            use_ver = target_ver
            hashes = []

        if hashes:
            if use_ver != target_ver:
                print(f"{len(hashes)} wheels "
                      f"(RHOAI version override: {target_ver} -> {use_ver})")
                version_overrides[key] = {
                    "name": info["name"],
                    "old_ver": target_ver,
                    "new_ver": use_ver,
                    "hashes": set(hashes),
                }
            else:
                print(f"{len(hashes)} wheels")
            rhoai_entries.append(
                {"name": info["name"], "version": use_ver, "hashes": hashes}
            )
            rhoai_hash_map[key] = set(hashes)
        else:
            if args.prefer_rhoai_version:
                print("no match (not on RHOAI)")
            else:
                avail = ", ".join(sorted(wheels_by_ver)) if wheels_by_ver else ""
                if avail:
                    print(f"no match (RHOAI has: {avail}; "
                          f"use --prefer-rhoai-version to override)")
                else:
                    print("no match")

    # ---- 4. Write requirements-rhoai.txt ----------------------------------
    print(f"\nWriting {args.output} ({len(rhoai_entries)} packages) ...")

    header = [
        "# RHOAI (Red Hat OpenShift AI) pre-built wheels for ppc64le and s390x.",
        "#",
        "# These packages lack manylinux wheels on public PyPI for ppc64le/s390x.",
        "# RHOAI provides pre-built wheels eliminating the need to compile from source.",
        f"# Index: {args.rhoai_index}",
        "#",
        "# cachi2 prefetches these into /cachi2/output/deps/pip/ alongside PyPI packages.",
        '# The Dockerfile\'s `uv pip install --find-links /cachi2/output/deps/pip` picks them up.',
        "# Corresponding hashes are also in requirements.txt so --verify-hashes passes.",
        "#",
        "# Auto-generated by: scripts/lockfile-generators/generate-rhoai-requirements.py",
        "# Versions match requirements.txt (may differ from uv.lock when --prefer-rhoai-version is used).",
        f"--index-url {args.rhoai_index}",
    ]

    body = []
    for entry in rhoai_entries:
        h_lines = [f"    --hash=sha256:{h}" for h in entry["hashes"]]
        body.append(f"{entry['name']}=={entry['version']} \\")
        for k, hl in enumerate(h_lines):
            body.append(hl + (" \\" if k < len(h_lines) - 1 else ""))

    args.output.write_text("\n".join(header + body) + "\n")

    # ---- 5. Apply RHOAI version overrides to requirements.txt --------------
    if version_overrides:
        print(f"\nApplying {len(version_overrides)} RHOAI version override(s) "
              f"to {args.requirements}:")
        for key in sorted(version_overrides):
            ov = version_overrides[key]
            print(f"  {ov['name']}: {ov['old_ver']} -> {ov['new_ver']}")
        update_versions_in_requirements(args.requirements, version_overrides)

        # Suggest adding override-dependencies to pyproject.toml so that
        # `uv lock` resolves the same version natively on the next re-lock.
        print()
        print("  NOTE: requirements.txt has been updated in-place.  To keep")
        print("  uv.lock consistent, add to pyproject.toml override-dependencies:")
        for key in sorted(version_overrides):
            ov = version_overrides[key]
            print(f'    "{ov["name"]}=={ov["new_ver"]}",')

    # ---- 6. Merge RHOAI hashes into requirements.txt ----------------------
    if args.merge_hashes and rhoai_hash_map:
        print(f"Merging RHOAI hashes into {args.requirements} ...")
        merge_hashes_into_requirements(args.requirements, rhoai_hash_map)

    # ---- Summary ----------------------------------------------------------
    names = ", ".join(e["name"] for e in rhoai_entries)
    print(f"\nDone.  RHOAI packages ({len(rhoai_entries)}): {names}")


if __name__ == "__main__":
    main()
