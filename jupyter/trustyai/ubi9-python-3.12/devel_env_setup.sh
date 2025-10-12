#!/bin/bash
set -eoux pipefail

#####################################################################################################
# This script is expected to be run on ppc64le and s390x hosts as `root`                           #
# It installs the required build-time dependencies for python wheels                                #
# OpenBlas is built from source (instead of distro provided) with recommended flags for performance #
#####################################################################################################

# Initialize environment variables with default values
if [[ $(uname -m) == "s390x" ]]; then
    export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1
    export CFLAGS="-O3"
    export CXXFLAGS="-O3"
else
    # For other architectures, set custom library paths
    export LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-/usr/local/lib64:/usr/local/lib}
    export PKG_CONFIG_PATH=${PKG_CONFIG_PATH:-/usr/local/lib64/pkgconfig:/usr/local/lib/pkgconfig}
fi

WHEELS_DIR=/wheelsdir
mkdir -p ${WHEELS_DIR}
if [[ $(uname -m) == "ppc64le" ]] || [[ $(uname -m) == "s390x" ]]; then
    CURDIR=$(pwd)

    # install development packages
    dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
    # patchelf: needed by `auditwheel repair`
    dnf install -y fribidi-devel gcc-toolset-13 lcms2-devel libimagequant-devel patchelf \
        libraqm-devel openjpeg2-devel tcl-devel tk-devel unixODBC-devel

     # Install build tools and libraries needed for compiling PyTorch/PyArrow
     if [[ $(uname -m) == "s390x" ]]; then
         dnf install -y gcc gcc-gfortran gcc-c++ make cmake ninja-build \
             autoconf automake libtool pkg-config \
             python3.12-devel python3-devel pybind11-devel \
             openssl-devel openblas-devel \
             libjpeg-devel zlib-devel libtiff-devel freetype-devel \
             lcms2-devel libwebp-devel \
             fribidi-devel openjpeg2-devel libraqm-devel libimagequant-devel \
             tcl-devel tk-devel unixODBC-devel \
             git tar wget unzip
     else
         # ppc64le packages
         dnf install -y fribidi-devel lcms2-devel libimagequant-devel \
             libraqm-devel openjpeg2-devel tcl-devel tk-devel unixODBC-devel
     fi

     # Install Rust for both ppc64le and s390x
     curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
     source $HOME/.cargo/env

     # Install cmake via pip (already available via dnf for s390x, but this ensures it's in PATH)
     uv pip install cmake

     # Set python alternatives for s390x
     if [[ $(uname -m) == "s390x" ]]; then
         alternatives --install /usr/bin/python python /usr/bin/python3.12 1
         alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
         alternatives --install /usr/bin/python3-config python3-config /usr/bin/python3.12-config 1
         alternatives --install /usr/bin/python3-devel python3-devel /usr/bin/python3.12-devel 1
         python --version && python3 --version
     fi

    export MAX_JOBS=${MAX_JOBS:-$(nproc)}

    # For s390x, we use the system openblas-devel package
    # Only build OpenBLAS from source for ppc64le
    if [[ $(uname -m) == "ppc64le" ]]; then
        export OPENBLAS_VERSION=${OPENBLAS_VERSION:-0.3.30}
        cd /root
        curl -L https://github.com/OpenMathLib/OpenBLAS/releases/download/v${OPENBLAS_VERSION}/OpenBLAS-${OPENBLAS_VERSION}.tar.gz | tar xz
        mv OpenBLAS-${OPENBLAS_VERSION}/ OpenBLAS/
        cd OpenBLAS/
        make -j${MAX_JOBS} TARGET=POWER9 BINARY=64 USE_OPENMP=1 USE_THREAD=1 NUM_THREADS=120 DYNAMIC_ARCH=1 INTERFACE64=0
        make PREFIX=/usr/local install NO_STATIC=1
        cd ..
    else
        # Create empty OpenBLAS directory for s390x (for Docker mount compatibility)
        mkdir -p /root/OpenBLAS/
    fi

    # Verify OpenBLAS is found by pkg-config for s390x
    if [[ $(uname -m) == "s390x" ]]; then
        echo "Checking OpenBLAS pkg-config..."
        pkg-config --exists openblas || echo "Warning: openblas.pc not found"
    fi

    export CMAKE_ARGS="-DPython3_EXECUTABLE=python -DCMAKE_PREFIX_PATH=/usr/local"
    export CMAKE_POLICY_VERSION_MINIMUM=3.5

    TMP=$(mktemp -d)

    # Torch
    cd ${CURDIR}
    TORCH_VERSION=$(grep -A1 '"torch"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    cd ${TMP}
    if [[ $(uname -m) == "s390x" ]]; then
        echo "Building PyTorch for s390x"
        export CMAKE_C_FLAGS="-fPIC -O2"
        export CMAKE_CXX_FLAGS="-fPIC -O2"
        export CFLAGS="-O2 -pipe"
        export CXXFLAGS="-O2 -pipe"
        git clone --recursive https://github.com/pytorch/pytorch.git -b v${TORCH_VERSION}
        cd pytorch
        pip install --no-cache-dir -r requirements.txt
        python setup.py develop
        rm -f dist/torch*+git*whl
        MAX_JOBS=${MAX_JOBS} PYTORCH_BUILD_VERSION=${TORCH_VERSION} PYTORCH_BUILD_NUMBER=1 uv build --wheel --out-dir ${WHEELS_DIR}
        echo "PyTorch build completed successfully"
    else
        git clone --recursive https://github.com/pytorch/pytorch.git -b v${TORCH_VERSION}
        cd pytorch
        uv pip install -r requirements.txt
        python setup.py develop
        rm -f dist/torch*+git*whl
        MAX_JOBS=${MAX_JOBS:-$(nproc)} \
            PYTORCH_BUILD_VERSION=${TORCH_VERSION} PYTORCH_BUILD_NUMBER=1 uv build --wheel --out-dir ${WHEELS_DIR}
    fi

    cd ${CURDIR}
    # Pyarrow
    PYARROW_VERSION=$(grep -A1 '"pyarrow"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    cd ${TMP}
    git clone --recursive https://github.com/apache/arrow.git -b apache-arrow-${PYARROW_VERSION}
    cd arrow/cpp
    mkdir build && cd build && \
    # Set architecture-specific CMake flags
    if [[ $(uname -m) == "s390x" ]]; then
        ARROW_CMAKE_FLAGS="-DCMAKE_BUILD_TYPE=Release \
            -DCMAKE_INSTALL_PREFIX=/usr/local \
            -DARROW_PYTHON=ON \
            -DARROW_PARQUET=ON \
            -DARROW_ORC=ON \
            -DARROW_FILESYSTEM=ON \
            -DARROW_JSON=ON \
            -DARROW_CSV=ON \
            -DARROW_DATASET=ON \
            -DARROW_DEPENDENCY_SOURCE=BUNDLED \
            -DARROW_WITH_LZ4=OFF \
            -DARROW_WITH_ZSTD=OFF \
            -DARROW_WITH_SNAPPY=OFF \
            -DARROW_BUILD_TESTS=OFF \
            -DARROW_BUILD_BENCHMARKS=OFF"
    else
        ARROW_CMAKE_FLAGS="-DCMAKE_BUILD_TYPE=release \
            -DCMAKE_INSTALL_PREFIX=/usr/local \
            -DARROW_PYTHON=ON \
            -DARROW_BUILD_TESTS=OFF \
            -DARROW_JEMALLOC=ON \
            -DARROW_BUILD_STATIC=OFF \
            -DARROW_PARQUET=ON"
    fi && \
    cmake ${ARROW_CMAKE_FLAGS} .. && \
    make -j${MAX_JOBS} VERBOSE=1 && \
    make install -j${MAX_JOBS} && \
    cd ../../python/ && \
    uv pip install -v -r requirements-build.txt && \
    if [[ $(uname -m) == "s390x" ]]; then
        PYARROW_WITH_PARQUET=1 \
        PYARROW_WITH_DATASET=1 \
        PYARROW_WITH_FILESYSTEM=1 \
        PYARROW_WITH_JSON=1 \
        PYARROW_WITH_CSV=1 \
        PYARROW_PARALLEL=${MAX_JOBS} \
        python setup.py build_ext --build-type=release --bundle-arrow-cpp bdist_wheel
    else
        PYARROW_PARALLEL=${PYARROW_PARALLEL:-$(nproc)} \
        python setup.py build_ext \
        --build-type=release --bundle-arrow-cpp \
        bdist_wheel
    fi && \
    mkdir -p /wheelsdir && cp dist/pyarrow-*.whl /wheelsdir/ && cp dist/pyarrow-*.whl ${WHEELS_DIR}/

    # Pillow (use auditwheel repaired wheel to avoid pulling runtime libs from EPEL)
    cd ${CURDIR}
    PILLOW_VERSION=$(grep -A1 '"pillow"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    cd ${TMP}
    git clone --recursive https://github.com/python-pillow/Pillow.git -b ${PILLOW_VERSION}
    cd Pillow
    uv build --wheel --out-dir /pillowwheel
    : ================= Fix Pillow Wheel ====================
    cd /pillowwheel
    uv pip install auditwheel
    auditwheel repair pillow*.whl
    mv wheelhouse/pillow*.whl ${WHEELS_DIR}

    ls -ltr ${WHEELS_DIR}

    cd ${CURDIR}
    # Install wheels for s390x and ppc64le
    if [[ $(uname -m) == "ppc64le" ]] || [[ $(uname -m) == "s390x" ]]; then
        pip install --no-cache-dir ${WHEELS_DIR}/*.whl
        uv pip install --refresh ${WHEELS_DIR}/*.whl accelerate==$(grep -A1 '"accelerate"' pylock.toml | grep -Eo '\b[0-9\.]+\b')
    fi

    uv pip list
    cd ${CURDIR}
else
    # only for mounting on non-ppc64le and non-s390x
    mkdir -p /root/OpenBLAS/
fi
