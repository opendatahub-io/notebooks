#!/bin/bash

# Install dependencies required for Notebooks PDF exports.
# Texlive components are installed from RPMs (see RHAIENG-2186).

set -Eeuxo pipefail

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

# Skip PDF export installation for s390x and ppc64le architectures
if [[ "$(uname -m)" == "s390x" || "$(uname -m)" == "ppc64le" ]]; then
    echo "PDF export functionality is not supported on $(uname -m) architecture. Skipping installation."
    exit 0
fi

# https://github.com/rh-aiservices-bu/workbench-images/blob/main/snippets/ides/1-jupyter/os/os-packages.txt
PACKAGES=(
texlive-adjustbox
texlive-bibtex
texlive-charter
texlive-ec
texlive-euro
texlive-eurosym
texlive-fpl
texlive-jknapltx
texlive-knuth-local
texlive-lm-math
texlive-marvosym
texlive-mathpazo
texlive-mflogo-font
texlive-parskip
texlive-plain
texlive-pxfonts
texlive-rsfs
texlive-tcolorbox
texlive-times
texlive-titling
texlive-txfonts
texlive-ulem
texlive-upquote
texlive-utopia
texlive-wasy
texlive-wasy-type1
texlive-wasysym
texlive-xetex
# dependencies of texlive-tcolorbox
texlive-environ
texlive-trimspaces
)

dnf install -y "${PACKAGES[@]}"
dnf clean all

pdflatex --version
texhash
kpsewhich tcolorbox.sty

# We use prebuilt pandoc for now, until AIPCC-7795 is done.
# Hermetic build: use Cachi2-prefetched tarball (see prefetch-input/*/artifacts.in.yaml).
# If not in cachi2 (e.g. non-hermetic/local build), download from GitHub releases.
PANDOC_VERSION="3.7.0.2"
PANDOC_TGZ="/cachi2/output/deps/generic/pandoc-${PANDOC_VERSION}-linux-${ARCH}.tar.gz"

if [[ -f "${PANDOC_TGZ}" ]]; then
    echo "Using Cachi2-prefetched pandoc tarball."
    mkdir -p /usr/local/pandoc
    tar xvzf "${PANDOC_TGZ}" --strip-components 1 -C /usr/local/pandoc/
else
    PANDOC_URL="https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-linux-${ARCH}.tar.gz"
    echo "Pandoc tarball not in cachi2, downloading from ${PANDOC_URL}"
    curl -fL "${PANDOC_URL}" -o /tmp/pandoc.tar.gz
    mkdir -p /usr/local/pandoc
    tar xzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
    rm -f /tmp/pandoc.tar.gz
fi

# dnf install -y pandoc
# mkdir -p /usr/local/pandoc/bin
# ln -s /usr/bin/pandoc /usr/local/pandoc/bin/pandoc
export PATH="/usr/local/pandoc/bin:$PATH"
pandoc --version
