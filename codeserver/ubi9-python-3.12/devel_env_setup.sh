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

    TEMP_BUILD_DIR=$(mktemp -d)
    cd ${TEMP_BUILD_DIR}

    : ================== Installing Pillow ==================
    git clone --recursive https://github.com/python-pillow/Pillow.git -b ${PILLOW_VERSION}
    cd Pillow
    uv build --wheel --out-dir /pillowwheel

    : ================= Fix Pillow Wheel ====================
    cd /pillowwheel
    uv pip install auditwheel
    auditwheel repair pillow*.whl
    mv wheelhouse/pillow*.whl ${WHEEL_DIR}

    cd ${CURDIR}
    rm -rf ${TEMP_BUILD_DIR}
}
build_pyarrow() {
    CURDIR=$(pwd)

    export PYARROW_VERSION=$1

    TEMP_BUILD_DIR=$(mktemp -d)
    cd ${TEMP_BUILD_DIR}

    : ================== Installing Pyarrow ==================
    git clone --recursive https://github.com/apache/arrow.git -b apache-arrow-${PYARROW_VERSION}
    cd arrow/cpp
    mkdir build && cd build
    cmake -DCMAKE_BUILD_TYPE=release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DARROW_PYTHON=ON \
        -DARROW_BUILD_TESTS=OFF \
        -DARROW_JEMALLOC=ON \
        -DARROW_BUILD_STATIC="OFF" \
        -DARROW_PARQUET=ON \
        ..
    make install -j ${MAX_JOBS:-$(nproc)}
    cd ../../python/
    uv pip install -v -r requirements-wheel-build.txt
    PYARROW_PARALLEL=${PYARROW_PARALLEL:-$(nproc)} \
    python setup.py build_ext \
        --build-type=release --bundle-arrow-cpp \
        bdist_wheel --dist-dir ${WHEEL_DIR}

    cd ${CURDIR}
    rm -rf ${TEMP_BUILD_DIR}
}

    # Additional dev tools only for s390x \
if [[ $(uname -m) == "s390x" ]]; then \

    dnf install -y --setopt=keepcache=1 perl mesa-libGL skopeo libxcrypt-compat python3.12-devel pkgconf-pkg-config gcc gcc-gfortran gcc-c++ ninja-build make openssl-devel python3-devel pybind11-devel autoconf automake libtool cmake openblas-devel libjpeg-devel zlib-devel libtiff-devel freetype-devel lcms2-devel libwebp-devel git tar wget && \
    dnf install -y --setopt=keepcache=1 https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    dnf install -y --setopt=keepcache=1 cmake gcc gcc-toolset-13 fribidi-devel lcms2-devel openjpeg2-devel libraqm-devel libimagequant-devel tcl-devel tk-devel

     # install rust
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

    source /opt/rh/gcc-toolset-13/enable
    source "$HOME/.cargo/env"

    export MAX_JOBS=${MAX_JOBS:-$(nproc)}
     
    if [[ $(uname -m) == "s390x" ]]; then
        echo "Checking OpenBLAS pkg-config..."
        pkg-config --exists openblas || echo "Warning: openblas.pc not found"
    fi

    export CMAKE_ARGS="-DPython3_EXECUTABLE=python -DCMAKE_PREFIX_PATH=/usr/local"

    PYARROW_VERSION=$(grep -A1 '"pyarrow"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    build_pyarrow ${PYARROW_VERSION}
    uv pip install ${WHEEL_DIR}/*.whl
fi


if [[ $(uname -m) == "ppc64le" ]]; then
    # install development packages
    dnf install -y --setopt=keepcache=1 https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
    # patchelf: needed by `auditwheel repair`
    dnf install -y --setopt=keepcache=1 cmake gcc-toolset-13 fribidi-devel lcms2-devel patchelf \
        libimagequant-devel libraqm-devel openjpeg2-devel tcl-devel tk-devel

    # install rust
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

    source /opt/rh/gcc-toolset-13/enable
    source "$HOME/.cargo/env"

    export MAX_JOBS=${MAX_JOBS:-$(nproc)}
    export OPENBLAS_VERSION=${OPENBLAS_VERSION:-0.3.30}

    # Install OpenBlas
    # IMPORTANT: Ensure Openblas is installed in the final image
    curl -L https://github.com/OpenMathLib/OpenBLAS/releases/download/v${OPENBLAS_VERSION}/OpenBLAS-${OPENBLAS_VERSION}.tar.gz | tar xz
    # rename directory for mounting (without knowing version numbers) in multistage builds
    mv OpenBLAS-${OPENBLAS_VERSION}/ OpenBLAS/
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

    uv pip install ${WHEEL_DIR}/*.whl
fi
if [[ $(uname -m) != "ppc64le" ]]; then
   # only for mounting on other ppc64le
   mkdir -p /root/OpenBLAS/
fi
