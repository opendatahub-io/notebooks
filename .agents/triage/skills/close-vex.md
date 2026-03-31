# Skill: Closing Security Issues with VEX Justification

This skill teaches AI agents how to properly close CVE/security tracking issues in Jira with appropriate Resolution and VEX (Vulnerability Exploitability eXchange) Justification fields.

## When to Use This Skill

Use this skill when:
- Closing security tracking issues (CVE, vulnerability issues)
- The issue is determined to be a false positive or not applicable
- VEX Justification needs to be set for Product Security tracking
- Resolution needs to be "Not a Bug" (not "Done")

## Quick Reference: Complete Workflow

**Preferred path (API transitions):**
1. For each verified child: add investigation comment, then call `transitionJiraIssue` with `resolution` + VEX fields
2. Verify via API that `status=Closed`, `resolution=Not a Bug`, `VEX=Component not Present`

**Fallback path (browser bulk wizard):**
1. **Add comments** to all N issues via Atlassian MCP `jira_add_comment` (reliable)
2. **Navigate** to bulk wizard with JQL filter
3. **Wizard Step 1**: Issues pre-selected → Click Next
4. **Wizard Step 2**: Select "Transition Issues" → Click Next  
5. **Wizard Step 3**: Select "Closed" transition → Click Next
6. **Wizard Step 3.5**: Use JavaScript to set Resolution, Assignee, VEX Justification
7. **Wizard Step 4**: Review confirmation → Click Confirm
8. **Wait** for bulk operation (20-40 seconds for 20 issues)
9. **Repeat** steps 2-8 if >20 issues (Jira 20-issue-per-batch limit)
10. **Verify** via API: Check all issues Closed with correct fields

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
- Chrome DevTools MCP server (`user-chrome-devtools`) configured (for bulk operations)
- User has appropriate Jira permissions
- `JIRA_TOKEN` environment variable set

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

```
Is the vulnerable package in the shipped container image?
├── NO (source-scan artifact, test dep, build tooling)
│   └── Use: "Vulnerable Code Not Present"
│       (the vulnerable code is not in the shipped artifact)
│
├── YES, but in base image (RPM from RHEL/UBI, not our code)
│   └── Is the code reachable in our product?
│       ├── NO → Use: "Vulnerable Code not in Execute Path"
│       └── YES → Do NOT close as VEX. Label ai-nonfixable, wait for base image fix.
│
└── YES, in our shipped code/deps
    └── Do NOT close as VEX. This is a real finding — fix it or label ai-nonfixable.
```

**Terminology note**: ProdSec uses `Vulnerable Code Not Present` (not `Component not Present`)
for source-scan false positives. Both are valid VEX justifications but have different meanings:
- `Vulnerable Code Not Present` — the vulnerable code itself is absent from the shipped artifact
- `Component not Present` — the entire component is absent from the product

For source-scan artifacts (package found in repo but not in image), prefer `Vulnerable Code Not Present`.
For components that were never part of the product at all, use `Component not Present`.

Common scenarios for notebooks:
- `sourceInfo` contains `/tests/browser/pnpm-lock.yaml` → **Vulnerable Code Not Present**
- `sourceInfo` contains `/jupyter/utils/addons/pnpm-lock.yaml` → **Vulnerable Code Not Present**
- `sourceInfo` contains `scripts/buildinputs/go.mod` → **Vulnerable Code Not Present**
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

### Fallback: Browser Bulk Operations

If the API transition does not expose Resolution or VEX fields for a particular
issue type or workflow, fall back to the Jira Bulk Change wizard via browser.
See the bulk wizard instructions below.

### Bulk Resolution (Chrome DevTools MCP + Jira UI)

For closing multiple issues with proper Resolution and VEX, use the Jira Bulk Change wizard via browser automation.

**IMPORTANT LIMITATION**: Jira bulk wizard processes only **20 issues per batch**. For 36+ issues, you must run multiple bulk operations.

#### Complete Workflow: Navigating the 4-Step Wizard

##### Step 1: Add Comments to All Issues (Recommended First)

Before starting bulk close, add investigation comments to all issues via Atlassian MCP:

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

This ensures all issues have proper documentation regardless of bulk operation success.

##### Step 2: Navigate to Bulk Edit Wizard

**Method 1: Direct JavaScript Navigation (Recommended)**

```python
# Navigate to issues list first
navigate_page(
    url="https://issues.redhat.com/issues/?jql=labels%20%3D%20CVE-2025-XXXXX%20AND%20component%20%3D%20%22Notebooks%20Images%22%20AND%20resolution%20%3D%20Unresolved%20ORDER%20BY%20key%20ASC"
)

# Then jump directly to bulk wizard
evaluate_script(
    function="() => { "
        "const jql = 'labels = CVE-2025-XXXXX AND component = \"Notebooks Images\" AND resolution = Unresolved ORDER BY key ASC'; "
        "window.location.href = `/secure/views/bulkedit/BulkEdit1!default.jspa?jqlQuery=${encodeURIComponent(jql)}`; "
        "return 'Navigating to bulk edit wizard'; "
    "}"
)
```

