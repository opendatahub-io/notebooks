#!/usr/bin/env bash
#
# Timed RHOAI 3.4 minimal workbench benchmark for cluster-bot clusters.
# Uses isolated kubeconfig under .cluster-bot-bench/<pass>/ and logs phases to timings.jsonl.
#
# Fixtures: .cursor/skills/cluster-bot/fixtures/
# Recipe:   .cursor/skills/cluster-bot/recipes/rhoai-3.4-minimal-bench.md
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FIXTURES="${REPO_ROOT}/.cursor/skills/cluster-bot/fixtures"

PASS=""
PHASE="all"
BENCH_ROOT="${REPO_ROOT}/.cluster-bot-bench"
CLUSTER_TYPE=""
CREDENTIALS_FILE=""
MARK_EVENT=""
SUMMARY_ONLY=false
POLL_INTERVAL=15
NOTEBOOK_NAME="bench-minimal"
NOTEBOOK_NS="rhods-notebooks"
NOTEBOOK_IMAGE="${NOTEBOOK_IMAGE:-}"
ODS_OPERATOR_NS="redhat-ods-operator"
ODS_APPS_NS="redhat-ods-applications"
OPERATOR_CSV="${OPERATOR_CSV:-}"

usage() {
    cat <<'EOF'
Usage: cluster-bot-rhoai-bench.sh --pass a|b [options]

Options:
  --pass a|b              Benchmark pass (isolated kubeconfig + timings)
  --phase PHASE           all | provision | operator_install | dsc_reconcile |
                          notebook_spawn | workbench_api | uninstall | deprovision |
                          install (operator+dsc+notebook+api) | post-provision
  --bench-root PATH       Default: <repo>/.cluster-bot-bench
  --cluster-type TYPE     Metadata: launch | rosa (default inferred from pass)
  --credentials-file F    API_URL, USER (or USERNAME), PASSWORD for oc login
  --mark-event EVENT      Record timestamp: cluster_request | cluster_credentials |
                          cluster_ready | deprovision_ack | provision_poll
  --poll-interval SEC     oc wait poll interval for nodes/API (default: 15)
  --notebook-image REF    Notebook container image (auto-resolved if unset)
  --summary               Print timing summary from timings.jsonl and exit
  -h, --help              Show this help

Environment:
  KUBECONFIG is set to <bench-root>/<pass>/kubeconfig for cluster phases.

Slack steps (cluster-bot U03GSGSMF38) are outside this script:
  Pass A: list → launch 4.20 aws → ... → done
  Pass B: rosa create 4.20 8h → ... → done

Examples:
  # After sending launch/rosa command in Slack:
  ./scripts/cluster-bot-rhoai-bench.sh --pass a --mark-event cluster_request

  # After auth / kubeconfig or oc login credentials from DM:
  ./scripts/cluster-bot-rhoai-bench.sh --pass a --phase provision \
    --cluster-type launch --credentials-file .cluster-bot-bench/a/credentials.env

  # RHOAI install through workbench API probe:
  ./scripts/cluster-bot-rhoai-bench.sh --pass a --phase install --cluster-type launch

  # Uninstall + summary:
  ./scripts/cluster-bot-rhoai-bench.sh --pass a --phase uninstall
  ./scripts/cluster-bot-rhoai-bench.sh --pass a --summary
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pass)
            PASS="${2:-}"
            shift 2
            ;;
        --phase)
            PHASE="${2:-}"
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
        --credentials-file)
            CREDENTIALS_FILE="${2:-}"
            shift 2
            ;;
        --mark-event)
            MARK_EVENT="${2:-}"
            shift 2
            ;;
        --poll-interval)
            POLL_INTERVAL="${2:-}"
            shift 2
            ;;
        --notebook-image)
            NOTEBOOK_IMAGE="${2:-}"
            shift 2
            ;;
        --summary)
            SUMMARY_ONLY=true
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
    echo "error: --pass a|b is required" >&2
    usage >&2
    exit 1
fi

