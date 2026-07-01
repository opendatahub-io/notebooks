#!/usr/bin/env bash
set -Eeuxo pipefail

ARCH=${TARGETARCH}
_=${PYTHON}
_=${VIRTUAL_ENV}
_=${PIP_INDEX_URL:?PIP_INDEX_URL must be set}

DNF_OPTS=(-y --nodocs --setopt=install_weak_deps=False --setopt=keepcache=True --setopt=max_parallel_downloads=10)

function get_os_vendor() {
    cut -d: -f3 /etc/system-release-cpe
}

function install_packages() {
    local os_vendor
    os_vendor=$(get_os_vendor)

    PKGS=()

    # common tools
    PKGS+=("git-core" "wget" "numactl" "file")
    # additional tools
    PKGS+=("skopeo" "jq" "nvtop")
    # additional developer tools
    # COPR has ninja-build 1.11.1+, ubi9 CRB only has 1.10.2
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=("make" "ninja-build >= 1.11.1" "gdb")
    else
        PKGS+=("make" "ninja-build" "gdb")
    fi
    # PKGS+=("vim")

    # for LANG / LC_ALL=en_US.UTF-8
    PKGS+=("glibc-langpack-en")

    # compiler for Torch Dynamo JIT and Triton
    PKGS+=("gcc" "gcc-c++")

    # font and image libraries
    PKGS+=("freetype" "lcms2" "libjpeg" "libpng" "libtiff" "libwebp" "openjpeg2")

    # compression libraries and tools
    PKGS+=("bzip2" "cpio" "lz4" "libzstd" "gzip" "xz" "xz-libs" "zlib" "zstd")
    # snappy is not available on ubi9
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=("snappy")
    fi

    # Mathematics libraries used by various packages
    PKGS+=("fftw" "gmp" "mpfr" "libmpc" "openblas" "libomp")

    # additional math libraries
    # TODO: check if we need all variants
    PKGS+=(
        "openblas-openmp" "openblas-serial"
        "openblas-openmp64" "openblas-serial64" "openblas-threads" "openblas-threads64"
    )

    # XML bindings for lxml
    PKGS+=("libxml2" "libxslt")

    # OpenMPI depends on openmpi-devel (Perl, GCC, glibc-devel)
    # openmpi is not available on ubi9
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=("openmpi")
    fi

    # async io for DeepSpeed
    PKGS+=("libaio")

    # PyArrow
    PKGS+=(
        "utf8proc"
        # RHELAI
        "re2" "thrift"
    )

    # PyTorch threading building blocks
    PKGS+=("tbb")

    # For opencv-python-headless
    # libva depends on libX11 and MESA
    PKGS+=("libva")

    # For soundfile
    PKGS+=("libsndfile")

    # docling: qpdf, tesseract are not available on ubi9
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=(
            "qpdf"
            # tesserocr
            "tesseract"
        )
    fi
    # RHELAI: loguru
    PKGS+=("loguru")

    # AIPCC-5427: not supported on big endian machines
    # if [[ "$ARCH" != "s390x" ]]; then
        # RHELAI: pypdfium2
        # libpdfium is not available publicly
        # PKGS+=("libpdfium")
    # fi

    # RHELAI: pyzmq for vLLM
    # COPR has zeromq 4.3.5, EPEL (ubi9) only has 4.3.4; both provide libzmq.so.5
    # COPR can't be enabled on ubi9 (its autoconf pulls gettext-devel which is missing)
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=("zeromq >= 4.3.5")
    else
        PKGS+=("zeromq")
    fi

    # RHELAI: for h5py (HDF5 1.14.x from Copr rebuild, provides libhdf5.so.310)
    PKGS+=("hdf5")

    # RHELAI: faster memory allocator / PyArrow
    PKGS+=("jemalloc")

    # RHELAI: for shapely
    # geos is not available on ubi9
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=("geos")
    fi

    # RHELAI: for rtree
    PKGS+=("spatialindex")

    # For pyodbc
    PKGS+=("unixODBC")

    # For psycopg2-binary Postgres driver
    PKGS+=("libpq")

    # For matplotlib
    # libqhull_r is not available on ubi9
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=("libqhull_r")
    fi

    # For opencv-python-headless, torchaudio, torchvision with FFmpeg support
    # ffmpeg-free-rhai is not available publicly
    # PKGS+=("ffmpeg-free-rhai")

    # Geospatial support in RHAIIS (pyproj, rasterio, shapely), AIPCC-6717
    # gdal-libs and proj are not available on ubi9
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=("gdal-libs" "proj")
    fi

    # For onnx
    # protobuf is not available on ubi9
    if [[ "${os_vendor}" == "centos" ]]; then
        PKGS+=("protobuf")
    fi

    # For memray
    PKGS+=("libunwind")

    # AIPCC-11329: For nixl UCCL backend
    PKGS+=("glog")

    PKGS+=(
        "${PYTHON:?}"
        "${PYTHON}-devel"
    )

    # AIPCC-9953, required by tacozip
    PKGS+=("libzip")

    # For mysqlclient
    PKGS+=("mariadb-connector-c")

    dnf install "${DNF_OPTS[@]}" "${PKGS[@]}"
}