**Method 2: Click Through UI (Alternative)**

```python
# Click Tools button
take_snapshot()  # Find Tools button UID
click(uid="X_Y")  # Tools button

# Click "Bulk Change: all N issue(s)"
take_snapshot()  # Find bulk change menu item UID
click(uid="X_Y")  # Bulk Change option
```

##### Step 3: Wizard Step 1 of 4 - Choose Issues

The wizard opens with issues pre-selected from your JQL query.

**Page indicators:**
- Heading: "Step 1 of 4: Choose Issues"
- Shows: "Selected 20 issues from 1 project(s)" (or fewer if <20 match)
- Issues table displayed

**Action:**
```python
# Issues are already selected, just click Next
take_snapshot()  # Find Next button UID
click(uid="X_Y")  # Next button
```

**Note**: If Jira displays more than 20 issues, only the first 20 are selected. You'll need to repeat the process for remaining issues.

##### Step 4: Wizard Step 2 of 4 - Choose Operation

Select "Transition Issues" to change workflow state.

**Page indicators:**
- Heading: "Step 2 of 4: Choose Operation"
- Radio buttons: Edit Issues, Move Issues, **Transition Issues**, Watch Issues, etc.

**Action:**
```python
# Click "Transition Issues" radio button
take_snapshot()  # Find radio button with text "Transition Issues"
click(uid="X_Y")  # Transition Issues radio

# Click Next
click(uid="X_Y")  # Next button
```

##### Step 5: Wizard Step 3 of 4 - Operation Details (Select Transition)

Choose the "Closed" workflow transition.

**Page indicators:**
- Heading: "Step 3 of 4: Operation Details"
- Subheading: "Workflow: OJA-WF-BD"
- Shows workflow diagram with transitions
- Radio buttons for each available transition: New, Backlog, Testing, Resolved, **Closed**, etc.

**Action:**
```python
# Click "Closed" radio button
take_snapshot()  # Find "Closed" radio button
click(uid="X_Y")  # Closed transition radio

# Click Next
click(uid="X_Y")  # Next button
```

##### Step 6: Wizard Step 3.5 of 4 - Transition Fields (Set Resolution, VEX, Assignee)

Configure fields for the Close transition.

**Page indicators:**
- Heading: "Transition Issues: Edit Fields"
- Shows: "Select and edit the fields available on this transition"
- Displays workflow diagram showing: NEW → CLOSED
- Form with checkboxes and fields:
  - **Change Resolution** (checkbox pre-checked, dropdown disabled)
  - **Change Assignee** (checkbox unchecked)
  - **Change VEX Justification** (checkbox unchecked)

**Critical JavaScript Field Setting:**

The UI is unreliable with click events. Use `evaluate_script` to manipulate form fields:

```python
# Method 1: Set all fields at once
evaluate_script(
    function="() => { "
        "// 1. Set Resolution to 'Not a Bug' "
        "let resolutionSelect = document.querySelector('select#resolution'); "
        "if (resolutionSelect) { "
        "  let options = resolutionSelect.options; "
        "  for (let i = 0; i < options.length; i++) { "
        "    if (options[i].text === 'Not a Bug') { "
        "      resolutionSelect.selectedIndex = i; "
        "      resolutionSelect.dispatchEvent(new Event('change', { bubbles: true })); "
        "      break; "
        "    } "
        "  } "
        "} "
        ""
        "// 2. Enable and set Assignee (use 'Assign to me' button) "
        "let assigneeCheckbox = document.querySelector('input[name=\"assignee_checkbox\"]'); "
        "if (assigneeCheckbox && !assigneeCheckbox.checked) { "
        "  assigneeCheckbox.checked = true; "
        "  assigneeCheckbox.dispatchEvent(new Event('change', { bubbles: true })); "
        "} "
        ""
        "// 3. Enable and set VEX Justification "
        "let vexCheckbox = document.querySelector('input[name=\"customfield_12325940_checkbox\"]'); "
        "if (vexCheckbox && !vexCheckbox.checked) { "
        "  vexCheckbox.checked = true; "
        "  vexCheckbox.dispatchEvent(new Event('change', { bubbles: true })); "
        "} "
        ""
        "let vexSelect = document.querySelector('select[name=\"customfield_12325940\"]'); "
        "if (vexSelect) { "
        "  let options = vexSelect.options; "
        "  for (let i = 0; i < options.length; i++) { "
        "    if (options[i].text === 'Component not Present') { "
        "      vexSelect.selectedIndex = i; "
        "      vexSelect.dispatchEvent(new Event('change', { bubbles: true })); "
        "      break; "
        "    } "
        "  } "
        "} "
        ""
        "return 'Fields set: Resolution=Not a Bug, VEX=Component not Present'; "
    "}"
)

# Method 2: Use "Assign to me" button (simpler for assignee)
take_snapshot()  # Find "Assign to me" button
click(uid="X_Y")  # This automatically checks the assignee checkbox and sets value
```

