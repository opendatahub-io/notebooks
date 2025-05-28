#!/bin/bash 

# Install dependencies required for Notebooks PDF exports

# tex live installation
echo "Installing TexLive to allow PDf export from Notebooks" 
curl -L https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz -o install-tl-unx.tar.gz 
zcat < install-tl-unx.tar.gz | tar xf -
cd install-tl-2*
perl ./install-tl --no-interaction --scheme=scheme-small --texdir=/usr/local/texlive
cd /usr/local/texlive/bin/x86_64-linux
./tlmgr install tcolorbox pdfcol adjustbox titling enumitem soul ucs collection-fontsrecommended

# pandoc installation
curl -L https://github.com/jgm/pandoc/releases/download/3.6.4/pandoc-3.6.4-linux-amd64.tar.gz  -o /tmp/pandoc.tar.gz
mkdir -p /usr/local/pandoc
tar xvzf /tmp/pandoc.tar.gz --strip-components 1 -C /usr/local/pandoc/
rm -f /tmp/pandoc.tar.gz