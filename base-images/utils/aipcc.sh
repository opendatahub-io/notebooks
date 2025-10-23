#!/usr/bin/env bash
set -Eeuxo pipefail

DNF_OPTS=(-y --nodocs --setopt=install_weak_deps=False --setopt=keepcache=True)

function install_epel() {
    dnf install "${DNF_OPTS[@]}" https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
}

function uninstall_epel() {
    dnf remove "${DNF_OPTS[@]}" epel-release
}

function main() {
    install_epel
    trap uninstall_epel EXIT

    dnf install "${DNF_OPTS[@]}" zeromq
    if ! test -f /usr/lib64/libzmq.so.5; then
        echo "Error: libzmq.so.5 was not found after installation"
        exit 1
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
