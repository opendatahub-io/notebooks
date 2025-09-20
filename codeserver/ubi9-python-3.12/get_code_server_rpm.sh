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
	export NODE_VERSION=${NODE_VERSION:-22.18.0}
	export CODESERVER_VERSION=${CODESERVER_VERSION:-v4.104.0}

	export NVM_DIR=/root/.nvm VENV=/opt/.venv
	export PATH=${VENV}/bin:$PATH

	export ELECTRON_SKIP_BINARY_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

	# install build dependencies
	# https://access.redhat.com/support/policy/updates/rhel-app-streams-life-cycle
	# https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/developing_c_and_cpp_applications_in_rhel_9/assembly_additional-toolsets-for-development-rhel-9_developing-applications#cpp-compatibility-in-gcc-toolset-14_gcc-toolset-14
	dnf install -y jq patch libtool rsync gettext gcc-toolset-14 krb5-devel libX11-devel

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
	source ${NVM_DIR}/nvm.sh
	while IFS= read -r src_patch; do echo "patches/$src_patch"; patch -p1 < "patches/$src_patch"; done < patches/series
	nvm use ${NODE_VERSION}
	npm install
	npm run build
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
