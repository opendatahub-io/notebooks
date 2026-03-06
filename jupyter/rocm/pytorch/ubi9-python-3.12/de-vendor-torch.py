#!/usr/bin/env python3
"""Replace PyTorch's vendored ROCm shared libraries with symlinks to system libraries.

Dynamically discovers the actual soname versions installed in the system,
so that ROCm version bumps don't silently produce dangling symlinks.

Source: https://github.com/tiran/instructlab-containers/blob/main/containers/rocm/de-vendor-torch.sh
"""

import glob
import os
import shutil
import sys

PYTHON = "python3.12"
ROCM_LIB = os.path.join(os.environ.get("ROCM_PATH", "/opt/rocm"), "lib")
TORCH_LIB = f"/opt/app-root/lib/{PYTHON}/site-packages/torch/lib"

SYSTEM_LIBS = {
    "/usr/lib64": [
        "libdrm",
        "libdrm_amdgpu",
    ],
}

ROCM_LIBS = [
    "libamd_comgr",
    "libamdhip64",
    "libhipblaslt",
    "libhipblas",
    "libhipfft",
    "libhiprand",
    "libhiprtc",
    "libhipsolver",
    "libhipsparse",
    "libhsa-runtime64",
    "libMIOpen",
    "librccl",
    "librocblas",
    "librocfft",
    "librocm_smi64",
    "librocrand",
    "librocsolver",
    "librocsparse",
    "libroctracer64",
    "libroctx64",
]

ROCM_DATA_DIRS = [
    "rocblas",
    "hipblaslt",
]


def find_soname(srcdir: str, basename: str) -> str:
    """Find the versioned soname file for a library basename.

    Returns the path to the first matching .so.* file, preferring the
    shortest name (e.g. libfoo.so.2 over libfoo.so.2.0.60304).
    """
    pattern = os.path.join(srcdir, f"{basename}.so.*")
    matches = sorted(glob.glob(pattern), key=len)
    if not matches:
        print(f"ERROR: {basename}.so.* not found in {srcdir}", file=sys.stderr)
        sys.exit(1)
    return matches[0]


def link_lib(srcdir: str, basename: str, dstdir: str) -> None:
    """Create a symlink dstdir/basename.so -> srcdir/basename.so.N"""
    target = find_soname(srcdir, basename)
    link_path = os.path.join(dstdir, f"{basename}.so")
    tmp_path = link_path + ".tmp"
    if os.path.islink(tmp_path) or os.path.exists(tmp_path):
        os.unlink(tmp_path)
    os.symlink(target, tmp_path)
    os.rename(tmp_path, link_path)
    print(f"  {link_path} -> {target}")


def main() -> None:
    print("De-vendoring PyTorch ROCm libraries")
    print(f"  ROCM_LIB:  {ROCM_LIB}")
    print(f"  TORCH_LIB: {TORCH_LIB}")

    for srcdir, basenames in SYSTEM_LIBS.items():
        for basename in basenames:
            link_lib(srcdir, basename, TORCH_LIB)

    for basename in ROCM_LIBS:
        link_lib(ROCM_LIB, basename, TORCH_LIB)

    for dirname in ROCM_DATA_DIRS:
        dst = os.path.join(TORCH_LIB, dirname)
        src = os.path.join(ROCM_LIB, dirname)
        if not os.path.isdir(src):
            print(f"WARNING: {src} does not exist, skipping", file=sys.stderr)
            continue
        if os.path.islink(dst):
            os.unlink(dst)
        elif os.path.isdir(dst):
            shutil.rmtree(dst)
        os.symlink(src, dst)
        print(f"  {dst} -> {src}")

    print("De-vendoring complete.")


if __name__ == "__main__":
    main()
