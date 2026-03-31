# ProdSec Scanning, SBOMs, and False Positive CVEs

## How Konflux Generates SBOMs

Konflux runs **two separate scans** per image build:

1. **Image scan**: Syft scans the built container image filesystem
2. **Source scan**: Syft scans the full source repository checkout

Both SBOMs are then **merged by Mobster** into a single aggregate SBOM attached to the image
in the OCI registry. ProdSec consumes this merged SBOM via manifest-box/newcli to file CVE
tracker Jira issues.

### Why This Causes False Positives

In a **monorepo** like notebooks, the source scan picks up every lockfile and dependency
manifest in the entire repo — not just the ones used by the image being built. This means:

- `tests/browser/pnpm-lock.yaml` (Playwright test deps) → attributed to ALL images
- `scripts/buildinputs/go.mod` (Go build tooling) → attributed to ALL images
- `jupyter/utils/addons/pnpm-lock.yaml` (JupyterLab build-time npm) → attributed to ALL images
- Root `pyproject.toml` / `uv.lock` (dev/CI Python tooling) → attributed to ALL images

**Result**: A single vulnerable package in test code generates CVE tickets against every
image built from the repo. For notebooks with ~20 images across ~5 RHOAI versions, this can
mean 100+ false positive Jira issues from a single CVE.

### This Is Not Just a Notebooks Problem

Multiple Red Hat teams have hit the same issue:

