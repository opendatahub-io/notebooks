# shellcheck shell=bash
# Source from host-side lock/prefetch tooling when local Red Hat CA PEMs exist.
# Never commit .local-ca/ (gitignored).
#
# packages.redhat.com is signed by Red Hat "2023 Certificate Authority RHCSv2"
# (not a public DigiCert root). Plain certifi/system trust fails Python probes
# with CERTIFICATE_VERIFY_FAILED / "No production or -test RH index".
#
# Setup once:
#   mkdir -p .local-ca
#   # RHSM CDN (optional, for hermeto cdn.redhat.com):
#   podman run --rm registry.access.redhat.com/ubi9/ubi \
#     cat /etc/rhsm/ca/redhat-uep.pem > .local-ca/redhat-uep.pem
#   # Then source this script (or run make refresh-lock-files) — it will
#   # fetch the RHCSv2 intermediate and build .local-ca/combined-ca-bundle.pem
#
# Prefer an explicit SSL_CERT_FILE if the caller already set one.

_local_ca_env_self=""
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  _local_ca_env_self="${BASH_SOURCE[0]}"
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  # zsh: path of the sourced file
  # shellcheck disable=SC2296
  _local_ca_env_self="${(%):-%x}"
else
  _local_ca_env_self="$0"
fi
_local_ca_env_root="$(cd "$(dirname "${_local_ca_env_self}")/../../.." && pwd)"
_local_ca_dir="${_local_ca_env_root}/.local-ca"
_combined="${_local_ca_dir}/combined-ca-bundle.pem"
_rhcs="${_local_ca_dir}/rhcs-v2-ca.pem"

_local_ca_ensure_rhcs_intermediate() {
  # Intermediate presented by packages.redhat.com (issuer of the leaf).
  if [[ -f "${_rhcs}" ]] && grep -q 'BEGIN CERTIFICATE' "${_rhcs}" 2>/dev/null; then
    return 0
  fi
  command -v openssl >/dev/null 2>&1 || return 1
  mkdir -p "${_local_ca_dir}"
  local tmp chain
  tmp="$(mktemp)"
  chain="$(mktemp)"
  if ! echo | openssl s_client -connect packages.redhat.com:443 \
      -servername packages.redhat.com -showcerts 2>/dev/null >"${chain}"; then
    rm -f "${tmp}" "${chain}"
    return 1
  fi
  # Second PEM in the chain is typically the RHCSv2 intermediate.
  awk '
    /BEGIN CERTIFICATE/ { n++; buf=$0; next }
    n { buf=buf ORS $0 }
    /END CERTIFICATE/ {
      if (n == 2) { print buf; exit }
    }
  ' "${chain}" >"${tmp}"
  rm -f "${chain}"
  if grep -q 'BEGIN CERTIFICATE' "${tmp}" 2>/dev/null; then
    mv "${tmp}" "${_rhcs}"
    return 0
  fi
  rm -f "${tmp}"
  return 1
}

_local_ca_rebuild_combined() {
  mkdir -p "${_local_ca_dir}"
  local base=""
  # Prefer certifi (uv/python) then macOS/Linux system bundle.
  if command -v python3 >/dev/null 2>&1; then
    base="$(python3 -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
  fi
  if [[ -z "${base}" || ! -f "${base}" ]]; then
    for candidate in /etc/ssl/cert.pem /etc/pki/tls/certs/ca-bundle.crt; do
      if [[ -f "${candidate}" ]]; then
        base="${candidate}"
        break
      fi
    done
  fi
  if [[ -z "${base}" || ! -f "${base}" ]]; then
    return 1
  fi
  cat "${base}" >"${_combined}.tmp"
  local f
  for f in "${_rhcs}" \
           "${_local_ca_dir}/redhat-uep.pem" \
           "${_local_ca_dir}/redhat-entitlement-authority.pem" \
           "${_local_ca_dir}/cdn-ca-bundle.pem"; do
    if [[ -f "${f}" ]]; then
      printf '\n' >>"${_combined}.tmp"
      cat "${f}" >>"${_combined}.tmp"
    fi
  done
  mv "${_combined}.tmp" "${_combined}"
  return 0
}

if [[ -z "${SSL_CERT_FILE:-}" ]]; then
  if [[ -d "${_local_ca_dir}" ]]; then
    _local_ca_ensure_rhcs_intermediate || true
    # Rebuild when missing or older than inputs.
    _need_rebuild=0
    if [[ ! -f "${_combined}" ]]; then
      _need_rebuild=1
    else
      for f in "${_rhcs}" \
               "${_local_ca_dir}/redhat-uep.pem" \
               "${_local_ca_dir}/redhat-entitlement-authority.pem" \
               "${_local_ca_dir}/cdn-ca-bundle.pem"; do
        if [[ -f "${f}" && "${f}" -nt "${_combined}" ]]; then
          _need_rebuild=1
          break
        fi
      done
    fi
    if [[ "${_need_rebuild}" -eq 1 ]]; then
      _local_ca_rebuild_combined || true
    fi
    if [[ -f "${_combined}" ]]; then
      export SSL_CERT_FILE="${_combined}"
    elif [[ -f "${_local_ca_dir}/cdn-ca-bundle.pem" ]]; then
      # Last resort: RHSM-oriented bundle alone (may break packages.redhat.com).
      export SSL_CERT_FILE="${_local_ca_dir}/cdn-ca-bundle.pem"
    elif [[ -f "${_local_ca_dir}/redhat-uep.pem" ]]; then
      export SSL_CERT_FILE="${_local_ca_dir}/redhat-uep.pem"
    fi
  fi
fi

if [[ -n "${SSL_CERT_FILE:-}" ]]; then
  export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-$SSL_CERT_FILE}"
  export CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-$SSL_CERT_FILE}"
  # uv: use OS/OpenSSL trust (respects SSL_CERT_FILE) instead of rustls webpki roots
  export UV_SYSTEM_CERTS="${UV_SYSTEM_CERTS:-1}"
fi

unset _local_ca_env_self _local_ca_env_root _local_ca_dir _combined _rhcs _need_rebuild
unset -f _local_ca_ensure_rhcs_intermediate _local_ca_rebuild_combined 2>/dev/null || true
