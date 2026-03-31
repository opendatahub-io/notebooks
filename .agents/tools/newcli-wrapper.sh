#!/usr/bin/env bash
# newcli-wrapper.sh — Run ProdSec's newcli (newtopia-cli) via uvx on macOS/Linux
#
# Clones the internal GitLab repo if not cached, then runs newcli with all
# required dependencies. Uses uvx --no-config to avoid interference from
# the repo's uv.toml version pin.
#
# Prerequisites:
#   - uv/uvx installed (brew install uv)
#   - VPN access to gitlab.cee.redhat.com (for clone + manifest-box DB download)
#
# Usage:
#   ./newcli-wrapper.sh --help
#   ./newcli-wrapper.sh -vvv -s -e pypi wheel
#   ./newcli-wrapper.sh -vvv -s -e pypi requests | grep notebook
#   ./newcli-wrapper.sh -a odh-workbench-jupyter-minimal-cpu-py312-rhel9
#
# The first run downloads the ~400MB manifest-box SQLite DB. Subsequent runs
# use the cached DB (stored in ~/.local/share/newcli/).
#
# To force a DB refresh, delete the cache:
#   rm -rf ~/.local/share/newcli/

set -Eeuo pipefail

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/newcli-wrapper"
CLONE_DIR="${CACHE_DIR}/newtopia-cli"
REPO_URL="https://gitlab.cee.redhat.com/prodsec-dev/newtopia-cli.git"

# Clone if not cached
if [ ! -d "${CLONE_DIR}/python/newtopia_cli" ]; then
    echo "Cloning newtopia-cli to ${CLONE_DIR}..." >&2
    mkdir -p "${CACHE_DIR}"
    git clone --depth 1 "${REPO_URL}" "${CLONE_DIR}" 2>&1 | tail -1 >&2
fi

exec uvx --no-config \
    --from "${CLONE_DIR}/python/newtopia_cli" \
    --with "${CLONE_DIR}/python/deptopia-client" \
    --with requests \
    --with appdirs \
    --with packageurl-python \
    --with argcomplete \
    newcli "$@"
