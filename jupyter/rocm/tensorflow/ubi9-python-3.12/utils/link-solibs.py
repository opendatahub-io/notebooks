#!/usr/bin/env python3
"""Create unversioned .so symlinks for ROCm libraries.

TensorFlow-ROCm dlopens unversioned .so names (e.g. librocblas.so).
AIPCC base images only ship versioned files (librocblas.so.4.2.60403).
This script creates the missing unversioned symlinks and runs ldconfig.
"""

import os
import subprocess
import sys


def main() -> None:
    rocm_path = os.environ.get("ROCM_PATH", "/opt/rocm")
    rocm_lib = os.path.join(rocm_path, "lib")
    created = 0

    for dirpath, _, filenames in os.walk(rocm_lib):
        for fn in filenames:
            if ".so." not in fn:
                continue
            base = fn[: fn.index(".so.")] + ".so"
            link = os.path.join(dirpath, base)
            if os.path.islink(link):
                if os.path.exists(link):
                    continue
                os.unlink(link)
            elif os.path.exists(link):
                continue
            os.symlink(fn, link)
            print(f"  ln -s {link} -> {fn}")
            created += 1

    print(f"Created {created} unversioned symlinks in {rocm_lib}")
    subprocess.run(["ldconfig"], check=True)


if __name__ == "__main__":
    main()
