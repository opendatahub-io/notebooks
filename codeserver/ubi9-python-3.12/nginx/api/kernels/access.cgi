#!/bin/bash
# CGI shim for the notebook controller culler.
#
# Code-Server has no Jupyter-compatible /api/kernels/ API. Apache (httpd) invokes
# this script for that path; it polls code-server's /healthz heartbeat and returns
# a single synthetic kernel record the culler can parse.
#
# Expected output shape (Jupyter kernels API):
#   [{"id":"...","name":"...","last_activity":"<RFC3339>","execution_state":"busy|idle","connections":1}]

# --- CGI response headers (required before any body output) ---
echo "Status: 200"
echo "Content-type: application/json"
echo

# --- Fetch code-server heartbeat ---
# Poll through nginx on 8888 using the same probe path as notebook-controller:
#   ${NB_PREFIX}/api  ->  ${NB_PREFIX}/codeserver/healthz/
# A bare /codeserver/healthz curl fails when NB_PREFIX is set because nginx only
# routes prefixed /codeserver/* to code-server. -L follows the probe redirect chain.
NB_PREFIX="${NB_PREFIX:-}"
HEALTHZ=$(curl -sL "http://localhost:8888${NB_PREFIX}/api")
# Example HEALTHZ JSON: {"status":"alive","lastHeartbeat":1742345025123}

# --- Derive last_activity (RFC3339 / ISO 8601) ---
# lastHeartbeat is milliseconds since epoch. The culler expects seconds in ISO format.
# On a fresh pod, code-server reports lastHeartbeat=0 until the first user interaction;
# date -d @0 would work but misleads the culler, so we use the current time instead
# (consistent with the initial entry written in run-code-server.sh).
LAST_HEARTBEAT_MS=$(echo "$HEALTHZ" | grep -Po 'lastHeartbeat":\K[0-9]+')
if [ -z "$LAST_HEARTBEAT_MS" ] || [ "$LAST_HEARTBEAT_MS" = "0" ]; then
    LAST_ACTIVITY=$(date -Iseconds)
else
    LAST_ACTIVITY=$(date -d "@$((LAST_HEARTBEAT_MS / 1000))" -Iseconds)
fi

# --- Map code-server status to Jupyter execution_state ---
# code-server uses alive/expired; the culler expects busy/idle (Jupyter kernel terms).
STATUS=$(sed 's/alive/busy/;s/expired/idle/' <<< "$(echo "$HEALTHZ" | grep -Po 'status":"\K.*?(?=")')")

# --- Emit synthetic kernel list (always one entry for the IDE session) ---
echo '[{"id":"code-server","name":"code-server","last_activity":"'"$LAST_ACTIVITY"'","execution_state":"'"$STATUS"'","connections":1}]'
