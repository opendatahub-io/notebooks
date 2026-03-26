# Skill: Assess Bug Fixability

The core triage skill. For each issue, analyze fixability, immediately label in Jira, and post a structured analysis comment.

## Inputs

- `$ARGUMENTS`: optional single issue key (e.g., `RHAIENG-3611`). If provided, assess only that issue. If not, read from `.artifacts/triage/ledger.json` and assess all pending issues.

## HITL Checkpoint

After assessing the **first issue you fully assess and intend to post**, show the analysis comment and label decision to the user before posting to Jira. Once approved, proceed with remaining issues without pausing.

## Procedure (per issue)

### 0. Pre-Assessment Checks

Before writing any assessment, do these checks in order:

1. **Read Jira fields, not just description**: pay attention to `Affects Version` (which
   RHOAI version — critical for determining if it's still relevant), `Target Version`,
   `Fix Version`, `Labels`, `Components`, and `Issue Links`.
2. **Do a quick repo-signal pass first**:
   - Run a low-cost `Grep` / `Glob` pass using the issue summary, error string, package name,
     or component name to identify likely files and repos.
   - Note issue-shape signals such as: linked issues, mentions of a PR/commit/branch/backport,
     regression language, "blocked on X", or evidence that the fix may already exist for another
     variant or release.
3. **Escalate to higher-cost history checks only when the issue shape justifies it**:
   - Search PRs in both repos when the issue references a fix, regression, backport, commit, or
     "already fixed" claim, or when linked issues suggest a prior solution pattern may exist.
   - Check branches when the issue mentions a release branch, z-stream, backport, or other branch-specific work.
   - Check linked/cloned issues when links exist; if they have PRs, read those PR diffs before
     writing the assessment.
   - Check blocking issues' current status only when a blocker is explicitly named or linked.

Existing Jira comments can be useful clues, but they never replace code verification.

### 1. Load Issue Details

If assessing from ledger, read the issue's entry. If assessing a single issue by key, fetch it via `mcp__atlassian__getJiraIssue`.

Read the full description. If the description is long, summarize the key facts (error message, reproduction steps, affected component) and drop the raw text from context.

### 2. Search the Repo for Context

**Important**: this repo builds container images. The local dev venv (from top-level pyproject.toml)
contains CI/development tools, NOT workbench packages. Never check package availability in the
local venv — always check the container build context.

Based on error messages or component names in the issue:
- Use **Grep** to find related files (error strings, class/function names, package names)
- Use **Glob** to find relevant Dockerfiles, pyproject.toml, test files, manifests
- Start with grep/glob to shortlist candidate files, then read the actual affected file(s)
- For Dockerfiles, shell build scripts, and other build orchestration files, read the whole file
  once shortlisted if partial matches do not explain the behavior

**For "module/package not found" bugs**, check the container's lock files:
- `*/uv.lock.d/pylock.cpu.toml` or `*/uv.lock.d/requirements.cpu.txt` — resolved versions and source URLs
- Note the **source URL**: packages from `packages.redhat.com/api/pulp-content/public-rhai/...` are
  Red Hat custom-built wheels that may differ from upstream PyPI (e.g., missing optional features,
  different build flags). A wheel suffix like `-2` or `-3` indicates a custom rebuild.
- Check `pyproject.toml` for the dependency declaration and whether extras are specified

**To verify inside the actual container** (if lock file analysis is insufficient):
1. Pull a pre-built image from `quay.io/opendatahub/odh-workbench-*` (Konflux builds),
   `quay.io/rhoai/odh-workbench-*` (downstream), or `registry.redhat.io/rhoai/*` (released,
   needs `podman login` — see `.agents/reference/registry-redhat-io.md`)
2. Or build locally: `gmake jupyter-datascience-ubi9-python-3.12` etc.
3. Or ad-hoc: install packages onto the base image using the correct Python index
4. If the user has a remote machine with podman (ask first!), pull and run there to avoid
   slow local image transfers

**Read whole build files, not just grep for keywords.** For complex builds (e.g.,
`devel_env_setup.sh`), reading end-to-end reveals architecture-specific patterns that
keyword grep misses. If context preservation is a concern (large files), use an
**Explore subagent** to read the file and summarize the relevant parts.

**When a fix exists for one arch/variant**, read that fix's PR and extend the same approach.
Don't invent a different solution when a proven one exists.

**Subagent trigger**: if the file is >200 lines OR the investigation requires checking >1
external repo, spawn an Explore subagent. The subagent returns a summary of which files
are affected and how.

### 3. Classify Bug Category

Map the issue to one of the 8 categories from `reference/bug-categories.md`:

1. Dockerfile/build — `*/Dockerfile.*`
2. Python dependency — `*/pyproject.toml`, lock files
3. Test infrastructure — `tests/**/*.py`
4. Manifest/version — `manifests/**/*.yaml`
5. Security/CVE — dependency files
6. CI/CD pipeline — `.tekton/`, `.github/workflows/`
7. Runtime/GPU — requires cluster/hardware
8. UI/browser — requires visual testing

For RStudio bugs, only `rstudio/rhel9-python-3.12/` is relevant for RHOAI. The
`rstudio/c9s-python-3.12/` variant is for ODH upstream only (CentOS Stream 9).

### 4. Determine Fixability

**AI-fixable** when ALL of these are true:
- Bug has a clear reproduction path or error message
- Fix is in files the agent can modify (Python, Dockerfiles, YAML, configs)
- No cluster access, GPU hardware, or live browser testing needed
- No upstream dependency release required
- No architectural decision needed
- Sufficient information in the issue description

**AI-nonfixable** when ANY of these are true:
- Requires cluster access to reproduce
- Requires GPU hardware
- Requires manual browser/UI testing (unless browser tools are available)
- Root cause is in another repository
- Insufficient information to understand the problem
- Architectural decision needed
- Upstream dependency must release a fix first

**When uncertain**: default to `ai-nonfixable`.

**Test type matters** — specify in the assessment which test type verifies the fix:
- `make test` = static/config consistency tests (pyproject, manifests)
- `pytest tests/containers --image=<img>` = container integration tests
- Playwright (`tests/browser/`) = browser/UI tests
- GPU hardware needed = cannot be tested locally

**Non-CVE bugs**: check all supported versions between Affects Version and main. A bug
might be fixed on main but still present on a supported release branch that needs a
z-stream fix. "Fixed on main" is NOT "resolved for all versions."

**Auth-related bugs**: check if Affects Version predates RHOAI 3.0. RHOAI 3.0 replaced
`openshift-auth-proxy` with **Gateway API + kube-rbac-proxy** — auth/session bugs from
before 3.0 may be completely different now.

For Red Hat maintained packages, see `reference/bug-categories.md` — these need team
coordination for version bumps, not just a simple fix.

### 5. Compose Analysis Comment

Write a structured comment. See `reference/comment-template.md` for the starting format. Include:
- Date, issue link, summary
- AI-Fixable verdict with reasoning
- Problem description
- Root cause analysis (with file paths if found)
- Files to modify (if fixable)
- Steps to resolve (if fixable)
- Testing notes
- Why not fixable (if nonfixable)

### 6. Apply Labels in Jira

Fetch current labels via `mcp__atlassian__getJiraIssue`. Append (do not replace):
- `ai-triaged` (always)
- `ai-fixable` or `ai-nonfixable` (exactly one)

Update via `mcp__atlassian__editJiraIssue` after fetching the current labels and merging them
with `ai-triaged` plus exactly one of `ai-fixable` / `ai-nonfixable`.

Example shape:
```json
{
  "fields": {
    "labels": ["CVE", "security", "ai-triaged", "ai-fixable"]
  }
}
```

### 7. Post Comment in Jira

Post the analysis comment via `mcp__atlassian__addCommentToJiraIssue`.

### 8. Update Ledger

Update the issue's entry in `.artifacts/triage/ledger.json`:
```json
{
  "triageStatus": "assessed",
  "assessment": {
    "category": "Python dependency",
    "fixable": true,
    "confidence": "high",
    "filesToModify": ["jupyter/datascience/ubi9-python-3.12/pyproject.toml"],
    "summary": "Missing pyarrow S3 module — need to add pyarrow[s3] extra"
  }
}
```

### 9. Quality Checklist

Before posting any assessment, verify:
- [ ] If the issue shape required it, searched PRs in opendatahub-io/notebooks AND red-hat-data-services/notebooks
- [ ] If Jira issue links exist, checked the linked issues (clones, related, blocks)
- [ ] If linked issues have PRs, read those PR diffs
- [ ] Read the actual affected files (not just grep for keywords)
- [ ] If fix exists for another arch/variant, read that fix's approach
- [ ] If blocker issues were mentioned, checked their current status
- [ ] Identified correct test type (static / container / browser / GPU)
- [ ] Comment mentions RHOAI product impact in first paragraph
- [ ] Did not trust Jira description without code verification
- [ ] "Fixed on main" noted but NOT treated as "resolved for all versions"

### 10. Move to Next Issue

Print a one-line summary (key, verdict, category) and continue to the next pending issue in the ledger.

## Error Handling

- If Jira API fails, log the error and skip to the next issue. Don't stop the whole batch.
- If a label update fails (e.g., permission denied), report clearly and continue.
