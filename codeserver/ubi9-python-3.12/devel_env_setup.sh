#!/bin/bash
set -eoux pipefail

#####################################################################################################
# This script is expected to be run on ppc64le hosts as `root`                                      #
# It installs the required build-time dependencies for python wheels                                #
# OpenBlas is built from source (instead of distro provided) with recommended flags for performance #
#####################################################################################################
export WHEEL_DIR=${WHEEL_DIR:-"/wheelsdir"}
mkdir -p ${WHEEL_DIR}

build_pillow() {
    CURDIR=$(pwd)

    export PILLOW_VERSION=$1

    : ================== Installing Pillow ==================
    PREFETCH_PILLOW="${PREFETCH_PILLOW:-/root/${CODESERVER_SOURCE_CODE:-codeserver/ubi9-python-3.12}/prefetch-input/Pillow}"
    [[ -d "${PREFETCH_PILLOW}" && -f "${PREFETCH_PILLOW}/pyproject.toml" ]] || { echo "Prefetched Pillow source not found at ${PREFETCH_PILLOW}"; exit 1; }
    cd "${PREFETCH_PILLOW}"
    # Konflux checks out the repo at the right ref; use tree as-is.
    uv build --wheel --out-dir /pillowwheel --no-index --find-links /cachi2/output/deps/pip

    : ================= Fix Pillow Wheel ====================
    cd /pillowwheel
    uv pip install --no-index --find-links /cachi2/output/deps/pip auditwheel
    auditwheel repair pillow*.whl
    mv wheelhouse/pillow*.whl ${WHEEL_DIR}

    cd ${CURDIR}
}
build_pyarrow() {
    CURDIR=$(pwd)

    export PYARROW_VERSION=$1

    : ================== Installing Pyarrow ==================
    PREFETCH_ARROW="${PREFETCH_ARROW:-/root/${CODESERVER_SOURCE_CODE:-codeserver/ubi9-python-3.12}/prefetch-input/arrow}"
    [[ -d "${PREFETCH_ARROW}" && -d "${PREFETCH_ARROW}/cpp" ]] || { echo "Prefetched Arrow source not found at ${PREFETCH_ARROW}"; exit 1; }

    # Point Arrow CMake to prefetched dependency tarballs (hermetic build: no network access).
    # These are NOT part of boost-devel — they are separate third-party libraries that Arrow
    # bundles and builds from source. Arrow reads ARROW_*_URL env vars and uses local files
    # instead of downloading. Versions must match arrow/cpp/thirdparty/versions.txt.
    GENERIC_DEPS="/cachi2/output/deps/generic"
    if [[ -d "${GENERIC_DEPS}" ]]; then
        export ARROW_THRIFT_URL="${GENERIC_DEPS}/thrift-0.22.0.tar.gz"
        export ARROW_JEMALLOC_URL="${GENERIC_DEPS}/jemalloc-5.3.0.tar.bz2"
        export ARROW_MIMALLOC_URL="${GENERIC_DEPS}/mimalloc-v2.2.4.tar.gz"
        export ARROW_RAPIDJSON_URL="${GENERIC_DEPS}/rapidjson-232389d4f1012dddec4ef84861face2d2ba85709.tar.gz"
        export ARROW_RE2_URL="${GENERIC_DEPS}/re2-2022-06-01.tar.gz"
        export ARROW_UTF8PROC_URL="${GENERIC_DEPS}/utf8proc-v2.10.0.tar.gz"
        export ARROW_XSIMD_URL="${GENERIC_DEPS}/xsimd-13.0.0.tar.gz"
        export ARROW_SNAPPY_URL="${GENERIC_DEPS}/snappy-1.2.2.tar.gz"
        export ARROW_BROTLI_URL="${GENERIC_DEPS}/brotli-v1.0.9.tar.gz"
        export ARROW_LZ4_URL="${GENERIC_DEPS}/lz4-v1.10.0.tar.gz"
        export ARROW_ZSTD_URL="${GENERIC_DEPS}/zstd-1.5.7.tar.gz"
        export ARROW_ZLIB_URL="${GENERIC_DEPS}/zlib-1.3.1.tar.gz"
    fi

    cd "${PREFETCH_ARROW}"
    # Konflux checks out the repo at the right ref; use tree as-is.
    cd cpp
    mkdir -p build && cd build
    cmake -DCMAKE_BUILD_TYPE=release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DARROW_PYTHON=ON \
        -DARROW_BUILD_TESTS=OFF \
        -DARROW_JEMALLOC=ON \
        -DARROW_BUILD_STATIC="OFF" \
        -DARROW_PARQUET=ON \
        -DBoost_SOURCE=SYSTEM \
        ..
    make install -j ${MAX_JOBS:-$(nproc)}
    cd ../../python/
    uv pip install --no-index --find-links /cachi2/output/deps/pip -v -r requirements-wheel-build.txt
    PYARROW_PARALLEL=${PYARROW_PARALLEL:-$(nproc)} \
    python setup.py build_ext \
        --build-type=release --bundle-arrow-cpp \
        bdist_wheel --dist-dir ${WHEEL_DIR}

    cd ${CURDIR}
}

build_matplotlib() {
    CURDIR=$(pwd)

    export MATPLOTLIB_VERSION=$1

    : ================== Building matplotlib ==================
    # matplotlib's meson build defaults to downloading its own FreeType and Qhull.
    # Under --network=none this fails. We tell it to use system freetype-devel and
    # qhull-devel (installed via dnf) via meson config settings.
    uv pip install --no-index --find-links /cachi2/output/deps/pip \
        --no-deps \
        --config-settings 'setup-args=-Dsystem-freetype=true' \
        --config-settings 'setup-args=-Dsystem-qhull=true' \
        "matplotlib==${MATPLOTLIB_VERSION}"

    cd ${CURDIR}
}

