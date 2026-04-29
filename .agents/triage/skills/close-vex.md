# Skill: Closing Security Issues with VEX Justification

This skill teaches AI agents how to properly close CVE/security tracking issues in Jira with appropriate Resolution and VEX (Vulnerability Exploitability eXchange) Justification fields.

## When to Use This Skill

Use this skill when:
- Closing security tracking issues (CVE, vulnerability issues)
- The issue is determined to be a false positive or not applicable
- VEX Justification needs to be set for Product Security tracking
- Resolution needs to be "Not a Bug" (not "Done")

## Quick Reference: Complete Workflow

1. For each verified child: add investigation comment, then call `transitionJiraIssue` with `resolution` + VEX fields
2. Verify via API that `status=Closed`, `resolution=Not a Bug`, `VEX=Component not Present`

### Mixed Tracker / Partial Closure

When a tracker has children across multiple image families and only some are false positives:

1. **Identify the exact closable subset** — only children backed by per-child SBOM proof
2. **Use `key in (...)` JQL** targeting only the verified keys, not the full CVE label
3. **Leave real-exposure children open** (e.g., code-server children with `/usr/lib/code-server/...` paths)
4. **Leave unverified children open** until their exact SBOM is checked
5. **Post a parent tracker comment** explaining what was closed, what remains open, and why

Example JQL for a verified subset:
```jql
key in (RHOAIENG-53125, RHOAIENG-53122, RHOAIENG-53120, RHOAIENG-53118, RHOAIENG-53116, RHOAIENG-53110, RHOAIENG-53107, RHOAIENG-53104, RHOAIENG-53101, RHOAIENG-53094) ORDER BY key ASC
```

**API/bulk efficiency never outranks exact per-child evidence selection.**
Close fewer issues correctly rather than more issues from inferred evidence.

## Prerequisites

- Jira MCP server (`user-mcp-atlassian`) configured
- User has appropriate Jira permissions

## Understanding VEX Justifications

VEX Justification explains why a reported vulnerability doesn't affect the product. Valid values:

| Justification | When to Use |
|---------------|-------------|
| **Component not Present** | Vulnerable component is not in the shipped product (build-time only, excluded from final image) |
| **Vulnerable Code not Present** | Vulnerable code paths are excluded (compiled out, conditional compilation) |
| **Vulnerable Code not in Execute Path** | Vulnerable code exists but is never called/executed |
| **Vulnerable Code cannot be Controlled by Adversary** | Vulnerable code cannot be exploited due to runtime constraints |
| **Inline Mitigations already Exist** | Built-in protections prevent exploitation |

## Critical Policy: NEVER Use "Won't Do"

