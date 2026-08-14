#!/usr/bin/env bash
#
# Watch cluster-bot launch Prow logs and record a provisioning state machine.
# Parses openshift/release multi-stage "launch" workflow steps for progress and deviations.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PASS=""
BENCH_ROOT="${REPO_ROOT}/.cluster-bot-bench"
CLUSTER_TYPE=""
PROW_URL=""
PROW_JOB=""
PROW_ID=""
POLL_INTERVAL=30
WATCH=false
ONCE=false
QUIET=false

# Ordered launch-aws-modern steps (ipi-aws-pre + ipi-install tail). Deviations if
# a step appears out of order or a known step fails.
EXPECTED_STEPS=(
    launch-ipi-conf
    launch-ipi-conf-telemetry
    launch-ipi-conf-aws
    launch-ipi-conf-aws-byo-ipv4-pool-public
    launch-ipi-install-monitoringpvc
    launch-ipi-conf-aws-user-min-permissions
    launch-aws-provision-iam-user
    launch-rhcos-conf-osstream
    launch-ipi-install-rbac
    launch-openshift-cluster-bot-rbac
    launch-ipi-install-hosted-loki
    launch-ipi-install-install
    launch-ipi-install-times-collection
    launch-nodes-readiness
    launch-multiarch-validate-nodes
    launch-openshift-tests-extension-admission-crd-install
)

usage() {
    cat <<'EOF'
Usage: cluster-bot-prow-watch.sh --pass a|b [options]

Watch Prow build logs from cluster-bot launch/rosa jobs. Records state transitions
to <bench-root>/<pass>/prow_states.jsonl and key events to timings.jsonl.

Options:
  --pass a|b
  --prow-url URL          e.g. https://prow.ci.openshift.org/view/gs/.../2086024205236703232
  --prow-job JOB          release-openshift-origin-installer-launch-aws-modern
  --prow-id ID            2086024205236703232
  --bench-root PATH
  --cluster-type launch|rosa
  --poll-interval SEC     Default: 30 (log tail poll, not Slack)
  --watch                 Loop until job complete or failed
  --once                  Fetch log once, emit state, exit
  --quiet                 Less console output during --watch
  -h, --help

Macro states (derived):
  importing_release, acquiring_leases, phase_pre, installer_running,
  nodes_readiness, post_install, job_succeeded, job_failed

Examples:
  ./scripts/cluster-bot-prow-watch.sh --pass a --once \
    --prow-url 'https://prow.ci.openshift.org/view/gs/test-platform-results/logs/release-openshift-origin-installer-launch-aws-modern/2086024205236703232'

  ./scripts/cluster-bot-prow-watch.sh --pass a --watch --poll-interval 30 \
    --prow-job release-openshift-origin-installer-launch-aws-modern \
    --prow-id 2086024205236703232
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pass)
            PASS="${2:-}"
            shift 2
            ;;
        --prow-url)
            PROW_URL="${2:-}"
            shift 2
            ;;
        --prow-job)
            PROW_JOB="${2:-}"
            shift 2
            ;;
        --prow-id)
            PROW_ID="${2:-}"
            shift 2
            ;;
        --bench-root)
            BENCH_ROOT="${2:-}"
            shift 2
            ;;
        --cluster-type)
            CLUSTER_TYPE="${2:-}"
            shift 2
            ;;
        --poll-interval)
            POLL_INTERVAL="${2:-}"
            shift 2
            ;;
        --watch)
            WATCH=true
            shift
            ;;
        --once)
            ONCE=true
            shift
            ;;
        --quiet)
            QUIET=true
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "${PASS}" ]]; then
    echo "error: --pass is required" >&2
    exit 1
fi

if [[ -z "${CLUSTER_TYPE}" ]]; then
    if [[ "${PASS}" == "a" ]]; then
        CLUSTER_TYPE="launch"
    else
        CLUSTER_TYPE="rosa"
    fi
fi

PASS_DIR="${BENCH_ROOT}/${PASS}"
STATES="${PASS_DIR}/prow_states.jsonl"
TIMINGS="${PASS_DIR}/timings.jsonl"
OFFSET_FILE="${PASS_DIR}/prow_log.offset"
SEEN_STEPS_FILE="${PASS_DIR}/prow_seen_steps.txt"
PROW_ENV="${PASS_DIR}/prow_job.env"
mkdir -p "${PASS_DIR}"

parse_prow_url() {
    local url="$1"
    if [[ "${url}" =~ /logs/([^/]+)/([0-9]+) ]]; then
        PROW_JOB="${BASH_REMATCH[1]}"
        PROW_ID="${BASH_REMATCH[2]}"
        return 0
    fi
    echo "error: cannot parse prow job/id from URL: ${url}" >&2
    return 1
}

if [[ -n "${PROW_URL}" ]]; then
    parse_prow_url "${PROW_URL}"
fi

if [[ -z "${PROW_JOB}" || -z "${PROW_ID}" ]]; then
    if [[ -f "${PROW_ENV}" ]]; then
        # shellcheck source=/dev/null
        source "${PROW_ENV}"
    else
        echo "error: need --prow-url or --prow-job + --prow-id (or ${PROW_ENV})" >&2
        exit 1
    fi
