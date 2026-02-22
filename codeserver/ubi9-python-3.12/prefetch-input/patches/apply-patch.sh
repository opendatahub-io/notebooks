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

    # [HERMETIC] CODESERVER_SOURCE_PREFETCH is set by Dockerfile ENV (points to prefetched code-server source).
    cd "${CODESERVER_SOURCE_PREFETCH}"

    # s390x: apply patch (from VSCodium: arch-4-s390x-package.json.patch)
    if [[ "$ARCH" == "s390x" ]]; then
        patch -p1 < patches/s390x.patch
    fi    

    # ppc64le/s390x: Disable @vscode/vsce-sign's postinstall script.
    #
    # WHAT IS @vscode/vsce-sign?
    #   It is a dependency of @vscode/vsce (the VS Code Extension CLI tool, used to
    #   package/publish/sign .vsix extension files).  Its postinstall script downloads
    #   a platform-specific native binary (bin/vsce-sign) that performs cryptographic
    #   signing and verification of VS Code extension packages.
    #
    # WHY DOES IT FAIL?
    #   The postinstall script only supports: linux-x64, linux-arm64, linux-arm,
    #   darwin-x64, darwin-arm64, win32-x64, win32-arm64, alpine-x64, alpine-arm64.
    #   On ppc64le/s390x, process.arch returns "ppc64"/"s390x" which the script does
    #   not recognise, so it throws:
    #     "The current platform (linux) and architecture (ppc64) is not supported."
    #   Microsoft has no plans to add ppc64le/s390x support (see github.com/microsoft/
    #   vscode-vsce/issues/1105, closed as "not planned").
    #
    # WHY IS IT SAFE TO REMOVE?
    #   @vscode/vsce-sign provides zero functionality to code-server:
    #
    #   1. Build time — @vscode/vsce is a devDependency in lib/vscode/build/package.json.
    #      code-server builds the VS Code Remote Extension Host (gulpfile.reh.js), which
    #      has zero references to vsce-sign.  The only reference is in gulpfile.vscode.js
    #      (desktop ASAR packaging), which code-server does not use.
    #
    #   2. Runtime — VS Code's extensionSignatureVerificationService.ts does import
    #      @vscode/vsce-sign at runtime for extension signature verification, BUT:
    #      a) code-server already applies patches/signature-verification.diff which
    #         hard-codes verifySignature=false, so the verify() path is never reached.
    #      b) Even without the patch, the code has graceful fallback: if the module
    #         fails to load, it logs a warning and skips verification (returns undefined).
    #
    #   3. External validation — b-data.ch (gitlab.b-data.ch/coder/code-server-builder)
    #      successfully builds and ships code-server on ppc64le/s390x by completely
    #      removing @vscode/vsce-sign: they downgrade @vscode/vsce from 3.6.1 to 2.20.1
    #      (which has no vsce-sign dependency at all).  They also apply an identical
    #      signature-verification.diff patch.  See:
    #        https://gitlab.b-data.ch/coder/code-server-builder (patches/4.105.0.patch)
    #        https://gitlab.b-data.ch/coder/code-server (patches/signature-verification.diff)
    #
    # HOW THE FIX WORKS:
    #   1. Patch the cached tarball: remove "postinstall" from its package.json so the
    #      download-binary script never runs.
    #   2. Patch the lockfile: set hasInstallScript=false (tells npm to skip lifecycle
    #      scripts) and remove the integrity hash (so npm accepts the modified tarball).
    #   Both steps are belt-and-suspenders — the lockfile flag alone is sufficient per
    #   npm documentation (see github.com/npm/cli/issues/2606), but patching the tarball
    #   adds defence in depth.
    if [[ "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then
        # Try to patch the cached tarball (remove postinstall from its package.json)
        VSCE_TGZ=$(find /cachi2/output/deps/npm -name "*vsce-sign*.tgz" -type f 2>/dev/null | head -1)
        if [[ -n "${VSCE_TGZ}" ]]; then
            echo "Patching vsce-sign: removing postinstall for ${ARCH} (${VSCE_TGZ})"
            tmpdir=$(mktemp -d)
            tar xzf "${VSCE_TGZ}" -C "$tmpdir"
            jq 'del(.scripts.postinstall)' "$tmpdir/package/package.json" \
                > /tmp/pkg-tmp.json && mv /tmp/pkg-tmp.json "$tmpdir/package/package.json"
            tar czf "${VSCE_TGZ}" -C "$tmpdir" package
            rm -rf "$tmpdir"
        else
            echo "WARNING: vsce-sign tarball not found in /cachi2/output/deps/npm/"
            echo "  Searched: find /cachi2/output/deps/npm -name '*vsce-sign*.tgz'"
            find /cachi2/output/deps/npm -name "*vsce*" -type f 2>/dev/null || true
        fi
        # Tell npm not to run vsce-sign's postinstall (hasInstallScript=false) and
        # strip integrity so npm accepts the modified tarball if found above.
        jq '
            (.packages["node_modules/@vscode/vsce-sign"].hasInstallScript = false) |
            del(.packages["node_modules/@vscode/vsce-sign"].integrity)
        ' lib/vscode/build/package-lock.json > /tmp/lock-tmp.json \
            && mv /tmp/lock-tmp.json lib/vscode/build/package-lock.json
    fi

    # apply code-server's own patches to VS Code source
    while IFS= read -r src_patch; do echo "patches/$src_patch"; patch -p1 < "patches/$src_patch"; done < patches/series    
    npm cache clean --force
else
  # we shall not download rpm for other architectures
  echo "Unsupported architecture: $ARCH" >&2
  exit 1
fi
