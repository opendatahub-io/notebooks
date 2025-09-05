#!/bin/bash
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

  cabal build -j"$(nproc)"
  mkdir -p /usr/local/pandoc/bin
  cabal install \
    --installdir=/usr/local/pandoc/bin \
    --overwrite-policy=always \
    --install-method=copy

  # Clean up Haskell build system
  rm -rf ~/.cabal ~/.ghc /tmp/pandoc
  dnf remove -y cabal-install ghc gmp-devel
  dnf clean all && rm -rf /var/cache/dnf

  # Verify installation
  /usr/local/pandoc/bin/pandoc --version

elif [[ "$ARCH" == "amd64" ]]; then
  # pandoc installation
  curl -fL "https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-linux-${ARCH}.tar.gz"  -o /tmp/pandoc.tar.gz
  mkdir -p /usr/local/pandoc
  tar xvzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
  rm -f /tmp/pandoc.tar.gz

else
  echo "Unsupported architecture: $ARCH" >&2
  exit 1
fi
