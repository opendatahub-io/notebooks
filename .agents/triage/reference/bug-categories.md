# Bug Categories for OpenDataHub Notebooks

Classification of bugs by type, with fixability heuristics for AI triage.
Each category includes typical symptoms, affected files, related repos, and AI fixability assessment.

## 1. Dockerfile / Build Issues

**Fixability: Usually AI-fixable**

Wrong base image, missing packages, layer ordering, COPY path errors, build argument mismatches.

- **Files**: `*/Dockerfile.*`, `*/Dockerfile.konflux.*`
- **Symptoms**: Build failures, missing binaries in image, wrong Python version
- **Related repos**: AIPCC base images (`gitlab.com/redhat/rhel-ai/core/base-images/app`)
- **Notes**: Must keep `Dockerfile.*` and `Dockerfile.konflux.*` variants in sync. Check KONFLUX=yes/no consistency.

## 2. Python Dependency Conflicts

**Fixability: Usually AI-fixable**

Version incompatibilities, missing dependencies, lock file drift, resolver failures.

- **Files**: `*/pyproject.toml`, `*/pylock.toml`, `*/uv.lock`
- **Symptoms**: `pip install` failures, import errors, version mismatch warnings
- **Related repos**: Upstream PyPI packages, AIPCC wheels index
- **Notes**: After modifying dependencies: `gmake refresh-lock-files` (or targeted: `./uv run scripts/pylocks_generator.py auto <dir>`). Understand the inheritance model — minimal -> datascience -> specialized.

## 3. Test Infrastructure

**Fixability: Usually AI-fixable**

Flaky tests, fixture issues, assertion errors, test configuration problems.

- **Files**: `tests/**/*.py`, `tests/browser/**`, `conftest.py`
- **Symptoms**: Intermittent test failures, wrong assertions, missing fixtures
- **Related repos**: None (self-contained)
- **Notes**: Mirror the source layout (`scripts/cve/` -> `tests/unit/scripts/cve/`). Run `./uv run pytest tests/unit/` to verify.

## 4. Image Manifest / Version Mismatches

**Fixability: Usually AI-fixable**

Wrong tags in imagestream manifests, missing image entries, version drift between manifests and Makefile.

- **Files**: `manifests/odh/base/*.yaml`, `manifests/rhoai/base/*.yaml`, `manifests/*/base/params-latest.env`
- **Symptoms**: Wrong image deployed, missing notebook option in dashboard, version mismatch
- **Related repos**: opendatahub-io/opendatahub-operator (deploys manifests), opendatahub-io/odh-dashboard (reads imagestreams)
- **Notes**: `params-latest.env` format differs by variant: ODH has image tags, RHOAI has placeholder values (operator overrides at deploy time via `RELATED_IMAGE_*`). After changing manifests: `./uv run manifests/tools/generate_kustomization.py`.

## 5. Security / CVE Updates

**Fixability: Usually AI-fixable**

Package version bumps for CVE remediation, vulnerability scanner findings.

- **Files**: Dependency files (pyproject.toml, `dependencies/cve-constraints.txt`), Dockerfiles (RPM packages)
- **Symptoms**: CVE scan alerts, security tracker issues
- **Related repos**: AIPCC base images, upstream package registries
- **Notes**: See `skills/scan-image.md` for scanning tools. See `skills/close-vex.md` for VEX justification workflow. See `skills/assess-cve.md` for CVE tracker triage. Check if CVE is in base image (AIPCC responsibility) vs. added packages (our responsibility).

## 6. CI/CD Pipeline Configuration

**Fixability: Often AI-fixable**

Tekton pipeline issues, GitHub Actions workflow problems, CI script bugs.

- **Files**: `.tekton/*.yaml`, `.github/workflows/*.yaml`, `ci/**`
- **Symptoms**: Pipeline failures, missing steps, wrong parameters
- **Related repos**: None (self-contained CI config)
- **Notes**: Tekton pipelines are generated/templated — check `scripts/generate_*.py` if the pipeline YAML is auto-generated.

## 7. Runtime / GPU Issues

**Fixability: Usually NOT AI-fixable**

CUDA/ROCm compatibility, GPU driver issues, kernel module problems, OOM on GPU workloads.

- **Files**: `cuda/`, GPU-specific Dockerfiles
- **Symptoms**: GPU not detected, CUDA errors, ROCm initialization failures
- **Related repos**: NVIDIA/CUDA base images, AMD ROCm
- **Why not fixable**: Requires actual GPU hardware or cluster with GPU nodes to reproduce and verify. Agent cannot test GPU operations locally.

## 8. UI / Browser Issues

**Fixability: Usually NOT AI-fixable**

JupyterLab rendering, Code Server UI problems, extension loading failures, notebook UI glitches.

- **Files**: `jupyter/utils/addons/`, extension configs, nginx configs
- **Symptoms**: UI doesn't render, extensions missing, browser console errors
- **Related repos**: opendatahub-io/odh-ide-extensions, opendatahub-io/odh-dashboard
- **Why not fixable**: Requires visual browser testing (Playwright) and potentially a running notebook server. Agent may be able to fix if browser testing tools are available (see prerequisites).

## Cross-Repo Issues

Some bugs span multiple repositories. When the root cause is outside this repo:

| Symptom in notebooks | Likely root cause repo |
|---------------------|----------------------|
| Notebook won't spawn | opendatahub-io/kubeflow (notebook controller) |
| Dashboard doesn't show notebook option | opendatahub-io/odh-dashboard |
| Pipeline execution fails in notebook | opendatahub-io/elyra |
| Extension won't load | opendatahub-io/odh-ide-extensions |
| Base image CVE | gitlab.com/redhat/rhel-ai/core/base-images/app |
| Operator doesn't deploy updated image | opendatahub-io/opendatahub-operator |

Mark cross-repo issues as `ai-nonfixable` in this repo unless the fix is clearly in notebook code.
