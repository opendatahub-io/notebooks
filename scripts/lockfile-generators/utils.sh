#!/bin/bash
set -euo pipefail

# Parse arguments: accept positional, named 'prefetch-input=...', or '--prefetch-input=...'
PREFETCH_INPUT_DIR=""
for arg in "$@"; do
    case "$arg" in
        prefetch-input=*|PREFETCH_INPUT_DIR=*)
            PREFETCH_INPUT_DIR="${arg#*=}"
            ;;
        *)
            if [ -z "$PREFETCH_INPUT_DIR" ]; then
                PREFETCH_INPUT_DIR="$arg"
            fi
            ;;
    esac
done

if [ -z "$PREFETCH_INPUT_DIR" ]; then
    echo "Usage: $0 prefetch-input=path/to/prefetch-input" >&2
    exit 1
fi

echo "Using prefetch input directory: $PREFETCH_INPUT_DIR"

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME=$ID
    OS_VER=$VERSION_ID
else
    OS_NAME="unknown"
    OS_VER="unknown"
fi

echo "Detected OS: $OS_NAME $OS_VER"
echo "------------------------------------"

pushd "/workspace/$PREFETCH_INPUT_DIR"
    # Check if subscription-manager exists
    if command -v subscription-manager &>/dev/null; then
        # Get Overall Status
        overall_status=$(subscription-manager status 2>/dev/null | grep "Overall Status" | awk -F': ' '{print $2}')
        echo "System Registration Status : $overall_status"

        if [[ -z "$overall_status" || "${overall_status,,}" == "unknown" ]]; then
            echo "System is NOT registered"
            echo "Will use the provided rpms.repo file"
        else
            echo "Since this RHEL is registered, we MUST use /etc/yum.repos.d/redhat.repo for rpms.in.yaml"
            sed -i 's|#- /etc/yum\.repos\.d/redhat\.repo$|- /etc/yum\.repos\.d/redhat\.repo|' rpms.in.yaml;
        fi
    else
        # For CentOS, Fedora, Alma, Rocky, etc.
        echo "subscription-manager not found. No Red Hat registration required."
    fi

    # cat rpms.in.yaml
    rpm-lockfile-prototype rpms.in.yaml
    ls -lah ./
popd
