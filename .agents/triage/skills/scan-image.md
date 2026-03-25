# Skill: Container Vulnerability Scanning Tools Guide

This guide documents vulnerability scanning tools and methodologies for investigating CVEs in container images, based on real-world investigations of CVE-2025-13465 (lodash), CVE-2025-15284 (qs), and CVE-2025-14178 (PHP false positive).

## Overview

When investigating CVE reports for container images, multiple scanning approaches are needed:

1. **SBOM Analysis** - Understand what packages are present
2. **Vulnerability Scanning** - Check for known CVEs
3. **Filesystem Inspection** - Verify actual component presence
4. **Scanner Comparison** - Cross-validate findings

## Tools Matrix

| Tool | Purpose | Strengths | Limitations | Use When |
|------|---------|-----------|-------------|----------|
| **Syft** | SBOM generation | Comprehensive, multi-ecosystem | No vulnerability matching | Need to catalog packages |
| **Grype** | Vulnerability scanning | Fast, accurate, multi-ecosystem | Requires updated database | Primary CVE verification |
| **Trivy** | Vulnerability scanning | Container-native, comprehensive | Large database downloads | Secondary verification |
| **Clair** | Vulnerability scanning | Red Hat/Konflux standard | No npm matcher | Konflux pipeline checks |
| **OSV-Scanner** | Vulnerability scanning | Google OSV database, layer-aware | Requires Docker/tar | OSV database verification |
| **OpenSCAP** | Compliance/CVE scanning | Red Hat OVAL definitions, authoritative | OVAL files required | RPM package verification |
| **sbom_analyze.py** | SBOM querying | Fast package search, Syft+SPDX support | No vulnerability data | Quick package location |

## Tool 1: Syft - SBOM Generation

### Purpose
Generate comprehensive Software Bill of Materials from container images.

### Installation

```bash
# macOS
brew install syft

# Linux
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin
```

### Usage

```bash
# Generate SBOM from container image
syft registry.redhat.io/rhoai/odh-workbench-jupyter-datascience-cpu-py312-rhel9@sha256:abc123... -o json > sbom.json

# Generate SBOM from local image
syft podman:image-name:tag -o json > sbom.json

# Generate SBOM with specific format
syft image:tag -o spdx-json > sbom-spdx.json
syft image:tag -o cyclonedx-json > sbom-cdx.json
```

### Real Example: CVE-2025-14178 Investigation

```bash
# On remote server with pulled image
ssh root@100.75.146.79 "syft registry.redhat.io/rhoai/odh-workbench-codeserver-datascience-cpu-py312-rhel9@sha256:4fedf0... -o json > /tmp/codeserver-fresh-sbom.json"

# Result: 29MB SBOM with 2314+ packages
```

### Output Format

```json
{
  "artifacts": [
    {
      "name": "php",
      "version": "1.0.0",
      "type": "npm",
      "foundBy": "javascript-package-cataloger",
      "locations": [
        {
          "path": "/usr/lib/code-server/lib/vscode/extensions/php/package.json"
        }
      ],
      "purl": "pkg:npm/php@1.0.0"
    }
  ]
}
```

### Lessons Learned

- **✅ Best for**: Creating comprehensive package inventory
- **⚠️ Large output**: 20-30MB for typical workbench images
- **⚠️ No CVE data**: Only catalogs packages, doesn't check vulnerabilities
- **✅ Multi-ecosystem**: Detects RPM, npm, Python, Go, Java, Ruby, etc.

## Tool 2: Grype - Vulnerability Scanning

### Purpose
Primary vulnerability scanner with comprehensive CVE database.

### Installation

```bash
# macOS
brew install grype

# Linux
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin
```

### Usage

```bash
# Scan container image directly
grype registry.redhat.io/rhoai/image:tag

# Scan from SBOM (faster, no image pull needed)
grype sbom:/path/to/sbom.json

# JSON output
grype sbom:/path/to/sbom.json -o json > grype-results.json

# Include all vulnerabilities (not just fixable)
grype sbom:/path/to/sbom.json --only-fixed=false

# Update vulnerability database
grype db update
```

### Real Example: CVE-2025-15284 Investigation

```bash
# Scan for qs npm package vulnerability
grype sbom:/tmp/workbench-sbom.json -o table | grep -i "qs\|CVE-2025-15284"

# Result: 984 total vulnerabilities, 0 PHP-related (CVE-2025-14178)
grype registry.redhat.io/rhoai/odh-workbench-codeserver-datascience-cpu-py312-rhel9@sha256:4fedf0... -o table
# Total: 984 vulnerabilities
# PHP CVEs: 0 (correctly ignored VSCode extensions)
```