if [[ "${PASS}" != "a" && "${PASS}" != "b" ]]; then
    echo "error: --pass must be a or b" >&2
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
KUBECONFIG="${PASS_DIR}/kubeconfig"
TIMINGS="${PASS_DIR}/timings.jsonl"
BENCH_START_FILE="${PASS_DIR}/bench_start_epoch"
mkdir -p "${PASS_DIR}"

export KUBECONFIG

oc_cmd() {
    oc --kubeconfig="${KUBECONFIG}" "$@"
}

now_iso() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

now_epoch() {
    date +%s
}

ensure_bench_start() {
    if [[ ! -f "${BENCH_START_FILE}" ]]; then
        now_epoch >"${BENCH_START_FILE}"
    fi
}

elapsed_sec() {
    local start_epoch="${1:-}"
    local end_epoch="${2:-}"
    echo $((end_epoch - start_epoch))
}

append_timing() {
    local phase="$1"
    local start_iso="$2"
    local end_iso="$3"
    local duration="$4"
    local status="${5:-ok}"
  # shellcheck disable=SC2016
    printf '{"phase":"%s","pass":"%s","cluster_type":"%s","start":"%s","end":"%s","duration_sec":%s,"status":"%s"}\n' \
        "${phase}" "${PASS}" "${CLUSTER_TYPE}" "${start_iso}" "${end_iso}" "${duration}" "${status}" >>"${TIMINGS}"
}

append_event() {
    local event="$1"
    local detail="${2:-}"
    ensure_bench_start
    local ts_iso
    ts_iso="$(now_iso)"
    local elapsed
    elapsed="$(elapsed_sec "$(cat "${BENCH_START_FILE}")" "$(now_epoch)")"
    if [[ -n "${detail}" ]]; then
        printf '{"event":"%s","pass":"%s","cluster_type":"%s","ts":"%s","elapsed_sec":%s,"detail":"%s"}\n' \
            "${event}" "${PASS}" "${CLUSTER_TYPE}" "${ts_iso}" "${elapsed}" "${detail}" >>"${TIMINGS}"
    else
        printf '{"event":"%s","pass":"%s","cluster_type":"%s","ts":"%s","elapsed_sec":%s}\n' \
            "${event}" "${PASS}" "${CLUSTER_TYPE}" "${ts_iso}" "${elapsed}" >>"${TIMINGS}"
    fi
}

iso_from_epoch() {
    date -u -r "${1}" +"%Y-%m-%dT%H:%M:%SZ"
}

run_phase_timed_from_bench_start() {
    local phase="$1"
    ensure_bench_start
    local start_epoch start_iso end_epoch end_iso
    start_epoch="$(cat "${BENCH_START_FILE}")"
    start_iso="$(iso_from_epoch "${start_epoch}")"

    if ! "$2"; then
        end_epoch="$(now_epoch)"
        end_iso="$(now_iso)"
        append_timing "${phase}" "${start_iso}" "${end_iso}" "$(elapsed_sec "${start_epoch}" "${end_epoch}")" "failed"
        echo "Phase ${phase} FAILED" >&2
        return 1
    fi

    end_epoch="$(now_epoch)"
    end_iso="$(now_iso)"
    local dur
    dur="$(elapsed_sec "${start_epoch}" "${end_epoch}")"
    append_timing "${phase}" "${start_iso}" "${end_iso}" "${dur}" "ok"
    echo "Phase ${phase} OK (${dur}s from cluster_request)"
}

run_phase_timed() {
    local phase="$1"
    local start_epoch start_iso end_epoch end_iso
    start_epoch="$(now_epoch)"
    start_iso="$(now_iso)"
    ensure_bench_start

    if ! "$2"; then
        end_epoch="$(now_epoch)"
        end_iso="$(now_iso)"
        append_timing "${phase}" "${start_iso}" "${end_iso}" "$(elapsed_sec "${start_epoch}" "${end_epoch}")" "failed"
        echo "Phase ${phase} FAILED" >&2
        return 1
    fi

    end_epoch="$(now_epoch)"
    end_iso="$(now_iso)"
    local dur
    dur="$(elapsed_sec "${start_epoch}" "${end_epoch}")"
    append_timing "${phase}" "${start_iso}" "${end_iso}" "${dur}" "ok"
    echo "Phase ${phase} OK (${dur}s)"
}

