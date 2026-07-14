#!/usr/bin/env python3
"""download-pip-packages.py — Parallel arch-aware pip wheel prefetch.

Downloads wheels listed in a requirements.txt (with --hash=sha256:… lines)
into cachi2/output/deps/pip/ for hermetic offline builds.

Architecture:
  Phase 1: Parse requirements.txt for (name, version, hashes, marker) or direct URL (name @ URL)
  Phase 2: Skip packages whose markers exclude the target arch
  Phase 3: Resolve URLs from index (10 parallel HTTP requests)
  Phase 4: Filter: skip sdists (AIPCC), keep target-arch + pure-python wheels
  Phase 5: Download (10 parallel wget)

Supports two index backends:
  - PEP 503 simple indexes (AIPCC/RHOAI) — auto-detected from --index-url
  - PyPI JSON API (fallback for pypi.org)

Usage:
  python3 download-pip-packages.py [--arch ARCH] [-o OUTPUT_DIR] requirements.txt
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse

from packaging.markers import Marker

OUT_DIR = Path("cachi2/output/deps/pip")
PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"
# 8 workers balances throughput vs Akamai burst rate-limiting on packages.redhat.com.
# uv uses 50 by default (astral-sh/uv#10570 discusses reducing to 8 for stability).
# At 10: stable 22s, at 20: 13s, at 50: 12s but high variance (Akamai throttling).
MAX_WORKERS = 8
# wget --timeout sets dns/connect/read idle timeouts (not total transfer time).
# Large wheels (e.g. torch >1GB) need a generous read idle window on slow links.
WGET_NETWORK_TIMEOUT_SECONDS = 300
# Per-file wall-clock cap for subprocess.run(); must cover multi-GB wheels when
# MAX_WORKERS parallel downloads share CI bandwidth (~1GB at ~1 MB/s ≈ 17 min).
DOWNLOAD_PROCESS_TIMEOUT_SECONDS = 3600
# Transient wget failures (Akamai/S3 blips under parallel load) are retried
# sequentially before the prefetch step fails.
DOWNLOAD_MAX_PASSES = 3

ARCH_ALIASES: dict[str, list[str]] = {
    "amd64": ["x86_64", "amd64"],
    "x86_64": ["x86_64", "amd64"],
    "arm64": ["aarch64", "arm64"],
    "aarch64": ["aarch64", "arm64"],
    "ppc64le": ["ppc64le"],
    "s390x": ["s390x"],
}


def get_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("requirements", type=Path, help="Path to requirements.txt")
    parser.add_argument("-o", "--output-dir", type=Path, default=OUT_DIR, help=f"Output directory (default: {OUT_DIR})")
    parser.add_argument("--arch", type=str, default=None, help="Target architecture (default: from BUILD_ARCH env or uname -m)")
    parser.add_argument("--python-version", type=str, default=None,
                        help="Target Python version, e.g. 3.12 (default: from RELEASE_PYTHON_VERSION env or current)")
    args = parser.parse_args()

    if args.arch is None:
        build_arch = os.environ.get("BUILD_ARCH", "")
        if build_arch:
            raw = build_arch.split("/")[-1]
            args.arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(raw, raw)
        else:
            import platform
            args.arch = platform.machine()

    if args.python_version is None:
        args.python_version = os.environ.get("RELEASE_PYTHON_VERSION", f"{sys.version_info.major}.{sys.version_info.minor}")

    req_path = args.requirements.resolve()
    if not req_path.is_file():
        print(f"Error: not a file: {req_path}", file=sys.stderr)
        sys.exit(1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return req_path, args.output_dir.resolve(), args.arch, args.python_version


def detect_index_url(req_path: Path) -> str | None:
    for line in req_path.read_text().splitlines():
        m = re.match(r"^\s*--index-url\s+(\S+)", line)
        if m:
            return m.group(1)
    return None


@dataclass(frozen=True)
class Requirement:
    name: str
    hashes: frozenset[str]
    marker: str
    version: str = ""
    direct_url: str = ""


def parse_requirements(req_path: Path) -> list[Requirement]:
    """Return packages from requirements.txt (name==version or name @ URL)."""
    text = req_path.read_text()
    text = re.sub(r" \\\n\s*", " ", text)
    packages: list[Requirement] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        hash_parts = line.split("--hash=")
        name_ver_marker = hash_parts[0].strip()

        marker = ""
        if ";" in name_ver_marker:
            name_ver, marker = name_ver_marker.split(";", 1)
            name_ver = name_ver.strip()
            marker = marker.strip()
        else:
            name_ver = name_ver_marker.strip()

        hashes = frozenset(re.findall(r"sha256:([a-f0-9]+)", line, re.I))

        if " @ " in name_ver:
            name, direct_url = name_ver.split(" @ ", 1)
            packages.append(Requirement(
                name=name.strip(),
                hashes=hashes,
                marker=marker,
                direct_url=direct_url.strip(),
            ))
            continue

        if "==" not in name_ver:
            continue
        name, version = name_ver.split("==", 1)
        packages.append(Requirement(
            name=name.strip(),
            version=version.strip(),
            hashes=hashes,
            marker=marker,
        ))
    return packages


def requirement_label(pkg: Requirement) -> str:
    if pkg.direct_url:
        return f"{pkg.name} @ {pkg.direct_url}"
    return f"{pkg.name}=={pkg.version}"


class _PoisonString(str):
    """Sentinel that detonates if marker evaluation touches an uncontrolled key."""

    def __new__(cls, key_name: str):
        obj = super().__new__(cls, "POISON")
        obj._key_name = key_name
        return obj

    def _boom(self, *args, **kwargs):
        raise _UnexpectedKeyAccess(super().__getattribute__("_key_name"))


class _UnexpectedKeyAccess(Exception):
    pass


# Poison all comparison/operator dunders so any use in marker evaluation explodes
for _op in ("__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
            "__contains__", "__hash__"):
    setattr(_PoisonString, _op, _PoisonString._boom)


def should_skip_for_marker(marker: str, arch: str, python_version: str) -> bool:
    """Return True when the marker excludes this architecture/python.

    Only evaluates markers that reference platform_machine (our purpose is
    arch filtering). Keys we control are set to target values; all other
    keys are filled with poison sentinels that explode if touched, ensuring
    no host values silently leak into the evaluation.
    """
    if not marker:
        return False
    if "platform_machine" not in marker:
        return False
    full_version = python_version if python_version.count(".") >= 2 else f"{python_version}.0"
    short_version = ".".join(full_version.split(".")[:2])
    controlled_env = {
        "implementation_name": "cpython",
        "platform_machine": arch,
        "platform_python_implementation": "CPython",
        "python_full_version": full_version,
        "python_version": short_version,
        "sys_platform": "linux",
    }
    # Poison any key from default_environment() that we don't explicitly control
    from packaging.markers import default_environment
    env = {k: _PoisonString(k) for k in default_environment()}
    env.update(controlled_env)
    try:
        return not Marker(marker).evaluate(env)
    except _UnexpectedKeyAccess as e:
        print(f"  WARN: marker touches uncontrolled key '{e}', not skipping: {marker}", file=sys.stderr)
        return False
    except Exception:
        return False


def should_keep_for_arch(filename: str, arch: str, skip_sdists: bool) -> bool:
    """Filter files by architecture and type."""
    if not filename.endswith(".whl"):
        return not skip_sdists

    stem = filename[:-4]
    parts = stem.split("-")
    if len(parts) < 3:
        return True
    platform_tag = parts[-1]

    if platform_tag in ("any", "none") or "any" in platform_tag.split("_"):
        return True

    return any(a in platform_tag for a in ARCH_ALIASES.get(arch, [arch]))


def fetch_simple_index_urls(index_url: str, name: str, version: str, wanted_hashes: set[str]) -> list[tuple[str, str, str]]:
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    page_url = f"{index_url.rstrip('/')}/{normalized}/"
    try:
        req = urllib.request.Request(page_url, headers={"Accept": "text/html", "User-Agent": "prefetch/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode()
    except Exception as e:
        print(f"  WARN: failed to fetch index page for {name}: {e}", file=sys.stderr)
        return []

    out = []
    for m in re.finditer(r'<a\s+href="([^"]*?)#sha256=([a-f0-9]+)"[^>]*>([^<]+)</a>', html):
        download_url, sha, filename = m.group(1), m.group(2), m.group(3).strip()
        download_url = urljoin(page_url, download_url)
        filename = PurePosixPath(filename).name
        if not filename or filename in (".", ".."):
            continue
        if sha in wanted_hashes:
            out.append((download_url, filename, sha))
    return out


def fetch_pypi_urls(name: str, version: str, wanted_hashes: set[str]) -> list[tuple[str, str, str]]:
    url = PYPI_JSON.format(name=name, version=version)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "prefetch/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print(f"  WARN: failed to fetch PyPI metadata for {name}: {e}", file=sys.stderr)
        return []

    out = []
    for entry in data.get("urls", []):
        raw_filename = entry["url"].split("/")[-1].split("?")[0]
        filename = PurePosixPath(raw_filename).name
        if not filename:
            continue
        if any(x in filename for x in ["macosx", "win_amd64", "win32", "win_arm64", "ios_"]):
            continue
        digests = entry.get("digests") or {}
        h = digests.get("sha256")
        if h and h in wanted_hashes:
            out.append((entry["url"], filename, h))
    return out


def resolve_one(args: tuple) -> list[tuple[str, str, str]]:
    """Resolve URLs for one package. Called in parallel."""
    name, version, wanted_hashes, index_url, use_simple = args
    if use_simple:
        return fetch_simple_index_urls(index_url, name, version, wanted_hashes)
    else:
        return fetch_pypi_urls(name, version, wanted_hashes)


def _wget_error_detail(result: subprocess.CompletedProcess[str] | subprocess.CalledProcessError) -> str:
    for stream in (result.stderr, result.stdout):
        if not stream:
            continue
        lines = [line.strip() for line in stream.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return f"wget exit {result.returncode}"


def download_one(args: tuple) -> tuple[bool, str]:
    """Download one file. Called in parallel."""
    url, dest_path, expected_hash = args
    try:
        subprocess.run(
            [
                "wget", "-q", "-O", str(dest_path),
                "--tries=3", "--waitretry=2",
                f"--timeout={WGET_NETWORK_TIMEOUT_SECONDS}",
                url,
            ],
            check=True, timeout=DOWNLOAD_PROCESS_TIMEOUT_SECONDS,
            capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        Path(dest_path).unlink(missing_ok=True)
        return False, f"TIMEOUT {Path(dest_path).name}"
    except subprocess.CalledProcessError as e:
        Path(dest_path).unlink(missing_ok=True)
        return False, f"FAIL {Path(dest_path).name}: {_wget_error_detail(e)}"

    actual = file_sha256(Path(dest_path))
    if actual != expected_hash:
        Path(dest_path).unlink(missing_ok=True)
        return False, f"HASH MISMATCH {Path(dest_path).name}: got {actual[:16]}..., expected {expected_hash[:16]}..."
    return True, f"OK {Path(dest_path).name}"


def _is_retryable(msg: str) -> bool:
    """Permanent failures (bad digest) should not be retried."""
    return not msg.startswith("HASH MISMATCH")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    req_path, out_dir, arch, python_version = get_args()

    index_url = detect_index_url(req_path)
    use_simple = index_url is not None and "pypi.org" not in index_url
    is_aipcc = index_url is not None and "packages.redhat.com/api/pypi/" in index_url
    skip_sdists = is_aipcc

    print(f"=== download-pip-packages.py ===")
    print(f"  requirements: {req_path}")
    print(f"  output:       {out_dir}")
    print(f"  arch:         {arch}")
    print(f"  python:       {python_version}")
    print(f"  index:        {index_url or 'PyPI (default)'}")
    print(f"  skip sdists:  {skip_sdists} (AIPCC={is_aipcc})")
    print()

    packages = parse_requirements(req_path)
    print(f"Parsed {len(packages)} packages from requirements.txt")

    # Phase 2: skip packages excluded by marker
    skipped_marker = []
    to_resolve = []
    direct_urls: list[tuple[str, str, str]] = []
    for pkg in packages:
        if should_skip_for_marker(pkg.marker, arch, python_version):
            skipped_marker.append(requirement_label(pkg))
            continue
        if pkg.direct_url:
            if len(pkg.hashes) != 1:
                print(f"  WARN: direct URL {requirement_label(pkg)} has "
                      f"{len(pkg.hashes)} hashes, expected 1", file=sys.stderr)
                continue
            filename = PurePosixPath(urlparse(pkg.direct_url).path).name
            if not filename:
                print(f"  WARN: could not derive filename from {pkg.direct_url}", file=sys.stderr)
                continue
            direct_urls.append((pkg.direct_url, filename, next(iter(pkg.hashes))))
        else:
            to_resolve.append((pkg.name, pkg.version, set(pkg.hashes), index_url, use_simple))

    if skipped_marker:
        print(f"\nSkipped by marker (platform_machine != '{arch}'): {len(skipped_marker)}")
        for pkg in skipped_marker:
            print(f"  - {pkg}")

    print(f"\nPhase 3: Resolving URLs for {len(to_resolve)} packages ({MAX_WORKERS} parallel)...")

    # Phase 3: parallel resolve
    all_files: list[tuple[str, str, str]] = list(direct_urls)
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for urls in executor.map(resolve_one, to_resolve):
            all_files.extend(urls)

    # Phase 4: filter by arch and type
    to_download = []
    for url, filename, sha in all_files:
        if should_keep_for_arch(filename, arch, skip_sdists):
            dest = out_dir / filename
            if dest.exists():
                actual = file_sha256(dest)
                if actual == sha:
                    continue
                else:
                    dest.unlink()
            to_download.append((url, dest, sha))

    print(f"  Resolved {len(all_files)} total files from index")
    print(f"  After arch filter: {len(to_download)} to download ({len(all_files) - len(to_download)} skipped/cached)")

    if not to_download:
        print("\nNothing to download.")
        return

    # Phase 5: parallel download with sequential retries for transient failures
    pending = list(to_download)
    downloaded = 0
    last_errors: dict[Path, str] = {}
    permanent_failures: list[tuple[str, Path, str]] = []

    for pass_num in range(1, DOWNLOAD_MAX_PASSES + 1):
        if not pending:
            break

        workers = MAX_WORKERS if pass_num == 1 else 1
        if pass_num == 1:
            print(f"\nPhase 5: Downloading {len(pending)} files ({workers} parallel)...")
        else:
            print(f"\nPhase 5 (retry {pass_num - 1}/{DOWNLOAD_MAX_PASSES - 1}): "
                  f"{len(pending)} failed download(s), retrying sequentially...")

        retry: list[tuple[str, Path, str]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(download_one, pending))

        for item, (ok, msg) in zip(pending, results):
            if ok:
                downloaded += 1
            else:
                last_errors[item[1]] = msg
                if _is_retryable(msg) and pass_num < DOWNLOAD_MAX_PASSES:
                    retry.append(item)
                else:
                    permanent_failures.append(item)

        pending = retry

    pending = permanent_failures
    print(f"\n  Downloaded: {downloaded}, Failed: {len(pending)}")

    if pending:
        for _url, dest_path, _sha in pending:
            msg = last_errors.get(dest_path, f"FAIL {dest_path.name}")
            print(f"  ERROR: {msg}", file=sys.stderr)
        print(f"\nERROR: {len(pending)} download(s) failed:", file=sys.stderr)
        for _url, dest_path, _sha in pending:
            print(f"  {last_errors.get(dest_path, f'FAIL {dest_path.name}')}", file=sys.stderr)
        sys.exit(1)

    total_files = len(list(out_dir.iterdir()))
    total_size_mb = sum(f.stat().st_size for f in out_dir.iterdir()) / (1024 * 1024)
    print(f"\nDone: {total_files} files in {out_dir} ({total_size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
