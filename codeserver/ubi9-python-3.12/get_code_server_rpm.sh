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

if [[ "$ARCH" == "amd64" || "$ARCH" == "arm64" ||"$ARCH" == "ppc64le" ]]; then

	export MAX_JOBS=${MAX_JOBS:-$(nproc)}
	export NODE_VERSION=${NODE_VERSION:-20}
	export CODESERVER_VERSION=${CODESERVER_VERSION:-v4.98.0}

	export NVM_DIR=/root/.nvm VENV=/opt/.venv
	export PATH=${VENV}/bin:$PATH

	export ELECTRON_SKIP_BINARY_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

	# install build dependencies
	dnf install -y jq patch libtool rsync gettext gcc-toolset-13 krb5-devel libX11-devel

	. /opt/rh/gcc-toolset-13/enable

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
	source ${NVM_DIR}/nvm.sh
	while IFS= read -r src_patch; do echo "patches/$src_patch"; patch -p1 < "patches/$src_patch"; done < patches/series
	# https://github.com/microsoft/vscode/issues/243708#issuecomment-2750733077
	patch -p1 <<'EOF'
diff --git i/package.json w/package.json
index 925462fb087..dfff96eb051 100644
--- code-server.orig/lib/vscode/package.json
+++ code-server/lib/vscode/package.json
@@ -32,7 +32,7 @@
     "watch-extensionsd": "deemon npm run watch-extensions",
     "kill-watch-extensionsd": "deemon --kill npm run watch-extensions",
     "precommit": "node build/hygiene.js",
-    "gulp": "node --max-old-space-size=8192 ./node_modules/gulp/bin/gulp.js",
+    "gulp": "node --max-old-space-size=16384 --optimize-for-size ./node_modules/gulp/bin/gulp.js",
     "electron": "node build/lib/electron",
     "7z": "7z",
     "update-grammars": "node build/npm/update-all-grammars.mjs",
EOF
	nvm use ${NODE_VERSION}
	npm install
	npm run build
	# https://github.com/coder/code-server/pull/7418
	# node: --optimize-for-size is not allowed in NODE_OPTIONS
	export NODE_OPTIONS="--max-old-space-size=16384"
	export TERSER_PARALLEL=2
	VERSION=${CODESERVER_VERSION/v/} npm run build:vscode
	npm run release
	npm run release:standalone

	# build codeserver rpm
	VERSION=${CODESERVER_VERSION/v/} npm run package
	mv release-packages/code-server-${CODESERVER_VERSION/v/}-${ARCH}.rpm /tmp/

else

  # we shall not download rpm for other architectures
  echo "Unsupported architecture: $ARCH" >&2
  exit 1

fi
