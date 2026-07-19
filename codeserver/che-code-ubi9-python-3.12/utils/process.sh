#!/usr/bin/env bash
set -euo pipefail

PID=""

function start_process() {
    trap stop_process TERM INT

    echo "Running command: $*"
    "$@" &

    PID=$!
    wait "$PID"
    trap - TERM INT
    wait "$PID"
    STATUS=$?
    exit "$STATUS"
}

function stop_process() {
    if [[ -n "$PID" ]]; then
        kill -TERM "$PID"
    fi
}
