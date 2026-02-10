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

    # ppc64le/s390x: patch @vscode/vsce-sign to skip binary download.
    # vsce-sign's postinstall.js downloads platform-specific signing binaries,
    # but no binaries exist for ppc64le/s390x, so the postinstall would fail.
    # We override the package with a patched version that skips on these arches.
    if [[ "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then
        if [[ -n "${VSCE_SIGN_VERSION:-}" ]]; then
            :
        else
            VSCE_SIGN_VERSION=$(node -e "try { const lock=require('./lib/vscode/build/package-lock.json'); console.log(lock?.packages?.['node_modules/@vscode/vsce-sign']?.version || ''); } catch (e) { console.log(''); }")
        fi
        if [[ -z "${VSCE_SIGN_VERSION}" || "${VSCE_SIGN_VERSION}" == "undefined" ]]; then
            echo "VSCE_SIGN_VERSION is required when @vscode/vsce-sign version cannot be read from lib/vscode/build/package-lock.json" >&2
            echo "Set VSCE_SIGN_VERSION to an explicit version (e.g. 2.0.9) to ensure reproducible builds." >&2
            exit 1
        fi
        if [[ ! -f lib/vscode/build/package.json ]]; then
            echo "Missing lib/vscode/build/package.json; cannot apply vsce-sign override" >&2
            exit 1
        fi
        VSCE_SIGN_PATCH_DIR=/tmp/vsce-sign-ppc64le
        rm -rf "${VSCE_SIGN_PATCH_DIR}"
        mkdir -p "${VSCE_SIGN_PATCH_DIR}/src"

        # [HERMETIC] Find vsce-sign tarball in cachi2 npm cache instead of using
        # `npm pack` (which needs network). cachi2 prefetches it as part of
        # lib/vscode/build's npm dependencies.
        VSCE_SIGN_TARBALL=$(find /cachi2/output/deps/npm -name "vsce-sign-${VSCE_SIGN_VERSION}.tgz" -type f 2>/dev/null | head -1)
        if [[ -n "${VSCE_SIGN_TARBALL}" ]]; then
            echo "Found vsce-sign tarball: ${VSCE_SIGN_TARBALL}"
            tar -xzf "${VSCE_SIGN_TARBALL}" -C "${VSCE_SIGN_PATCH_DIR}" --strip-components=1
            if [[ -f "${VSCE_SIGN_PATCH_DIR}/src/postinstall.js" ]]; then
                mv "${VSCE_SIGN_PATCH_DIR}/src/postinstall.js" "${VSCE_SIGN_PATCH_DIR}/src/postinstall.orig.js"
            fi
        else
            echo "WARNING: vsce-sign tarball not found in cachi2 cache, creating minimal override"
            cat > "${VSCE_SIGN_PATCH_DIR}/package.json" <<MINPKG
{"name":"@vscode/vsce-sign","version":"${VSCE_SIGN_VERSION}","scripts":{"postinstall":"node src/postinstall.js"}}
MINPKG
        fi

        cat > "${VSCE_SIGN_PATCH_DIR}/src/postinstall.js" <<'EOL'
const platform = process.platform;
const arch = process.arch;
if (platform === 'linux' && (arch === 'ppc64' || arch === 'ppc64le' || arch === 's390x')) {
  console.warn(`[vsce-sign] Skipping binary install on unsupported architecture: ${platform}-${arch}`);
  process.exit(0);
}
try { require('./postinstall.orig.js'); } catch (e) { console.warn('[vsce-sign] Original postinstall not available, skipping.'); }
EOL

        jq --arg override "file:${VSCE_SIGN_PATCH_DIR}" \
            '.overrides = (.overrides // {}) | .overrides["@vscode/vsce-sign"] = $override' \
            lib/vscode/build/package.json > /tmp/build-package.json \
            && mv /tmp/build-package.json lib/vscode/build/package.json
        echo "Applied vsce-sign override for ${ARCH} (version ${VSCE_SIGN_VERSION})"
    fi

    # apply code-server's own patches to VS Code source
    while IFS= read -r src_patch; do echo "patches/$src_patch"; patch -p1 < "patches/$src_patch"; done < patches/series    
    npm cache clean --force
else
  # we shall not download rpm for other architectures
  echo "Unsupported architecture: $ARCH" >&2
  exit 1
fi
