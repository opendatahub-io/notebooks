#!/bin/bash
set -euxo pipefail

ARCH=$(uname -m)

if [[ "$ARCH" == "ppc64le" ]]; then
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
  cd pandoc-cli
  cabal build -j$(nproc)
  cabal install --installdir=/usr/local --overwrite-policy=always --install-method=copy

  # Clean up Haskell build system
  rm -rf ~/.cabal ~/.ghc /tmp/pandoc
  dnf remove -y cabal-install ghc gmp-devel
  dnf clean all && rm -rf /var/cache/dnf
fi

if [[ "$ARCH" == "x86_64" ]]; then
  # pandoc installation
  curl -L https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-linux-amd64.tar.gz  -o /tmp/pandoc.tar.gz
  mkdir -p /usr/local/pandoc
  tar xvzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
  rm -f /tmp/pandoc.tar.gz
fi

/usr/local/pandoc --version
