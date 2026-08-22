# Hermetic Build Spike - Public PyPI

**Jira:** RHAIENG-6564
**Branch:** `spike/hermetic-public-pypi`
**PR:** https://github.com/opendatahub-io/notebooks/pull/4393
**Date:** 2026-08-16
**Updated:** 2026-08-22 (with Jiri's clarification)

## Executive Summary

| Finding | Status |
|---------|--------|
| Public PyPI package availability | ✅ All 113 packages available |
| Prefetch from public PyPI | ✅ Works (270MB) |
| Binary wheels for ODH | ✅ Feasible |
| AIPCC binary wheels for RHOAI | ✅ **Allowed by Conforma** |
| Public PyPI binary wheels for RHOAI | ❌ **Blocked by Conforma** |

**Final Recommendation:** Stick with **AIPCC** for RHOAI workbenches.
Public PyPI adds complexity with no benefit since Conforma blocks PyPI binary wheels anyway.

---

## Key Clarification from Jiri (2026-08-17)

> "AIPCC binary wheels don't trigger Conforma, only PyPI do"

This is the critical insight:

| Package Source | Binary Wheels | Conforma |
|----------------|---------------|----------|
| **AIPCC** (RH internal index) | ✅ Allowed | ✅ Pass |
| **Public PyPI** | ❌ Blocked | ❌ Fail |

**Why:** AIPCC packages are vetted by Red Hat's security process. Public PyPI packages are not.

---

## Final Conclusion

### For RHOAI (Red Hat OpenShift AI)
**NO CHANGE NEEDED** - Continue using AIPCC.
- AIPCC binary wheels work fine with Conforma
- Public PyPI would require source-build (complex, slow)
- No benefit to switching

### For ODH (opendatahub.io)
**OPTIONAL** - Public PyPI could work.
- ODH is not subject to Conforma
- But adds maintenance burden (two build paths)
- Recommendation: Use AIPCC for consistency

---

## Setup Completed

| Step | Status | Notes |
|------|--------|-------|
| Create test image | ✅ | `jupyter/testing/ubi9-python-3.12` |
| Remove CUDA/ROCM | ✅ | CPU-only for spike |
| Regenerate locks | ✅ | 113 packages from public PyPI |
| Create Tekton PipelineRun | ✅ | `/build-testing-spike` trigger |
| Run prefetch | ✅ | 270MB pip, 3GB RPMs |

---

## Investigation Results

### A) Hermetic Build Path ✅

| Check | Result |
|-------|--------|
| Prefetch pip from public PyPI | ✅ Works |
| Prefetch RPMs | ✅ Works |
| GPG key import | ✅ Works |

### B) Conforma Policy (Updated)

**Original finding:** Conforma blocks binary wheels via `sbom_spdx.disallowed_package_attributes`.

**Jiri's clarification:** This only applies to **public PyPI** binary wheels, not AIPCC.

| Source | Binary Wheels | Conforma | Reason |
|--------|---------------|----------|--------|
| AIPCC | ✅ Allowed | ✅ Pass | Red Hat vetted |
| Public PyPI | ❌ Blocked | ❌ Fail | Not vetted |

### C) RHDS rhoai-2.25 Comparison

| Aspect | RHDS rhoai-2.25 | ODH main |
|--------|-----------------|----------|
| Hermetic | ⚠️ Partial (hash verify) | ✅ Full (Cachi2 prefetch) |
| Download during build | Yes | No |
| Index | AIPCC | AIPCC |

### D) Pandoc/PDF Export

| Finding | Detail |
|---------|--------|
| `pandoc-rhai` | ❌ Not on public PyPI |
| Impact | Would need alternative for public PyPI path |
| Resolution | Not relevant - staying with AIPCC |

---

## Decision Matrix (Updated)

| Option | ODH | RHOAI | Effort | Recommendation |
|--------|-----|-------|--------|----------------|
| **AIPCC (current)** | ✅ | ✅ | Low | ✅ **Keep this** |
| Public PyPI + wheels | ✅ | ❌ | Low | Not for RHOAI |
| Public PyPI + sdist | ✅ | ⚠️ | High | Too complex |
| Hybrid | ⚠️ | ⚠️ | Medium | Adds complexity |

---

## Spike Outcome

**Result:** No change recommended.

The current AIPCC-based hermetic build approach is correct:
- ✅ Works with Conforma
- ✅ Uses binary wheels (fast builds)
- ✅ Packages are Red Hat vetted
- ✅ Already implemented

Public PyPI path is technically feasible but offers no advantage for RHOAI due to Conforma constraints.

---

## Follow-up Stories

**None required** - current approach is validated.

If ODH wants a separate public PyPI path in the future, that would be a new initiative (not blocking).

---

## Files Changed (Spike Artifacts)

```
jupyter/testing/ubi9-python-3.12/
├── Dockerfile.konflux.cpu
├── SPIKE-NOTES.md
├── build-args/konflux.cpu.conf
├── pylock.toml (113 packages)
├── requirements.cpu.txt
└── uv.lock

.tekton/
└── odh-workbench-jupyter-testing-cpu-py312-ubi9-pull-request.yaml

scripts/lockfile-generators/
└── create-requirements-lockfile.sh (added testing to PUBLIC_INDEX_PROJECTS)
```

---

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| Spike repro steps documented | ✅ |
| Hermetic build attempted | ✅ |
| Conforma assessment | ✅ (Updated with Jiri's input) |
| RHDS comparison documented | ✅ |
| Pandoc decision documented | ✅ |
| Blocker list | ✅ (None - AIPCC works) |
| Clear recommendation | ✅ **Stick with AIPCC** |
| Follow-up stories | ✅ None needed |
