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

# Parse arguments: accept env var (from create-rpm-lockfile.sh), positional,
# named 'prefetch-input=...', or '--prefetch-input=...'
PREFETCH_INPUT_DIR="${PREFETCH_INPUT_DIR:-}"
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

# Set module_platform_id so DNF can resolve modular streams (e.g. nodejs:22).
# The patch in Dockerfile.rpm-lockfile reads this from the environment.
export RPM_LOCKFILE_MODULE_PLATFORM_ID="platform:el${OS_VER%%.*}"
echo "RPM_LOCKFILE_MODULE_PLATFORM_ID=$RPM_LOCKFILE_MODULE_PLATFORM_ID"

# Ensure the EPEL GPG key exists (needed by repos/epel.repo gpgcheck)
EPEL_KEY="/etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-9"
if [[ ! -f "$EPEL_KEY" ]]; then
    mkdir -p "$(dirname "$EPEL_KEY")"
    curl -sL "https://dl.fedoraproject.org/pub/epel/RPM-GPG-KEY-EPEL-${OS_VER%%.*}" -o "$EPEL_KEY"
    echo "Downloaded EPEL GPG key to $EPEL_KEY"
fi

pushd "/workspace/$PREFETCH_INPUT_DIR" >/dev/null
    if command -v subscription-manager &>/dev/null; then
        overall_status=$(subscription-manager status 2>/dev/null | grep "Overall Status" | awk -F': ' '{print $2}' || true)
        echo "System Registration Status: $overall_status"

        # RHOAI/AIPCC runtime images use RHEL 9.6 EUS repos (baseos/appstream/CRB).
        # Without EUS enabled, rpm-lockfile-prototype resolves system RPMs like python3
        # from the older non-EUS dist channel (el9_6.2) instead of EUS (el9_6.6).
        basearch=$(rpm --eval '%{_arch}')
        echo "Enabling RHEL 9.6 EUS repos (match AIPCC/RHOAI base images)..."
        for repo in \
            "rhel-9-for-${basearch}-baseos-eus-rpms" \
            "rhel-9-for-${basearch}-appstream-eus-rpms" \
            "codeready-builder-for-rhel-9-${basearch}-eus-rpms"; do
            subscription-manager repos --enable="$repo" 2>/dev/null || true
        done

        # Layered-product repos for openshift-clients and texlive-tcolorbox (also set in
        # Dockerfile.rpm-lockfile at image build time; re-enable here for cached images).
        dnf config-manager --set-enabled "rhocp-4.16-for-rhel-9-${basearch}-rpms" 2>/dev/null || true
        dnf config-manager --set-enabled "rhelai-3.3-for-rhel-9-${basearch}-rpms" 2>/dev/null || true

        # subscription-manager generates redhat.repo with literal x86_64
        # in URLs (e.g. .../9.6/x86_64/appstream/os). For multi-arch
        # resolution, replace with $basearch so each architecture solver
        # fetches the correct repo metadata from CDN.
        REDHAT_REPO="/etc/yum.repos.d/redhat.repo"
        if [[ -f "$REDHAT_REPO" ]]; then
            sed -i 's|/x86_64/|/$basearch/|g' "$REDHAT_REPO"
            echo "Rewrote redhat.repo: x86_64 -> \$basearch"
        fi

        # Some RHEL layered-product repos return 403 for non-x86_64 arches
        export RPM_LOCKFILE_SKIP_UNAVAILABLE=1
    else
        echo "subscription-manager not found. Using repo file from rpms.in.yaml (e.g. ubi.repo, centos.repo)."
    fi

    RPM_LOCKFILE_SKIP_UNAVAILABLE="${RPM_LOCKFILE_SKIP_UNAVAILABLE:-0}" \
    rpm-lockfile-prototype rpms.in.yaml
    ls -lah ./
popd >/dev/null
