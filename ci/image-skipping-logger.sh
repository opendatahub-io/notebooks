#!/bin/bash

# This helper script is used by notebooks-digest-updater.sh and runtimes-digest-updater.sh 
# to log information about images that were not updated during the execution of the 
# notebooks-digest-updater GitHub Action. 
# The log file it generates is not committed after the digest updater completes only used to poloulate 
# the pull request description. 

SKIPPED_LOG="${SKIPPED_LOG_PATH:-$(pwd)/skipped-images.txt}"

init_skipped_log() {
    mkdir -p "$(dirname "$SKIPPED_LOG")"
}

log_skipped_image() {
    local image_name="$1"
    echo ":x: — No matching sha for $image_name" >> "$SKIPPED_LOG"
}
