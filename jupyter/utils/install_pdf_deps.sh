#!/bin/bash

# Install dependencies required for Notebooks PDF exports

set -euo pipefail
set -x

ARCH=$(uname -m)

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
  export PATH="/usr/local/texlive/bin/powerpc64le-unknown-linux-gnu:$PATH"
  pdflatex --version

  # Install dependencies
  dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
  dnf install -y cabal-install ghc gmp-devel
  # Set version
  PANDOC_VERSION=3.7.0.2
  
  # Clone repo
  cd /tmp
  git clone --recurse-submodules https://github.com/jgm/pandoc.git
  cd pandoc
  git checkout ${PANDOC_VERSION}
  git submodule update --init --recursive
  
  # Update Cabal
  cabal update
  
  # Build the CLI tool (not the top-level library package)
  cd pandoc-cli
  
  # Clean previous builds
  cabal clean
  
  # Configure and build
  cabal build -j
  
  # Install the CLI executable
  cabal install --installdir=/usr/local/bin --overwrite-policy=always
  
  # Verify installation
  /usr/local/bin/pandoc --version

fi

if [[ "$ARCH" == "x86_64" ]]; then
  # tex live installation
  echo "Installing TexLive to allow PDf export from Notebooks" 
  curl -L https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz -o install-tl-unx.tar.gz 
  zcat < install-tl-unx.tar.gz | tar xf -
  cd install-tl-2*
  perl ./install-tl --no-interaction --scheme=scheme-small --texdir=/usr/local/texlive
  cd /usr/local/texlive/bin/x86_64-linux
  ./tlmgr install tcolorbox pdfcol adjustbox titling enumitem soul ucs collection-fontsrecommended

  # pandoc installation
  curl -L https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-linux-amd64.tar.gz  -o /tmp/pandoc.tar.gz
  mkdir -p /usr/local/pandoc
  tar xvzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
  rm -f /tmp/pandoc.tar.gz

fi