### Output Interpretation

```bash
NAME                    INSTALLED    FIXED-IN     TYPE    VULNERABILITY   SEVERITY
lodash                  4.17.21      (none)       npm     CVE-2025-13465  High
```

**Key fields:**
- `FIXED-IN: (none)` = No fix available yet
- `TYPE` = Package ecosystem (critical for false positive detection)

### Lessons Learned

- **✅ Ecosystem-aware**: Correctly distinguishes npm `php` (VSCode extension) from PHP runtime
- **✅ Comprehensive**: Checks all package types
- **✅ Fast**: ~1 minute for SBOM scan
- **⚠️ Database age**: Check with `grype db status`
- **✅ Primary tool**: Use this first for CVE verification

## Tool 3: Trivy - Container Security Scanner

### Purpose
Alternative comprehensive vulnerability scanner with container-native features.

### Installation

```bash
# macOS
brew install trivy

# Linux (dnf/yum)
dnf install trivy
```

### Usage

```bash
# Scan container image
trivy image registry.redhat.io/rhoai/image:tag

# Scan with high/critical only
trivy image --severity HIGH,CRITICAL image:tag

# JSON output
trivy image --format json --output results.json image:tag

# Scan SBOM
trivy sbom /path/to/sbom.json

# Update database
trivy image --download-db-only
```

### Real Example: CVE-2025-14178 Verification

```bash
trivy image registry.redhat.io/rhoai/odh-workbench-codeserver-datascience-cpu-py312-rhel9@sha256:4fedf0... 2>&1 | grep -i "php\|CVE-2025-14178"

# Showed PHP extensions with 0 vulnerabilities
# CVE-2025-14178: NOT reported
```

### Lessons Learned

- **✅ Container-optimized**: Better layer analysis than general scanners
- **✅ Ecosystem-aware**: Like Grype, correctly identifies package types
- **⚠️ Database size**: Downloads can be large
- **✅ Good for cross-validation**: Use alongside Grype for confidence

## Tool 4: Clair - Konflux/Quay Scanner

### Purpose
Red Hat's official container vulnerability scanner used in Konflux CI/CD pipelines.

### Installation

```bash
# Pull Clair-in-CI image (contains clair-action CLI)
podman pull quay.io/konflux-ci/clair-in-ci:v1
```

### Usage

```bash
# Run clair-action report
podman run --rm --privileged \
  quay.io/konflux-ci/clair-in-ci:v1 \
  clair-action report \
  --image-ref=registry.redhat.io/rhoai/image@sha256:abc... \
  --format=clair > clair-report.json

# With authentication
podman run --rm --privileged \
  -v ~/.docker/config.json:/root/.docker/config.json:ro \
  quay.io/konflux-ci/clair-in-ci:v1 \
  clair-action report \
  --image-ref=registry.redhat.io/rhoai/image@sha256:abc... \
  --docker-config-dir=/root/.docker \
  --format=clair
```

### Available Matchers

**Clair supports** (from libvuln):
- gobin, oracle, rhel, aws-matcher, java-maven
- python, ruby-gem, debian-matcher, rhel-container-matcher
- ubuntu-matcher, alpine-matcher, photon, suse

**Missing**: ❌ npm, javascript, node

### Real Example: CVE-2025-14178 Investigation

```bash
clair-action report --image-ref=registry.redhat.io/rhoai/odh-workbench-codeserver-datascience-cpu-py312-rhel9@sha256:4fedf0...

# Result:
# - 97 total vulnerabilities (RPM, Python only)
# - 0 PHP packages detected (no npm matcher)
# - 0 CVE-2025-14178 (correctly ignored)
```

### Lessons Learned

- **⚠️ No npm support**: Cannot detect npm packages at all
- **✅ RPM-focused**: Excellent for RHEL base images
- **✅ Konflux standard**: What actually runs in CI/CD
- **⚠️ Authentication tricky**: Needs proper docker config

## Tool 5: OSV-Scanner - Google's OSV Database

### Purpose
Scan using Google's Open Source Vulnerabilities database (same source RHTPA uses).

### Installation

```bash
# Download latest release
curl -sSfL https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64 -o /usr/local/bin/osv-scanner
chmod +x /usr/local/bin/osv-scanner
```

