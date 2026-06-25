#!/usr/bin/env python3
"""Copy prefetched wheels with group-writable ZIP modes for OpenShift (gid 0).

uv unpacks wheels using modes stored in the wheel ZIP (typically 644/755).
Arbitrary UIDs in group 0 need g+w on site-packages for runtime pip installs.
Rewriting external_attr to 664 (files) / 775 (dirs) before install avoids
post-install chmod/fix-permissions tree walks (#3928).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

FILE_MODE = 0o664
DIR_MODE = 0o775


def _rewrite_wheel(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            mode = DIR_MODE if info.filename.endswith("/") else FILE_MODE
            new_info.external_attr = (mode & 0xFFFF) << 16
            new_info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(new_info, data)


def prepare_wheels(src_dir: Path, dst_dir: Path) -> int:
    if not src_dir.is_dir():
        print(f"ERROR: source directory missing: {src_dir}", file=sys.stderr)
        return 1

    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True)

    count = 0
    for wheel in sorted(src_dir.glob("*.whl")):
        _rewrite_wheel(wheel, dst_dir / wheel.name)
        count += 1

    print(f"PREPARE_GROUP_WRITABLE_WHEELS src={src_dir} dst={dst_dir} wheels={count}")
    return 0 if count else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src_dir", type=Path, help="Directory of prefetched wheels (e.g. /cachi2/output/deps/pip)")
    parser.add_argument("dst_dir", type=Path, help="Output directory for rewritten wheels")
    args = parser.parse_args()
    return prepare_wheels(args.src_dir, args.dst_dir)


if __name__ == "__main__":
    raise SystemExit(main())
