# Working with the ProdSec Manifest Box Repository

This guide covers how to work with the Red Hat Product Security manifest-box repository for vulnerability management and SBOM analysis.

## Overview

The [manifest-box](https://gitlab.cee.redhat.com/product-security/manifest-box) repository contains:

- **SBOMs** (Software Bill of Materials) for all Red Hat Konflux products
- **SQLite databases** for querying component/package data
- **Tools** for fetching and processing manifests

Data sources include Konflux, App Interface, SBOMer, Product Definitions, and Pyxis.

## Repository Size Warning

⚠️ The full repository is **~4.7 GB**:

| Component | Size |
|-----------|------|
| `manifests/` | 2.0 GB |
| `manifest-box-konflux.sqlite` | 402 MB |
| `tools/` | 101 MB |
| `.git/` | ~2 GB |

## Efficient Cloning Options

### Option 1: Sparse Checkout (Recommended)

Only checkout the files you need:

```bash
git clone --filter=blob:none --sparse \
    https://gitlab.cee.redhat.com/product-security/manifest-box.git
cd manifest-box
git sparse-checkout set manifests/konflux/openshift-ai
```

### Option 2: Skip Git LFS

Avoid downloading large binary files:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 \
    https://gitlab.cee.redhat.com/product-security/manifest-box.git
```

### Option 3: Download SQLite DB Only

If you only need to query the data:

```bash
curl -O https://gitlab.cee.redhat.com/product-security/manifest-box/-/raw/main/manifest-box-konflux.sqlite
```

### Option 4: Use a Remote VM

For large operations, use an internal Red Hat VM with better network access to GitLab.

### Option 5: Fetch One SBOM via GitLab API + Git LFS

Use this when you only need one or two SBOM JSON files for triage.
It avoids downloading the 400MB+ SQLite DB or cloning the full repository.

## Querying the SQLite Database

The main database for Konflux builds is `manifest-box-konflux.sqlite`.

### Discovering the Schema

```bash
# List all tables
sqlite3 manifest-box-konflux.sqlite ".tables"

# Show schema for a specific table
sqlite3 manifest-box-konflux.sqlite ".schema builds"
sqlite3 manifest-box-konflux.sqlite ".schema components"
sqlite3 manifest-box-konflux.sqlite ".schema build_components"
```

### Key Tables

| Table | Purpose |
|-------|---------|
| `builds` | Container image builds with manifest file paths |
| `components` | Packages/dependencies (name, version, purl, type) |
| `build_components` | Many-to-many relationship between builds and components |
| `streams` | Product streams |

### Common Queries

#### Find all builds for an image

```sql
SELECT * FROM builds 
WHERE name LIKE '%tensorflow%rocm%';
```

#### Check if a package exists in an image

```sql
SELECT b.name AS build_name, c.name AS component, c.version 
FROM builds b
JOIN build_components bc ON b.build_id = bc.build_id
JOIN components c ON bc.component_id = c.component_id
WHERE b.name LIKE '%tensorflow%rocm%' 
  AND c.name = 'feast';
```

#### Compare package versions across images

```sql
SELECT b.name AS build_name, c.name AS component, c.version 
FROM builds b
JOIN build_components bc ON b.build_id = bc.build_id
JOIN components c ON bc.component_id = c.component_id
WHERE c.name = 'feast'
ORDER BY b.name, c.version;
```

#### Find all components in a specific build

```sql
SELECT c.name, c.version, c.type
FROM builds b
JOIN build_components bc ON b.build_id = bc.build_id
JOIN components c ON bc.component_id = c.component_id
WHERE b.name = 'rhoai/odh-workbench-jupyter-datascience-cpu-py312-rhel9'
ORDER BY c.name;
```

## Practical Example: Validating CVE Reports

When security issues are filed against images, verify they're valid:

```bash
# 1. Clone or download the database
curl -O https://gitlab.cee.redhat.com/product-security/manifest-box/-/raw/main/manifest-box-konflux.sqlite

# 2. Check if the vulnerable package exists in the image
sqlite3 manifest-box-konflux.sqlite "
SELECT b.name, b.manifest_file, c.name, c.version 
FROM builds b
JOIN build_components bc ON b.build_id = bc.build_id
JOIN components c ON bc.component_id = c.component_id
WHERE b.name LIKE '%tensorflow%rocm%' 
  AND c.name = 'feast'
"
```

If the query returns results, the image contains the package and the CVE is valid.
If empty, the CVE may be a false positive.

## Understanding Version Differences

Different product versions may have different components. Always check the manifest file path to identify the version:

```sql
SELECT manifest_file, name 
FROM builds 
WHERE name LIKE '%tensorflow%rocm%';
```

Example output:
```bash
.../rhoai_odh-workbench-jupyter-tensorflow-rocm-py312-rhel9:v2.25.1-...json
.../rhoai_odh-workbench-jupyter-tensorflow-rocm-py312-rhel9:v3.0.0-...json
```

Then query each version separately to compare components.

## Analyzing Raw JSON SBOM Files

When the SQLite database doesn't provide enough detail (e.g., you need to know exactly WHERE a package was found), analyze the raw JSON SBOM files directly.

### Locating SBOM Files

SBOM files are stored at:
```text
https://gitlab.cee.redhat.com/product-security/manifest-box/-/tree/main/manifests/konflux/openshift-ai
```

Files are named according to:
- **Jira component field**: e.g., `odh-workbench-codeserver-py312-rhel9`
- **Image hash**: Included in filename for traceability

### Fetch One SBOM via GitLab API + Git LFS

For one-off CVE work, prefer this flow over downloading the SQLite database:

1. **Search the manifest tree for the component**
```bash
curl -s \
  "https://gitlab.cee.redhat.com/api/v4/projects/product-security%2Fmanifest-box/repository/tree?path=manifests/konflux/openshift-ai&per_page=1000" \
  | python3 -c "import sys, json; items = json.load(sys.stdin); [print(x['name']) for x in items if 'odh-workbench-codeserver-datascience-cpu-py312-rhel9' in x['name']]"
```

2. **Fetch the manifest file pointer**
```bash
encoded_path="manifests%2Fkonflux%2Fopenshift-ai%2Frhoai_odh-workbench-codeserver-datascience-cpu-py312-rhel9%40sha256%3Ad9ad95375705d41dfa4dc47a0ba20b45b0ad8ecb09579f140b2e2cf5b0a83087.json"
curl -s \
  "https://gitlab.cee.redhat.com/api/v4/projects/product-security%2Fmanifest-box/repository/files/${encoded_path}/raw?ref=main" \
  > sbom.pointer
```

3. **Extract the Git LFS object id and size**
```bash
oid=$(python3 -c "from pathlib import Path; lines = Path('sbom.pointer').read_text().splitlines(); print(lines[1].split()[1].split(':', 1)[1])")
size=$(python3 -c "from pathlib import Path; lines = Path('sbom.pointer').read_text().splitlines(); print(lines[2].split()[1])")
```

4. **Resolve the real download URL**
```bash
curl -s -X POST \
  "https://gitlab.cee.redhat.com/product-security/manifest-box.git/info/lfs/objects/batch" \
  -H "Accept: application/vnd.git-lfs+json" \
  -H "Content-Type: application/vnd.git-lfs+json" \
  -d "{\"operation\":\"download\",\"transfers\":[\"basic\"],\"objects\":[{\"oid\":\"${oid}\",\"size\":${size}}]}" \
  > lfs.json

download_url=$(python3 -c "import json; print(json.load(open('lfs.json'))['objects'][0]['actions']['download']['href'])")
curl -sL "${download_url}" > sbom.json
```

5. **Inspect the package location**
```bash
./uv run scripts/cve/sbom_analyze.py sbom.json undici
```

If you prefer a wrapper for this flow, use:
```bash
./uv run python scripts/cve/fetch_manifestbox_sbom.py --component odh-workbench-codeserver-datascience-cpu-py312-rhel9 --pick 2 --expect-version v3-3 --output sbom.json --package undici
```

Or use `--prefer-version` to auto-select the correct SBOM without guessing `--pick`:
```bash
./uv run python scripts/cve/fetch_manifestbox_sbom.py \
    --component odh-workbench-codeserver-datascience-cpu-py312-rhel9 \
    --prefer-version v3-3 \
    --output sbom.json --package undici
```
`--prefer-version` probes each candidate's `build_component` with a small HTTP Range
request (first 4KB) and picks the first match. This avoids downloading the wrong full
SBOM blob and re-trying.

Or use `--version-tag` for exact digest-based selection via the Pyxis catalog API (most
accurate, zero guessing):
```bash
python3 scripts/cve/fetch_manifestbox_sbom.py \
    --component odh-workbench-codeserver-datascience-cpu-py312-rhel9 \
    --version-tag v3.3 \
    --output sbom.json --package undici --insecure
```
`--version-tag` queries `catalog.redhat.com` (public, no auth) for the amd64 image digest
at the given tag, then matches it directly against the manifest-box SBOM filename. This is
a single HTTP call that gives an exact match -- no probing, no partial downloads, no
guessing.

If your environment cannot validate the internal GitLab certificate chain, add `--insecure`
to the helper script or `-k` to the manual `curl` commands above.

**Sandbox note**: `./uv run` may fail in sandboxed environments because `uv` writes
temp files outside the workspace (e.g., `~/.local/share/uv/tools/`). If that happens,
either request `all` permissions or invoke the script directly with `python3` when the
script does not require venv-specific dependencies.

If you need to run large downloads or batch probes on a remote host, see
`reference/remote-artifact-investigation.md`.

### Selecting the Right SBOM When Multiple Digests Match

Multiple SBOM files often exist for the same image name (one per product version / rebuild).
Do NOT guess based on filename ordering or `--pick` position.

**Best approach — exact digest via Pyxis (`--version-tag`):**
```bash
python3 scripts/cve/fetch_manifestbox_sbom.py \
    --component odh-workbench-jupyter-minimal-cpu-py312-rhel9 \
    --version-tag v3.3 \
    --output .artifacts/sbom/minimal-v3-3.json --insecure
```
This queries the Red Hat catalog API for the per-architecture image digest at the given
version tag, then matches the digest directly against manifest-box filenames. One public
API call, exact match, zero ambiguity.

**Good approach — probe `build_component` (`--prefer-version`):**
```bash
python3 scripts/cve/fetch_manifestbox_sbom.py \
    --component odh-workbench-jupyter-minimal-cpu-py312-rhel9 \
    --prefer-version v3-3 \
    --output .artifacts/sbom/minimal-v3-3.json --insecure
```
Fetches the first 4KB of each candidate SBOM to read `build_component` without
downloading the full blob. Use this when Pyxis is unavailable or the version tag format
does not match the catalog (e.g., pre-release builds not yet in the catalog).

**Fallback — manual pick with post-download verification:**
1. Check `build_component` in the downloaded JSON (e.g., `odh-workbench-jupyter-minimal-cpu-py312-v3-3`)
2. Confirm the version suffix matches the tracker version (`v3-3`, `v2-25`, etc.)
3. If mismatched, download the other candidate and re-check

Use `--expect-version` with the helper script to fail loudly on mismatch:
```bash
./uv run python scripts/cve/fetch_manifestbox_sbom.py \
    --component odh-workbench-jupyter-minimal-cpu-py312-rhel9 \
    --pick 1 --expect-version v3-3 \
    --output .artifacts/sbom/minimal-v3-3.json
```

**Anti-pattern:** "first/second matching digest" is never evidence by itself. Always verify `build_component`.

### How `--version-tag` Works (Pyxis Digest Resolution)

The manifest-box SBOM filenames embed the per-architecture image digest:
```text
rhoai_odh-workbench-jupyter-minimal-cpu-py312-rhel9@sha256:44c8c278...json
                                                          ^^^^^^^^^^
                                                          this is manifest_schema2_digest (amd64)
```

The Pyxis catalog API at `catalog.redhat.com` returns this exact digest when queried by
version tag:
```text
GET /v1/repositories/registry/registry.access.redhat.com/repository/rhoai/{component}/images
    ?filter=architecture==amd64;repositories.tags.name=={tag}
    &include=data.repositories.manifest_schema2_digest
    &page_size=1
```

The `--component` argument maps directly to the Pyxis repository path `rhoai/{component}`.
The `--version-tag` uses the catalog tag format (e.g., `v3.3`, `v2.25`) — note the dot, not
a dash. This differs from the `build_component` suffix format (`v3-3`, `v2-25`) used by
`--prefer-version` and `--expect-version`.

The Pyxis API is public and requires no authentication for read-only queries.

| Method | Flag | Accuracy | Network cost | When to use |
|--------|------|----------|-------------|-------------|
| Pyxis digest | `--version-tag v3.3` | Exact (digest match) | 1 public API call | Default — use whenever the image is in the Red Hat catalog |
| Build-component probe | `--prefer-version v3-3` | High (substring match) | 2-6 internal GitLab calls | When Pyxis is unavailable or the build is not yet in the catalog |
| Manual pick | `--pick N --expect-version v3-3` | Post-hoc verification | 1 full download per attempt | Last resort |

### Deriving `--component` From Jira `pscomponent:` Labels

Child vulnerability issues carry a `pscomponent:` label that maps directly to the manifest-box component substring:

1. Read the label value (e.g., `pscomponent:rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9`)
2. Strip the `rhoai/` prefix
3. Use the remainder as the `--component` argument

Example:
```text
pscomponent:rhoai/odh-pipeline-runtime-pytorch-cuda-py312-rhel9
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                  → --component odh-pipeline-runtime-pytorch-cuda-py312-rhel9
```

### Determining Product Version

The product version is in the first 10 lines of the JSON file:

```bash
# After downloading, check the version
head -10 sbom-file.json | jq -r '.source.name, .source.version'

# Or extract version from the descriptor section
head -50 sbom-file.json | jq -r '.descriptor.configuration // .source'
```

### Understanding the Syft JSON Structure

```json
{
  "artifacts": [],           // Package nodes discovered
  "artifactRelationships": [],// Edges between packages and files
  "files": [],               // File nodes discovered (with file metadata)
  "source": {},              // What was scanned (image, directory, etc.)
  "distro": {},              // Linux distribution discovered
  "descriptor": {},          // Syft version and configuration
  "schema": {}               // Schema version
}
```

Each package artifact contains:
- `name`, `version`, `type`: Package identification
- `foundBy`: Which cataloger discovered it (e.g., `npm-cataloger`, `python-package-cataloger`)
- `locations`: Array of paths where the package was found
- `purl`: Package URL for cross-tool compatibility
- `metadata`: Ecosystem-specific fields

### Key JQ Queries for CVE Investigation

#### Find a package and its location

This is the most important query for CVE investigation—finding WHERE a vulnerable package exists:

```bash
# Find package by name and show its location
jq '.artifacts[] | select(.name == "esbuild") | {name, version, type, foundBy, locations: [.locations[].path]}' sbom.json

# Partial name match (useful when you don't know exact package name)
jq '.artifacts[] | select(.name | test("esbuild"; "i")) | {name, version, type, foundBy, locations: [.locations[].path]}' sbom.json
```

Example output showing where to look for the vulnerable component:
```json
{
  "name": "esbuild",
  "version": "0.17.14",
  "type": "npm",
  "foundBy": "javascript-package-cataloger",
  "locations": [
    "/usr/lib/code-server/lib/vscode/extensions/php/package.json"
  ]
}
```

#### Group packages by ecosystem type

```bash
jq '[.artifacts[]] | group_by(.type) | map({type: .[0].type, count: length}) | sort_by(.count) | reverse' sbom.json
```

#### Find all packages at a specific path

```bash
jq '.artifacts[] | select(.locations[].path | contains("/code-server/")) | {name, version, path: .locations[0].path}' sbom.json
```

#### Find packages by cataloger (ecosystem)

```bash
# Find all npm packages
jq '.artifacts[] | select(.type == "npm") | {name, version, locations: [.locations[].path]}' sbom.json

# Find all Python packages
jq '.artifacts[] | select(.type == "python") | {name, version, locations: [.locations[].path]}' sbom.json

# Find all RPM packages
jq '.artifacts[] | select(.type == "rpm") | {name, version}' sbom.json
```

#### Extract Package URLs (PURLs) for a package

PURLs are useful for cross-referencing with vulnerability databases:

```bash
jq '.artifacts[] | select(.name == "openssl") | {name, version, purl}' sbom.json
```

### Python Script for SBOM Analysis

For more complex analysis, use Python:

```python
#!/usr/bin/env python3
"""Analyze syft SBOM JSON files for CVE investigation."""

import json
import sys
from pathlib import Path


def find_package(sbom_path: str, package_name: str, case_insensitive: bool = True) -> list:
    """Find a package in the SBOM and return its details."""
    with open(sbom_path) as f:
        sbom = json.load(f)
    
    results = []
    for artifact in sbom.get("artifacts", []):
        name = artifact.get("name", "")
        if case_insensitive:
            match = package_name.lower() in name.lower()
        else:
            match = package_name == name
        
        if match:
            results.append({
                "name": name,
                "version": artifact.get("version"),
                "type": artifact.get("type"),
                "foundBy": artifact.get("foundBy"),
                "locations": [loc.get("path") for loc in artifact.get("locations", [])],
                "purl": artifact.get("purl"),
            })
    return results


def get_sbom_info(sbom_path: str) -> dict:
    """Extract SBOM metadata (source, version, etc.)."""
    with open(sbom_path) as f:
        sbom = json.load(f)
    
    return {
        "source_name": sbom.get("source", {}).get("name"),
        "source_version": sbom.get("source", {}).get("version"),
        "distro": sbom.get("distro", {}).get("name"),
        "distro_version": sbom.get("distro", {}).get("version"),
        "syft_version": sbom.get("descriptor", {}).get("version"),
        "artifact_count": len(sbom.get("artifacts", [])),
    }


def summarize_by_type(sbom_path: str) -> dict:
    """Summarize packages by ecosystem type."""
    with open(sbom_path) as f:
        sbom = json.load(f)
    
    counts = {}
    for artifact in sbom.get("artifacts", []):
        pkg_type = artifact.get("type", "unknown")
        counts[pkg_type] = counts.get(pkg_type, 0) + 1
    
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python sbom_analyze.py <sbom.json> <package_name>")
        sys.exit(1)
    
    sbom_file = sys.argv[1]
    package_name = sys.argv[2]
    
    print(f"=== SBOM Info ===")
    info = get_sbom_info(sbom_file)
    for k, v in info.items():
        print(f"  {k}: {v}")
    
    print(f"\n=== Searching for '{package_name}' ===")
    results = find_package(sbom_file, package_name)
    
    if not results:
        print(f"  Package '{package_name}' not found")
    else:
        for r in results:
            print(f"\n  {r['name']}@{r['version']}")
            print(f"    Type: {r['type']}")
            print(f"    Found by: {r['foundBy']}")
            print(f"    Locations: {r['locations']}")
            print(f"    PURL: {r['purl']}")
```

### Workflow: Investigating a CVE

1. **Get the Jira component name** from the CVE ticket
2. **Download the relevant SBOM**:
   ```bash
   # Using sparse checkout
   git clone --filter=blob:none --sparse \
       https://gitlab.cee.redhat.com/product-security/manifest-box.git
   cd manifest-box
   git sparse-checkout set manifests/konflux/openshift-ai
   
   # Find files for your component
   ls manifests/konflux/openshift-ai/*codeserver*
```

3. **Check product version** from the first few lines:
   ```bash
   head -20 <sbom-file>.json | jq '.source'
```

4. **Search for the vulnerable package**:
   ```bash
   jq '.artifacts[] | select(.name | test("vulnerable-pkg"; "i")) | {name, version, type, locations: [.locations[].path]}' <sbom-file>.json
```

5. **Determine remediation path** based on the location:
   - `/lib/apk/db/installed` → Alpine system package (update base image or install newer version)
   - `/usr/lib/python3.*/site-packages/` → Python package (update in pyproject.toml/requirements.txt)
   - `/node_modules/` or `.../package.json` → npm package (update in package.json or parent package)
   - `/usr/share/gems/` → Ruby gem

### Common Location Patterns

| Location Pattern | Ecosystem | Remediation Approach |
|------------------|-----------|---------------------|
| `/lib/apk/db/installed` | Alpine APK | Update base image or `apk add` |
| `/var/lib/dpkg/status` | Debian/Ubuntu | Update base image or `apt install` |
| `/var/lib/rpm/` | RHEL/Fedora | Update base image or `dnf install` |
| `/usr/lib/python*/site-packages/` | Python (system) | pip install or pyproject.toml |
| `/opt/app-root/lib/python*/site-packages/` | Python (venv) | pip install or pyproject.toml |
| `*/node_modules/*/package.json` | npm | package.json or parent package update |
| `/usr/share/gems/` | Ruby | Gemfile update |
| `*.jar` | Java | pom.xml or build.gradle |

### Interpreting `sourceInfo`

`sourceInfo` is often the fastest way to tell whether a package is truly shipped in the image or only present in source-scan material.

| `sourceInfo` pattern | Interpretation | Typical action |
|----------------------|----------------|----------------|
| `/usr/lib/code-server/.../node_modules/...` | Real shipped code-server npm component | Treat as real exposure |
| `/tests/browser/pnpm-lock.yaml` or other `/tests/...` path | Test-only or source-scan finding | Likely VEX `Component not Present` review |
| `/jupyter/utils/addons/pnpm-lock.yaml` | Currently a source-scan artifact from repository content, not shipped runtime image content | Usually review for VEX `Component not Present` unless image-specific evidence shows otherwise |
| `/usr/lib/python*/site-packages/` or `/opt/app-root/lib/python*/site-packages/` | Real shipped Python dependency | Treat as real image content |
| `/var/lib/rpm/` | Base OS package | Base image / RPM remediation path |
| `/usr/bin/skopeo` or another shipped CLI binary | Real shipped RPM/Go tool | Not VEX; check Red Hat security data, Bugzilla, and errata for package-fix availability |

### After You Confirm A Shipped RPM / CLI Tool

If manifest-box shows the vulnerable component via a shipped binary or RPM-managed tool path:
1. Do **not** route the tracker to VEX `Component not Present`
2. Check Red Hat security data to see whether the package is still `Affected` or already `Fixed`
3. Check the canonical Product Security Bugzilla and any released errata for the same CVE
4. If no fixed Red Hat package exists yet, the best current triage outcome is usually:
   real shipped exposure, but `ai-nonfixable` pending fixed RPM / erratum

## Fetching SBOMs Directly from Quay.io (Without manifest-box)

Konflux attaches SBOMs to built images in the OCI registry as tagged artifacts. You can
fetch them directly from `quay.io` without needing access to the internal manifest-box
GitLab repository.

### Prerequisites

Install one of: `oras`, `cosign`, or `skopeo`.

```bash
brew install oras        # recommended — cleanest workflow
brew install cosign      # alternative
brew install skopeo      # useful for inspecting image metadata
```

### Step 1: Find the Image Digest

SBOMs are stored under tags derived from the image digest. First, get the per-architecture
digest (not the manifest list digest):

```bash
# List available tags
skopeo list-tags docker://quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9 \
  | python3 -c "import sys,json; [print(t) for t in sorted(json.load(sys.stdin)['Tags']) if not t.startswith('sha256-')]"

# Get the amd64 digest from a version tag
skopeo inspect docker://quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9:rhoai-3.4-linux-x86-64 \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['Digest'])"
# → sha256:8a1646277f754072416b4256bc47d299c754c50647ca32d5aeb469b3169ce0ee
```

### Step 2: Download the SBOM

The SBOM is stored at the tag `sha256-<digest>.sbom` (replace `:` with `-`):

```bash
# Using oras (recommended)
DIGEST="8a1646277f754072416b4256bc47d299c754c50647ca32d5aeb469b3169ce0ee"
IMAGE="quay.io/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9"

oras copy "${IMAGE}:sha256-${DIGEST}.sbom" --to-oci-layout /tmp/sbom-download

# The SBOM is the largest blob in the layout
ls -lS /tmp/sbom-download/blobs/sha256/ | head -3
# Copy out the SBOM JSON (it's the blob with media type text/spdx+json)
SBOM_BLOB=$(ls -S /tmp/sbom-download/blobs/sha256/ | head -1)
cp "/tmp/sbom-download/blobs/sha256/${SBOM_BLOB}" sbom.json
```

### Step 3: Analyze the SBOM

The Konflux SBOM is SPDX 2.3 format. Key fields per package:
- `name`, `version`: Package identification
- `sourceInfo`: Where the package was found (critical for false positive detection)
- `externalRefs`: PURLs for cross-referencing with vulnerability databases

```bash
# Quick summary: list all sourceInfo patterns
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

# Search for a specific package
python3 -c "
import json
with open('sbom.json') as f:
    sbom = json.load(f)
for p in sbom['packages']:
    if 'requests' in p.get('name','').lower():
        print(f\"{p['name']} {p.get('version','')}  — {p.get('sourceInfo','')[:100]}\")
"
```

### Other Tags Available per Digest

Konflux publishes several artifacts alongside each image:

| Tag suffix | Content |
|------------|---------|
| `.sbom` | SPDX SBOM (Software Bill of Materials) |
| `.att` | In-toto attestation (build provenance) |
| `.sig` | Cosign signature |
| `.src` | Source container reference |
| `.dockerfile` | Dockerfile used for the build |

```bash
# Download the build attestation
oras copy "${IMAGE}:sha256-${DIGEST}.att" --to-oci-layout /tmp/att-download

# Download the Dockerfile
oras copy "${IMAGE}:sha256-${DIGEST}.dockerfile" --to-oci-layout /tmp/dockerfile-download
```

### SPDX vs Syft Format

- **manifest-box** SBOMs use **Syft JSON** format (`.artifacts[]`, `.source`, `.descriptor`)
- **Quay.io/Konflux** SBOMs use **SPDX 2.3** format (`.packages[]`, `.relationships[]`)

The field mapping:

| Syft JSON | SPDX 2.3 | Description |
|-----------|----------|-------------|
| `.artifacts[].name` | `.packages[].name` | Package name |
| `.artifacts[].version` | `.packages[].versionInfo` | Version |
| `.artifacts[].locations[].path` | `.packages[].sourceInfo` | Where found |
| `.artifacts[].purl` | `.packages[].externalRefs[].referenceLocator` | Package URL |
| `.artifacts[].foundBy` | (not directly available) | Cataloger that found it |

## Running newcli on macOS

newcli is ProdSec's CLI for querying manifest-box and deptopia. It is not on PyPI but can
be installed from the internal GitLab repo via uvx:

```bash
# Use the wrapper script (handles clone + deps automatically)
.agents/tools/newcli-wrapper.sh --help

# Or manually:
git clone --depth 1 https://gitlab.cee.redhat.com/prodsec-dev/newtopia-cli.git /tmp/newtopia-cli
uvx --no-config \
  --from /tmp/newtopia-cli/python/newtopia_cli \
  --with /tmp/newtopia-cli/python/deptopia-client \
  --with requests --with appdirs --with packageurl-python --with argcomplete \
  newcli --help
```

### Common newcli Queries

```bash
# Search for a package across all products (verbose output)
newcli -vvv -s -e pypi wheel

# Filter by ecosystem
newcli -vvv -s -e npm undici

# Find which streams ship a specific image component
newcli -a odh-workbench-jupyter-minimal-cpu-py312-rhel9
```

### newcli Data Sources

newcli queries **two** backends:
1. **Deptopia REST API** (fast, no download) — covers Brew/CPaaS builds only
2. **manifest-box SQLite** (~400MB download) — covers Konflux builds

For notebooks (Konflux), the SQLite download is unavoidable on first run. Set
`konflux_path` in `~/.config/newcli/config.ini` to use a pre-downloaded local file.

## Deptopia vs manifest-box

| | Deptopia | manifest-box |
|---|---------|-------------|
| Build system | Brew / CPaaS | Konflux |
| Access | REST API (fast) | SQLite download (~400MB) |
| Queried by | newcli (automatic), direct API | newcli (automatic) |
| Products | Older RHOAI versions (pre-Konflux) | Current RHOAI versions |

## Atlas/Trustify (Next-Gen)

Atlas (Red Hat Trusted Profile Analyzer) is the next-gen SBOM management platform replacing
manifest-box and deptopia. Built on [Trustify](https://github.com/guacsec/trustify) (open-source Rust).

- **Live at**: `https://atlas.build.devshift.net/`
- **Swagger UI**: `https://atlas.build.devshift.net/swagger-ui/`
- **Auth**: Red Hat Employee SSO (OIDC)
- **API**: 49 endpoints at `/api/v2/` — SBOMs, PURLs, vulnerabilities, advisories, products
- **Status**: In production, coverage expanding. ProdSec is migrating from manifest-box.

## Related Tools

- **NewCLI** (`newtopia-cli`): Uses manifest-box data for vulnerability queries
- **Syft**: Used to generate SBOMs from container images
- **Cosign**: Used to pull SBOMs from container registries
- **ORAS**: OCI Registry As Storage — fetch any OCI artifact (SBOMs, attestations, etc.)
- **Skopeo**: Inspect and copy container images and metadata
- **Atlas/Trustify**: Next-gen SBOM platform at `atlas.build.devshift.net`

## References

- [manifest-box GitLab Repository](https://gitlab.cee.redhat.com/product-security/manifest-box)
- [NewCLI (newtopia-cli)](https://gitlab.cee.redhat.com/prodsec-dev/newtopia-cli)
- [Product Definitions](https://gitlab.cee.redhat.com/prodsec/product-definitions)
- [Atlas/Trustify](https://atlas.build.devshift.net/) (requires Employee SSO)
- [Trustify source code](https://github.com/guacsec/trustify)
- [ProdSec Scanning Reference](prodsec-scanning.md) — full API landscape and false positive handling

---

## Footnotes

### SQL Schema Discovery Tricks

When working with an unfamiliar SQLite database, use these commands to explore:

```bash
# List all tables
sqlite3 database.sqlite ".tables"

# Show full schema (all CREATE statements)
sqlite3 database.sqlite ".schema"

# Show schema for specific table
sqlite3 database.sqlite ".schema tablename"

# Show column info (pragma)
sqlite3 database.sqlite "PRAGMA table_info(tablename);"

# Sample data from a table
sqlite3 database.sqlite "SELECT * FROM tablename LIMIT 5;"

# Find foreign key relationships
sqlite3 database.sqlite "PRAGMA foreign_key_list(tablename);"
```

### Understanding the manifest-box Data Model

```text
streams (product streams)
    └── builds (container image builds)
            └── build_components (junction table)
                    └── components (packages/dependencies)
```

The `build_components` table is a many-to-many junction table that links builds to their components. To find what packages are in an image, you must JOIN all three tables:

```sql
SELECT b.name, c.name, c.version
FROM builds b
JOIN build_components bc ON b.build_id = bc.build_id
JOIN components c ON bc.component_id = c.component_id
WHERE ...
```

### Key Learnings from RHOAI Feast CVE Investigation

1. **SBOM reflects built images, not source code**: The pyproject.toml in git may differ from what's in shipped images
2. **Check version-specific SBOMs**: v2.25 and v3.0 may have different components
3. **Dependency conflicts cause removals**: Feast was removed from tensorflow-rocm due to numpy version conflicts
4. **Scanner uses SBOM data**: Vulnerabilities are filed based on SBOM contents, not source code analysis
