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
OUTPUT_DIR="${2:-gha-job-logs-${RUN_ID}}"
REPO="${REPO:-red-hat-data-services/notebooks}"

mkdir -p "${OUTPUT_DIR}"

mapfile -t jobs < <(
  gh api "repos/${REPO}/actions/runs/${RUN_ID}/jobs" --paginate \
    -q '.jobs[] | select(.status=="completed") | [.id, .conclusion, .name] | @tsv'
)

if ((${#jobs[@]} == 0)); then
  echo "No completed jobs yet for run ${RUN_ID} in ${REPO}" >&2
  exit 1
fi

for entry in "${jobs[@]}"; do
  IFS=$'\t' read -r job_id conclusion name <<<"${entry}"
  safe_name=$(echo "${name}" | tr '/: ' '___')
  out="${OUTPUT_DIR}/job-${job_id}-${safe_name}.log"
  echo "Fetching ${job_id} (${conclusion}): ${name}"
  if gh api --allow-escape-sequences "repos/${REPO}/actions/jobs/${job_id}/logs" |
    sed -E 's/\x1B\[([0-9]{1,2}(;[0-9]{1,2})*)?[mGK]//g' >"${out}"; then
    echo "  -> ${out}"
  else
    echo "  -> failed (log may be expired or unavailable)" >&2
    rm -f "${out}"
  fi
done

echo "Done. Logs in ${OUTPUT_DIR}/"