**Verifying Fields Are Set:**

After JavaScript execution, take a snapshot and check:
- Resolution dropdown shows: "Not a Bug" (selected)
- Assignee shows: Your name (e.g., "Jiri Daněk")
- VEX Justification checkbox: checked
- VEX Justification dropdown shows: "Component not Present" (selected)

**Action:**
```python
# Click Next to proceed to confirmation
click(uid="X_Y")  # Next button
```

##### Step 7: Wizard Step 4 of 4 - Confirmation

Review and execute the bulk operation.

**Page indicators:**
- Heading: "Transition Issues: Bulk Workflow Transition Confirmation"
- Shows summary table:
  - **Updated Fields**: Assignee, VEX Justification, Resolution
  - **Workflow**: OJA-WF-BD
  - **Selected Transition**: Closed
  - **Status Transition**: NEW → CLOSED
- Text: "This change will affect N issues"

**Verification before execution:**
Check the "Updated Fields" table displays:
- Assignee: Jiri Daněk (or your name)
- VEX Justification: Component not Present
- Resolution: Not a Bug

**Action:**
```python
# Take screenshot for records (optional)
take_screenshot()

# Click Confirm to execute
click(uid="X_Y")  # Confirm button
```

##### Step 8: Monitor Progress

**Page indicators:**
- Heading: "Bulk Operation Progress"
- Text: "Transitioning N issues"
- Progress: "Bulk operation is X% complete."
- Shows elapsed time and completion estimate

**Action:**
```python
# Wait for completion (usually 20-40 seconds for 20 issues)
import time
time.sleep(30)

# Check if complete by taking snapshot or clicking Refresh
take_snapshot()  # Should show "100% complete" and "Ok, got it" button

# Click "Ok, got it" when done
click(uid="X_Y")
```

##### Step 9: Handle Remaining Issues (if >20 total)

If you have more than 20 issues to close:

1. **Update JQL to target next batch:**
   ```python
   # Example: For issues 21-36, use key range filter
   evaluate_script(
       function="() => { "
           "const jql = 'key >= RHOAIENG-43327 AND key <= RHOAIENG-43342 AND labels = CVE-2025-15284 AND component = \"Notebooks Images\" AND resolution = Unresolved ORDER BY key ASC'; "
           "window.location.href = `/secure/views/bulkedit/BulkEdit1!default.jspa?jqlQuery=${encodeURIComponent(jql)}`; "
           "return 'Navigating to next batch'; "
       "}"
   )
   ```

2. **Repeat Steps 3-8** for the new batch

3. **Continue until all issues are closed**

#### Alternative: Manual UI Navigation (User-Driven)

If Chrome MCP is unreliable or you want the user to control the process:

1. **Agent adds comments via API** (Step 1 above)
2. **Agent navigates to filtered issue list**
3. **User clicks through wizard manually:**
   - Tools → Bulk Change → all N issue(s)
   - Click Next (Step 1)
   - Select "Transition Issues" → Next (Step 2)
   - Select "Closed" → Next (Step 3)
   - Set Resolution="Not a Bug", Assignee=yourself, VEX="Component not Present" → Next (Step 3.5)
   - Review confirmation → Confirm (Step 4)
4. **Agent verifies completion via API**

### Alternative: Add Comments After Bulk Close

If bulk comment doesn't work, add comments individually after closing:

```python
issues = ["RHOAIENG-47539", "RHOAIENG-47540", ...]  # All issues
comment_text = """Investigation Results - Not a Bug (Component Not Present)

**SBOM Analysis:**
..."""

for issue in issues:
    jira_add_comment(issue_key=issue, comment=comment_text)
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

## Common Issues and Solutions

### Issue: "Field cannot be set" Error

**Cause**: Resolution and VEX Justification fields are only editable during specific workflow transitions or via UI.

**Solution**: Use bulk transition workflow via Chrome MCP, not `update_issue` or `transition_issue` API.

### Issue: Chrome MCP Dropdown Interactions Timeout

**Cause**: User approving MCP actions causes page refreshes that invalidate element UIDs.

**Solution**: Use `evaluate_script` to directly manipulate `<select>` elements via JavaScript rather than clicking individual options.

### Issue: Comment Checkbox Not Enabling

**Cause**: UI state management may not register clicks from MCP.

**Solution**: 
1. Skip bulk comments in the wizard entirely
2. Add comments individually via Atlassian MCP `jira_add_comment` before starting bulk close

### Issue: "Resolution is invalid" Error

**Cause**: Dropdown shows "Please select..." or wrong value despite script execution.

**Solution**: 
1. Use text-based option matching: `options[i].text === 'Not a Bug'`
2. Set `select.selectedIndex = i` instead of `select.value = 'id'`
3. Always dispatch `change` event after setting value

### Issue: "You must select at least one issue" Error

**Cause**: Navigating to bulk wizard URL without proper JQL parameter, or issues weren't pre-selected.

**Solution**: Use `jqlQuery` parameter in URL: `/secure/views/bulkedit/BulkEdit1!default.jspa?jqlQuery=${encodeURIComponent(jql)}`

### Issue: Only 20 of 36 Issues Processed

**Cause**: Jira bulk wizard has a 20-issue-per-batch limit.

**Solution**: 
1. Complete first batch of 20 issues
2. Use key range filter for next batch: `key >= RHOAIENG-XXXXX AND key <= RHOAIENG-YYYYY`
3. Repeat until all issues closed

### Issue: Red Hat Maintenance Page Appears

**Cause**: Some Jira pages redirect to maintenance/error pages intermittently.

**Solution**:
1. Navigate back to issues list: `https://issues.redhat.com/issues/?jql=...`
2. Use JavaScript navigation to bulk wizard again
3. If persistent, let user manually navigate through wizard while agent monitors via API

### Issue: Element UID No Longer Exists

**Cause**: Page transitioned to next step, invalidating previous UIDs.

**Solution**: This is expected behavior. Take a new snapshot after each page transition to get fresh UIDs.

## Field Reference

### Atlassian Jira Field IDs

- **VEX Justification**: `customfield_12325940` (type: select/option)
- **Resolution**: `resolution` (standard field, but not API-editable after close)

### Finding Field IDs

```python
jira_search_fields(keyword="vex", limit=10)
jira_search_fields(keyword="resolution", limit=10)
```

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

## Recommendations for Future Automation

Current limitations suggest these improvements:

1. **Playwright-based automation**: More reliable than Chrome MCP for complex UI workflows
2. **Jira API enhancement**: Request Product Security to expose Resolution/VEX fields in transition API
3. **Jira plugin/script**: Develop a Jira Script Runner script for bulk VEX updates
4. **Browser extension**: Create a Jira extension that adds VEX field to transition screens

## Related Documentation

- [docs/cve-remediation-guide.md](cve-remediation-guide.md) - Complete CVE investigation workflow
- [docs/case-study-cve-2025-13465.md](case-study-cve-2025-13465.md) - Real example with 36 issues
- [scripts/create_cve_trackers.py](../scripts/create_cve_trackers.py) - Create parent trackers in RHAIENG

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

## Key Learnings from Real-World Usage

### Pagination Limitation

**Jira displays maximum 20 issues per batch** in the bulk wizard, even if your JQL query matches more.

**Solution**: Run multiple bulk operations:
- For 36 issues: Run 2 batches (20 + 16)
- For 100 issues: Run 5 batches (20 × 5)

**Recommended approach:**
1. First batch: Use original JQL (processes first 20 issues)
2. Second batch: Use `key >= RHOAIENG-XXXXX AND key <= RHOAIENG-YYYYY ...` to target remaining issues
3. Repeat until all issues closed

### Field Setting Reliability

**What works reliably:**
- ✅ JavaScript `evaluate_script` for dropdown values
- ✅ "Assign to me" button click
- ✅ Text matching for option selection (`option.text === 'Not a Bug'`)

**What doesn't work reliably:**
- ❌ Direct `click` on dropdown options (times out, page refresh invalidates UIDs)
- ❌ Setting fields via Jira API during/after transition
- ❌ Bulk comments in the wizard (timeouts, race conditions)

### Verification Strategy

Always verify bulk operations completed successfully:

```python
# Check no unresolved issues remain
jira_search(jql="labels = CVE-XXXX AND component = \"Notebooks Images\" AND resolution = Unresolved", limit=5)
# Expected: total = 0

# Check all issues are closed with correct fields
jira_search(
    jql="labels = CVE-XXXX AND component = \"Notebooks Images\" AND status = Closed",
    fields="*all",
    limit=40
)
# Verify sample issues have: resolution.name = "Not a Bug", customfield_12325940.value = "Component not Present", assignee set
```

---

**Last Updated**: 2026-01-29  
**Tested With**: 
- CVE-2025-13465 (36 issues, lodash) - Successfully closed
- CVE-2025-15284 (36 issues, qs npm) - Successfully closed with improved process