### Usage

```bash
# Scan container image (requires docker/podman tar export)
podman save image:tag -o image.tar
osv-scanner scan image --archive image.tar --format json > osv-results.json

# Scan SBOM
osv-scanner --sbom=/path/to/sbom.json --format json > results.json

# Scan source directory
osv-scanner scan source -r /path/to/project
```

### Real Example: CVE-2025-14178 Verification

```bash
# Exported 3.6GB image to tar
podman save registry.redhat.io/rhoai/odh-workbench-codeserver...@sha256:4fedf0... -o codeserver-image.tar

# Scanned with OSV
osv-scanner scan image --archive codeserver-image.tar --format json > osv-results.json

# Result:
# - Total vulnerabilities: 135
# - CVE-2025-14178: NOT FOUND ❌
# - PHP packages: 0 vulnerabilities
```

### Lessons Learned

- **✅ RHTPA's data source**: Uses same OSV database as Red Hat Trusted Profile Analyzer
- **✅ Authoritative for npm**: Excellent npm/JavaScript coverage
- **⚠️ Requires tar export**: Can't scan images directly with podman
- **✅ Critical validation**: Proves what RHTPA backend would report

## Tool 6: OpenSCAP - Red Hat OVAL Scanner

### Purpose
Official Red Hat compliance and vulnerability scanner using OVAL definitions.

### Installation

```bash
# RHEL/Fedora
dnf install openscap-scanner openscap-utils

# Includes oscap-podman for container scanning
```

### Usage

```bash
# Download RHEL OVAL definitions
curl -sSfL "https://access.redhat.com/security/data/oval/v2/RHEL9/rhel-9.oval.xml.bz2" -o rhel-9.oval.xml.bz2
bunzip2 rhel-9.oval.xml.bz2

# Scan container image
oscap-podman <image_id> oval eval --results results.xml --report report.html rhel-9.oval.xml

# Check specific advisory result
grep "oval:com.redhat.rhsa:def:20261429" results.xml | grep "result="
```

### Real Example: CVE-2025-14178 (RHSA-2026:1429) Verification

```bash
# Mounted image and scanned with RHEL9 OVAL
oscap-podman e4f178d42292 oval eval --results oscap-results.xml rhel-9.oval.xml

# Search for PHP advisory
grep "def:20261429" oscap-results.xml | grep "result="
# Result: <definition definition_id="oval:com.redhat.rhsa:def:20261429" result="false">

# Interpretation:
# - OVAL definition exists for CVE-2025-14178
# - Checks for PHP RPM packages (php:8.3 module)
# - Result: FALSE = PHP not installed ✅
```

### OVAL Definition Structure

```xml
<definition id="oval:com.redhat.rhsa:def:20261429">
  <criteria operator="AND">
    <criterion test_ref="..." comment="Module php:8.3 is enabled"/>
    <criterion test_ref="..." comment="php is earlier than 0:8.3.29-1..."/>
    <criterion test_ref="..." comment="php-cli is earlier than 0:8.3.29-1..."/>
  </criteria>
</definition>
```

**Key insight:** OVAL checks for **RPM packages**, not npm packages. npm `php` (editor extension) ≠ RPM `php` (runtime).

### Lessons Learned

- **✅ Authoritative for RHEL**: Red Hat's official CVE definitions
- **✅ RPM-focused**: Checks system packages (php, php-cli, php-common)
- **⚠️ No npm/JavaScript**: Doesn't check non-RPM packages
- **✅ Compliance**: Use for regulatory compliance scans
- **⚠️ Requires OVAL files**: Must download definitions first

## Tool 7: Custom sbom_analyze.py

### Purpose
Quick package search and location finding in SBOM files.

### Installation

```bash
# Already in repository
/Users/jdanek/IdeaProjects/notebooks/scripts/sbom_analyze.py
```

### Usage

```bash
# Search for package
python3 scripts/sbom_analyze.py /path/to/sbom.json packagename

# Show SBOM info
python3 scripts/sbom_analyze.py /path/to/sbom.json --info

# Find packages at path
python3 scripts/sbom_analyze.py /path/to/sbom.json --path /opt/app-root

# JSON output
python3 scripts/sbom_analyze.py /path/to/sbom.json packagename --json
```

### Real Examples