fi

LOG_URL="https://prow.ci.openshift.org/log?job=${PROW_JOB}&id=${PROW_ID}"
VIEW_URL="https://prow.ci.openshift.org/view/gs/test-platform-results/logs/${PROW_JOB}/${PROW_ID}"

cat >"${PROW_ENV}" <<EOF
PROW_JOB=${PROW_JOB}
PROW_ID=${PROW_ID}
PROW_LOG_URL=${LOG_URL}
PROW_VIEW_URL=${VIEW_URL}
EOF

now_iso() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

now_epoch() {
    date +%s
}

bench_elapsed() {
    local bench_start="${PASS_DIR}/bench_start_epoch"
    if [[ -f "${bench_start}" ]]; then
        echo $(( $(now_epoch) - $(cat "${bench_start}") ))
    else
        echo 0
    fi
}

dedup_append_state() {
    local kind="$1" state="$2" detail="${3:-}"
    local key="${kind}:${state}:${detail}"
    if [[ -f "${PASS_DIR}/prow_seen_states.txt" ]] && grep -qxF "${key}" "${PASS_DIR}/prow_seen_states.txt"; then
        return 0
    fi
    echo "${key}" >>"${PASS_DIR}/prow_seen_states.txt"
    append_state "${kind}" "${state}" "${detail}"
}

append_state() {
    local kind="$1"
    local state="$2"
    local detail="${3:-}"
    local elapsed
    elapsed="$(bench_elapsed)"
    if [[ -n "${detail}" ]]; then
        printf '{"kind":"%s","state":"%s","pass":"%s","cluster_type":"%s","ts":"%s","elapsed_sec":%s,"detail":"%s","prow_job":"%s","prow_id":"%s"}\n' \
            "${kind}" "${state}" "${PASS}" "${CLUSTER_TYPE}" "$(now_iso)" "${elapsed}" "${detail}" "${PROW_JOB}" "${PROW_ID}" >>"${STATES}"
    else
        printf '{"kind":"%s","state":"%s","pass":"%s","cluster_type":"%s","ts":"%s","elapsed_sec":%s,"prow_job":"%s","prow_id":"%s"}\n' \
            "${kind}" "${state}" "${PASS}" "${CLUSTER_TYPE}" "$(now_iso)" "${elapsed}" "${PROW_JOB}" "${PROW_ID}" >>"${STATES}"
    fi
    if [[ -f "${TIMINGS}" ]]; then
        if [[ -n "${detail}" ]]; then
            printf '{"event":"prow_%s","pass":"%s","cluster_type":"%s","ts":"%s","elapsed_sec":%s,"detail":"%s"}\n' \
                "${kind}" "${PASS}" "${CLUSTER_TYPE}" "$(now_iso)" "${elapsed}" "${detail}" >>"${TIMINGS}"
        else
            printf '{"event":"prow_%s","pass":"%s","cluster_type":"%s","ts":"%s","elapsed_sec":%s,"state":"%s"}\n' \
                "${kind}" "${PASS}" "${CLUSTER_TYPE}" "$(now_iso)" "${elapsed}" "${state}" >>"${TIMINGS}"
        fi
    fi
}

step_index() {
    local step="$1"
    local i
    for i in "${!EXPECTED_STEPS[@]}"; do
        if [[ "${EXPECTED_STEPS[$i]}" == "${step}" ]]; then
            echo "${i}"
            return 0
        fi
    done
    echo -1
}

macro_for_step() {
    case "$1" in
        launch-ipi-install-install)
            echo "installer_running"
            ;;
        launch-nodes-readiness)
            echo "nodes_readiness"
            ;;
        launch-ipi-install-times-collection | launch-multiarch-validate-nodes | launch-openshift-tests-extension-admission-crd-install)
            echo "post_install"
            ;;
        *)
            echo "phase_pre"
            ;;
    esac
}

strip_ansi() {
    printf '%s' "${1}" | sed -E 's/\x1B\[([0-9]{1,2}(;[0-9]{1,2})*)?[mGK]//g'
}

fetch_log_chunk() {
    local offset="${1:-0}"
    curl -sfL "${LOG_URL}" | tail -c +$((offset + 1)) 2>/dev/null || true
}

