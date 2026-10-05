#!/bin/bash
# Shim: plain `podman` -> renamed binary (AppArmor path bypass on s390x).
# On s390x, translate --userns=keep-id to --userns=host (LXD blocks
# user-namespace mapping there: crun "write to gid_map: Operation not
# permitted"); rootful identity mapping either way. See the Dockerfile
# header comment.
if [ "$(uname -m)" = "s390x" ]; then
  args=()
  for a in "$@"; do
    if [ "$a" = "--userns=keep-id" ]; then
      args+=("--userns=host")
    else
      args+=("$a")
    fi
  done
  set -- "${args[@]}"
fi
exec /usr/bin/podman-build "$@"