**CVE-2025-15284 (qs package):**
```bash
$ python3 scripts/sbom_analyze.py /tmp/workbench-sbom.json qs

=== Searching for 'qs' ===
  Found 2 matching package(s):

  @types/qs@6.9.18
    Type: npm
    Locations:
      - /jupyter/utils/addons/pnpm-lock.yaml
    PURL: pkg:npm/%40types/qs@6.9.18

  qs@6.13.0
    Type: npm
    Locations:
      - /jupyter/utils/addons/pnpm-lock.yaml
    PURL: pkg:npm/qs@6.13.0
```

**CVE-2025-14178 (PHP false positive):**
```bash
$ python3 scripts/sbom_analyze.py /tmp/codeserver-sbom.json php

  php@1.0.0
    Type: npm
    Locations:
      - /usr/lib/code-server/lib/vscode/extensions/php/package.json
    PURL: pkg:npm/php@1.0.0
```

### Lessons Learned

- **✅ Fastest**: Instant results, no scanning delay
- **✅ Dual format**: Supports both Syft and SPDX (manifest-box)
- **✅ Location-aware**: Shows exact file paths
- **⚠️ No vulnerability data**: Must use separate scanner for CVEs
- **✅ First step**: Always start with this for quick package location

## Complete Investigation Workflow

### Step 1: Obtain SBOM

**Option A: Download from manifest-box** (if available)
```bash
curl -s -k "https://gitlab.cee.redhat.com/product-security/manifest-box/-/raw/main/manifests/konflux/openshift-ai/rhoai_component@sha256:digest.json" -o sbom.json
```

**Option B: Generate fresh SBOM**
```bash
# Pull image first (if needed)
podman login registry.redhat.io
podman pull registry.redhat.io/rhoai/image@sha256:digest

# Generate SBOM
syft registry.redhat.io/rhoai/image@sha256:digest -o json > fresh-sbom.json
```

### Step 2: Quick Package Search

```bash
# Find the vulnerable package
python3 scripts/sbom_analyze.py sbom.json <package-name>

# Example: CVE-2025-13465
python3 scripts/sbom_analyze.py sbom.json lodash
# Output shows: lodash@4.17.21 at /jupyter/utils/addons/pnpm-lock.yaml
```

### Step 3: Verify with Multiple Scanners

```bash
# Primary: Grype
grype sbom:sbom.json -o table | grep "<package-name>"

# Secondary: Trivy
trivy image image:tag 2>&1 | grep -i "<package-name>\|<CVE-ID>"

# OSV verification (if npm/Go/Python)
osv-scanner --sbom=sbom.json --format json > osv.json
cat osv.json | jq '.results[].packages[].vulnerabilities[]? | select(.id | contains("<CVE-ID>"))'
```

### Step 4: Filesystem Verification (for false positives)

```bash
# Pull and mount image
podman pull registry.redhat.io/rhoai/image@sha256:digest
IMAGE_ID=$(podman images --format="{{.ID}}" --filter="reference=*@sha256:digest" | head -1)
MOUNT_DIR=$(podman image mount $IMAGE_ID)

# Search for actual runtime/binaries
find $MOUNT_DIR -name "php" -type f -executable 2>/dev/null
rpm -qa --root $MOUNT_DIR | grep -i php

# Check if binary exists and get version
chroot $MOUNT_DIR /usr/bin/php --version 2>/dev/null || echo "No PHP interpreter"

# Unmount when done
podman image unmount $IMAGE_ID
```

### Step 5: OVAL Verification (for RPM packages)

```bash
# Download RHEL OVAL definitions
curl -sSfL "https://access.redhat.com/security/data/oval/v2/RHEL9/rhel-9.oval.xml.bz2" -o rhel-9.oval.xml.bz2
bunzip2 rhel-9.oval.xml.bz2

# Scan with OpenSCAP
oscap-podman $IMAGE_ID oval eval --results results.xml rhel-9.oval.xml

# Check specific advisory
grep "def:<advisory_number>" results.xml | grep "result="
```

## Real-World Case Studies

### Case 1: CVE-2025-13465 (Lodash) - SOURCE-SCAN ARTIFACT

**Package:** `lodash@4.17.21`  
**Location:** `/jupyter/utils/addons/pnpm-lock.yaml`  
**Type:** npm (repository source-scan artifact in the current image layout)