login_from_credentials() {
    if [[ -z "${CREDENTIALS_FILE}" ]]; then
        if [[ -f "${PASS_DIR}/credentials.env" ]]; then
            CREDENTIALS_FILE="${PASS_DIR}/credentials.env"
        else
            echo "error: no kubeconfig and no --credentials-file" >&2
            return 1
        fi
    fi
    # shellcheck source=/dev/null
    source "${CREDENTIALS_FILE}"
    local user="${USER:-${USERNAME:-}}"
    if [[ -z "${API_URL:-}" || -z "${user}" || -z "${PASSWORD:-}" ]]; then
        echo "error: credentials file needs API_URL, USER (or USERNAME), PASSWORD" >&2
        return 1
    fi
    oc login "${API_URL}" --username="${user}" --password="${PASSWORD}" --insecure-skip-tls-verify=true
}

phase_provision() {
    if [[ ! -f "${KUBECONFIG}" ]]; then
        login_from_credentials || return 1
    fi
    if ! oc_cmd get nodes --no-headers 2>/dev/null | grep -q .; then
        login_from_credentials || return 1
    fi
    echo "Waiting for all nodes Ready (poll every ${POLL_INTERVAL}s)..."
    local ready=false
    local deadline=$((SECONDS + 1800))
    while ((SECONDS < deadline)); do
        local not_ready total
        total="$(oc_cmd get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')"
        not_ready="$(oc_cmd get nodes --no-headers 2>/dev/null | grep -cv ' Ready ' || true)"
        append_event "provision_poll" "nodes_total=${total} not_ready=${not_ready}"
        if [[ "${not_ready}" -eq 0 ]] && [[ "${total}" -gt 0 ]]; then
            ready=true
            break
        fi
        sleep "${POLL_INTERVAL}"
    done
    if [[ "${ready}" != "true" ]]; then
        echo "error: nodes not all Ready within 30m" >&2
        return 1
    fi
    append_event "cluster_ready"
    oc_cmd get nodes
    return 0
}

apply_fixtures() {
    oc_cmd apply -f "${FIXTURES}/rhoai-operator-sub.yaml"
    oc_cmd apply -f "${FIXTURES}/operatorgroup-rhods.yaml"
}

wait_csv_succeeded() {
    echo "Waiting for rhods-operator CSV Succeeded..."
    local deadline=$((SECONDS + 1800))
    local csv_name=""
    while ((SECONDS < deadline)); do
        csv_name="$(oc_cmd get csv -n "${ODS_OPERATOR_NS}" -o name 2>/dev/null | grep rhods-operator | head -1 || true)"
        if [[ -n "${csv_name}" ]]; then
            break
        fi
        sleep 15
    done
    if [[ -z "${csv_name}" ]]; then
        echo "error: rhods-operator CSV not found within 30m" >&2
        return 1
    fi
    if [[ -n "${OPERATOR_CSV}" ]]; then
        csv_name="csv/${OPERATOR_CSV}"
    fi
    oc_cmd wait "${csv_name}" -n "${ODS_OPERATOR_NS}" \
        --for=jsonpath='{.status.phase}'=Succeeded --timeout=30m
    local installed
    installed="$(oc_cmd get csv -n "${ODS_OPERATOR_NS}" -o jsonpath='{.items[?(@.status.phase=="Succeeded")].metadata.name}' 2>/dev/null | awk '{print $1}')"
    if [[ -n "${installed}" ]]; then
        echo "rhods-operator CSV Succeeded: ${installed}"
    fi
}

phase_operator_install() {
    apply_fixtures
    wait_csv_succeeded
    if ! oc_cmd get dscinitialization default-dsci >/dev/null 2>&1; then
        oc_cmd apply -f "${FIXTURES}/dsci-default.yaml"
    fi
    return 0
}

