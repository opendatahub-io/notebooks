#!/usr/bin/env bash
set -Eeuxo pipefail

# Verified against dnf 4.14.0 on UBI9/RHEL 9.7 (dnf config-manager --dump)
DNF_OPTS=(
    -y
    --nodocs
    # do not set --noplugins, we do need subscription-manager plugin
    --setopt=install_weak_deps=0
    --setopt=max_parallel_downloads=10
    --setopt=keepcache=0
    --setopt=deltarpm=0
)

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
    upgrade)
        # Problem: The operation would result in removing the following protected packages: systemd
        #  (try to add '--allowerasing' to command line to replace conflicting packages or '--skip-broken' to skip uninstallable packages)
        # Solution: --best --skip-broken does not work either, so use --nobest
        dnf upgrade --refresh --nobest --skip-broken "${DNF_OPTS[@]}" "$@"
        ;;
    install)
        dnf install "${DNF_OPTS[@]}" "$@"
        ;;
    *)
        echo "Usage: $0 {upgrade|install} [packages...]"
        exit 1
        ;;
esac

dnf clean all
rm -rf /var/cache/yum /var/cache/dnf
