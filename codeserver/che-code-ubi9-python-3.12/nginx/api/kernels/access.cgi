#!/bin/bash
set -euo pipefail

echo "Status: 200"
echo "Content-type: application/json"
echo ""

VALID_ACTIVITY=false

# Primary: kubeflow-activity-tracker extension writes epoch seconds
if [[ -f /tmp/last-activity ]]; then
    LAST_EPOCH=$(cat /tmp/last-activity || echo "")
    NOW=$(date +%s)
    # Accept only numeric values that are plausible epoch seconds (not in the future, not before 2020)
    if [[ "$LAST_EPOCH" =~ ^[0-9]+$ ]] && (( LAST_EPOCH > 1577836800 && LAST_EPOCH <= NOW )); then
        VALID_ACTIVITY=true
        LAST_ACTIVITY=$(date -d @"$LAST_EPOCH" -Iseconds 2>/dev/null || date -Iseconds)
        IDLE_SECONDS=$(( NOW - LAST_EPOCH ))
        if (( IDLE_SECONDS > 60 )); then
            STATUS="idle"
        else
            STATUS="busy"
        fi
    fi
fi

# Fallback: invalid/missing activity file — check if che-code is alive
if [[ "$VALID_ACTIVITY" == "false" ]]; then
    HEALTHZ=$(curl -s --max-time 2 http://localhost:3100/healthz 2>/dev/null || true)
    if [[ "${HEALTHZ:-}" == "OK" ]]; then
        STATUS="busy"
    else
        STATUS="idle"
    fi
    LAST_ACTIVITY=$(date -Iseconds)
fi

echo "[{\"id\":\"che-code\",\"name\":\"che-code\",\"last_activity\":\"${LAST_ACTIVITY}\",\"execution_state\":\"${STATUS}\",\"connections\":1}]"