phase_dsc_reconcile() {
    oc_cmd apply -f "${FIXTURES}/dsc-minimal-workbenches.yaml"
    echo "Waiting for DSC default-dsc phase=Ready..."
    oc_cmd wait dsc/default-dsc --for=jsonpath='{.status.phase}'=Ready --timeout=30m
    local wb
    wb="$(oc_cmd get dsc default-dsc -o jsonpath='{.status.installedComponents.workbenches}' 2>/dev/null || true)"
    if [[ "${wb}" != "true" ]]; then
        echo "warning: status.installedComponents.workbenches is '${wb}', expected true" >&2
    fi
    echo "Waiting for namespace ${NOTEBOOK_NS}..."
    local deadline=$((SECONDS + 600))
    while ((SECONDS < deadline)); do
        if oc_cmd get namespace "${NOTEBOOK_NS}" >/dev/null 2>&1; then
            break
        fi
        sleep 10
    done
    oc_cmd get namespace "${NOTEBOOK_NS}" >/dev/null 2>&1
}

wait_notebook_ready() {
    if oc_cmd wait "notebook/${NOTEBOOK_NAME}" -n "${NOTEBOOK_NS}" \
        --for=condition=Ready --timeout=15m 2>/dev/null; then
        return 0
    fi
    echo "Notebook Ready condition missing or slow; waiting for pod..."
    oc_cmd wait pod -l "notebook-name=${NOTEBOOK_NAME}" -n "${NOTEBOOK_NS}" \
        --for=condition=Ready --timeout=15m
}

cluster_has_registry_redhat_io() {
    oc_cmd get secret -n openshift-config pull-secret \
        -o jsonpath='{.data.\.dockerconfigjson}' 2>/dev/null \
        | base64 -d 2>/dev/null | grep -q 'registry.redhat.io' || return 1
}

imagestream_tag_ref() {
    local tag="$1"
    oc_cmd get imagestream s2i-minimal-notebook -n "${ODS_APPS_NS}" \
        -o "jsonpath={.status.tags[?(@.tag==\"${tag}\")].items[0].dockerImageReference}" 2>/dev/null
}

resolve_notebook_image() {
    if [[ -n "${NOTEBOOK_IMAGE}" ]]; then
        echo "${NOTEBOOK_IMAGE}"
        return 0
    fi
    # CI launch clusters lack mirrored operand images in the internal registry; quay.io works.
    if [[ "${CLUSTER_TYPE}" == "launch" ]]; then
        local quay_ref
        quay_ref="$(imagestream_tag_ref "2024.2")"
        if [[ -n "${quay_ref}" && "${quay_ref}" =~ ^quay\.io ]]; then
            echo "warning: launch cluster notebook image uses quay.io fallback (${quay_ref})" >&2
            echo "${quay_ref}"
            return 0
        fi
    fi
    local ref
    ref="$(imagestream_tag_ref "3.4")"
    if [[ -z "${ref}" ]]; then
        ref="$(imagestream_tag_ref "2024.2")"
    fi
    if [[ "${ref}" =~ ^registry\.redhat\.io ]] && ! cluster_has_registry_redhat_io; then
        local fallback
        fallback="$(imagestream_tag_ref "2024.2")"
        if [[ -n "${fallback}" && "${fallback}" =~ ^quay\.io ]]; then
            echo "warning: cluster pull-secret lacks registry.redhat.io; notebook image fallback to ${fallback}" >&2
            ref="${fallback}"
        fi
    fi
    if [[ -z "${ref}" ]]; then
        echo "error: could not resolve notebook image from s2i-minimal-notebook imagestream" >&2
        return 1
    fi
    echo "${ref}"
}