**Investigation:**
```bash
# 1. SBOM search
python3 scripts/sbom_analyze.py workbench-sbom.json lodash
# Found: lodash@4.17.21

# 2. Grype scan
grype sbom:workbench-sbom.json | grep lodash
# Confirmed: CVE-2025-13465 present

# 3. Source code verification
grep "lodash" jupyter/utils/addons/pnpm-lock.yaml
# Current: lodash@4.17.21 (vulnerable)

# 4. Git history
git log -- jupyter/utils/addons/pnpm-lock.yaml
# No fix found yet
```

**Conclusion:** Do not assume runtime exposure from this path alone. In the current image layout, this should trigger image-specific SBOM verification and likely VEX `Component not Present` review.

### Case 2: CVE-2025-15284 (qs) - FIXED IN SOURCE

**Package:** `qs@6.13.0` (vulnerable) → `qs@6.14.1` (fixed)  
**Location:** `/jupyter/utils/addons/pnpm-lock.yaml`  
**Type:** npm (repository source-scan artifact in the current image layout)

**Investigation:**
```bash
# 1. SBOM shows old build
python3 scripts/sbom_analyze.py workbench-sbom.json qs
# Found: qs@6.13.0 (VULNERABLE, < 6.14.1)

# 2. Check current source
grep "qs@" jupyter/utils/addons/pnpm-lock.yaml
# Current: qs@6.14.1 (FIXED ✅)

# 3. Git history
git log --patch -S "qs@6.14.1" -- jupyter/utils/addons/pnpm-lock.yaml
# Fixed: Jan 15, 2026, commit 29d8e26ee, PR #2804
```

**Conclusion:** Already fixed in source, close with VEX "Component not Present" (builds after Jan 15).

### Case 3: CVE-2025-14178 (PHP) - FALSE POSITIVE

**Package:** `php@1.0.0` and `php-language-features@1.0.0`  
**Type:** npm (VSCode editor extensions)  
**CVE:** Affects PHP runtime `array_merge()` function

**Investigation:**
```bash
# 1. SBOM analysis
python3 scripts/sbom_analyze.py codeserver-sbom.json php
# Found: php@1.0.0 (npm), Location: /usr/lib/code-server/lib/vscode/extensions/php/package.json

# 2. Filesystem inspection
podman image mount $IMAGE_ID
find $MOUNT_DIR -name "php" -type f -executable
# Result: NO PHP binaries found

rpm -qa --root $MOUNT_DIR | grep -i php
# Result: NO PHP RPM packages

# 3. Scanner verification (ALL 5 scanners)
grype sbom:sbom.json | grep -i "php\|CVE-2025-14178"  # 0 matches
trivy image image@sha256:... | grep -i php            # 0 PHP CVEs
clair-action report ...                               # 0 PHP packages (no npm matcher)
osv-scanner scan image --archive image.tar            # 0 CVE-2025-14178
oscap-podman image oval eval rhel-9.oval.xml          # result="false"
```

