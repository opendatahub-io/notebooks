#!/bin/bash

# Install dependencies required for Notebooks PDF exports

set -euxo

ARCH=$(uname -m)

if [[ "$ARCH" == "ppc64le" ]]; then
  echo "Installing TeX Live from source for $ARCH"

  # Download and extract source
  wget https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/texlive-20250308-source.tar.xz
  tar -xf texlive-20250308-source.tar.xz
  cd texlive-20250308-source

  # Install build dependencies
  dnf install -y gcc gcc-c++ perl make libX11-devel libXt-devel \
    zlib-devel freetype-devel libpng-devel ncurses-devel \
    gd-devel libtool wget tar xz bison flex libXaw-devel

  # Create build directory
  mkdir ../texlive-build
  cd ../texlive-build

  # Configure, build, install
  ../texlive-20250308-source/configure --prefix=/opt/texlive/2025
  make -j$(nproc)
  make install

  # Symlink for pdflatex
  cd /opt/texlive/2025/bin/powerpc64le-unknown-linux-gnu
  ln -s pdftex pdflatex
  export PATH="/opt/texlive/2025/bin/powerpc64le-unknown-linux-gnu:$PATH"
  pdflatex --version

  # Install pandoc
  dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
  dnf install -y pandoc

else
  echo "Installing TeX Live from installer for $ARCH"

  # Download and install from official installer
  curl -L https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz -o install-tl-unx.tar.gz
  zcat < install-tl-unx.tar.gz | tar xf -
  cd install-tl-2*
  perl ./install-tl --no-interaction --scheme=scheme-small --texdir=/usr/local/texlive
  cd /usr/local/texlive/bin/x86_64-linux
  ./tlmgr install tcolorbox pdfcol adjustbox titling enumitem soul ucs collection-fontsrecommended
fi

# pandoc installation
curl -L https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-linux-amd64.tar.gz -o /tmp/pandoc.tar.gz
mkdir -p /usr/local/pandoc
tar xvzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
rm -f /tmp/pandoc.tar.gz
