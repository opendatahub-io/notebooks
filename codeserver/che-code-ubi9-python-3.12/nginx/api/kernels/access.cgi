#!/bin/bash
echo "Status: 200"
echo "Content-type: application/json"
echo ""

# Primary: kubeflow-activity-tracker extension writes epoch seconds
if [[ -f /tmp/last-activity ]]; then
    LAST_EPOCH=$(cat /tmp/last-activity)
    LAST_ACTIVITY=$(date -d @"$LAST_EPOCH" -Iseconds 2>/dev/null || date -Iseconds)
    NOW=$(date +%s)
    IDLE_SECONDS=$(( NOW - LAST_EPOCH ))
    if [[ $IDLE_SECONDS -gt 60 ]]; then
        STATUS="idle"
    else
        STATUS="busy"
    fi
else
    # Fallback: che-code is running but no activity tracker data yet
    HEALTHZ=$(curl -s --max-time 2 http://localhost:3100/healthz 2>/dev/null)
    if [[ "$HEALTHZ" == "OK" ]]; then
        STATUS="busy"
    else
        STATUS="idle"
    fi
    LAST_ACTIVITY=$(date -Iseconds)
fi

echo "[{\"id\":\"che-code\",\"name\":\"che-code\",\"last_activity\":\"${LAST_ACTIVITY}\",\"execution_state\":\"${STATUS}\",\"connections\":1}]"
