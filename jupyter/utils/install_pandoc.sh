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

  # Install Pandoc from source
  dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
  dnf install -y pandoc
  mkdir -p /usr/local/pandoc/bin
  ln -s /usr/bin/pandoc /usr/local/pandoc/bin/pandoc
  export PATH="/usr/local/pandoc/bin:$PATH"
  pandoc --version

fi
