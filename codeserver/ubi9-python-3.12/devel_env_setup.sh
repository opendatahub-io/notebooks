#!/bin/bash
set -eoux pipefail

#####################################################################################################
# This script is expected to be run on ppc64le hosts as `root`                                      #
# It installs the required build-time dependencies for python wheels                                #
# OpenBlas is built from source (instead of distro provided) with recommended flags for performance #
#####################################################################################################

if [[ $(uname -m) == "ppc64le" ]]; then
    # install development packages
    dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
    dnf install -y cmake gcc-toolset-13 fribidi-devel lcms2-devel \
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
else
    # only for mounting on non-ppc64le
    mkdir -p /root/OpenBLAS/
fi
