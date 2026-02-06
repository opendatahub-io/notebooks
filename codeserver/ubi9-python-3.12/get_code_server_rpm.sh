#!/bin/bash
set -euxo pipefail

##############################################################################
# This script is expected to be run as `root`                                #
# It builds code-server rpm for `ppc64le`                                    #
# For other architectures, the rpm is downloaded from the available releases #
##############################################################################


# Mapping of `uname -m` values to equivalent GOARCH values
declare -A UNAME_TO_GOARCH
UNAME_TO_GOARCH["x86_64"]="amd64"
UNAME_TO_GOARCH["aarch64"]="arm64"
UNAME_TO_GOARCH["ppc64le"]="ppc64le"
UNAME_TO_GOARCH["s390x"]="s390x"

ARCH="${UNAME_TO_GOARCH[$(uname -m)]}"

if [[ "$ARCH" == "amd64" || "$ARCH" == "arm64" || "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then   
    # starting with node-22, c++20 is required (gcc-toolset-14 installed from prefetched RPMs)
    . /opt/rh/gcc-toolset-14/enable
    # [HERMETIC] Install nfpm (RPM packager) from prefetched RPM (previously fetched from GitHub releases API at build time).
    dnf install -y /cachi2/output/deps/generic/nfpm-2.44.1-1.$(uname -m).rpm
    # [HERMETIC] CODESERVER_SOURCE_PREFETCH is set by Dockerfile ENV (points to prefetched code-server source).
    cd "${CODESERVER_SOURCE_PREFETCH}"

    # [HERMETIC] Apply offline-build patches (cachi2 rewrites, offline npm, etc.)
    # Use `patch` instead of `git apply` because the prefetched source contains a
    # nested git submodule (lib/vscode) whose .git reference is broken inside the
    # container, causing `git apply` to fail on files within that submodule.
    for p in patches/[0-9]*-*.patch; do
        echo "Applying $p"
        patch -p1 < "$p"
    done

    # s390x: apply patch (from VSCodium: arch-4-s390x-package.json.patch)
    if [[ "$ARCH" == "s390x" ]]; then
        patch -p1 < patches/s390x.patch
    fi
    
    # apply code-server's own patches to VS Code source
    while IFS= read -r src_patch; do echo "patches/$src_patch"; patch -p1 < "patches/$src_patch"; done < patches/series    
    npm cache clean --force
else
  # we shall not download rpm for other architectures
  echo "Unsupported architecture: $ARCH" >&2
  exit 1
fi
