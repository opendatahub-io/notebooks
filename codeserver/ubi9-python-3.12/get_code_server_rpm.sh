#!/bin/bash
set -euxo pipefail

##############################################################################
# This script is expected to be run as `root`                                #
# It builds code-server RPM from source for all supported architectures      #
# For ppc64le/s390x: Additional patches and stubs are required               #
##############################################################################


# Mapping of `uname -m` values to equivalent GOARCH values
declare -A UNAME_TO_GOARCH
UNAME_TO_GOARCH["x86_64"]="amd64"
UNAME_TO_GOARCH["aarch64"]="arm64"
UNAME_TO_GOARCH["ppc64le"]="ppc64le"
UNAME_TO_GOARCH["s390x"]="s390x"

ARCH="${UNAME_TO_GOARCH[$(uname -m)]}"

if [[ "$ARCH" == "amd64" || "$ARCH" == "arm64" || "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then
	echo "Building code-server from source for ${ARCH}..."

	export MAX_JOBS=${MAX_JOBS:-$(nproc)}
	export NODE_VERSION=${NODE_VERSION:-22.21.1}
	export CODESERVER_VERSION=${CODESERVER_VERSION:-v4.108.2}

	export NVM_DIR=/root/.nvm VENV=/opt/.venv
	export PATH=${VENV}/bin:$PATH

	export ELECTRON_SKIP_BINARY_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

	# install build dependencies
	# https://access.redhat.com/support/policy/updates/rhel-app-streams-life-cycle
	# https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/developing_c_and_cpp_applications_in_rhel_9/assembly_additional-toolsets-for-development-rhel-9_developing-applications#cpp-compatibility-in-gcc-toolset-14_gcc-toolset-14
	dnf install -y jq patch libtool rsync gettext gcc-toolset-14 gcc-toolset-14-libatomic-devel krb5-devel libX11-devel

	# starting with node-22, c++20 is required
	. /opt/rh/gcc-toolset-14/enable

	# build libxkbfile
	export UTIL_MACROS_VERSION=1.20.2
	curl -L https://www.x.org/releases/individual/util/util-macros-${UTIL_MACROS_VERSION}.tar.gz | tar xz
	cd util-macros-${UTIL_MACROS_VERSION}/
	./configure --prefix=/usr && make install -j ${MAX_JOBS}
	cd .. && rm -rf util-macros-${UTIL_MACROS_VERSION}/

	export X_KB_FILE_VERSION=1.1.3
	curl -L https://www.x.org/releases/individual/lib/libxkbfile-${X_KB_FILE_VERSION}.tar.gz | tar xz
	cd libxkbfile-${X_KB_FILE_VERSION}/
	./configure --prefix=/usr && make install -j ${MAX_JOBS}
	cd .. && rm -rf libxkbfile-${X_KB_FILE_VERSION}/
	export PKG_CONFIG_PATH=$(find / -type d -name "pkgconfig" 2>/dev/null | tr '\n' ':')

	# install nfpm to build rpm
	NFPM_VERSION=$(curl -s "https://api.github.com/repos/goreleaser/nfpm/releases/latest" | jq -r '.tag_name') \
	    && dnf install -y https://github.com/goreleaser/nfpm/releases/download/${NFPM_VERSION}/nfpm-${NFPM_VERSION:1}-1.$(uname -m).rpm

	# install node
	NVM_VERSION=$(curl -s "https://api.github.com/repos/nvm-sh/nvm/releases/latest" | jq -r '.tag_name') \
	    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash \
	    && source ${NVM_DIR}/nvm.sh && nvm install ${NODE_VERSION}

	# build codeserver
	git clone --depth 1 --branch "${CODESERVER_VERSION}" --recurse-submodules --shallow-submodules https://github.com/coder/code-server.git
	cd code-server

	# patch taken from vscodium s390x IBM : https://github.com/VSCodium/vscodium/blob/master/patches/linux/reh/s390x/arch-4-s390x-package.json.patch
	if [[ "$ARCH" == "s390x" ]]; then
cat > s390x.patch <<EOL
diff --git a/lib/vscode/package-lock.json b/lib/vscode/package-lock.json
index 0d0272a92b2..73e8feb92dd 100644
--- a/lib/vscode/package-lock.json
+++ b/lib/vscode/package-lock.json
@@ -18236,10 +18236,11 @@
       }
     },
     "node_modules/web-tree-sitter": {
-      "version": "0.20.8",
-      "resolved": "https://registry.npmjs.org/web-tree-sitter/-/web-tree-sitter-0.20.8.tgz",
-      "integrity": "sha512-weOVgZ3aAARgdnb220GqYuh7+rZU0Ka9k9yfKtGAzEYMa6GgiCzW9JjQRJyCJakvibQW+dfjJdihjInKuuCAUQ==",
-      "dev": true
+      "version": "0.23.0",
+      "resolved": "https://registry.npmjs.org/web-tree-sitter/-/web-tree-sitter-0.23.0.tgz",
+      "integrity": "sha512-p1T+ju2H30fpVX2q5yr+Wv/NfdMMWMjQp9Q+4eEPrHAJpPFh9DPfI2Yr9L1f5SA5KPE+g1cNUqPbpihxUDzmVw==",
+      "dev": true,
+      "license": "MIT"
     },
     "node_modules/webidl-conversions": {
       "version": "3.0.1",
diff --git a/lib/vscode/package.json b/lib/vscode/package.json
index a4c7a2a3a35..d7f816248af 100644
--- a/lib/vscode/package.json
+++ b/lib/vscode/package.json
@@ -227,6 +227,9 @@
     "node-gyp-build": "4.8.1",
     "kerberos@2.1.1": {
       "node-addon-api": "7.1.0"
+    },
+    "@vscode/l10n-dev@0.0.35": {
+      "web-tree-sitter": "0.23.0"
     }
   },
   "repository": {
EOL

		git apply s390x.patch
	fi

	# @vscode/vsce-sign does not support ppc64le/s390x; optionally provide a stub.
	if [[ "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then
		if [[ "${ALLOW_VSCE_SIGN_STUB:-}" != "1" ]]; then
			echo "vsce-sign has no ${ARCH} binary. Set ALLOW_VSCE_SIGN_STUB=1 to use a stub (disables signature verification)." >&2
			exit 1
		fi

		VSCE_SIGN_STUB_DIR="lib/vscode/build/vsce-sign-stub"
		mkdir -p "${VSCE_SIGN_STUB_DIR}/src" "${VSCE_SIGN_STUB_DIR}/bin"
		cat > "${VSCE_SIGN_STUB_DIR}/package.json" <<'EOF'
{
  "name": "@vscode/vsce-sign",
  "version": "0.0.0-stub",
  "main": "src/main.js",
  "bin": {
    "vsce-sign": "bin/vsce-sign"
  },
  "license": "MIT"
}
EOF

		cat > "${VSCE_SIGN_STUB_DIR}/src/main.js" <<'EOF'
'use strict';

const fs = require('fs');
const path = require('path');

const ExtensionSignatureVerificationCode = {
  Success: 'Success',
  UnknownError: 'UnknownError'
};

const ReturnCode = {};
ReturnCode[ReturnCode[ExtensionSignatureVerificationCode.Success] = 0] = ExtensionSignatureVerificationCode.Success;
ReturnCode[ReturnCode[ExtensionSignatureVerificationCode.UnknownError] = 39] = ExtensionSignatureVerificationCode.UnknownError;

class ExtensionSignatureVerificationResult {
  constructor(code, didExecute, internalCode, output) {
    this.code = code;
    this.internalCode = internalCode;
    this.didExecute = didExecute;
    this.output = output;
  }
}

async function verify(_vsixFilePath, _signatureArchiveFilePath, _verbose) {
  return new ExtensionSignatureVerificationResult(
    ExtensionSignatureVerificationCode.Success,
    false,
    0,
    'vsce-sign stub: verification skipped on unsupported architecture'
  );
}

async function generateManifest(vsixFilePath, manifestFilePath, _verbose) {
  const outputPath = manifestFilePath || path.join(path.dirname(vsixFilePath), '.signature.manifest');
  fs.writeFileSync(outputPath, '');
  return outputPath;
}

async function zip(manifestFilePath, _signatureFilePath, signatureArchiveFilePath, _verbose) {
  const outputPath = signatureArchiveFilePath || path.join(path.dirname(manifestFilePath), '.signature.zip');
  fs.writeFileSync(outputPath, '');
  return outputPath;
}

module.exports = {
  verify,
  generateManifest,
  zip,
  ReturnCode,
  ExtensionSignatureVerificationCode,
  ExtensionSignatureVerificationResult
};
EOF

		cat > "${VSCE_SIGN_STUB_DIR}/bin/vsce-sign" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
		chmod +x "${VSCE_SIGN_STUB_DIR}/bin/vsce-sign"

		python3 - <<'PY'
import json
from pathlib import Path

build_pkg = Path("lib/vscode/build/package.json")
data = json.loads(build_pkg.read_text())
overrides = data.get("overrides", {})
overrides["@vscode/vsce-sign"] = "file:vsce-sign-stub"
data["overrides"] = overrides
build_pkg.write_text(json.dumps(data, indent=2) + "\n")
PY
	fi

	source ${NVM_DIR}/nvm.sh
	while IFS= read -r src_patch; do echo "patches/$src_patch"; patch -p1 < "patches/$src_patch"; done < patches/series
	nvm use ${NODE_VERSION}

	# Avoid VS Code build workers hitting default V8 heap limits.
	# Set a high value (16GB) to accommodate the VS Code build which spawns multiple workers.
	# The default V8 heap limit is ~4GB on 64-bit systems.
	export NODE_MAX_OLD_SPACE_SIZE=${NODE_MAX_OLD_SPACE_SIZE:-16384}
	export NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE}"
	
	# Also set via npm config to ensure it propagates to child processes
	npm config set node-options "--max-old-space-size=${NODE_MAX_OLD_SPACE_SIZE}"
	
	# VS Code build uses worker threads that need their own memory limits
	# UV_THREADPOOL_SIZE limits async I/O threads
	# VSCODE_BUILD_WEBVIEW_USE_PROCESS disables problematic webview worker
	export UV_THREADPOOL_SIZE=${UV_THREADPOOL_SIZE:-4}
	
	# Limit gulp/VS Code build concurrency to reduce memory pressure
	# Lower concurrency = fewer workers = less total memory usage
	export JOBS=${JOBS:-2}
	export BUILD_CONCURRENCY=${BUILD_CONCURRENCY:-1}
	export VSCODE_BUILD_CONCURRENCY=${BUILD_CONCURRENCY}
	
	# Disable parallel compilation to reduce memory pressure
	export npm_config_jobs=1
	
	# Configure npm for better network reliability in CI environments
	# Increase timeouts and add retry logic for flaky connections
	npm config set fetch-retries 5
	npm config set fetch-retry-mintimeout 30000
	npm config set fetch-retry-maxtimeout 180000
	npm config set fetch-timeout 600000

	
	echo "=== Build Configuration ==="
	echo "NODE_OPTIONS: ${NODE_OPTIONS}"
	echo "npm node-options: $(npm config get node-options)"
	echo "JOBS: ${JOBS}"
	echo "BUILD_CONCURRENCY: ${BUILD_CONCURRENCY}"
	echo "npm fetch-retries: $(npm config get fetch-retries)"
	echo "npm fetch-timeout: $(npm config get fetch-timeout)"
	echo "==========================="

	npm cache clean --force
	
	# Install with retry logic for network resilience
	MAX_RETRIES=3
	RETRY_COUNT=0
	until npm install || [ $RETRY_COUNT -ge $MAX_RETRIES ]; do
		RETRY_COUNT=$((RETRY_COUNT + 1))
		echo "npm install failed (attempt $RETRY_COUNT/$MAX_RETRIES), retrying in 30 seconds..."
		sleep 30
		npm cache clean --force
	done
	
	if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
		echo "ERROR: npm install failed after $MAX_RETRIES attempts"
		exit 1
	fi
	# Ensure @vscode/vsce-sign is resolvable at runtime for ppc64le/s390x builds.
	if [[ "$ARCH" == "ppc64le" || "$ARCH" == "s390x" ]]; then
		if [[ "${ALLOW_VSCE_SIGN_STUB:-}" == "1" ]]; then
			STUB_NODE_MODULE_DIR="lib/vscode/build/node_modules/@vscode/vsce-sign"
			if [[ ! -d "${STUB_NODE_MODULE_DIR}" ]]; then
				mkdir -p "$(dirname "${STUB_NODE_MODULE_DIR}")"
				cp -R "${VSCE_SIGN_STUB_DIR}" "${STUB_NODE_MODULE_DIR}"
			fi
		fi
	fi
	npm run build
	
	# Build VS Code - this is the memory-intensive step
	# NODE_OPTIONS should propagate to child npm processes
	echo "Building VS Code (memory-intensive step)..."
	VERSION=${CODESERVER_VERSION/v/} npm run build:vscode
	export KEEP_MODULES=1
	npm run release
	npm run release:standalone

	# build codeserver rpm
	VERSION=${CODESERVER_VERSION/v/} npm run package
	mv release-packages/code-server-${CODESERVER_VERSION/v/}-${ARCH}.rpm /tmp/

else
	# Unsupported architecture
	echo "Unsupported architecture: $ARCH" >&2
	exit 1
fi
