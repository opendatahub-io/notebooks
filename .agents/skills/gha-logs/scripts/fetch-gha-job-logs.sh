#!/usr/bin/env bash
# Fetch per-job logs from a GitHub Actions workflow run.
# `gh run view RUN_ID --log` waits until the entire workflow completes; this script
# downloads logs for each finished job as soon as it is available.
#
# Usage:
#   ./.agents/skills/gha-logs/scripts/fetch-gha-job-logs.sh RUN_ID [OUTPUT_DIR]
#   REPO=owner/repo ./.agents/skills/gha-logs/scripts/fetch-gha-job-logs.sh RUN_ID
#
# Requires: gh CLI authenticated for the target repository.

set -Eeuo pipefail

RUN_ID="${1:?Usage: $0 RUN_ID [OUTPUT_DIR]}"
REPO="${REPO:-red-hat-data-services/notebooks}"

if [[ ! "${RUN_ID}" =~ ^[0-9]+$ ]]; then
  echo "Error: RUN_ID must be numeric, got '${RUN_ID}'" >&2
  exit 1
fi

if [[ ! "${REPO}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "Error: REPO must be in owner/repo form, got '${REPO}'" >&2
  exit 1
fi

OUTPUT_DIR="${2:-gha-job-logs-${RUN_ID}}"

mkdir -p "${OUTPUT_DIR}"

jobs_tsv=$(
  gh api "repos/${REPO}/actions/runs/${RUN_ID}/jobs" --paginate \
    -q '.jobs[] | select(.status=="completed") | [.id, .conclusion, .name] | @tsv'
)

jobs=()
if [[ -n "${jobs_tsv}" ]]; then
  mapfile -t jobs <<<"${jobs_tsv}"
fi

if ((${#jobs[@]} == 0)); then
  echo "No completed jobs yet for run ${RUN_ID} in ${REPO}" >&2
  exit 1
fi

for entry in "${jobs[@]}"; do
  IFS=$'\t' read -r job_id conclusion name <<<"${entry}"
  safe_name=$(printf '%s' "${name}" | tr -c 'A-Za-z0-9._-' '_')
  safe_name="${safe_name:0:100}"
  out="${OUTPUT_DIR}/job-${job_id}-${safe_name}.log"
  printf 'Fetching %s (%s): %q\n' "${job_id}" "${conclusion}" "${name}"
  if gh api --allow-escape-sequences "repos/${REPO}/actions/jobs/${job_id}/logs" |
    sed -E 's#\x1B\][^\x07\x1B]*(\x07|\x1B\\)##g; s#\x1B\[[0-?]*[ -/]*[@-~]##g' |
    tr -d '\000-\010\013-\037\177' >"${out}"; then
    echo "  -> ${out}"
  else
    echo "  -> failed (log may be expired or unavailable)" >&2
    rm -f "${out}"
  fi
done

echo "Done. Logs in ${OUTPUT_DIR}/"