function install_epel() {
    dnf install "${DNF_OPTS[@]}" https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
}

function uninstall_epel() {
    dnf remove "${DNF_OPTS[@]}" epel-release
}

# COPR repo with newer rebuilds of EPEL packages (e.g. hdf5 with libhdf5.so.310)
# https://copr.fedorainfracloud.org/coprs/aaiet-notebooks/rhelai-el9/
# CentOS-only: enabling COPR on ubi9 causes dep failures (e.g. autoconf needs gettext-devel)
function install_copr() {
    if [[ "$(get_os_vendor)" == "centos" ]]; then
        dnf install "${DNF_OPTS[@]}" 'dnf-command(copr)'
        dnf copr enable -y aaiet-notebooks/rhelai-el9
    fi
}

function uninstall_copr() {
    if [[ "$(get_os_vendor)" == "centos" ]]; then
        dnf copr disable -y aaiet-notebooks/rhelai-el9
    fi
}

# AIPCC bases enable codeready-builder, so we need to do the CentOS equivalent
# In RHEL this is codeready-builder-for-rhel-${RELEASEVER_MAJOR}-${ARCH}-eus-rpms
# or codeready-builder-for-rhel-${RELEASEVER_MAJOR}-${ARCH}-rpms
function install_csb() {
    dnf install "${DNF_OPTS[@]}" dnf-plugins-core

    local os_vendor
    os_vendor=$(get_os_vendor)

    if [[ "${os_vendor}" == "centos" ]]; then
      dnf config-manager --set-enabled crb
    fi
}

# create Python virtual env, install pip + uv
# Downstream (AIPCC/RHOAI) python-venv.sh does the same:
#   https://gitlab.com/redhat/rhel-ai/core/base-images/app/-/blob/main/context/app/python-venv.sh
function install_python_venv() {
    # install venv with bundled pip (no --upgrade-deps)
    "${PYTHON}" -m venv "${VIRTUAL_ENV}"

    # All current AIPCC indices (cpu, cuda12.9, cuda13.0, rocm7.1) carry
    # pip, setuptools, wheel, and uv. Install from PIP_INDEX_URL directly.
    "${PYTHON}" -m pip install --force-reinstall --upgrade \
            pip setuptools wheel

    "${PYTHON}" -m pip install uv
}

function main() {
    install_csb

    install_epel
    install_copr

    # install security updates
    dnf update "${DNF_OPTS[@]}" --security

    install_packages
    # https://github.com/opendatahub-io/notebooks/pull/2609
    if ! test -f /usr/lib64/libzmq.so.5; then
        echo "Error: libzmq.so.5 was not found after installation"
        exit 1
    fi
    # https://github.com/opendatahub-io/notebooks/issues/2944
    if [[ "$(get_os_vendor)" == "centos" ]]; then
        if ! test -f /usr/lib64/libhdf5.so.310; then
            echo "Error: libhdf5.so.310 was not found after installation (see https://github.com/opendatahub-io/notebooks/issues/2944)"
            exit 1
        fi
    fi

    dnf install "${DNF_OPTS[@]}" ${PYTHON}-devel ${PYTHON}-pip
    install_python_venv

    # Makefile: REQUIRED_RUNTIME_IMAGE_COMMANDS="curl python3"
    dnf install "${DNF_OPTS[@]}" which

    uninstall_copr
    uninstall_epel
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
