# Conforma (Enterprise Contract) Container Image Labels

Conforma enforces container image label policies for Red Hat product releases.
Only RHOAI images (built via Konflux at `red-hat-data-services/notebooks`) are
checked by Conforma. ODH images at `quay.io/opendatahub/` are not subject to
Conforma policy.

## Policy source of truth

The required labels are defined in
[`release-engineering/rhtap-ec-policy/data/rule_data.yml`](https://github.com/release-engineering/rhtap-ec-policy/blob/main/data/rule_data.yml)
under `required_labels`. The policy is enforced by the `labels.required_labels`
Conforma check during the release pipeline.

Related Jira: [KONFLUX-1329](https://redhat.atlassian.net/browse/KONFLUX-1329)
(reassess and enforce required container labels).

## Where labels come from

### Auto-injected by the Konflux buildah task

These labels are added automatically by `buildah-remote-oci-ta`. Do NOT set them
in Dockerfiles or conf files:

| Label | Value |
|---|---|
| `architecture` | `$(uname -m)` |
| `build-date` | RFC 3339 build timestamp |
| `distribution-scope` | `public` |
| `org.opencontainers.image.created` | RFC 3339 build timestamp |
| `org.opencontainers.image.revision` | git commit SHA |
| `org.opencontainers.image.source` | git repo URL |
| `vcs-ref` | git commit SHA |
| `vcs-type` | `git` |
| `vendor` | `Red Hat, Inc.` |

These labels flow into RHOAI builds via the automated "Update Konflux
references" PRs from `konflux-internal-p02[bot]` that bump task bundle digests
in `red-hat-data-services/konflux-central`. When the upstream buildah task is
updated (e.g., to add new labels), the fix propagates automatically without
manual pipeline changes.

Historical example: `distribution-scope` and `vendor` were missing in
[RHOAIENG-42631](https://redhat.atlassian.net/browse/RHOAIENG-42631). They were
fixed by an upstream buildah task update, confirmed by a rebuild
(RHSA-2026:1027), with no code changes in the notebooks repo.

### Auto-injected by the `konflux-central` pipeline

The shared pipeline at
`red-hat-data-services/konflux-central/pipelines/multi-arch-container-build.yaml`
adds these via the `LABELS` parameter on the buildah task:

| Label | Value |
|---|---|
| `url` | `$(params.git-url)` |
| `release` | `$(tasks.clone-repository.results.commit-timestamp)` |
| `git.url` | `$(params.git-url)` |
| `git.commit` | `$(params.revision)` |

### Computed by `rhoai-init` task

The `rhoai-init` task in
[`red-hat-data-services/rhoai-konflux-tasks`](https://github.com/red-hat-data-services/rhoai-konflux-tasks/blob/main/konflux-tekton-tasks/rhoai-init/0.3/rhoai-init.yaml)
computes the CPE label from the `rhoai-version` pipeline parameter:

```bash
cpe_id="cpe:/a:redhat:openshift_ai:${x}.${y}::el${rhel_version}"
```

| Label | Example value |
|---|---|
| `cpe` | `cpe:/a:redhat:openshift_ai:3.5::el9` |

### Set in Dockerfiles (via build-args)

These labels are set in the Dockerfile `LABEL` block, parameterized via
`LABEL_REGISTRY_PREFIX` and `LABEL_COMPONENT` build-args from the conf files:

| Label | Source |
|---|---|
| `name` | `${LABEL_REGISTRY_PREFIX}/${LABEL_COMPONENT}` |
| `com.redhat.component` | `${LABEL_COMPONENT}` |
| `io.k8s.display-name` | `${LABEL_COMPONENT}` |
| `summary` | Hardcoded per Dockerfile |
| `description` | Hardcoded per Dockerfile |
| `io.k8s.description` | Hardcoded per Dockerfile |
| `com.redhat.license_terms` | Hardcoded (Red Hat EULA URL) |

The conf files provide different values per build environment:

- ODH: `LABEL_REGISTRY_PREFIX=opendatahub`, `LABEL_COMPONENT=odh-workbench-...-ubi9`
- Konflux: `LABEL_REGISTRY_PREFIX=rhoai`, `LABEL_COMPONENT=odh-workbench-...-rhel9`

### Disallowed inherited labels

Conforma requires these labels to be set directly on the image, not inherited
from the base image:

`description`, `io.k8s.description`, `io.k8s.display-name`, `io.openshift.tags`,
`summary`, `name`, `com.redhat.component`

## Verifying labels

Check labels on a built image:

```bash
skopeo inspect --no-tags docker://quay.io/rhoai/<image>:<tag> | jq '.Labels'
```

Install the `ec` CLI ([releases](https://github.com/enterprise-contract/ec-cli/releases)):

```bash
# macOS / Linux — download snapshot binary
curl -sLO https://github.com/enterprise-contract/ec-cli/releases/download/snapshot/ec_$(uname -s | tr '[:upper:]' '[:lower:]')_amd64
chmod +x ec_* && sudo mv ec_* /usr/local/bin/ec
```

Run Conforma locally against a Konflux-built image (requires SLSA attestations):

```bash
ec validate image \
  --image quay.io/rhoai/<image>:<tag> \
  --policy '{"sources":[{"policy":["oci::quay.io/conforma/release-policy:konflux"],"data":["github.com/release-engineering/rhtap-ec-policy//data"]}]}' \
  --output yaml
```

## Key policy checks beyond labels

The full set of Conforma release checks is in
[`enterprise-contract/ec-policies/policy/release/`](https://github.com/enterprise-contract/ec-policies/tree/main/policy/release).
The ones most relevant to notebook images:

| Check | What it enforces |
|---|---|
| `rpm_signature` | All RPMs installed in the image must be signed with [Red Hat release keys](https://access.redhat.com/security/team/key). Third-party RPMs (e.g., ROCM/AMD) need a policy exception. |
| `sbom` / `sbom_cyclonedx` | SBOM must exist. Disallowed package attributes are checked — notably `hermeto:pip:package:binary` and `cachi2:pip:package:binary` must not be `"true"`. This means **Python packages must be sdist (source distributions), not binary wheels**. |
| `cve` | Known CVEs must be addressed within Red Hat SLA windows (critical: 6 days, high: 29 days). |
| `slsa_provenance_available` | SLSA provenance attestation must exist. |
| `hermetic_task` / `trusted_task` | Build must run in a hermetic, trusted Tekton task. |
| `labels` | Required container labels (see above). |

Policy data (allowed RPM keys, disallowed attributes, CVE windows) is configured in
[`rhtap-ec-policy/data/rule_data.yml`](https://github.com/release-engineering/rhtap-ec-policy/blob/main/data/rule_data.yml).

## Policy exceptions

When an image cannot satisfy a Conforma check (e.g., unsigned third-party RPMs),
request an exception via MR to
[`releng/konflux-release-data`](https://gitlab.cee.redhat.com/releng/konflux-release-data).

Exception config lives in per-product YAML files:

- `registry-rhoai-stage.yaml` — staging
- `registry-rhoai-prod.yaml` — production

Each exception entry has:

```yaml
- value: "rpm_signature.allowed:9386b48a1a693c5c"
  effectiveUntil: "2025-10-04T00:00:00Z"
  reference: https://issues.redhat.com/browse/RHOAIENG-33270
```

Example:
[MR !9851](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/merge_requests/9851)
— ROCM/AMD RPM signature exception for RHOAI notebooks (RHOAIENG-33270).

## Troubleshooting

If a Conforma `labels.required_labels` violation appears:

1. Check if the label is supposed to be auto-injected (see tables above). If
   so, the fix is likely an upstream buildah task update that will flow through
   `konflux-central` automatically.
2. If the label should be in the Dockerfile, check `build-args/*.conf` files
   for the correct values.
3. If a new label is added to the policy with an `effective_on` date, check the
   [rule_data.yml](https://github.com/release-engineering/rhtap-ec-policy/blob/main/data/rule_data.yml)
   for details.
4. For label-related Conforma violations, see past tickets:
   [RHOAIENG-42631](https://redhat.atlassian.net/browse/RHOAIENG-42631),
   [RHAIENG-5138](https://redhat.atlassian.net/browse/RHAIENG-5138).
