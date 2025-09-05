#!/bin/bash

# Install dependencies required for Notebooks PDF exports

set -euxo pipefail

# Mapping of `uname -m` values to equivalent GOARCH values
declare -A UNAME_TO_GOARCH
UNAME_TO_GOARCH["x86_64"]="amd64"
UNAME_TO_GOARCH["aarch64"]="arm64"
UNAME_TO_GOARCH["ppc64le"]="ppc64le"
UNAME_TO_GOARCH["s390x"]="s390x"

ARCH="${UNAME_TO_GOARCH[$(uname -m)]}"
if [[ -z "${ARCH:-}" ]]; then
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 1
fi

# Skip PDF export installation for s390x architecture
if [[ "$(uname -m)" == "s390x" ]]; then
    echo "PDF export functionality is not supported on s390x architecture. Skipping installation."
    exit 0
fi

if [[ "$ARCH" == "ppc64le" ]]; then
  echo "Installing TeX Live from source for $ARCH"

  # Download and extract source
  wget https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/texlive-20250308-source.tar.xz
  tar -xf texlive-20250308-source.tar.xz
  cd texlive-20250308-source

  # Install build dependencies
  dnf install -y gcc-toolset-13 perl make libX11-devel libXt-devel \
    zlib-devel freetype-devel libpng-devel ncurses-devel \
    gd-devel libtool wget tar xz bison flex libXaw-devel

  source /opt/rh/gcc-toolset-13/enable

  # Create build directory
  mkdir ../texlive-build
  cd ../texlive-build

  # Configure, build, install
  ../texlive-20250308-source/configure --prefix=/usr/local/texlive
  make -j$(nproc)
  make install

  # Symlink for pdflatex
  cd /usr/local/texlive/bin/powerpc64le-unknown-linux-gnu
  ln -s pdftex pdflatex

  # Cleanup TeX source to reduce image size
  rm -rf /texlive-20250308-source /texlive-build

  export PATH="/usr/local/texlive/bin/powerpc64le-unknown-linux-gnu:$PATH"
  pdflatex --version

  # Install Pandoc from source
  dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
  dnf install -y cabal-install ghc gmp-devel

  # Set version
  PANDOC_VERSION=3.7.0.2

  cd /tmp
  git clone --recurse-submodules https://github.com/jgm/pandoc.git
  cd pandoc
  git checkout ${PANDOC_VERSION}
  git submodule update --init --recursive

  cabal update

  # Build the CLI tool (not the top-level library package)
  cd pandoc-cli

  # Clean previous builds
  cabal clean

  cabal build -j$(nproc)
  cabal install --installdir=/usr/local/bin --overwrite-policy=always --install-method=copy

  # Clean up Haskell build system
  rm -rf ~/.cabal ~/.ghc /tmp/pandoc
  dnf remove -y cabal-install ghc gmp-devel
  dnf clean all && rm -rf /var/cache/dnf

  # Verify installation
  /usr/local/bin/pandoc --version

fi

if [[ "$ARCH" == "amd64" ]]; then
  # tex live installation
  echo "Installing TexLive to allow PDf export from Notebooks"
  curl -fL https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz -o install-tl-unx.tar.gz
  zcat < install-tl-unx.tar.gz | tar xf -
  cd install-tl-2*
  perl ./install-tl --no-interaction --scheme=scheme-small --texdir=/usr/local/texlive
  mv /usr/local/texlive/bin/"$(uname -m)-linux" /usr/local/texlive/bin/linux
  cd /usr/local/texlive/bin/linux
  ./tlmgr install tcolorbox pdfcol adjustbox titling enumitem soul ucs collection-fontsrecommended

  # pandoc installation
  curl -fL "https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-linux-${ARCH}.tar.gz " -o /tmp/pandoc.tar.gz
  mkdir -p /usr/local/pandoc
  tar xvzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
  rm -f /tmp/pandoc.tar.gz

fi
