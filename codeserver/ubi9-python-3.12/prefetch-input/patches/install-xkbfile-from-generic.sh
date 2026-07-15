#!/bin/bash
# [HERMETIC] Build and install util-macros + libxkbfile from prefetched X.org tarballs.
# Provides xkbfile.pc and headers for native-keymap (node-gyp) without libxkbfile-devel RPM.
set -euo pipefail

UTIL_MACROS_VERSION=1.20.2
X_KB_FILE_VERSION=1.1.3
GENERIC="${HERMETO_OUTPUT:-/cachi2/output}/deps/generic"
MAX_JOBS="${MAX_JOBS:-$(nproc)}"

if [[ -f /opt/rh/gcc-toolset-14/enable ]]; then
    # shellcheck source=/dev/null
    . /opt/rh/gcc-toolset-14/enable
fi

for tarball in \
    "${GENERIC}/util-macros-${UTIL_MACROS_VERSION}.tar.gz" \
    "${GENERIC}/libxkbfile-${X_KB_FILE_VERSION}.tar.gz"; do
    if [[ ! -f "${tarball}" ]]; then
        echo "ERROR: missing prefetched X.org tarball: ${tarball}" >&2
        exit 1
    fi
done

workdir=$(mktemp -d)
trap 'rm -rf "${workdir}"' EXIT

cd "${workdir}"

tar xf "${GENERIC}/util-macros-${UTIL_MACROS_VERSION}.tar.gz"
cd "util-macros-${UTIL_MACROS_VERSION}"
./configure --prefix=/usr
make install -j "${MAX_JOBS}"

cd "${workdir}"
tar xf "${GENERIC}/libxkbfile-${X_KB_FILE_VERSION}.tar.gz"
cd "libxkbfile-${X_KB_FILE_VERSION}"
./configure --prefix=/usr
make install -j "${MAX_JOBS}"

export PKG_CONFIG_PATH="$(
    find /usr/lib64/pkgconfig /usr/lib/pkgconfig /usr/share/pkgconfig -type d 2>/dev/null \
        | tr '\n' ':'
)${PKG_CONFIG_PATH:-}"

if ! pkg-config --exists x11 xkbfile; then
    echo "ERROR: pkg-config could not find x11/xkbfile after source install" >&2
    pkg-config --print-errors x11 xkbfile >&2 || true
    exit 1
fi

if [[ ! -f /usr/include/X11/extensions/XKBfile.h ]]; then
    echo "ERROR: xkbfile header missing after source install" >&2
    exit 1
fi

echo "libxkbfile headers ready: $(pkg-config --cflags --libs x11 xkbfile)"