process_log_lines() {
    local chunk="$1"
    local clean
    clean="$(strip_ansi "${chunk}")"

    if [[ "${clean}" == *"Importing release"* && "${clean}" == *"to tag release:latest"* ]]; then
        dedup_append_state "macro" "importing_release" "release_import_started"
    fi
    if [[ "${clean}" == *"Acquiring leases for test launch"* ]]; then
        dedup_append_state "macro" "acquiring_leases"
    fi
    if [[ "${clean}" == *"Running multi-stage phase pre"* ]]; then
        dedup_append_state "macro" "phase_pre"
    fi
    if [[ "${clean}" == *"Running multi-stage phase post"* ]]; then
        dedup_append_state "macro" "phase_post"
    fi

    local line step duration macro idx
    while IFS= read -r line; do
        step="$(printf '%s' "${line}" | sed -n 's/.*Running step launch-\([^ ]*\).*/\1/p' | sed 's/\.$//')"
        if [[ -z "${step}" ]]; then
            continue
        fi
        step="launch-${step}"
        if ! grep -qx "${step}" "${SEEN_STEPS_FILE}" 2>/dev/null; then
            echo "${step}" >>"${SEEN_STEPS_FILE}"
            macro="$(macro_for_step "${step}")"
            idx="$(step_index "${step}")"
            dedup_append_state "step_start" "${step}" "index=${idx} macro=${macro}"
            dedup_append_state "macro" "${macro}" "step=${step}"
        fi
    done < <(grep -E 'Running step launch-' <<<"${clean}" || true)

    while IFS= read -r line; do
        step="$(printf '%s' "${line}" | sed -n 's/.*Step launch-\([^ ]*\) succeeded after \(.*\)\./\1/p')"
        duration="$(printf '%s' "${line}" | sed -n 's/.*Step launch-\([^ ]*\) succeeded after \(.*\)\./\2/p')"
        if [[ -n "${step}" ]]; then
            dedup_append_state "step_done" "launch-${step}" "duration=${duration}"
        fi
    done < <(grep -E 'Step launch-.* succeeded after' <<<"${clean}" || true)

    while IFS= read -r line; do
        step="$(printf '%s' "${line}" | sed -n 's/.*Step launch-\([^ ]*\) failed.*/\1/p')"
        if [[ -n "${step}" ]]; then
            dedup_append_state "deviation" "step_failed" "launch-${step}"
            dedup_append_state "macro" "job_failed" "launch-${step}"
        fi
    done < <(grep -E 'Step launch-.* failed' <<<"${clean}" || true)

    if grep -q 'BUILD FAILURE\|FAILED' <<<"${clean}"; then
        dedup_append_state "deviation" "build_failure" "matched_FAILURE_pattern"
    fi
    if grep -q 'cluster failed to start' <<<"${clean}"; then
        dedup_append_state "deviation" "cluster_failed"
        dedup_append_state "macro" "job_failed"
    fi
}

current_progress() {
    local completed total pct current current_since running
    completed="$(grep -c '"kind":"step_done"' "${STATES}" 2>/dev/null || echo 0)"
    total="${#EXPECTED_STEPS[@]}"
    pct=0
    if [[ "${total}" -gt 0 ]]; then
        pct=$((completed * 100 / total))
    fi
    running="$(grep '"kind":"step_start"' "${STATES}" 2>/dev/null | tail -1 | sed -n 's/.*"state":"\([^"]*\)".*/\1/p' | sed 's/\.$//' || true)"
    current_since="$(grep '"kind":"step_start"' "${STATES}" 2>/dev/null | tail -1 | sed -n 's/.*"ts":"\([^"]*\)".*/\1/p' || true)"
    if [[ -z "${running}" ]]; then
        current="unknown"
    elif grep '"kind":"step_done"' "${STATES}" 2>/dev/null | grep -q "\"state\":\"${running}\""; then
        current="${running} (done)"
    else
        current="${running} (running)"
    fi
    printf 'progress=%d%% steps_done=%d/%d current=%s current_since=%s elapsed_sec=%s prow=%s\n' \
        "${pct}" "${completed}" "${total}" "${current}" "${current_since}" "$(bench_elapsed)" "${VIEW_URL}"
}

analyze_once() {
    touch "${SEEN_STEPS_FILE}"
    local offset=0
    if [[ -f "${OFFSET_FILE}" ]]; then
        offset="$(cat "${OFFSET_FILE}")"
    fi
    local chunk
    chunk="$(fetch_log_chunk "${offset}")"
    local new_offset
    new_offset=$((offset + ${#chunk}))
    echo "${new_offset}" >"${OFFSET_FILE}"
    if [[ -n "${chunk}" ]]; then
        process_log_lines "${chunk}"
    fi
    if [[ "${QUIET}" != "true" ]]; then
        current_progress
    fi
}

job_terminal() {
    if grep '"kind":"macro"' "${STATES}" 2>/dev/null | grep -q '"state":"job_succeeded"'; then
        return 0
    fi
    if grep '"kind":"macro"' "${STATES}" 2>/dev/null | grep -q '"state":"job_failed"'; then
        return 0
    fi
    if grep '"kind":"step_done"' "${STATES}" 2>/dev/null | grep -q 'launch-nodes-readiness'; then
        return 0
    fi
    return 1
}

if [[ "${ONCE}" == "true" || "${WATCH}" != "true" ]]; then
    analyze_once
    if [[ "${WATCH}" != "true" ]]; then
        exit 0
    fi
fi

echo "Watching ${LOG_URL} every ${POLL_INTERVAL}s → ${STATES}"
while true; do
    analyze_once
    if job_terminal; then
        current_progress
        echo "Prow watch: terminal state reached."
        exit 0
    fi
    sleep "${POLL_INTERVAL}"
done
