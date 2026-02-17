#!/usr/bin/env bash
set -euo pipefail

# rpm-lockfile-generate.sh — Run rpm-lockfile-prototype inside the lockfile container.
#
# Invoked by create-rpm-lockfile.sh inside the notebook-rpm-lockfile container.
# NOT meant to be run directly on the host.
#
# What it does:
#   1. Parse the prefetch-input directory path from arguments.
#   2. Detect OS and subscription-manager registration status.
#   3. If RHEL is registered, enable /etc/yum.repos.d/redhat.repo in rpms.in.yaml
#      (uncomments the line); otherwise use the repo files listed in rpms.in.yaml
#      (ubi.repo, centos.repo, epel.repo).
#   4. Run rpm-lockfile-prototype rpms.in.yaml to generate rpms.lock.yaml.

# Parse arguments: accept positional, named 'prefetch-input=...', or '--prefetch-input=...'
PREFETCH_INPUT_DIR=""
for arg in "$@"; do
    case "$arg" in
        prefetch-input=*|PREFETCH_INPUT_DIR=*)
            PREFETCH_INPUT_DIR="${arg#*=}"
            ;;
        *)
            [[ -z "$PREFETCH_INPUT_DIR" ]] && PREFETCH_INPUT_DIR="$arg"
            ;;
    esac
done

[[ -z "$PREFETCH_INPUT_DIR" ]] && { echo "Usage: $0 prefetch-input=path/to/prefetch-input" >&2; exit 1; }

echo "Using prefetch input directory: $PREFETCH_INPUT_DIR"

if [[ -f /etc/os-release ]]; then
    # shellcheck source=/dev/null
    . /etc/os-release
    OS_NAME="${ID:-unknown}"
    OS_VER="${VERSION_ID:-unknown}"
else
    OS_NAME="unknown"
    OS_VER="unknown"
fi

echo "Detected OS: $OS_NAME $OS_VER"
echo "------------------------------------"

pushd "/workspace/$PREFETCH_INPUT_DIR" >/dev/null
    if command -v subscription-manager &>/dev/null; then
        overall_status=$(subscription-manager status 2>/dev/null | grep "Overall Status" | awk -F': ' '{print $2}' || true)
        echo "System Registration Status: $overall_status"

        if [[ -z "$overall_status" || "${overall_status,,}" == "unknown" ]]; then
            echo "System is NOT registered. Will use the repo file from rpms.in.yaml (e.g. ubi.repo or centos.repo)."
        else
            echo "RHEL is registered; enabling /etc/yum.repos.d/redhat.repo in rpms.in.yaml."
            sed -i 's|#- /etc/yum\.repos\.d/redhat\.repo$|- /etc/yum.repos.d/redhat.repo|' rpms.in.yaml
        fi
    else
        echo "subscription-manager not found. Using repo file from rpms.in.yaml (e.g. ubi.repo, centos.repo)."
    fi

    rpm-lockfile-prototype rpms.in.yaml
    ls -lah ./
popd >/dev/null
