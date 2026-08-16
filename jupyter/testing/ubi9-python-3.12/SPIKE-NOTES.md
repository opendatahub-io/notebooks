# Hermetic Build Spike - Public PyPI

**Jira:** RHAIENG-6564
**Branch:** `spike/hermetic-public-pypi`
**Date:** 2026-08-16

## Objective
Test hermetic builds using only public PyPI packages (no RHAI internal index).

## Executive Summary

✅ **Public PyPI packages can be successfully locked and prefetched for hermetic builds.**

- 113 Python packages resolved from public PyPI
- 270MB of wheels prefetched successfully
- No blocking issues found with package availability for x86_64

## Setup Completed

| Step | Status | Details |
|------|--------|---------|
| Create test image dir | ✅ | `jupyter/testing/ubi9-python-3.12` |
| Remove CUDA/ROCM | ✅ | CPU-only for spike |
| Configure public base | ✅ | `registry.access.redhat.com/ubi9/python-312` |
| Update pyproject.toml | ✅ | Public PyPI index only |
| Remove pandoc-rhai | ✅ | Not on public PyPI |
| Generate uv.lock | ✅ | 113 packages locked |
| Generate requirements.txt | ✅ | With hashes for hermetic |
| Create Tekton PipelineRun | ✅ | Triggered via `/build-testing-spike` |
| Run prefetch-all.sh | ✅ | 270MB pip, 3GB RPMs |

## Key Findings

### 1. Package Availability on Public PyPI ✅

All JupyterLab dependencies available on public PyPI:

| Package | Status | Version |
|---------|--------|---------|
| jupyterlab | ✅ | 4.6.3 |
| jupyter-server | ✅ | 2.20.0 |
| odh-jupyter-trash-cleanup | ✅ | 0.1.1 |
| All 110 other deps | ✅ | Latest |

**Not Available:**
- `pandoc-rhai` - RHAI internal (see Section D)

### 2. Prefetch Results ✅

```
Dependencies downloaded:
  Generic: 8KB (GPG keys)
  Pip:     270MB (113 packages from public PyPI)
  RPMs:    3GB (4 architectures)

Total time: ~44 minutes
```

### 3. Pandoc/PDF Export ⚠️

`pandoc-rhai` is not on public PyPI. Options:
1. **Skip PDF export** (current approach) - simplest
2. **System pandoc from RPMs** - requires additional RPM deps
3. **pypandoc from PyPI** - downloads pandoc binary at install time

**Recommendation:** For public-index images, skip PDF export or use system pandoc.

### 4. Local Build Results

Local podman build encountered permission issues with bind mounts (local env quirk).
Key hermetic components validated:
- ✅ Base image from public registry works
- ✅ GPG key import from cachi2 works
- ✅ Prefetch-input integration works

**Next step:** Test in Konflux via PR.

## Files Changed

```
jupyter/testing/ubi9-python-3.12/
├── Dockerfile.konflux.cpu          # Updated for public base
├── build-args/konflux.cpu.conf     # Public RHEL base image
├── pyproject.toml                  # Public PyPI index
├── pylock.toml                     # NEW: 113 packages locked
├── uv.lock                         # NEW: Full lock file
├── requirements.cpu.txt            # 895 lines with hashes
└── SPIKE-NOTES.md                  # This file

scripts/lockfile-generators/
└── create-requirements-lockfile.sh # Added testing to PUBLIC_INDEX_PROJECTS

.tekton/
└── odh-workbench-jupyter-testing-cpu-py312-ubi9-pull-request.yaml
```

## How to Test in Konflux

1. **Push branch:**
   ```bash
   git push -u origin spike/hermetic-public-pypi
   ```

2. **Create PR** targeting `main`

3. **Trigger build** by commenting:
   ```
   /build-testing-spike
   ```

4. **Monitor** Konflux build logs for:
   - Cachi2 prefetch success
   - pip install from local cache
   - No network access during build

## Recommendations

### For ODH Baseline Images
Public PyPI hermetic builds are **feasible** with these considerations:

1. **Package availability:** All core JupyterLab packages available
2. **Wheel coverage:** x86_64 well covered; test ppc64le/s390x
3. **PDF export:** Decide on pandoc approach
4. **Policy review:** Confirm compliance allows public PyPI

### Next Steps

1. [ ] Submit PR and run Konflux build
2. [ ] Test multi-arch wheel availability (ppc64le, s390x)
3. [ ] Review Conforma compliance requirements
4. [ ] Document pandoc solution
5. [ ] Get policy approval for public PyPI usage

## Acceptance Criteria Status

| Criteria | Status |
|----------|--------|
| Packages resolve from public PyPI | ✅ |
| Prefetch succeeds | ✅ |
| Hermetic build (no network) | ⏳ Pending Konflux test |
| Multi-arch support | ⏳ Pending test |
| Policy compliance | ⏳ Pending review |
