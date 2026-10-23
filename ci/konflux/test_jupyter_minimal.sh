#!/usr/bin/env bash
set -Eeuo pipefail

mode="${1:?usage: test_jupyter_minimal.sh <browser|e2e> <image> <repo-url> <revision> <source-root>}"
image="${2:?missing image}"
repo_url="${3:?missing repository URL}"
revision="${4:?missing revision}"
source_root="${5:?missing source root}"

case "${mode}" in
  browser|e2e) ;;
  *)
    echo "Unsupported test mode: ${mode}" >&2
    exit 2
    ;;
esac

image_repository="${image%:*}"
image_tag="${image##*:}"
created_source_root=0
if [[ "${source_root}" == "auto" ]]; then
  source_root="$(mktemp -d)"
  created_source_root=1
fi
workdir="${source_root}"
namespace="jupyter-minimal-${mode}-${RANDOM}"
namespace_created=0
deployment_started=0
cleanup_failed=0

cleanup() {
  set +e
  if (( deployment_started )); then
    (
      cd "${workdir}/source"
      make undeploy9-jupyter-minimal-ubi9-python-3.12
    ) || cleanup_failed=1
  fi
  if (( namespace_created )); then
    oc delete namespace "${namespace}" --wait=false >/dev/null 2>&1 || true
  fi
  if (( created_source_root )); then
    rm -rf "${workdir}"
  fi
  if (( cleanup_failed )); then
    exit 1
  fi
}
trap cleanup EXIT

if [[ ! -d "${workdir}/source/.git" ]]; then
  git init "${workdir}/source"
  git -C "${workdir}/source" remote add origin "${repo_url}"
  git -C "${workdir}/source" fetch --depth=1 origin "${revision}"
  git -C "${workdir}/source" checkout FETCH_HEAD
fi

oc new-project "${namespace}"
namespace_created=1
oc project "${namespace}"

cd "${workdir}/source"
deployment_started=1
if [[ "${mode}" == "browser" ]] && ! grep -Eq \
  '"@playwright/test"[[:space:]]*:[[:space:]]*"=1\.63\.0"' \
  tests/browser/package.json5; then
  echo "The pinned browser-test image is Playwright 1.63.0; update it when tests/browser/package.json5 changes" >&2
  exit 1
fi
make deploy9-jupyter-minimal-ubi9-python-3.12 \
  IMAGE_REGISTRY="${image_repository}" \
  NOTEBOOK_TAG="${image_tag}"

oc wait --for=condition=ready pod \
  -l app=jupyter-minimal-ubi9-python-3-12 \
  --timeout=600s
workbench_pod="$(
  oc get pod -l app=jupyter-minimal-ubi9-python-3-12 \
    -o jsonpath='{.items[0].metadata.name}'
)"

if [[ "${mode}" == "e2e" ]]; then
  make test-jupyter-minimal-ubi9-python-3.12
  exit 0
fi

oc exec "${workbench_pod}" -- bash -lc '
  set -Eeuo pipefail
  git config --global user.name "Offline Browser Fixture"
  git config --global user.email offline-browser@example.invalid
  mkdir -p /opt/app-root/src/offline-git-remote.git /opt/app-root/src/offline-git-repo
  git -C /opt/app-root/src/offline-git-remote.git init --bare
  git -C /opt/app-root/src/offline-git-repo init
  printf "%s\n" "initial content" >/opt/app-root/src/offline-git-repo/git-ui.txt
  git -C /opt/app-root/src/offline-git-repo add git-ui.txt
  git -C /opt/app-root/src/offline-git-repo commit -m "initial offline fixture"
  git -C /opt/app-root/src/offline-git-repo remote add origin \
    file:///opt/app-root/src/offline-git-remote.git
'

cat <<'EOF' | oc apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: browser-test
spec:
  restartPolicy: Never
  containers:
    - name: browser-test
      image: quay.io/opendatahub/workbench-images-tests@sha256:a4f85171ac50dbe8222986b1ea91c3ef97397e2b96242c122aa4c3dbb33c81ac
      command: ["/bin/bash", "-c", "sleep infinity"]
      env:
        - name: CI
          value: "true"
        - name: OFFLINE_BASE_URL
          value: http://jupyter-minimal-ubi9-python-3-12-notebook:8888/notebook/opendatahub/jovyan/
        - name: OFFLINE_FAKE_VALUE
          value: konflux-browser-fixture
      resources:
        requests:
          cpu: "1"
          memory: 2Gi
        limits:
          cpu: "2"
          memory: 4Gi
      volumeMounts:
        - name: shared-memory
          mountPath: /dev/shm
  volumes:
    - name: shared-memory
      emptyDir:
        medium: Memory
        sizeLimit: 1Gi
EOF

oc wait --for=condition=ready pod/browser-test --timeout=300s
oc cp tests/browser/tests/. "${namespace}/browser-test:/home/pwuser/tests/browser/tests/"
oc cp tests/browser/playwright.config.ts "${namespace}/browser-test:/home/pwuser/tests/browser/playwright.config.ts"
oc cp tests/browser/package.json5 "${namespace}/browser-test:/home/pwuser/tests/browser/package.json5"
oc cp tests/browser/pnpm-lock.yaml "${namespace}/browser-test:/home/pwuser/tests/browser/pnpm-lock.yaml"
oc cp tests/browser/pnpm-workspace.yaml "${namespace}/browser-test:/home/pwuser/tests/browser/pnpm-workspace.yaml"

oc exec browser-test -- \
  ./node_modules/.bin/playwright test --project=chromium --grep @jupyter

oc exec browser-test -- bash -lc \
  'if [[ -f results/junit.xml ]]; then cat results/junit.xml; fi'