Per [ProdSec policy](https://spaces.redhat.com/spaces/PRODSEC/pages/436147380/),
**"Won't Do" is prohibited** as a Resolution for any CVE tracker. Using it will cause the
CVE to appear as an unpatched vulnerability in the product's security posture.

Always use **"Not a Bug"** with the appropriate VEX Justification.

## VEX Justification Decision Tree

Use this to select the correct justification:

```text
Is the vulnerable package in the shipped container image?
├── NO (source-scan artifact, test dep, build tooling)
│   └── Use: "Component not Present"
│       (the component is not included in the shipped product;
│        its presence in the SBOM is a manifest error from source scanning)
│
├── YES, but we ship an older/patched version without the vulnerable code
│   └── Use: "Vulnerable Code not Present"
│       (we ship the component but our version doesn't contain the vuln code)
│
├── YES, but in base image (RPM from RHEL/UBI, not our code)
│   └── Is the code reachable in our product?
│       ├── NO → Use: "Vulnerable Code not in Execute Path"
│       └── YES → Do NOT close as VEX. Label ai-nonfixable, wait for base image fix.
│
└── YES, in our shipped code/deps
    └── Do NOT close as VEX. This is a real finding — fix it or label ai-nonfixable.
```

**Terminology** (per [ProdSec Confluence](https://redhat.atlassian.net/wiki/spaces/PRODSEC/pages/289223326)):
- `Component not Present` — the component is **not included** in the product. ProdSec notes
  "this scenario should be rare and may indicate an error in the software manifest" — which
  is exactly what source-scan contamination is.
- `Vulnerable Code not Present` — the component **is** shipped, but our version doesn't
  include the vulnerable code (e.g., older version without the vulnerable feature).
- `Vulnerable Code not in Execute Path` — vulnerable code is shipped but never executed.

**Note**: Some Slack discussions use "Vulnerable Code not Present" loosely for source-scan
false positives. The Confluence definitions are authoritative — use `Component not Present`
when the component is absent from the image entirely.

Common scenarios for notebooks:
- `sourceInfo` contains `/tests/browser/pnpm-lock.yaml` → **Component not Present**
- `sourceInfo` contains `/jupyter/utils/addons/pnpm-lock.yaml` → **Component not Present**
- `sourceInfo` contains `scripts/buildinputs/go.mod` → **Component not Present**
- We ship the package but an older version without the vuln → **Vulnerable Code not Present**
- Package inherited from base image, unreachable → **Vulnerable Code not in Execute Path**
- Package in `/usr/bin/skopeo` (shipped binary) → NOT a VEX case, keep open

Reference: [VEX Not Affected Justifications](https://spaces.redhat.com/spaces/PRODSEC/pages/580257978/)
and [SPDX VEX Spec](https://spdx.github.io/spdx-spec/v3.0.1/model/Security/Vocabularies/VexJustificationType/)

## Evidence Requirements

**Hard rule: representative-family sampling is for tracker-level triage only.**
Closing individual child issues requires exact per-child SBOM proof.

Required evidence chain before closing any child:
1. Exact child key (e.g., `RHOAIENG-53125`)
2. Exact `pscomponent:` / image name from the child's labels
3. Exact product version (`v3-3`, `v2-25`, etc.) matching the tracker
4. Exact matching SBOM file with verified `build_component`
5. Exact `sourceInfo` path proving the package is not in a shipped runtime location

Do NOT close children based on:
- "likely" or "representative" evidence from another image family
- the second matching SBOM file without checking `build_component`
- repo grep or lockfile analysis alone

## Workflow

### Preferred: API Transition (Sets Resolution + VEX in One Call)

For `Vulnerability` issues in RHOAIENG, the Jira transition API can set Resolution and
VEX Justification during the `Closed` transition when those fields are exposed on the
transition screen. This was confirmed working on CVE-2026-1526 children.

**Step 1:** Get available transitions and check for `resolution` and VEX fields:
```python
transitions = getTransitionsForJiraIssue(issueIdOrKey="RHOAIENG-XXXXX", expand="transitions.fields")
# Look for transition named "Closed" — note the id
# Check if fields include "resolution" and "customfield_10873" (VEX Justification)
```

**Step 2:** Add investigation comment, then transition with fields:
```python
# Add comment first
addCommentToJiraIssue(issueIdOrKey="RHOAIENG-XXXXX", commentBody="...")

# Transition to Closed with Resolution and VEX set atomically
transitionJiraIssue(
    issueIdOrKey="RHOAIENG-XXXXX",
    transition={"id": "<closed_transition_id>"},
    fields={
        "resolution": {"id": "<not_a_bug_id>"},
        "customfield_10873": {"id": "<component_not_present_id>"}
    }
)
```

**Important:** Do not hardcode transition or field IDs globally. Always discover them
dynamically from `getTransitionsForJiraIssue` for at least one representative issue,
since IDs can vary by project and workflow.

**Step 3:** Verify after transition:
```python
issue = getJiraIssue(issueIdOrKey="RHOAIENG-XXXXX", fields=["status", "resolution", "customfield_10873"])
# Confirm: status=Closed, resolution=Not a Bug, VEX=Component not Present
```

### Bulk Closure via API Loop

For closing multiple issues, loop over the verified keys and call the API transition
for each one. No batch size limit — the API processes one issue at a time.

#### Step 1: Add Comments to All Issues

Add investigation comments to all issues via Atlassian MCP:

```python
issues = ["RHOAIENG-43307", "RHOAIENG-43308", ...]  # All issue keys
comment = """**CVE-XXXX Resolution**

**Vulnerable component**: `package@version` (build-time dependency)
**Fixed in**: PR #XXXX (Date) - updated to `package@fixed_version`
**Runtime impact**: None (not shipped in containers)

**SBOM Analysis**: `/path/to/lockfile` (ecosystem, transitive dependency)
**VEX Justification**: Component not Present - Build-time only component.

See docs/case-study-cve-XXXX.md for full investigation."""

for issue_key in issues:
    jira_add_comment(issue_key=issue_key, comment=comment)
```

This ensures all issues have proper documentation.

#### Step 2: Transition Each Issue via API

For each verified issue key, call the transition with Resolution + VEX fields:

```python
for issue_key in verified_keys:
    # Transition to Closed with Resolution and VEX set atomically
    transitionJiraIssue(
        issueIdOrKey=issue_key,
        transition={"id": "61"},            # Closed
        fields={
            "resolution": {"id": "10037"},  # Not a Bug
            "customfield_10873": {"id": "17000"}  # Component not Present
        }
    )
```

**Important**: Discover transition and field IDs dynamically from `getTransitionsForJiraIssue`
for at least one representative issue first. The IDs above were verified on RHOAIENG
Vulnerability issues but may differ for other projects or issue types.

#### Step 3: Verify All Closed

```python
# Check no unresolved issues remain
searchJiraIssuesUsingJql(
    jql="labels = CVE-XXXX AND component = \"Notebooks Images\" AND resolution = Unresolved",
    maxResults=5
)
# Expected: 0 results
```

## Best Practices

### 1. Always Add Explanatory Comments

Include:
- **SBOM Analysis**: Where the package was detected
- **Root Cause**: Why it's a false positive
- **What Gets Shipped**: What actually ends up in the image
- **Verification**: How to confirm the claim
- **Resolution**: VEX justification and rationale

### 2. Use Consistent VEX Justification

Choose the most accurate VEX justification:
- Build-time only → **Component not Present**
- Transitive dependency not used → **Vulnerable Code not in Execute Path**
- Compiled out → **Vulnerable Code not Present**

### 3. Document Your Investigation

Reference specific files, line numbers, and commands used to investigate. This helps others verify your work.

### 4. Verify After Bulk Operations

After bulk closing, spot-check a few issues to ensure:
- Resolution is "Not a Bug" (not "Done")
- VEX Justification is set correctly
- Comments were added (if applicable)

### 5. Handle Already-Closed Issues

If some issues are already closed with wrong resolution:
- The bulk operation wizard will skip them or handle mixed states
- You may need to manually fix already-closed issues via UI
- Consider filtering JQL to exclude already-closed issues

## Field Reference (verified via live Jira API)

### Jira REST API Field IDs

- **VEX Justification**: `customfield_10873` (type: select/option)
  - `Component not Present` (id=17000)
  - `Inline Mitigations already Exist` (id=17001)
  - `Vulnerable Code cannot be Controlled by Adversary` (id=17002)
  - `Vulnerable Code not in Execute Path` (id=17003)
  - `Vulnerable Code not Present` (id=17004)
- **Resolution**: `resolution` (standard field)
  - `Not a Bug` (id=10037)
- **Closed transition**: id=61

**Discovery**: Always discover IDs dynamically from `getTransitionsForJiraIssue` with
`expand=transitions.fields` for at least one representative issue. IDs may vary by
project and workflow.

### Issue Types for Security

Security issues typically have:
- Issue Type: `Vulnerability`, `Bug`, or `Weakness`
- Labels: `SecurityTracking`, specific CVE ID (e.g., `CVE-2025-13465`)
- Component: `Notebooks Images` (for notebook-related CVEs)

## Example JQL Queries

```jql
# Find all unresolved CVEs for Notebooks Images
project = RHOAIENG AND issuetype in (Bug, Vulnerability, Weakness)
  AND resolution = Unresolved AND labels = SecurityTracking
  AND component = "Notebooks Images" ORDER BY created DESC

# Find specific CVE issues
project = RHOAIENG AND labels = CVE-2025-13465
  AND component = "Notebooks Images" ORDER BY key ASC

# Find issues with VEX justification set
project = RHOAIENG AND "VEX Justification" is not EMPTY
```

## Related Documentation

- [docs/cve-remediation-guide.md](cve-remediation-guide.md) - Complete CVE investigation workflow
- [docs/case-study-cve-2025-13465.md](case-study-cve-2025-13465.md) - Real example with 36 issues
- [scripts/cve/create_cve_trackers.py](../../../scripts/cve/create_cve_trackers.py) - Create parent trackers in RHOAIENG

## Template Comment for "Component not Present"

```markdown
Investigation Results - Not a Bug (Component Not Present)

**SBOM Analysis:**
{package}@{version} detected at: `{location_in_sbom}`

**Root Cause:**
The {package} package is a {build-time/test/dev}-only dependency used by {tool/framework} in `{directory}/`. {Explanation of what this directory does}.

**What Gets Shipped:**
Only the generated output (`{artifact}`) is copied into the final container images. The {package} and its dependencies are never included in the shipped images.

**Verification:**
See `{dockerfile_or_script}` line {N}: Only `{artifact}` is copied to the runtime image.

**Resolution:**
- VEX Justification: Component not Present
- Rationale: {package} is a {purpose} dependency that does not exist in the runtime container image.
```

---

**Last Updated**: 2026-03-31
**Verified field IDs**: via `getTransitionsForJiraIssue` on RHOAIENG-56150
