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
curl -fL "https://github.com/jgm/pandoc/releases/download/3.7.0.2/pandoc-3.7.0.2-linux-${ARCH}.tar.gz"  -o /tmp/pandoc.tar.gz
mkdir -p /usr/local/pandoc
tar xvzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
rm -f /tmp/pandoc.tar.gz