| Team | Problem | Source |
|------|---------|--------|
| **OSSM (Istio)** | Ruby Rack CVE from bookinfo sample app attributed to all operator images | Slack: prodsec-engineering channel |
| **RHDH (Backstage)** | Yarn workspace monorepo: Hermeto prefetch resolves root lockfile for all plugins, ~16x CVE duplication | [build-definitions#3259](https://github.com/konflux-ci/build-definitions/pull/3259) |
| **Ansible** | `wheel` build dependency found via hermeto, tracker filed correctly but confusing | Slack: prodsec-scanning channel |

### Upstream Fix Proposals

1. **`.syft.yaml` exclusions** (our approach): Repo-level config that tells syft to skip
   non-shipped paths during source scan. Verified working for notebooks.

2. **`INCLUDE_PREFETCH_SBOM` / `INCLUDE_SOURCE_SBOM` params** (RHDH approach):
   [build-definitions#3259](https://github.com/konflux-ci/build-definitions/pull/3259)
   proposes pipeline-level params to opt out of prefetch/source SBOM inclusion.
   Requires Conforma policy exception. Status: under discussion.

3. **Mobster improvements**: ProdSec acknowledges the issue and is working on more accurate
   SBOM merging. Atlas/Trustify migration may help.

## How to Verify SBOMs

### Fetch SBOM from Quay.io (No Auth Needed)

```bash
# 1. Get the per-architecture image digest
DIGEST=$(skopeo inspect docker://quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9:rhoai-3.4-linux-x86-64 \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['Digest'])")

# 2. Download SBOM via oras
oras copy "quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9:sha256-${DIGEST#sha256:}.sbom" \
  --to-oci-layout /tmp/sbom-download

# 3. Extract and analyze
SBOM_BLOB=$(ls -S /tmp/sbom-download/blobs/sha256/ | head -1)
cp "/tmp/sbom-download/blobs/sha256/${SBOM_BLOB}" sbom.json
```

### Check for False Positives

```bash
python3 -c "
import json
from collections import Counter
with open('sbom.json') as f:
    sbom = json.load(f)
print(f'Total packages: {len(sbom[\"packages\"])}')
for si, count in Counter(
    p.get('sourceInfo','')[:120] for p in sbom['packages']
).most_common():
    print(f'  {count:4d}  {si}')
"
```

If you see `sourceInfo` paths like `tests/browser/pnpm-lock.yaml` or `scripts/buildinputs/go.mod`,
the source scan is contaminating the SBOM.

## ProdSec Tooling Landscape

### Public APIs (No Auth)

| Tool | URL | Best For |
|------|-----|----------|
| **OSV API** | `POST https://api.osv.dev/v1/query` | "Is package X@version vulnerable? What's the fix version?" |
| **RH Security Data API** | `https://access.redhat.com/hydra/rest/securitydata/cve/CVE-XXXX-XXXXX.json` | "What's the Red Hat fix state for this CVE?" |
| **Pyxis catalog API** | `https://catalog.redhat.com/api/containers/v1/...` | Image digests, container grades |
| **oras/skopeo** | `oras copy ...sha256-<digest>.sbom` | Download SBOM for a specific Konflux build |

### Internal APIs (Require VPN or SSO)

| Tool | URL | Best For |
|------|-----|----------|
| **Deptopia API** | `https://deptopia.prodsec.redhat.com/api/v1/` | Package search in Brew/CPaaS builds (fast, no DB download) |
| **OSIDB API** | `https://osidb.prodsec.redhat.com/osidb/api/v1/` | CVE flaw database queries |
| **Atlas/Trustify** | `https://atlas.build.devshift.net/api/v2/` | Next-gen SBOM/vulnerability platform (49 endpoints, SSO auth) |
| **newcli** | CLI tool (see wrapper) | Unified search across manifest-box + deptopia |

### newcli Quick Start

```bash
# Install and run via the wrapper script
.agents/tools/newcli-wrapper.sh --help

# Search for a package across all products
.agents/tools/newcli-wrapper.sh -vvv -s -e pypi wheel | grep notebook

# Find which streams ship a component
.agents/tools/newcli-wrapper.sh -a odh-workbench-jupyter-minimal-cpu-py312-rhel9
```

Note: First run downloads ~400MB manifest-box SQLite DB. Requires VPN.

### Deptopia API Quick Queries

```bash
# Search for a package (Brew/CPaaS builds only, NOT Konflux)
curl -sk "https://deptopia.prodsec.redhat.com/api/v1/dependencies/search?name=wheel&ecosystem=pypi"

# Find builds containing a package
curl -sk "https://deptopia.prodsec.redhat.com/api/v1/contains?name=wheel"

# Full API docs
curl -sk "https://deptopia.prodsec.redhat.com/api/v1/swagger.json" | python3 -m json.tool
```

### Atlas/Trustify API (Next-Gen)

```bash
# Swagger UI (requires Employee SSO login in browser)
open https://atlas.build.devshift.net/swagger-ui/

# OpenAPI spec
curl -sk https://atlas.build.devshift.net/openapi.json | python3 -c "
import sys, json
for path in sorted(json.load(sys.stdin)['paths']):
    print(path)
"
```

Key endpoints: `/api/v2/sbom`, `/api/v2/purl`, `/api/v2/vulnerability`, `/api/v2/advisory`,
`/api/v2/analysis/component`, `/api/v2/product`.

## VEX Justifications for Closing False Positives

When closing CVE trackers as false positives, use **Resolution: "Not a Bug"** with one of:

| VEX Justification | When to Use |
|-------------------|-------------|
| `Vulnerable Code Not Present` | Package only appears in source-scan SBOM, not in shipped image |
| `Vulnerable Code not in Execute Path` | Code exists in base image but is unreachable in our product |
| `Component Not Present` | Component not actually shipped in this product version |

**NEVER use "Won't Do"** — this is prohibited by ProdSec policy and will cause the CVE to
show as an unpatched vulnerability in the product.

Reference: [VEX Not Affected Justifications](https://spaces.redhat.com/spaces/PRODSEC/pages/580257978/)

## Base Image CVEs

- Trackers for CVEs in **base images** (not our code) should be closed as "Not a Bug"
- We do NOT include base image CVEs in release notes/errata
- Container grades (visible at [catalog.redhat.com](https://catalog.redhat.com)) handle base image vulnerability tracking
- If the CVE is in a base image component, we cannot take action — we wait for the base image to be updated

## Embargoed CVEs

- Do NOT include embargoed CVEs in release advisories
- Be careful creating trackers — avoid leaking embargo details to non-affected teams
- Container grade may still show 'A' because the CVE is not yet public
- Close tracker as "Not a Bug" if the embargoed CVE doesn't affect our code

## References

- [ProdSec Essential Docs for Engineering Teams](https://spaces.redhat.com/spaces/PRODSEC/pages/436147380/)
- [VEX Justifications](https://spaces.redhat.com/spaces/PRODSEC/pages/580257978/)
- [SPDX VEX Spec](https://spdx.github.io/spdx-spec/v3.0.1/model/Security/Vocabularies/VexJustificationType/)
- [CVE Remediation Training (Google Doc)](https://docs.google.com/document/d/1nAeyewcvrxwkFe55AWVWQ8-QdLpbMY5hESSw_d8SYuE/)
- [manifest-box GitLab Repository](https://gitlab.cee.redhat.com/product-security/manifest-box)
- [newtopia-cli (newcli)](https://gitlab.cee.redhat.com/prodsec-dev/newtopia-cli)
- [Trustify (Atlas backend)](https://github.com/guacsec/trustify)
- [Konflux SBOM PR: build-definitions#3259](https://github.com/konflux-ci/build-definitions/pull/3259)
- [ProdSec Issue Form](https://docs.google.com/forms/d/e/1FAIpQLSfa6zTaEGohRdiIqGVAvWTSAL0kpO_DkkEICuIHzQHFwmKswg/viewform)
