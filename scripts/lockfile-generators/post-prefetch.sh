#!/usr/bin/env bash
set -Eeuo pipefail

# post-prefetch.sh — Move prefetched dependencies off the root partition.
#
# On GHA runners the LVM overlay script (gha_lvm_overlay.sh) allocates
# nearly all free space on / to the build volume, leaving only ~4 GB.
# The prefetch step downloads 2–3 GB of dependencies into cachi2/output/
# on the root partition, which can push / dangerously close to full and
# cause the podman build to fail.
#
# This script relocates cachi2/output/ to the LVM-backed build volume
# (${HOME}/.local/share/containers/) and leaves a symlink behind so that
# the --volume mount in the workflow and Makefile continues to work.
#
# Called automatically by build-notebooks-TEMPLATE.yaml after
# prefetch-all.sh when the script is present and executable.

CACHI2_DIR="cachi2/output"
BUILD_VOLUME="${HOME}/.local/share/containers"
DEST="${BUILD_VOLUME}/cachi2-output"

if [[ ! -d "$CACHI2_DIR" ]]; then
    echo "post-prefetch.sh: no $CACHI2_DIR directory — nothing to do"
    exit 0
fi

if [[ ! -d "$BUILD_VOLUME" ]]; then
    echo "post-prefetch.sh: $BUILD_VOLUME does not exist (not a GHA runner?) — skipping"
    exit 0
fi

echo "post-prefetch.sh: moving $CACHI2_DIR → $DEST to free root partition space"
df -h / | tail -1 | awk '{print "  root before: " $4 " free"}'

mv "$CACHI2_DIR" "$DEST"
ln -s "$DEST" "$CACHI2_DIR"

df -h / | tail -1 | awk '{print "  root after:  " $4 " free"}'
echo "post-prefetch.sh: done"
