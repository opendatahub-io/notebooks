#!/usr/bin/env bash
set -euo pipefail

# apply-patches.sh — Apply local patches to pip-installed Python packages.
#
# Called during the Dockerfile.rpm-lockfile build to patch rpm-lockfile-prototype
# before any lockfile generation runs.

PATCHES_DIR="$(cd "$(dirname "$0")" && pwd)"

# rpm-lockfile-prototype: add module_platform_id and skip_if_unavailable
# support via environment variables (RPM_LOCKFILE_MODULE_PLATFORM_ID,
# RPM_LOCKFILE_SKIP_UNAVAILABLE).
rpm_lockfile_dir=$(/usr/bin/python3 -c "import rpm_lockfile, pathlib; print(pathlib.Path(rpm_lockfile.__file__).parent)")
patch -p1 -d "$rpm_lockfile_dir/.." < "$PATCHES_DIR/rpm-lockfile-prototype-dnf-conf.patch"
echo "Applied rpm-lockfile-prototype-dnf-conf.patch"
