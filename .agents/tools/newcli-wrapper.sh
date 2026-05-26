#!/usr/bin/env bash
# newcli-wrapper.sh — Run ProdSec's newcli (newtopia-cli) via uvx on macOS/Linux
#
# No manual clone needed — uvx fetches directly from GitLab and caches automatically.
#
# Prerequisites:
#   - uv/uvx installed (brew install uv)
#   - VPN access to gitlab.cee.redhat.com (for fetch + manifest-box DB download)
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

REPO="git+https://gitlab.cee.redhat.com/prodsec-dev/newtopia-cli.git"

exec uvx --no-config \
    --from "newtopia-cli @ ${REPO}#subdirectory=python/newtopia_cli" \
    --with "deptopia-client @ ${REPO}#subdirectory=python/deptopia-client" \
    --with requests \
    --with appdirs \
    --with packageurl-python \
    --with argcomplete \
    newcli "$@"