#!/bin/bash
set -Eeuxo pipefail

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
# available in epel but not in rhel9
#texlive-tcolorbox
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

# install texlive-tcolorbox by other means
dnf install -y cpio
dnf clean all
pushd /
texlive_toolbox_rpm=https://download.fedoraproject.org/pub/epel/9/Everything/x86_64/Packages/t/texlive-tcolorbox-20200406-37.el9.noarch.rpm
curl -sSfL ${texlive_toolbox_rpm} | rpm2cpio /dev/stdin | cpio -idmv
popd
texhash
kpsewhich tcolorbox.sty