apply_notebook_fixture() {
    local img
    img="$(resolve_notebook_image)" || return 1
    echo "Notebook image: ${img}"
    oc_cmd apply -f "${FIXTURES}/notebook-minimal.yaml"
    oc_cmd patch "notebook/${NOTEBOOK_NAME}" -n "${NOTEBOOK_NS}" --type=json \
        -p="[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/image\",\"value\":\"${img}\"}]"
    if oc_cmd get statefulset "${NOTEBOOK_NAME}" -n "${NOTEBOOK_NS}" >/dev/null 2>&1; then
        local current
        current="$(oc_cmd get statefulset "${NOTEBOOK_NAME}" -n "${NOTEBOOK_NS}" \
            -o jsonpath='{.spec.template.spec.containers[0].image}')"
        if [[ "${current}" != "${img}" ]]; then
            oc_cmd rollout restart "statefulset/${NOTEBOOK_NAME}" -n "${NOTEBOOK_NS}"
        fi
    fi
}

phase_notebook_spawn() {
    apply_notebook_fixture
    wait_notebook_ready
}

probe_workbench_api() {
    local pod
    pod="$(oc_cmd get pod -l "notebook-name=${NOTEBOOK_NAME}" -n "${NOTEBOOK_NS}" \
        -o jsonpath='{.items[0].metadata.name}')"
    if [[ -z "${pod}" ]]; then
        echo "error: no notebook pod found" >&2
        return 1
    fi
    local api_path="/notebook/${NOTEBOOK_NS}/${NOTEBOOK_NAME}/api"
    local deadline=$((SECONDS + 300))
    while ((SECONDS < deadline)); do
        if oc_cmd exec -n "${NOTEBOOK_NS}" "${pod}" -- \
            curl -sf "http://localhost:8888${api_path}" >/dev/null 2>&1; then
            echo "Jupyter API OK at ${api_path}"
            return 0
        fi
        sleep 10
    done
    echo "error: Jupyter /api probe failed within 5m" >&2
    return 1
}

phase_workbench_api() {
    probe_workbench_api
}

phase_uninstall() {
    oc_cmd delete notebook "${NOTEBOOK_NAME}" -n "${NOTEBOOK_NS}" --ignore-not-found --timeout=5m
    oc_cmd delete dsc default-dsc --ignore-not-found --timeout=10m
    oc_cmd delete dscinitialization default-dsci --ignore-not-found --timeout=5m
    oc_cmd delete -f "${FIXTURES}/rhoai-operator-sub.yaml" --ignore-not-found
    oc_cmd delete -f "${FIXTURES}/operatorgroup-rhods.yaml" --ignore-not-found
    local deadline=$((SECONDS + 600))
    while ((SECONDS < deadline)); do
        if ! oc_cmd get csv -n "${ODS_OPERATOR_NS}" 2>/dev/null | grep -q rhods-operator; then
            echo "rhods CSV removed"
            return 0
        fi
        sleep 15
    done
    echo "warning: rhods CSV may still exist after uninstall window" >&2
    return 0
}

phase_deprovision() {
    echo "Deprovision is via Slack 'done' to cluster-bot; use --mark-event deprovision_ack after bot confirms."
    return 0
}

