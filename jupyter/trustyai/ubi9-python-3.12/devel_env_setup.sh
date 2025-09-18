#!/bin/bash
set -eoux pipefail

#####################################################################################################
# This script is expected to be run on ppc64le hosts as `root`                                      #
# It installs the required build-time dependencies for python wheels                                #
# OpenBlas is built from source (instead of distro provided) with recommended flags for performance #
#####################################################################################################
WHEELS_DIR=/wheelsdir
mkdir -p ${WHEELS_DIR}
if [[ $(uname -m) == "ppc64le" ]]; then
    CURDIR=$(pwd)

    # install development packages
    dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
    dnf install -y fribidi-devel gcc-toolset-13 lcms2-devel libimagequant-devel \
        libraqm-devel openjpeg2-devel tcl-devel tk-devel unixODBC-devel

    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

    source /opt/rh/gcc-toolset-13/enable
    source $HOME/.cargo/env
    
    uv pip install cmake

    export MAX_JOBS=${MAX_JOBS:-$(nproc)}
    export OPENBLAS_VERSION=${OPENBLAS_VERSION:-0.3.30}

    # Install OpenBlas
    # IMPORTANT: Ensure Openblas is installed in the final image
    cd /root
    curl -L https://github.com/OpenMathLib/OpenBLAS/releases/download/v${OPENBLAS_VERSION}/OpenBLAS-${OPENBLAS_VERSION}.tar.gz | tar xz
    # rename directory for mounting (without knowing version numbers) in multistage builds
    mv OpenBLAS-${OPENBLAS_VERSION}/ OpenBLAS/
    cd OpenBLAS/
    make -j${MAX_JOBS} TARGET=POWER9 BINARY=64 USE_OPENMP=1 USE_THREAD=1 NUM_THREADS=120 DYNAMIC_ARCH=1 INTERFACE64=0
    make install
    cd ..

    # set path for openblas
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/OpenBLAS/lib/:/usr/local/lib64:/usr/local/lib
    export PKG_CONFIG_PATH=$(find / -type d -name "pkgconfig" 2>/dev/null | tr '\n' ':')
    export CMAKE_ARGS="-DPython3_EXECUTABLE=python"
    export CMAKE_POLICY_VERSION_MINIMUM=3.5

    TMP=$(mktemp -d)

    # Torch
    cd ${CURDIR}
    TORCH_VERSION=$(grep -A1 '"torch"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    cd ${TMP}
    git clone --recursive https://github.com/pytorch/pytorch.git -b v${TORCH_VERSION}
    cd pytorch
    uv pip install -r requirements.txt
    python setup.py develop
    rm -f dist/torch*+git*whl
    MAX_JOBS=${MAX_JOBS:-$(nproc)} \
        PYTORCH_BUILD_VERSION=${TORCH_VERSION} PYTORCH_BUILD_NUMBER=1 uv build --wheel --out-dir ${WHEELS_DIR}

    cd ${CURDIR}
    # Pyarrow
    PYARROW_VERSION=$(grep -A1 '"pyarrow"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    cd ${TMP}
    git clone --recursive https://github.com/apache/arrow.git -b apache-arrow-${PYARROW_VERSION}
    cd arrow/cpp
    mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DARROW_PYTHON=ON \
        -DARROW_BUILD_TESTS=OFF \
        -DARROW_JEMALLOC=ON \
        -DARROW_BUILD_STATIC="OFF" \
        -DARROW_PARQUET=ON \
        .. && \
    make install -j ${MAX_JOBS:-$(nproc)} && \
    cd ../../python/ && \
    uv pip install -v -r requirements-wheel-build.txt && \
    PYARROW_PARALLEL=${PYARROW_PARALLEL:-$(nproc)} \
    python setup.py build_ext \
    --build-type=release --bundle-arrow-cpp \
    bdist_wheel --dist-dir ${WHEELS_DIR}

    ls -ltr ${WHEELS_DIR}

    cd ${CURDIR}
    uv pip install --refresh ${WHEELS_DIR}/*.whl accelerate==$(grep -A1 '"accelerate"' pylock.toml | grep -Eo '\b[0-9\.]+\b')

    uv pip list
    cd ${CURDIR}
else
    # only for mounting on non-ppc64le
    mkdir -p /root/OpenBLAS/
fi
