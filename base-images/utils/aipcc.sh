#!/usr/bin/env bash
set -Eeuxo pipefail

ARCH=${TARGETARCH}
_=${PYTHON}
_=${VIRTUAL_ENV}

DNF_OPTS=(-y --nodocs --setopt=install_weak_deps=False --setopt=keepcache=True --setopt=max_parallel_downloads=10)

function install_packages() {
    local os_vendor
    os_vendor=$(cut -d: -f3 /etc/system-release-cpe)

    PKGS=()

    # common tools
    PKGS+=("git-core" "wget" "numactl" "file")
    # additional tools
    PKGS+=("skopeo" "jq" "nvtop")
    # additional developer tools
    PKGS+=("make" "ninja-build" "gdb")
    # PKGS+=("vim")

    # for LANG / LC_ALL=en_US.UTF-8
    PKGS+=("glibc-langpack-en")

    # compiler for Torch Dynamo JIT and Triton
    PKGS+=("gcc")

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

    # RHELAI: pyzmq for vLLM
    PKGS+=("zeromq")

    # RHELAI: for h5py
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

    PKGS+=(
        "${PYTHON:?}"
        "${PYTHON}-devel"
    )

    dnf install "${DNF_OPTS[@]}" "${PKGS[@]}"
}

# This is a hack, AIPCC bases lack many packages that the python-3.12 scl image provides
#  so we install them temporarily, to avoid breaking the build.
# The list is obtained as explained in c9s-python-3.12/README.md
function install_scl_packages() {
    local os_vendor
    os_vendor=$(cut -d: -f3 /etc/system-release-cpe)

    SCL_PACKAGES=(
        "annobin"
        "apr"
        "apr-devel"
        "apr-util"
        "apr-util-bdb"
        "apr-util-devel"
        "apr-util-ldap"
        "apr-util-openssl"
        "atlas"
        "atlas-devel"
        "autoconf"
        "automake"
        "brotli"
        "brotli-devel"
        "bsdtar"
        "bzip2-devel"
        "cmake-filesystem"
        "cyrus-sasl"
        "cyrus-sasl-devel"
        "dwz"
        "ed"
        "efi-srpm-macros"
        "enchant"
        "expat-devel"
        "fontconfig-devel"
        "fonts-srpm-macros"
        "freetype-devel"
        "gcc-c++"
        "gcc-gfortran"
        "gcc-plugin-annobin"
        "gd"
        "gd-devel"
        "gettext"
        "gettext-libs"
        "ghc-srpm-macros"
        "git"
        "git-core-doc"
        "glib2-devel"
        "glibc-gconv-extra"
        "glibc-locale-source"
        "go-srpm-macros"
        "graphite2-devel"
        "harfbuzz-devel"
        "harfbuzz-icu"
        "hostname"
        "httpd"
        "httpd-core"
        "httpd-devel"
        "httpd-filesystem"
        "httpd-tools"
        "hunspell"
        "hunspell-en"
        "hunspell-en-GB"
        "hunspell-en-US"
        "hunspell-filesystem"
        "info"
        "kernel-srpm-macros"
        "keyutils-libs-devel"
        "krb5-devel"
        "libICE"
        "libSM"
        "libX11-devel"
        "libXau-devel"
        "libXpm"
        "libXpm-devel"
        "libXt"
        "libblkid-devel"
        "libcom_err-devel"
        "libcurl-devel"
        "libdb-devel"
        "libffi-devel"
        "libgpg-error-devel"
        "libicu-devel"
        "libjpeg-turbo-devel"
        "libkadm5"
        "libmount-devel"
        "libpath_utils"
        "libpng-devel"
        "libpq-devel"
        "libselinux-devel"
        "libsepol-devel"
        "libstdc++-devel"
        "libtalloc"
        "libtiff-devel"
        "libverto-devel"
        "libwebp-devel"
        "libxcb-devel"
        "libxml2-devel"
        "libxslt-devel"
        "llvm-filesystem"
        "lsof"
        "lua-srpm-macros"
        "m4"
        "mailcap"
        "mariadb-connector-c"
        "mariadb-connector-c-config"
        "mariadb-connector-c-devel"
        "mod_auth_gssapi"
        "mod_http2"
        "mod_ldap"
        "mod_lua"
        "mod_session"
        "mod_ssl"
        "ncurses"
        "nodejs"
        "nodejs-docs"
        "nodejs-full-i18n"
        "nodejs-libs"
        "npm"
        "nss_wrapper-libs"
        "ocaml-srpm-macros"
        "openblas-srpm-macros"
        "openldap-devel"
        "openssl-devel"
        "patch"
        "pcre-cpp"
        "pcre-devel"
        "pcre-utf16"
        "pcre-utf32"
        "pcre2-devel"
        "pcre2-utf16"
        "pcre2-utf32"
        "perl-AutoLoader"
        "perl-B"
        "perl-Carp"
        "perl-Class-Struct"
        "perl-Data-Dumper"
        "perl-Digest"
        "perl-Digest-MD5"
        "perl-DynaLoader"
        "perl-Encode"
        "perl-Errno"
        "perl-Error"
        "perl-Exporter"
        "perl-Fcntl"
        "perl-File-Basename"
        "perl-File-Compare"
        "perl-File-Copy"
        "perl-File-Find"
        "perl-File-Path"
        "perl-File-Temp"
        "perl-File-stat"
        "perl-FileHandle"
        "perl-Getopt-Long"
        "perl-Getopt-Std"
        "perl-Git"
        "perl-HTTP-Tiny"
        "perl-IO"
        "perl-IO-Socket-IP"
        "perl-IO-Socket-SSL"
        "perl-IPC-Open3"
        "perl-MIME-Base64"
        "perl-Mozilla-CA"
        "perl-NDBM_File"
        "perl-Net-SSLeay"
        "perl-POSIX"
        "perl-PathTools"
        "perl-Pod-Escapes"
        "perl-Pod-Perldoc"
        "perl-Pod-Simple"
        "perl-Pod-Usage"
        "perl-Scalar-List-Utils"
        "perl-SelectSaver"
        "perl-Socket"
        "perl-Storable"
        "perl-Symbol"
        "perl-Term-ANSIColor"
        "perl-Term-Cap"
        "perl-TermReadKey"
        "perl-Text-ParseWords"
        "perl-Text-Tabs+Wrap"
        "perl-Thread-Queue"
        "perl-Time-Local"
        "perl-URI"
        "perl-base"
        "perl-constant"
        "perl-if"
        "perl-interpreter"
        "perl-lib"
        "perl-libnet"
        "perl-libs"
        "perl-mro"
        "perl-overload"
        "perl-overloading"
        "perl-parent"
        "perl-podlators"
        "perl-srpm-macros"
        "perl-subs"
        "perl-threads"
        "perl-threads-shared"
        "perl-vars"
        "pyproject-srpm-macros"
        "python-srpm-macros"
        "python3.12-pip"
        "python3.12-setuptools"
        "qt5-srpm-macros"
        "redhat-rpm-config"
        "rsync"
        "rust-srpm-macros"
        "scl-utils"
        "sqlite"
        "sqlite-devel"
        "sscg"
        "sysprof-capture-devel"
        "unzip"
        "xorg-x11-proto-devel"
        "xz-devel"
        "zip"
        "zlib-devel"
    )

    # CentOS-specific packages not available on ubi9
    if [[ "${os_vendor}" == "centos" ]]; then
        SCL_PACKAGES+=(
            "centos-gpg-keys"
            "centos-logos-httpd"
            "centos-stream-release"
            "centos-stream-repos"
        )
    fi

    dnf install "${DNF_OPTS[@]}" "${SCL_PACKAGES[@]}"
}