print_summary() {
    if [[ ! -f "${TIMINGS}" ]]; then
        echo "No timings at ${TIMINGS}"
        return 0
    fi
    echo ""
    echo "=== cluster-bot RHOAI bench summary (pass=${PASS}, type=${CLUSTER_TYPE}) ==="
    echo "timings: ${TIMINGS}"
    echo ""
    printf "%-22s %10s %s\n" "PHASE" "SEC" "STATUS"
    printf "%-22s %10s %s\n" "--------------------" "----------" "------"
    while IFS= read -r line; do
        if [[ "${line}" == *'"phase"'* ]]; then
            local phase dur status
            phase="$(printf '%s' "$line" | sed -n 's/.*"phase":"\([^"]*\)".*/\1/p')"
            dur="$(printf '%s' "$line" | sed -n 's/.*"duration_sec":\([^,}]*\).*/\1/p')"
            status="$(printf '%s' "$line" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p')"
            printf "%-22s %10s %s\n" "${phase}" "${dur}" "${status}"
        fi
    done <"${TIMINGS}"

    local cluster_req provision_end workbench_end
    cluster_req="$(grep '"event":"cluster_request"' "${TIMINGS}" 2>/dev/null | tail -1 | sed -n 's/.*"elapsed_sec":\([^,}]*\).*/\1/p' || true)"
    workbench_end="$(grep '"phase":"workbench_api"' "${TIMINGS}" 2>/dev/null | tail -1 || true)"
    if [[ -n "${workbench_end}" ]]; then
        local wb_start wb_dur
        wb_start="$(printf '%s' "${workbench_end}" | sed -n 's/.*"start":"\([^"]*\)".*/\1/p')"
        wb_dur="$(printf '%s' "${workbench_end}" | sed -n 's/.*"duration_sec":\([^,}]*\).*/\1/p')"
        echo ""
        echo "workbench_api end: ${wb_start} (+${wb_dur}s phase)"
        if [[ -n "${cluster_req}" ]]; then
            local total
            total="$(grep '"phase":"workbench_api"' "${TIMINGS}" | tail -1 | sed -n 's/.*"duration_sec":\([^,}]*\).*/\1/p')"
            # E2E from cluster_request event elapsed to workbench phase end
            local wb_end_elapsed
            wb_end_elapsed=$((cluster_req + total))
            echo "E2E cluster_request → workbench_api (approx): ${wb_end_elapsed}s from bench start marker"
        fi
    fi
    echo ""
}

if [[ "${SUMMARY_ONLY}" == "true" ]]; then
    print_summary
    exit 0
fi

if [[ -n "${MARK_EVENT}" ]]; then
    case "${MARK_EVENT}" in
        cluster_request)
            ensure_bench_start
            append_event "cluster_request"
            echo "Marked cluster_request at $(now_iso)"
            ;;
        cluster_credentials)
            append_event "cluster_credentials"
            echo "Marked cluster_credentials at $(now_iso)"
            ;;
        cluster_ready)
            append_event "cluster_ready"
            echo "Marked cluster_ready at $(now_iso)"
            ;;
        deprovision_ack)
            append_event "deprovision_ack"
            echo "Marked deprovision_ack at $(now_iso)"
            ;;
        *)
            echo "error: unknown --mark-event ${MARK_EVENT}" >&2
            exit 1
            ;;
    esac
    exit 0
fi

run_phases() {
    local phases=("$@")
    local p
    for p in "${phases[@]}"; do
        case "${p}" in
            provision)
                run_phase_timed_from_bench_start cluster_provision phase_provision
                ;;
            operator_install)
                run_phase_timed operator_install phase_operator_install
                ;;
            dsc_reconcile)
                run_phase_timed dsc_reconcile phase_dsc_reconcile
                ;;
            notebook_spawn)
                run_phase_timed notebook_spawn phase_notebook_spawn
                ;;
            workbench_api)
                run_phase_timed workbench_api phase_workbench_api
                ;;
            uninstall)
                run_phase_timed uninstall phase_uninstall
                ;;
            deprovision)
                run_phase_timed deprovision phase_deprovision
                ;;
            *)
                echo "error: unknown phase ${p}" >&2
                return 1
                ;;
        esac
    done
}

case "${PHASE}" in
    all)
        run_phases provision operator_install dsc_reconcile notebook_spawn workbench_api uninstall
        ;;
    provision)
        run_phases provision
        ;;
    operator_install)
        run_phases operator_install
        ;;
    dsc_reconcile)
        run_phases dsc_reconcile
        ;;
    notebook_spawn)
        run_phases notebook_spawn
        ;;
    workbench_api)
        run_phases workbench_api
        ;;
    uninstall)
        run_phases uninstall
        ;;
    deprovision)
        run_phases deprovision
        ;;
    install)
        run_phases operator_install dsc_reconcile notebook_spawn workbench_api
        ;;
    post-provision)
        run_phases operator_install dsc_reconcile notebook_spawn workbench_api uninstall
        ;;
    *)
        echo "error: unknown --phase ${PHASE}" >&2
        usage >&2
        exit 1
        ;;
esac

print_summary
