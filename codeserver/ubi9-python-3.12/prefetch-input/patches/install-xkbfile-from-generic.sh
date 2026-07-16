#!/bin/bash
# Build and install util-macros + libxkbfile for native-keymap (node-gyp).
# Prefers prefetched tarballs under /cachi2/output/deps/generic/; otherwise
# downloads from x.org (rhoai-2.25 hermetic=false / network builds).
set -euo pipefail

UTIL_MACROS_VERSION=1.20.2
X_KB_FILE_VERSION=1.1.3
GENERIC="${HERMETO_OUTPUT:-/cachi2/output}/deps/generic"
MAX_JOBS="${MAX_JOBS:-$(nproc)}"
UTIL_URL="https://www.x.org/releases/individual/util/util-macros-${UTIL_MACROS_VERSION}.tar.gz"
XKB_URL="https://www.x.org/releases/individual/lib/libxkbfile-${X_KB_FILE_VERSION}.tar.gz"

if [[ -f /opt/rh/gcc-toolset-14/enable ]]; then
    # shellcheck source=/dev/null
    . /opt/rh/gcc-toolset-14/enable
fi

workdir=$(mktemp -d)
trap 'rm -rf "${workdir}"' EXIT

fetch_tarball() {
    local name="$1"
    local url="$2"
    local dest="${workdir}/${name}"
    local cached="${GENERIC}/${name}"
    if [[ -f "${cached}" ]]; then
        cp "${cached}" "${dest}"
        echo "Using prefetched ${name}"
    else
        echo "Downloading ${url}"
        curl -fsSL "${url}" -o "${dest}"
    fi
}

fetch_tarball "util-macros-${UTIL_MACROS_VERSION}.tar.gz" "${UTIL_URL}"
fetch_tarball "libxkbfile-${X_KB_FILE_VERSION}.tar.gz" "${XKB_URL}"

cd "${workdir}"

tar xf "util-macros-${UTIL_MACROS_VERSION}.tar.gz"
cd "util-macros-${UTIL_MACROS_VERSION}"
./configure --prefix=/usr
make install -j "${MAX_JOBS}"

cd "${workdir}"
tar xf "libxkbfile-${X_KB_FILE_VERSION}.tar.gz"
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