build_onnx() {
    CURDIR=$(pwd)

    export ONNX_VERSION=$1

    : ================== Building onnx ==================
    # onnx's CMake build downloads protobuf via FetchContent, and protobuf
    # downloads abseil-cpp. It also git-clones nanobind. Under --network=none
    # all of these fail. We:
    #   1. Extract prefetched protobuf + abseil-cpp tarballs and redirect via
    #      FETCHCONTENT_SOURCE_DIR_* CMake variables.
    #   2. Install nanobind from the pip cache so onnx's find_package(nanobind)
    #      succeeds and skips the git clone entirely.
    GENERIC_DEPS="/cachi2/output/deps/generic"
    ONNX_BUILD_DIR="/tmp/onnx-build-deps"
    mkdir -p ${ONNX_BUILD_DIR}

    tar xzf "${GENERIC_DEPS}/protobuf-31.1.tar.gz" -C ${ONNX_BUILD_DIR}
    tar xzf "${GENERIC_DEPS}/abseil-cpp-20250127.0.tar.gz" -C ${ONNX_BUILD_DIR}

    # Install nanobind so CMake find_package(nanobind) succeeds (avoids git clone)
    uv pip install --no-index --find-links /cachi2/output/deps/pip nanobind
    NANOBIND_CMAKE_DIR=$(python3 -c "import nanobind; print(nanobind.cmake_dir())")

    # Save and extend CMAKE_ARGS so only the onnx build sees the overrides
    OLD_CMAKE_ARGS="${CMAKE_ARGS:-}"
    export CMAKE_ARGS="${CMAKE_ARGS} -DFETCHCONTENT_SOURCE_DIR_PROTOBUF=${ONNX_BUILD_DIR}/protobuf-31.1 -DFETCHCONTENT_SOURCE_DIR_ABSL=${ONNX_BUILD_DIR}/abseil-cpp-20250127.0 -Dnanobind_DIR=${NANOBIND_CMAKE_DIR}"

    uv pip install --no-index --find-links /cachi2/output/deps/pip \
        --no-deps \
        "onnx==${ONNX_VERSION}"

    export CMAKE_ARGS="${OLD_CMAKE_ARGS}"

    cd ${CURDIR}
}

# s390x-specific build setup (system packages are installed by the Dockerfile)
if [[ $(uname -m) == "s390x" ]]; then
    source /opt/rh/gcc-toolset-13/enable

    export MAX_JOBS=${MAX_JOBS:-$(nproc)}

    if [[ $(uname -m) == "s390x" ]]; then
        echo "Checking OpenBLAS pkg-config..."
        pkg-config --exists openblas || echo "Warning: openblas.pc not found"
    fi

    export CMAKE_ARGS="-DPython3_EXECUTABLE=python -DCMAKE_PREFIX_PATH=/usr/local"

    PYARROW_VERSION=$(grep -A1 '"pyarrow"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    build_pyarrow ${PYARROW_VERSION}
    uv pip install --no-index --find-links /cachi2/output/deps/pip "${WHEEL_DIR}"/*.whl
fi


# ppc64le-specific build setup (system packages are installed by the Dockerfile)
if [[ $(uname -m) == "ppc64le" ]]; then
    source /opt/rh/gcc-toolset-13/enable

    export MAX_JOBS=${MAX_JOBS:-$(nproc)}
    export OPENBLAS_VERSION=${OPENBLAS_VERSION:-0.3.30}

    # Install OpenBlas (from Cachi2 prefetch; see prefetch-input/artifacts.in.yaml)
    # IMPORTANT: Ensure Openblas is installed in the final image
    cp "/cachi2/output/deps/generic/OpenBLAS-${OPENBLAS_VERSION}.tar.gz" ./
    tar xzf "OpenBLAS-${OPENBLAS_VERSION}.tar.gz"
    # rename directory for mounting (without knowing version numbers) in multistage builds
    mv "OpenBLAS-${OPENBLAS_VERSION}/" OpenBLAS/
    cd OpenBLAS/
    make -j${MAX_JOBS} TARGET=POWER9 BINARY=64 USE_OPENMP=1 USE_THREAD=1 NUM_THREADS=120 DYNAMIC_ARCH=1 INTERFACE64=0
    make install
    cd ..

    # set path for openblas
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/OpenBLAS/lib/
    export PKG_CONFIG_PATH=$(find / -type d -name "pkgconfig" 2>/dev/null | tr '\n' ':')
    export CMAKE_ARGS="-DPython3_EXECUTABLE=python"

    PYARROW_VERSION=$(grep -A1 '"pyarrow"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    build_pyarrow ${PYARROW_VERSION}

    PILLOW_VERSION=$(grep -A1 '"pillow"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    build_pillow ${PILLOW_VERSION}

    MATPLOTLIB_VERSION=$(grep -A1 '"matplotlib"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    build_matplotlib ${MATPLOTLIB_VERSION}

    ONNX_VERSION=$(grep -A1 '"onnx"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    build_onnx ${ONNX_VERSION}

    uv pip install --no-index --find-links /cachi2/output/deps/pip "${WHEEL_DIR}"/*.whl
fi
if [[ $(uname -m) != "ppc64le" ]]; then
   # only for mounting on other ppc64le
   mkdir -p /root/OpenBLAS/
fi
