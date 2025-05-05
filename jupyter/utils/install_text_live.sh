echo "Installing TexLive to allow PDf export from Notebooks" && \
curl -L https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz -o install-tl-unx.tar.gz && \
zcat < install-tl-unx.tar.gz | tar xf - && \
cd install-tl-2* && \
perl ./install-tl --no-interaction --scheme=scheme-small && \
cd /usr/local/texlive/2025/bin/x86_64-linux && \
./tlmgr install tcolorbox pdfcol adjustbox titling enumitem soul ucs collection-fontsrecommended