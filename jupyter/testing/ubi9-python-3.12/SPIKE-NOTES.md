# Hermetic Build Spike - Public PyPI

**Jira:** RHAIENG-6564
**Branch:** `spike/hermetic-public-pypi`
**PR:** https://github.com/opendatahub-io/notebooks/pull/4393
**Date:** 2026-08-16

## Executive Summary

| Finding | Status |
|---------|--------|
| Public PyPI package availability | ✅ All 113 packages available |
| Prefetch from public PyPI | ✅ Works (270MB) |
| Binary wheels for ODH | ✅ Feasible |
| Binary wheels for RHOAI | ❌ **BLOCKED by Conforma** |
| Source-build (sdist) path | ⚠️ Not yet tested |

**Recommendation:** Public PyPI hermetic builds are feasible for **ODH only**.
For **RHOAI**, binary wheels violate Conforma policy - source-build required.

---

## Setup Completed

| Step | Status | Notes |
|------|--------|-------|
| Create test image | ✅ | `jupyter/testing/ubi9-python-3.12` |
| Remove CUDA/ROCM | ✅ | CPU-only for spike |
| Regenerate locks | ✅ | 113 packages from public PyPI |
| Create Tekton PipelineRun | ✅ | `/build-testing-spike` trigger |
| Run prefetch | ✅ | 270MB pip, 3GB RPMs |
| Konflux build | 🔄 | Triggered, awaiting results |

---

## Investigation Results

### A) Hermetic Build Path ✅

| Check | Result |
|-------|--------|
| Prefetch pip from public PyPI | ✅ Works |
| Prefetch RPMs | ✅ Works |
| Offline install | ⏳ Konflux test pending |
| GPG key import | ✅ Works |

### B) Public PyPI Policy 🚨

**CRITICAL FINDING:** Conforma prohibits binary wheels for RHOAI!

From `docs/conforma.md`:
> `sbom_spdx.disallowed_package_attributes` - Python packages must be **sdist (source distributions), NOT binary wheels**.

| Policy | ODH | RHOAI |
|--------|-----|-------|
| Binary wheels allowed | ✅ Yes | ❌ **NO** |
| Conforma checked | No | Yes |
| Source-build required | No | **Yes** |

### C) Wheels vs Sdists

Current spike uses **binary wheels**. For RHOAI compliance:

| Approach | Pros | Cons |
|----------|------|------|
| Binary wheels | Fast install, no compile | ❌ Violates Conforma |
| Source dist (sdist) | ✅ Conforma compliant | Slow compile, needs toolchain |

Packages requiring compilation (partial list):
- `aiohttp` (7.9MB source)
- `frozenlist`, `multidict`, `yarl` (Cython)
- `cffi`, `pycparser`
- `debugpy`, `pyzmq`

### D) RHDS rhoai-2.25 Comparison

| Aspect | RHDS rhoai-2.25 | ODH main |
|--------|-----------------|----------|
| Hermetic | ⚠️ Partial (hash verify) | ✅ Full (Cachi2 prefetch) |
| Download during build | Yes | No |
| Index strategy | `unsafe-best-match` | `--no-index` |
| Cachi2 | Not used | Used |

**Key difference:** RHDS downloads during build with hash verification.
ODH uses full hermetic prefetch - no network during build.

### E) Pandoc/PDF Export ✅

| Finding | Detail |
|---------|--------|
| `pandoc-rhai` | ❌ Not on public PyPI |
| Recommendation | Skip PDF export for public-index images |
| Alternative | System pandoc from RPMs (needs investigation) |

### F) Conforma/ProdSec ✅

| Check | Status for public PyPI |
|-------|------------------------|
| `hermetic_task` | ✅ Satisfied |
| `trusted_task` | ✅ Satisfied |
| `rpm_signature` | ✅ Using signed RPMs |
| `sbom_spdx.disallowed_package_attributes` | ❌ **FAILS with binary wheels** |

---

## Decision Matrix

| Option | ODH Feasible | RHOAI Feasible | Effort | Notes |
|--------|--------------|----------------|--------|-------|
| **1. Public PyPI + wheels** | ✅ Yes | ❌ No | Low | Current spike |
| **2. Public PyPI + sdist** | ✅ Yes | ✅ Yes | High | Needs compiler toolchain |
| **3. Policy exception** | N/A | ⚠️ Maybe | Medium | Requires PSX approval |
| **4. Hybrid (AIPCC + PyPI)** | ❓ | ❓ | Medium | Index mixing unclear |

---

## Recommendations

### For ODH (opendatahub.io)
**GO** - Public PyPI with binary wheels is feasible.
- Not subject to Conforma policy
- All packages available
- Prefetch works

### For RHOAI (Red Hat OpenShift AI)
**CONDITIONAL GO** - Requires one of:

1. **Source-build path** (Recommended)
   - Use sdist instead of wheels
   - Add compiler toolchain to build image
   - Longer build times (~10-30 min compile)
   - Need follow-up spike to measure

2. **Policy exception** (Alternative)
   - Request PSX approval for binary wheels
   - Document business justification
   - Time-limited exception

---

## Follow-up Stories

1. **Source-build spike** - Test sdist compile path, measure build time
2. **Dockerfile redesign** - Multi-stage build with compiler toolchain
3. **Pandoc solution** - System RPM vs alternative
4. **Multi-arch testing** - Validate ppc64le, s390x wheel/sdist availability
5. **Policy exception request** - If source-build not viable

---

## Files Changed

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
| Hermetic build attempted | ✅ (Konflux pending) |
| Sdist source-build tested | ❌ (Follow-up needed) |
| RHDS comparison documented | ✅ |
| Pandoc decision documented | ✅ |
| Conforma assessment | ✅ |
| Blocker list | ✅ |
| Clear recommendation | ✅ |
| Follow-up stories | ✅ |
