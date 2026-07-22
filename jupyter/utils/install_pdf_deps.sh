#!/bin/bash

# Install OS dependencies required for JupyterLab PDF export.
# Uses RHEL/UBI AppStream texlive RPMs plus EPEL for texlive-tcolorbox and pandoc.
# Requires AppStream (subscription or c9s); plain unsubscribed UBI lacks these packages
# (see https://github.com/red-hat-data-services/notebooks/issues/2310).
# Backport of main's RPM approach (RHAIENG-2186 / RHAIENG-2345); replaces Utah/CTAN curl.

set -Eeuxo pipefail

# Skip PDF export installation for s390x and ppc64le architectures
if [[ "$(uname -m)" == "s390x" || "$(uname -m)" == "ppc64le" ]]; then
    echo "PDF export functionality is not supported on $(uname -m) architecture. Skipping installation."
    exit 0
fi

# https://github.com/rh-aiservices-bu/workbench-images/blob/main/snippets/ides/1-jupyter/os/os-packages.txt
# texlive-tcolorbox is not in AppStream; install from EPEL (do not curl a pinned Fedora RPM URL).
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

# EPEL provides texlive-tcolorbox and pandoc (dynamic binary; check-payload friendly).
dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm

if ! dnf install -y "${PACKAGES[@]}" pandoc; then
    echo "ERROR: Failed to install texlive/pandoc RPMs." >&2
    echo "AppStream texlive packages require a subscribed RHEL/UBI build or c9s AppStream." >&2
    echo "Unsubscribed UBI-only template builds are tracked in" >&2
    echo "https://github.com/red-hat-data-services/notebooks/issues/2310" >&2
    exit 1
fi

dnf clean all

pdflatex --version
pandoc --version
texhash
kpsewhich tcolorbox.sty
command -v pandoc
command -v pdflatex
