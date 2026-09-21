#!/usr/bin/env bash
# Shared helpers for the custom-workbenches wizard.

set -Eeuo pipefail

WIZARD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_ROOT="$(cd "${WIZARD_ROOT}/.." && pwd)"
SRC_DIR="${WIZARD_ROOT}/src"

# shellcheck source=../defaults/bases.env
source "${SRC_DIR}/defaults/bases.env"
# shellcheck source=../defaults/channels.env
source "${SRC_DIR}/defaults/channels.env"

# Top-level dirs that must not be overwritten by a generated image.
RESERVED_NAMES=(src .git)

ui() {
  echo "$@" >&2
}

die() {
  ui ""
  ui "Error: $*"
  exit 1
}

require_tools() {
  local missing=()
  for tool in podman envsubst; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
      missing+=("${tool}")
    fi
  done
  if ((${#missing[@]} > 0)); then
    die "Missing: ${missing[*]}. Install podman and gettext (envsubst)."
  fi
}

screen_reset() {
  if [[ -t 2 ]]; then
    clear >&2
  fi
}

ask_menu() {
  local var_name="$1"
  local heading="$2"
  shift 2
  local default=1
  if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
    default="$1"
    shift
  fi
  local options=("$@")
  local n=${#options[@]}
  local i choice

  screen_reset
  ui "${heading}"
  ui ""
  for i in "${!options[@]}"; do
    ui "  $((i + 1))  ${options[i]}"
  done
  ui ""
  while true; do
    read -r -p "Your choice [1-${n}, Enter = ${default}]: " choice </dev/tty
    choice="${choice:-$default}"
    if [[ "${choice}" =~ ^[0-9]+$ ]] && ((choice >= 1 && choice <= n)); then
      printf -v "${var_name}" '%s' "${choice}"
      return 0
    fi
    ui "  Please enter a number from 1 to ${n}."
  done
}

prompt_var() {
  local var_name="$1"
  local label="$2"
  local default="${3:-}"
  local reply

  ui ""
  if [[ -n "${default}" ]]; then
    read -r -p "${label} [${default}]: " reply </dev/tty
    printf -v "${var_name}" '%s' "${reply:-${default}}"
  else
    read -r -p "${label}: " reply </dev/tty
    printf -v "${var_name}" '%s' "${reply}"
  fi
}

sanitize_name() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9._-' '-' | sed 's/^-*//;s/-*$//'
}

is_reserved_name() {
  local name="$1"
  local r
  for r in "${RESERVED_NAMES[@]}"; do
    [[ "${name}" == "${r}" ]] && return 0
  done
  return 1
}

normalize_quay_org() {
  local s="$1"
  s="${s#https://}"
  s="${s#http://}"
  s="${s#quay.io/}"
  s="${s%%/*}"
  s="${s%%:*}"
  s="${s// /}"
  echo "${s}"
}

normalize_quay_repo() {
  local s="$1"
  local org="$2"
  s="${s#https://}"
  s="${s#http://}"
  s="${s#quay.io/}"
  if [[ "${s}" == */* ]]; then
    s="${s#*/}"
  fi
  if [[ -n "${org}" && "${s}" == "${org}/"* ]]; then
    s="${s#${org}/}"
  fi
  s="${s%%:*}"
  s="${s%%/*}"
  s="${s// /}"
  echo "${s}"
}