function install_epel() {
    dnf install "${DNF_OPTS[@]}" https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
}

function uninstall_epel() {
    dnf remove "${DNF_OPTS[@]}" epel-release
}

# AIPCC bases enable codeready-builder, so we need to do the CentOS equivalent
# In RHEL this is codeready-builder-for-rhel-${RELEASEVER_MAJOR}-${ARCH}-eus-rpms
# or codeready-builder-for-rhel-${RELEASEVER_MAJOR}-${ARCH}-rpms
function install_csb() {
    dnf install "${DNF_OPTS[@]}" dnf-plugins-core

    local os_vendor
    os_vendor=$(cut -d: -f3 /etc/system-release-cpe)

    if [[ "${os_vendor}" == "centos" ]]; then
      dnf config-manager --set-enabled crb
    fi
}

# create Python virtual env and update pip inside the venv
function install_python_venv() {
    # install venv with bundled pip (no --upgrade-deps)
    "${PYTHON}" -m venv "${VIRTUAL_ENV}"

    "${PYTHON}" -m pip install --force-reinstall --upgrade \
            --index-url https://pypi.org/simple/ \
            pip setuptools wheel
}

function main() {
    install_csb

    install_epel

    # install security updates
    dnf update "${DNF_OPTS[@]}" --security

    install_packages
    if ! test -f /usr/lib64/libzmq.so.5; then
        echo "Error: libzmq.so.5 was not found after installation"
        exit 1
    fi

    dnf install "${DNF_OPTS[@]}" ${PYTHON}-devel ${PYTHON}-pip
    install_python_venv

    # TODO(jdanek): we want to eventually remove this
    install_scl_packages
    # Makefile: REQUIRED_RUNTIME_IMAGE_COMMANDS="curl python3"
    dnf install "${DNF_OPTS[@]}" which

    uninstall_epel
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
