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

	export MAX_JOBS=${MAX_JOBS:-$(nproc)}
	export NODE_VERSION=${NODE_VERSION:-22.18.0}
	export CODESERVER_VERSION=${CODESERVER_VERSION:-v4.104.0}

	export NVM_DIR=/root/.nvm VENV=/opt/.venv
	export PATH=${VENV}/bin:$PATH

	export ELECTRON_SKIP_BINARY_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

	# install build dependencies
	# https://access.redhat.com/support/policy/updates/rhel-app-streams-life-cycle
	# https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/developing_c_and_cpp_applications_in_rhel_9/assembly_additional-toolsets-for-development-rhel-9_developing-applications#cpp-compatibility-in-gcc-toolset-14_gcc-toolset-14
	#dnf install -y jq patch libtool rsync gettext gcc-toolset-14 gcc-toolset-14-libatomic-devel krb5-devel libX11-devel

	# starting with node-22, c++20 is required
	. /opt/rh/gcc-toolset-14/enable

	# build libxkbfile
	export UTIL_MACROS_VERSION=1.20.2
	tar -xzf /cachi2/output/deps/generic/util-macros-${UTIL_MACROS_VERSION}.tar.gz
	cd util-macros-${UTIL_MACROS_VERSION}/
	./configure --prefix=/usr && make install -j ${MAX_JOBS}
	cd .. && rm -rf util-macros-${UTIL_MACROS_VERSION}/

	export X_KB_FILE_VERSION=1.1.3
	tar -xzf /cachi2/output/deps/generic/libxkbfile-${X_KB_FILE_VERSION}.tar.gz
	cd libxkbfile-${X_KB_FILE_VERSION}/
	./configure --prefix=/usr && make install -j ${MAX_JOBS}
	cd .. && rm -rf libxkbfile-${X_KB_FILE_VERSION}/
    export PKG_CONFIG_PATH=$(find / -type d -name "pkgconfig" 2>/dev/null | tr '\n' ':')

	# install nfpm to build rpm
	#NFPM_VERSION=$(curl -s "https://api.github.com/repos/goreleaser/nfpm/releases/latest" | jq -r '.tag_name') \
	#NFPM_VERSION="v2.44.1" && dnf install -y https://github.com/goreleaser/nfpm/releases/download/${NFPM_VERSION}/nfpm-${NFPM_VERSION:1}-1.$(uname -m).rpm
	dnf install -y /cachi2/output/deps/generic/nfpm-2.44.1-1.$(uname -m).rpm


	# install node
	#NVM_VERSION="v0.40.3" && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash \
	#    && source ${NVM_DIR}/nvm.sh && nvm install ${NODE_VERSION}
	# bash /cachi2/output/deps/generic/nvm-install.sh
	# source ${NVM_DIR}/nvm.sh
	# nvm install ${NODE_VERSION}

	#dnf install -y nodejs

	# build codeserver
	#git clone --depth 1 --branch "${CODESERVER_VERSION}" --recurse-submodules --shallow-submodules https://github.com/coder/code-server.git
	#
	## Mine
	# unzip -q -o /cachi2/output/deps/generic/${CODESERVER_VERSION}.zip
	# cd code-server-*
	# rm -rf lib/vscode/ # Remove old empty link, replace with actual vscode content
	# unzip -q -o /cachi2/output/deps/generic/vscode.zip -d ./lib/
	# mv lib/vscode-* lib/vscode

	cd /root/code-server
	ls -alh ./
        
#patch taken from vscodium s390x IBM : https://github.com/VSCodium/vscodium/blob/master/patches/linux/reh/s390x/arch-4-s390x-package.json.patch
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
    #ls -alh /cachi2/output/deps/npm/    	
	#source ${NVM_DIR}/nvm.sh
	while IFS= read -r src_patch; do echo "patches/$src_patch"; patch -p1 < "patches/$src_patch"; done < patches/series
	#nvm use ${NODE_VERSION}
	npm cache clean --force


	# export NPM_CACHE=/tmp/npm-cache
	# mkdir -p "$NPM_CACHE"
	# npm cache add /cachi2/output/deps/npm/*.tgz --cache "$NPM_CACHE"
	# ls -alh "$NPM_CACHE"
	# npm ci --offline --cache "$NPM_CACHE" --no-audit --no-fund

	#npm config set cache /cachi2/output/deps/npm/
	# cat /cachi2/cachi2.env
	# source /cachi2/cachi2.env
	# npm install

	# npm run build
	# VERSION=${CODESERVER_VERSION/v/} npm run build:vscode
	# export KEEP_MODULES=1
	# npm run release
	# npm run release:standalone

	# # build codeserver rpm
	# VERSION=${CODESERVER_VERSION/v/} npm run package
	# mv release-packages/code-server-${CODESERVER_VERSION/v/}-${ARCH}.rpm /tmp/

else

  # we shall not download rpm for other architectures
  echo "Unsupported architecture: $ARCH" >&2
  exit 1

fi
