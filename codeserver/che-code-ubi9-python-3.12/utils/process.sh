#!/usr/bin/env bash
set -euo pipefail

PID=""
INTERRUPTED=0

function start_process() {
    trap stop_process TERM INT

    echo "Running command: $*"
    "$@" &

    PID=$!
    if wait "$PID"; then
        STATUS=0
    else
        STATUS=$?
    fi
    trap - TERM INT
    if (( INTERRUPTED )); then
        if wait "$PID"; then
            STATUS=0
        else
            STATUS=$?
        fi
    fi
    exit "$STATUS"
}

function stop_process() {
    INTERRUPTED=1
    if [[ -n "$PID" ]]; then
        kill -TERM "$PID"
    fi
}
