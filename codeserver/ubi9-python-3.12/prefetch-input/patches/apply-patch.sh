#!/bin/bash
set -euxo pipefail

##############################################################################
# This script is expected to be run as `root`                                #
# It applies patches and offline fixes to the prefetched code-server source  #
# for all supported architectures (amd64, arm64, ppc64le, s390x).            #
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
    #
    # [RIPGREP] Overwrite @vscode/ripgrep postinstall in the cached npm tarball with our
    # patched version (ripgrep/postinstall.js). When RIPGREP_BINARY_PATH is set (by
    # setup-offline-binaries.sh from the RHOAI Python wheel), the binary is copied from
    # there; otherwise the script falls back to downloading the prebuilt v13.0.0-13.
    RIPGREP_PATCHED="${CODESERVER_SOURCE_PREFETCH}/ripgrep/postinstall.js"
    RIPGREP_TGZ=$(find /cachi2/output/deps/npm -name "*ripgrep*.tgz" -type f 2>/dev/null | head -1)
    if [[ -n "${RIPGREP_TGZ}" && -f "${RIPGREP_PATCHED}" ]]; then
        echo "Patching @vscode/ripgrep: overwrite with ${RIPGREP_PATCHED}"
        tmpdir=$(mktemp -d)
        tar xzf "${RIPGREP_TGZ}" -C "$tmpdir"
        cp "${RIPGREP_PATCHED}" "$tmpdir/package/lib/postinstall.js"
        tar czf "${RIPGREP_TGZ}" -C "$tmpdir" package
        rm -rf "$tmpdir"
        # Strip integrity so npm accepts the modified tarball (lib/vscode, remote, and build all depend on @vscode/ripgrep).
        for lock in lib/vscode/package-lock.json lib/vscode/remote/package-lock.json lib/vscode/build/package-lock.json; do
            jq 'del(.packages["node_modules/@vscode/ripgrep"].integrity)' "$lock" > /tmp/lock-ripgrep.json && mv /tmp/lock-ripgrep.json "$lock"
        done
    elif [[ -z "${RIPGREP_TGZ}" ]]; then
        echo "WARNING: @vscode/ripgrep tarball not found in /cachi2/output/deps/npm/"
    elif [[ ! -f "${RIPGREP_PATCHED}" ]]; then
        echo "WARNING: ripgrep postinstall not found at ${RIPGREP_PATCHED}"
    fi

    # [AGENT-BROWSER] Overwrite agent-browser postinstall in the cached npm tarball.
    # The npm tarball bundles native binaries for linux-x64/arm64 only; ppc64le/s390x
    # are missing. Upstream postinstall then downloads from GitHub releases (not npm),
    # which fails in hermetic builds. arm64/amd64 succeed because the bundled binary
    # is found before any download is attempted.
    AGENT_BROWSER_PATCHED="${CODESERVER_SOURCE_PREFETCH}/agent-browser/postinstall.js"
    AGENT_BROWSER_TGZ=$(find /cachi2/output/deps/npm -name "agent-browser-*.tgz" -type f 2>/dev/null | head -1)
    if [[ -n "${AGENT_BROWSER_TGZ}" && -f "${AGENT_BROWSER_PATCHED}" ]]; then
        echo "Patching agent-browser: overwrite with ${AGENT_BROWSER_PATCHED}"
        tmpdir=$(mktemp -d)
        tar xzf "${AGENT_BROWSER_TGZ}" -C "$tmpdir"
        cp "${AGENT_BROWSER_PATCHED}" "$tmpdir/package/scripts/postinstall.js"
        tar czf "${AGENT_BROWSER_TGZ}" -C "$tmpdir" package
        rm -rf "$tmpdir"
        jq 'del(.packages["node_modules/agent-browser"].integrity)' \
            lib/vscode/package-lock.json > /tmp/lock-agent-browser.json \
            && mv /tmp/lock-agent-browser.json lib/vscode/package-lock.json
    elif [[ -z "${AGENT_BROWSER_TGZ}" ]]; then
        echo "WARNING: agent-browser tarball not found in /cachi2/output/deps/npm/"
    elif [[ ! -f "${AGENT_BROWSER_PATCHED}" ]]; then
        echo "WARNING: agent-browser postinstall not found at ${AGENT_BROWSER_PATCHED}"
    fi

    # [@parcel/watcher] Hermetic builds prefetch @parcel/watcher-linux-* optional deps.
    # GHA also disables build_from_source via tweak-gha.sh (lib/vscode .npmrc) and
    # npm_config_build_from_source=false in codeserver-offline-env.sh. Belt-and-suspenders:
    # replace the install script with a no-op in the cached tarball and skip scripts in lockfiles.
    patch_parcel_watcher_lock() {
        local lock="$1"
        [[ -f "$lock" ]] || return 0
        jq '
            (.packages["node_modules/@parcel/watcher"].hasInstallScript = false) |
            del(.packages["node_modules/@parcel/watcher"].integrity)
        ' "$lock" > /tmp/lock-parcel.json && mv /tmp/lock-parcel.json "$lock"
    }
    for lock in \
        custom-packages/package-lock.json \
        lib/vscode/package-lock.json \
        lib/vscode/remote/package-lock.json \
        lib/vscode/extensions/package-lock.json; do
        patch_parcel_watcher_lock "$lock"
    done
    PARCEL_TGZ=$(find /cachi2/output/deps/npm -name 'parcel-watcher-2.5.6.tgz' -type f 2>/dev/null | head -1)
    if [[ -n "${PARCEL_TGZ}" ]]; then
        echo "Patching @parcel/watcher: no-op install script (${PARCEL_TGZ})"
        tmpdir=$(mktemp -d)
        tar xzf "${PARCEL_TGZ}" -C "$tmpdir"
        jq '.scripts.install = "node -e \"process.exit(0)\""' "$tmpdir/package/package.json" \
            > /tmp/pkg-parcel.json && mv /tmp/pkg-parcel.json "$tmpdir/package/package.json"
        tar czf "${PARCEL_TGZ}" -C "$tmpdir" package
        rm -rf "$tmpdir"
    else
        echo "WARNING: @parcel/watcher tarball not found in /cachi2/output/deps/npm/"
    fi

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
    while IFS= read -r src_patch || [[ -n "$src_patch" ]]; do
        [[ -z "$src_patch" ]] && continue
        echo "patches/$src_patch"
        patch -p1 < "patches/$src_patch"
    done < patches/series
    npm cache clean --force

    # GitHub Actions runners (16GB RAM) need reduced build parallelism.
    # GHA_BUILD is passed from the Dockerfile ARG, set only in the GHA workflow.
    if [[ "${GHA_BUILD:-false}" == "true" ]]; then
        "${CODESERVER_SOURCE_CODE}/patches/tweak-gha.sh"
    fi
else
  echo "Unsupported architecture: $ARCH" >&2
  exit 1
fi
