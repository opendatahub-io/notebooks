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
  dnf install -y gcc-toolset-13 perl make libX11-devel libXt-devel \
    zlib-devel freetype-devel libpng-devel ncurses-devel \
    gd-devel libtool wget tar xz bison flex libXaw-devel

  # Step 1: Download and extract the TeX Live source
  #wget https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/texlive-20250308-source.tar.xz
  wget --no-check-certificate https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/texlive-20250308-source.tar.xz
  tar -xf texlive-20250308-source.tar.xz
  cd texlive-20250308-source

  # Enable newer GCC toolchain
  source /opt/rh/gcc-toolset-13/enable

  # Create build directory and build
  mkdir ../texlive-build
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
  wget http://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz
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

elif [[ "$ARCH" == "amd64" ]]; then
  # tex live installation
  echo "Installing TexLive to allow PDf export from Notebooks"
  curl -fL https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz -o install-tl-unx.tar.gz
  zcat < install-tl-unx.tar.gz | tar xf -
  cd install-tl-2*
  perl ./install-tl --no-interaction --scheme=scheme-small --texdir=/usr/local/texlive
  mv /usr/local/texlive/bin/"$(uname -m)-linux" /usr/local/texlive/bin/linux
  cd /usr/local/texlive/bin/linux
  ./tlmgr install tcolorbox pdfcol adjustbox titling enumitem soul ucs collection-fontsrecommended

else
  echo "Unsupported architecture: $ARCH" >&2
  exit 1

fi

