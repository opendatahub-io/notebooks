#!/usr/bin/env python3
"""Create unversioned .so symlinks for ROCm libraries.

TensorFlow-ROCm dlopens unversioned .so names (e.g. librocblas.so).
AIPCC base images only ship versioned files (librocblas.so.4.2.60403).
This script creates the missing unversioned symlinks, registers ROCm library
directories (including nested rocm_sysdeps paths) with ldconfig, and refreshes
the loader cache.
"""

import os
import subprocess
import sys


def _rocm_lib_roots(rocm_path: str) -> list[str]:
    """Return ROCm lib trees to scan (base images may use /opt/rocm/core/lib)."""
    candidates = [
        os.path.join(rocm_path, "lib"),
        os.path.join("/opt/rocm", "lib"),
        os.path.join("/opt/rocm", "core", "lib"),
    ]
    roots: list[str] = []
    for path in candidates:
        if os.path.isdir(path) and path not in roots:
            roots.append(path)
    return roots


def _shared_library_dirs_under(*roots: str) -> set[str]:
    dirs: set[str] = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            if any(".so" in name for name in filenames):
                dirs.add(dirpath)
    return dirs


def _create_unversioned_symlinks(lib_roots: list[str]) -> int:
    created = 0
    for rocm_lib in lib_roots:
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
    return created


def _register_ld_library_paths(dirs: set[str]) -> None:
    if not dirs:
        return
    conf_path = "/etc/ld.so.conf.d/999-rocm-notebooks-extra.conf"
    with open(conf_path, "w", encoding="utf-8") as conf:
        for path in sorted(dirs):
            conf.write(f"{path}\n")
    print(f"Registered {len(dirs)} ROCm library directories in {conf_path}")


def main() -> None:
    rocm_path = os.environ.get("ROCM_PATH", "/opt/rocm")
    lib_roots = _rocm_lib_roots(rocm_path)
    if not lib_roots:
        print(f"No ROCm lib directories found under {rocm_path} or /opt/rocm", file=sys.stderr)
        sys.exit(1)

    created = _create_unversioned_symlinks(lib_roots)
    print(f"Created {created} unversioned symlinks under {', '.join(lib_roots)}")

    # Nested layouts (e.g. /opt/rocm/core/lib/rocm_sysdeps/lib) are not always on
    # the loader path; TensorFlow-ROCm imports fail with missing librocm_sysdeps_*.so.1.
    ld_dirs = _shared_library_dirs_under("/opt/rocm")
    _register_ld_library_paths(ld_dirs)
    subprocess.run(["ldconfig"], check=True)


if __name__ == "__main__":
    main()
