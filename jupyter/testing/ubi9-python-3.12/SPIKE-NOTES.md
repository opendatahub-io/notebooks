# Hermetic Build Spike - Public PyPI

**Jira:** RHAIENG-6564
**Branch:** `spike/hermetic-public-pypi`
**PR:** https://github.com/opendatahub-io/notebooks/pull/4393
**Date:** 2026-08-16
**Updated:** 2026-08-25 (added sdist source-build test per Jiri's feedback)

## Executive Summary

| Finding | Status |
|---------|--------|
| Public PyPI package availability | ✅ All 113 packages available |
| Prefetch from public PyPI | ✅ Works (270MB wheels, sdist TBD) |
| Binary wheels for ODH | ✅ Feasible |
| AIPCC binary wheels for RHOAI | ✅ Allowed by Conforma |
| Public PyPI binary wheels for RHOAI | ❌ Blocked by Conforma |
| **PyPI sdist (source build)** | 🔄 **Testing in progress** |

---

## Update: RHAISTRAT-1482 Source Build Path (2026-08-25)

Per Jiri's feedback, the original spike conclusion was incomplete. The logical chain is:

1. **AIPCC** → ❌ Blocked by "no-mixing" rule (customers can't safely extend)
2. **PyPI binary wheels** → ❌ Blocked by Conforma (third-party binaries)
3. **PyPI sdist (source)** → ✅ **The only viable path for community images**

### What We're Testing Now

| Component | Change |
|-----------|--------|
| Tekton PipelineRun | Removed `binary.arch` to download sdist instead of wheels |
| Dockerfile | Added build tools: Rust, cmake, zeromq-devel, etc. |
| Trigger command | `/build-testing-sdist` |

### Build Tools Added

```
gcc gcc-c++ make     # C/C++ compilers
cmake                # For pyzmq
rust cargo           # For cryptography
zeromq-devel         # For pyzmq
libffi-devel         # For cffi
openssl-devel        # For cryptography
libyaml-devel        # For pyyaml
```

### Expected Build Time

| Build Type | Estimated Time |
|------------|---------------|
| Binary wheels | ~5 minutes |
| Source (sdist) | ~30-60 minutes |

---

## Key Clarification from Jiri (2026-08-17)

> "AIPCC binary wheels don't trigger Conforma, only PyPI do"

| Package Source | Binary Wheels | Conforma |
|----------------|---------------|----------|
| **AIPCC** (RH internal index) | ✅ Allowed | ✅ Pass |
| **Public PyPI binary** | ❌ Blocked | ❌ Fail |
| **Public PyPI sdist** | ✅ Allowed | ✅ Pass |

---

## Two Use Cases

### 1. RHOAI Secure Tier
**Recommendation:** Continue using AIPCC.
- AIPCC binary wheels work with Conforma
- Customers get enterprise support
- No mixing issues (images not meant to be extended)

### 2. Community/ODH Images (RHAISTRAT-1482)
**Recommendation:** Build from PyPI sdist.
- Customers can freely extend with PyPI packages
- Same ecosystem = no ABI conflicts
- Passes Conforma (source-built, not third-party binaries)

---

## Setup Completed

| Step | Status | Notes |
|------|--------|-------|
| Create test image | ✅ | `jupyter/testing/ubi9-python-3.12` |
| Remove CUDA/ROCM | ✅ | CPU-only for spike |
| Regenerate locks | ✅ | 113 packages from public PyPI |
| Binary wheel prefetch | ✅ | 270MB pip deps |
| Add build tools | ✅ | Rust, cmake, zeromq-devel |
| **Sdist build test** | 🔄 | Trigger with `/build-testing-sdist` |

---

## Investigation Results

### A) Hermetic Build Path ✅

| Check | Result |
|-------|--------|
| Prefetch pip from public PyPI | ✅ Works (binary) |
| Prefetch RPMs | ✅ Works |
| GPG key import | ✅ Works |
| Sdist prefetch | 🔄 Testing |
| Sdist compilation | 🔄 Testing |

### B) Conforma Policy

| Source | Binary Wheels | Sdist | Conforma |
|--------|---------------|-------|----------|
| AIPCC | ✅ Allowed | N/A | ✅ Pass |
| Public PyPI | ❌ Blocked | ✅ Allowed | ✅ Pass (sdist) |

### C) Packages Requiring Compilation

| Package | Build Dependency | Estimated Compile Time |
|---------|-----------------|----------------------|
| `cryptography` | Rust, OpenSSL | ~2-5 min |
| `pyzmq` | cmake, zeromq-devel | ~3-5 min |
| `cffi` | libffi-devel | ~1 min |
| `aiohttp` | Cython | ~2-3 min |
| `pyyaml` | libyaml-devel | ~1 min |
| Pure Python | None | Instant |

### D) Pandoc/PDF Export

| Finding | Detail |
|---------|--------|
| `pandoc-rhai` | ❌ Not on public PyPI |
| Alternative | Use `pypandoc` from PyPI or system pandoc |

---

## Decision Matrix (Updated)

| Option | ODH | RHOAI Secure | RHOAI Community | Effort |
|--------|-----|--------------|-----------------|--------|
| **AIPCC (current)** | ✅ | ✅ | ❌ (mixing) | Low |
| PyPI binary wheels | ✅ | ❌ (Conforma) | ❌ (Conforma) | Low |
| **PyPI sdist** | ✅ | ✅ | ✅ | High |

---

## Next Steps

1. **Run `/build-testing-sdist`** on the PR to trigger Konflux build
2. **Measure actual build time** for sdist compilation
3. **Verify Conforma passes** for source-built packages
4. **Document multi-stage Dockerfile** pattern (remove compilers from final image)

---

## Files Changed (Spike Artifacts)

```
jupyter/testing/ubi9-python-3.12/
├── Dockerfile.konflux.cpu        # Added build tools for sdist
├── SPIKE-NOTES.md                # This file
├── build-args/konflux.cpu.conf
├── pylock.toml (113 packages)
├── requirements.cpu.txt
└── uv.lock

.tekton/
└── odh-workbench-jupyter-testing-cpu-py312-ubi9-pull-request.yaml
    # Changed to sdist prefetch (removed binary.arch)
    # Changed trigger to /build-testing-sdist

scripts/lockfile-generators/
└── create-requirements-lockfile.sh (added testing to PUBLIC_INDEX_PROJECTS)
```

---

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| Spike repro steps documented | ✅ |
| Binary wheel build attempted | ✅ |
| **Sdist source build attempted** | 🔄 In progress |
| Conforma assessment | ✅ |
| RHDS comparison documented | ✅ |
| Pandoc decision documented | ✅ |
| Blocker list | ✅ |
| Clear recommendation | ✅ Sdist for community, AIPCC for secure |
| Follow-up stories | 🔄 Pending sdist results |
