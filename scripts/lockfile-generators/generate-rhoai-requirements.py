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
  4. Write requirements-rhoai.txt  (consumed by cachi2 as a second pip source).
  5. (--merge-hashes) Append RHOAI hashes into requirements.txt so that
     `uv pip install --verify-hashes` accepts both PyPI and RHOAI wheels.

Usage
-----
  python3 scripts/lockfile-generators/generate-rhoai-requirements.py \\
    --requirements codeserver/ubi9-python-3.12/requirements.txt \\
    --output       codeserver/ubi9-python-3.12/requirements-rhoai.txt \\
    [--rhoai-index URL] [--merge-hashes] [--python-tag cp312]
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

    for key in overlap:
        info = req_pkgs[key]
        raw_name = rhoai_pkgs[key]
        target_ver = info["version"]
        print(f"  {info['name']}=={target_ver} ... ", end="", flush=True)

        hashes = []
        for whl_name, sha, _url in fetch_rhoai_wheels(args.rhoai_index, raw_name):
            _, whl_ver = parse_wheel_version(whl_name)
            if whl_ver != target_ver:
                continue
            if args.python_tag and args.python_tag not in whl_name:
                continue
            hashes.append(sha)

        if hashes:
            print(f"{len(hashes)} wheels")
            rhoai_entries.append(
                {"name": info["name"], "version": target_ver, "hashes": hashes}
            )
            rhoai_hash_map[key] = set(hashes)
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
        "# Versions must match requirements.txt.",
        f"--index-url {args.rhoai_index}",
    ]

    body = []
    for entry in rhoai_entries:
        h_lines = [f"    --hash=sha256:{h}" for h in entry["hashes"]]
        body.append(f"{entry['name']}=={entry['version']} \\")
        for k, hl in enumerate(h_lines):
            body.append(hl + (" \\" if k < len(h_lines) - 1 else ""))

    args.output.write_text("\n".join(header + body) + "\n")

    # ---- 5. Merge RHOAI hashes into requirements.txt ----------------------
    if args.merge_hashes and rhoai_hash_map:
        print(f"Merging RHOAI hashes into {args.requirements} ...")
        merge_hashes_into_requirements(args.requirements, rhoai_hash_map)

    # ---- Summary ----------------------------------------------------------
    names = ", ".join(e["name"] for e in rhoai_entries)
    print(f"\nDone.  RHOAI packages ({len(rhoai_entries)}): {names}")


if __name__ == "__main__":
    main()
