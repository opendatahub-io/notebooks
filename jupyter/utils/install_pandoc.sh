#!/bin/bash

# Install dependencies required for Notebooks PDF export (TeX Live + pandoc).
#
# TeX Live is installed from the upstream installer tarball; pandoc from the
# official GitHub release tarball. Prefetched artifacts (artifacts.in.yaml) are
# used when present under /cachi2/output/deps/generic/; otherwise curl is used
# for local/non-hermetic builds.

set -Eeuxo pipefail

if [[ "$(uname -m)" == "s390x" || "$(uname -m)" == "ppc64le" ]]; then
    echo "PDF export functionality is not supported on $(uname -m) architecture. Skipping installation."
    exit 0
fi

declare -A UNAME_TO_GOARCH=(["x86_64"]="amd64" ["aarch64"]="arm64")
_arch="$(uname -m)"
_goarch="${UNAME_TO_GOARCH[${_arch}]}"
if [[ -z "${_goarch}" ]]; then
    echo "ERROR: unsupported architecture for PDF export: ${_arch}" >&2
    exit 1
fi

declare -A UNAME_TO_TEXLIVE_BIN=(
    ["x86_64"]="x86_64-linux"
    ["aarch64"]="aarch64-linux"
)
_texlive_bin="${UNAME_TO_TEXLIVE_BIN[${_arch}]}"

CACHI2_GENERIC="/cachi2/output/deps/generic"
INSTALL_TL_VERSION="install-tl-unx"
PANDOC_VERSION="3.7.0.2"
PANDOC_ARTIFACT="pandoc-${PANDOC_VERSION}-linux-${_goarch}.tar.gz"

_fetch_or_copy() {
    local dest="$1"
    local url="$2"
    local artifact="${3:-$(basename "${url}")}"

    if [[ -f "${CACHI2_GENERIC}/${artifact}" ]]; then
        cp "${CACHI2_GENERIC}/${artifact}" "${dest}"
        return 0
    fi

    curl --fail --location --show-error -o "${dest}" "${url}"
}

# tex live installation
echo "Installing TeX Live to allow PDF export from Notebooks"
_workdir="$(mktemp -d)"
trap 'rm -rf "${_workdir}"' EXIT
_install_tl_tgz="${_workdir}/${INSTALL_TL_VERSION}.tar.gz"
_fetch_or_copy "${_install_tl_tgz}" \
    "https://mirror.ctan.org/systems/texlive/tlnet/${INSTALL_TL_VERSION}.tar.gz" \
    "${INSTALL_TL_VERSION}.tar.gz"
tar -xzf "${_install_tl_tgz}" -C "${_workdir}"
pushd "${_workdir}/${INSTALL_TL_VERSION}" >/dev/null
perl ./install-tl --no-interaction --scheme=scheme-small --texdir=/usr/local/texlive
popd >/dev/null

pushd "/usr/local/texlive/bin/${_texlive_bin}" >/dev/null
./tlmgr install tcolorbox pdfcol adjustbox titling enumitem soul ucs collection-fontsrecommended
popd >/dev/null

ln -sfn "${_texlive_bin}" /usr/local/texlive/bin/current
export PATH="/usr/local/texlive/bin/current:/usr/local/pandoc/bin:${PATH}"

# pandoc installation
_pandoc_tgz="${_workdir}/${PANDOC_ARTIFACT}"
_fetch_or_copy "${_pandoc_tgz}" \
    "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/${PANDOC_ARTIFACT}" \
    "${PANDOC_ARTIFACT}"
mkdir -p /usr/local/pandoc
tar xzf "${_pandoc_tgz}" --strip-components 1 -C /usr/local/pandoc/

pandoc --version
pdflatex --version
kpsewhich tcolorbox.sty
