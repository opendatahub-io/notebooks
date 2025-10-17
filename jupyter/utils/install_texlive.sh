#!/bin/bash
set -euxo pipefail

# Mapping of `uname -m` values to equivalent GOARCH values
declare -A UNAME_TO_GOARCH
UNAME_TO_GOARCH["x86_64"]="amd64"
UNAME_TO_GOARCH["aarch64"]="arm64"
UNAME_TO_GOARCH["ppc64le"]="ppc64le"
UNAME_TO_GOARCH["s390x"]="s390x"

ARCH="${UNAME_TO_GOARCH[$(uname -m)]}"

if [[ "$ARCH" == "ppc64le" ]]; then
  
  echo "Installing TeX Live from source for $ARCH..."

  # Install build dependencies
  dnf install -y gcc-toolset-13 perl make libX11-devel \
    zlib-devel freetype-devel libpng-devel ncurses-devel \
    gd-devel libtool wget tar xz \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/libXmu-devel-1.1.3-8.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/libXext-devel-1.3.4-8.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/libICE-devel-1.0.10-8.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/libSM-devel-1.2.3-10.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/libXmu-1.1.3-8.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/libXaw-devel-1.0.13-19.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/libXaw-1.0.13-19.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/libXt-devel-1.2.0-6.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/flex-2.6.4-9.el9.ppc64le.rpm \
    https://mirror.stream.centos.org/9-stream/AppStream/ppc64le/os/Packages/bison-3.7.4-5.el9.ppc64le.rpm

  # Step 1: Download and extract the TeX Live source
  wget https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/texlive-20250308-source.tar.xz
  tar -xf texlive-20250308-source.tar.xz
  cd texlive-20250308-source

  # Enable newer GCC toolchain
  source /opt/rh/gcc-toolset-13/enable

  # Create build directory and build
  mkdir -p ../texlive-build
  cd ../texlive-build
  ../texlive-20250308-source/configure --prefix=/usr/local/texlive
  make -j"$(nproc)"
  make install

  # Symlink for pdflatex
  ln -sf pdftex /usr/local/texlive/bin/powerpc64le-unknown-linux-gnu/pdflatex
  
  # Cleanup sources to reduce image size
  rm -rf /texlive-20250308-source /texlive-build

  # Step 2: Run TeX Live installer for runtime tree setup
  cd /
  wget https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz
  tar -xzf install-tl-unx.tar.gz
  cd install-tl-2*/

  # Create a custom install profile
  TEXLIVE_INSTALL_PREFIX="/usr/local/texlive"
  cat <<EOF > texlive.profile
selected_scheme scheme-small
TEXDIR $TEXLIVE_INSTALL_PREFIX
TEXMFCONFIG ~/.texlive2025/texmf-config
TEXMFVAR ~/.texlive2025/texmf-var
option_doc 0
option_src 0
EOF

  ./install-tl --profile=texlive.profile --custom-bin=$TEXLIVE_INSTALL_PREFIX/bin/powerpc64le-unknown-linux-gnu

# TeX Live binary directory
TEX_BIN_DIR="/usr/local/texlive/bin/powerpc64le-unknown-linux-gnu"

# Create standard symlink 'linux' → arch-specific folder
ln -sf "$TEX_BIN_DIR" /usr/local/texlive/bin/linux


  # Set up environment
  export PATH="$TEXLIVE_INSTALL_PREFIX/bin/linux:$PATH"
  pdflatex --version
  tlmgr --version

fi
