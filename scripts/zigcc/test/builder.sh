#!/usr/bin/env bash
set -Eeuxo pipefail

podman build --tag cross --target arm64-sysroot -f /Users/jdanek/IdeaProjects/notebooks/scripts/zigcc/test/Dockerfile.crosscompiler
#container build --tag cross --target arm64-sysroot -f /Users/jdanek/IdeaProjects/notebooks/scripts/zigcc/test/Dockerfile.crosscompiler

# container build --tag cross --target arm64-sysroot -f /Users/jdanek/IdeaProjects/notebooks/scripts/zigcc/test/Dockerfile.crosscompiler
#⠦ [1/3] Fetching BuildKit image 4% (5 of 10 blobs, 4.6/99.6 MB, 381 KB/s) [8s]
#❯ container build --tag cross --target arm64-sysroot -f /Users/jdanek/IdeaProjects/notebooks/scripts/zigcc/test/Dockerfile.crosscompiler
#⠇ [3/3] Starting BuildKit container [4m 10s]

❯ container build --tag cross --target arm64-sysroot -f /Users/jdanek/IdeaProjects/notebooks/scripts/zigcc/test/Dockerfile.crosscompiler
Error: internalError: "failed to create container" (cause: "internalError: "XPC timeout for request to com.apple.container.apiserver/containerCreate"")



IMAGE=cross

cd /Users/jdanek/IdeaProjects/notebooks/scripts/zigcc/test/root
NAME=$(podman create $IMAGE)
podman cp $NAME:/ .
podman rm $NAME