**Scanner Results:**
- Clair: ❌ No (no npm matcher)
- Grype: ❌ No (correct ecosystem detection)
- Trivy: ❌ No (correct ecosystem detection)
- OSV-Scanner: ❌ No (OSV database - RHTPA's source!)
- OpenSCAP: ❌ No (checks RPM only)

**Conclusion:** FALSE POSITIVE - Created by manual review, NOT by any scanner. VSCode extensions ≠ PHP runtime.

## False Positive Detection

### Red Flags Indicating Possible False Positive

1. **Package name matches but wrong ecosystem**
   - Example: npm `php` vs language `php`
   - Check: `type` field in SBOM and package location

2. **Editor/IDE extensions**
   - Paths like `/usr/lib/code-server/lib/vscode/extensions/`
   - Package names like `php-language-features`, `python-extension`
   - These provide syntax highlighting, NOT runtime

3. **Build-time vs runtime**
   - Webpack, build tools in `pnpm-lock.yaml`
   - Check Dockerfile: Is it COPY'd to runtime?

4. **Scanner disagreement**
   - If grype says "no" but manual review says "yes" → investigate deeper
   - Multiple scanners disagreeing → likely false positive

### Verification Checklist for Suspected False Positives

```bash
# 1. Check package ecosystem
python3 scripts/sbom_analyze.py sbom.json <package> | grep "Type:"
# Is it npm/Python/RPM? Does CVE affect that ecosystem?

# 2. Check package location
python3 scripts/sbom_analyze.py sbom.json <package> | grep "Location:"
# Is it in /vscode/extensions/ or similar IDE path?

# 3. Mount and inspect actual filesystem
podman image mount <image_id>
# Is the actual binary/interpreter present?

# 4. Run multiple scanners
grype sbom:sbom.json | grep <CVE-ID>
trivy image image:tag | grep <CVE-ID>
osv-scanner --sbom=sbom.json | grep <CVE-ID>
# Do they agree? If all say "no" → false positive

# 5. Check source code
grep -r <package> repository/
# Is it actually used or just detected by scanner?
```

## Scanner Selection Guide

### Primary Investigation

**Start with:** `sbom_analyze.py` + `grype`

```bash
# Quick package location
python3 scripts/sbom_analyze.py sbom.json <package>

# Primary vulnerability check
grype sbom:sbom.json -o table | grep <package>
```

### Deep Verification

**Add:** `trivy` + `osv-scanner`

```bash
# Cross-validate with Trivy
trivy sbom sbom.json

# If npm/JavaScript, verify with OSV
osv-scanner --sbom=sbom.json
```

### False Positive Investigation

**Add:** Filesystem inspection + `OpenSCAP` + multiple scanners

```bash
# Mount and search
podman image mount <image>
find $MOUNT_DIR -name <binary>

# OVAL check (for RPM)
oscap-podman <image> oval eval rhel-9.oval.xml

# Compare all scanners
# If ALL say "no" → strong evidence of false positive
```

## Common Pitfalls and Solutions

### Pitfall 1: Trusting Package Names Alone

**Problem:** Package named "php" doesn't mean PHP runtime installed.

**Solution:** Always check:
- Package ecosystem (`type` field)
- Package location (path in container)
- Actual binary presence (filesystem inspection)

**Example:** npm `php@1.0.0` = VSCode extension, NOT PHP runtime

### Pitfall 2: Ignoring Build-time vs Runtime

**Problem:** Package in SBOM but not in shipped container.

**Solution:** Check Dockerfile/build process:
```bash
# Is it COPY'd to runtime image?
grep "COPY.*pnpm-lock.yaml" Dockerfile
# Usually: NO - lock files stay in build layer

# Is it npm devDependency?
# These are NOT shipped in node_modules
```

**Example:** CVE-2025-15284 - `qs` was webpack-dev-server dependency (build-time only)

### Pitfall 3: Outdated Scanner Databases

**Problem:** Scanner reports no vulnerability because database is old.

**Solution:** Always update before scanning:
```bash
grype db update
trivy image --download-db-only
# Check database age
grype db status
```

### Pitfall 4: Single Scanner Validation

**Problem:** Relying on one scanner can miss issues or create false positives.

**Solution:** Use at least 2-3 scanners:
```bash
# Minimum viable verification
grype sbom:sbom.json          # Primary
trivy image image:tag         # Secondary
python3 scripts/sbom_analyze.py sbom.json pkg  # Location confirmation
```

**Example:** CVE-2025-14178 - All 5 scanners agreed: false positive

### Pitfall 5: Ignoring Ecosystem Matchers

**Problem:** Scanner doesn't support package ecosystem, gives false negative.

**Solution:** Know your scanner's capabilities:
- **Clair**: No npm matcher → Can't detect npm CVEs
- **OpenSCAP**: No npm matcher → RPM only
- **Grype/Trivy**: Multi-ecosystem → Best coverage

**Example:** Clair found 0 PHP packages because it has no npm matcher (expected behavior)

## Authentication and Access

### Red Hat Registry Authentication

```bash
# Method 1: Using pull-secret JSON
python3 << EOF
import json, base64
with open("pull-secret.json") as f:
    secret = json.load(f)
dockerconfig = base64.b64decode(secret["data"][".dockerconfigjson"]).decode()
with open("/tmp/dockerconfig.json", "w") as f:
    f.write(dockerconfig)
EOF

# Extract credentials and login
python3 << EOF
import json, base64
with open("/tmp/dockerconfig.json") as f:
    config = json.load(f)
auth = config["auths"]["registry.redhat.io"]["auth"]
username, password = base64.b64decode(auth).decode().split(":", 1)
print(f"{username}\n{password}")
EOF > /tmp/creds.txt

username=$(head -1 /tmp/creds.txt)
password=$(tail -1 /tmp/creds.txt)
echo "$password" | podman login --username "$username" --password-stdin registry.redhat.io
```

### RHTPA API Authentication (Future)

```bash
# Get offline token from: https://access.redhat.com/management/api

# Exchange for access token
export TPA_TOKEN=$(curl -s -d 'client_id=rhsm-api' \
  -d 'grant_type=refresh_token' \
  -d "refresh_token=<YOUR_OFFLINE_TOKEN>" \
  https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token \
  | jq -r .access_token)

# Use with Exhort API
curl -X POST https://rhda.rhcloud.com/api/v5/analysis \
  -H "Authorization: Bearer $TPA_TOKEN" \
  -H "Content-Type: application/vnd.spdx+json" \
  --data-binary @sbom.json
```

## Best Practices

### 1. Always Use Multiple Scanners

**Minimum:** 2 scanners from different vendors
**Recommended:** 3+ scanners for high-confidence results

**Rationale:** Different scanners have different:
- Vulnerability databases
- Ecosystem support
- Matching algorithms

**Example:** CVE-2025-14178 - Only by testing 5 scanners did we prove unanimous false positive.

### 2. Verify Package Ecosystem

```bash
# Don't just search for package name
# Check ecosystem type
python3 scripts/sbom_analyze.py sbom.json php | grep "Type:"
# npm ≠ PHP runtime language
```

### 3. Check Actual File Presence

```bash
# SBOM says package exists?
# Mount and verify it's actually there
podman image mount <image>
ls -la $MOUNT_DIR/path/from/sbom
```

### 4. Understand Build vs Runtime

```bash
# Check Dockerfile for multi-stage build
grep "FROM.*AS builder" Dockerfile
grep "COPY --from=builder" Dockerfile

# Build-time dependencies often don't ship
```

### 5. Document Scanner Versions

Always include scanner versions in reports:
```bash
syft version          # v1.41.1
grype version         # v1.41.1
trivy --version       # dev
osv-scanner --version # v2.3.2
oscap --version       # 1.4.3
```

## Troubleshooting

### Issue: "Image not found" errors

```bash
# Check if image is locally available
podman images | grep <image-name>

# Pull with authentication
podman login registry.redhat.io
podman pull <full-image-reference-with-digest>
```

### Issue: Scanner reports nothing

```bash
# Check scanner database age
grype db status
# Update if needed
grype db update

# For Clair: Check matcher list
# Look for your ecosystem in the matchers output
```

### Issue: SBOM too large

```bash
# Check size
ls -lh sbom.json

# If >50MB, parsing may be slow
# Use jq for quick queries instead of loading full file
cat sbom.json | jq '.artifacts[] | select(.name=="packagename")'
```

### Issue: SELinux blocks podman mount

```bash
# Use --privileged or adjust SELinux
podman run --privileged ...

# Or create temp directory
mkdir -p /var/tmp/scan-work
cd /var/tmp/scan-work
```

## Summary: Scanner Capabilities Matrix

| Scanner | SBOM Gen | RPM | npm | Python | Go | Java | CVE Match | Best For |
|---------|----------|-----|-----|--------|----|----|-----------|----------|
| **Syft** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | SBOM generation |
| **Grype** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Primary CVE scan |
| **Trivy** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Container security |
| **Clair** | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | Konflux verification |
| **OSV-Scanner** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | OSV DB verification |
| **OpenSCAP** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | RHEL OVAL compliance |
| **sbom_analyze.py** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | Quick package search |

## Key Takeaways

1. **No single scanner is perfect** - Always use multiple tools
2. **Ecosystem matters** - npm `php` ≠ PHP runtime language
3. **Filesystem is truth** - When in doubt, mount and inspect
4. **Build ≠ Runtime** - Check what actually ships in the container
5. **Scanner comparison reveals false positives** - If all say "no", it's probably false

## Related Documentation

- [docs/cve-remediation-guide.md](cve-remediation-guide.md) - Complete CVE workflow
- [docs/manifestbox.md](manifestbox.md) - SBOM repository usage
- [scripts/sbom_analyze.py](../scripts/sbom_analyze.py) - Custom SBOM tool
- [docs/case-study-cve-2025-13465.md](case-study-cve-2025-13465.md) - Lodash investigation
- [docs/case-study-cve-2025-15284.md](case-study-cve-2025-15284.md) - qs investigation

---

**Last Updated**: 2026-01-30  
**Tested With**: CVE-2025-13465, CVE-2025-15284, CVE-2025-14178  
**Scanners Tested**: Syft, Grype, Trivy, Clair, OSV-Scanner, OpenSCAP
