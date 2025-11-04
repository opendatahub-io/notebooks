# 5. Implement Dockerfile templating to remove duplication

Date: 2025-11-04

## Status

Accepted

## Context
The project contains multiple Dockerfiles/Containerfiles with significant duplication across different variants (CPU/GPU, different Python versions, different base distributions).
Maintaining these duplicated files is error-prone, as changes need to be manually propagated across multiple files, increasing the risk of inconsistencies, merge conflicts, and bugs.

We agreed to implement a templating solution to reduce duplication.

We are aware that introducing abstractions may make the project harder to understand for newcomers, and inappropriate abstractions would make it more difficult to make changes that used to be easy.
Therefore, we're committed to maintaining clarity and debuggability of the build process and to keeping the abstraction malleable so that it can be adjusted to future needs as the project evolves.

## Decision
We are already using the standard `${VARIABLE}` substitution via `podman build --build-arg-file`.

Implement Dockerfile/Containerfile templating using a phased approach:

### Phase 1: Containerfile.in with Podman/CPP

Begin using Podman's native `Containerfile.in` preprocessing feature (available since Podman 2.2.1).

Containerfiles with `.in` suffix are automatically preprocessed via CPP(1), enabling:
- **C preprocessor directives**: `#include`, `#define`, `#ifdef`, `#if`, `#else`, `#endif`, etc.
- **File decomposition**: Break Containerfiles into reusable parts via `#include` directive
- **Manual preprocessing**: Files can be preprocessed outside Podman via `cpp -E Containerfile.in`
- **Already in use**: We currently use this feature in the project

Documentation: https://docs.podman.io/en/v2.2.1/markdown/podman-build.1.html

Note: Historical issues with comment handling (https://github.com/containers/buildah/issues/3229) were resolved in https://github.com/containers/buildah/pull/3241

### Phase 2: Python-based Templating
When Containerfile.in proves insufficient for complex templating needs, adopt a Python-based solution:

Options evaluated:
1. **Python f-strings**: Simple, native, no dependencies, good for basic interpolation
2. **stencils** (https://github.com/devcoons/stencils): Lightweight alternative, less mature
3. **Jinja2**: Industry-standard, powerful control structures (loops, conditionals), extensive ecosystem

Recommendation: Jinja2 for Phase 2 due to widespread adoption, maturity, and powerful templating capabilities.

### Generated Code Management Decision
Must decide whether to:
- **Option A: Commit generated Containerfiles to Git**
  - Pros: Reproducible builds, easier debugging, clear history of what was built
  - Cons: Potential for drift between templates and committed files, larger repo

- **Option B: Generate on-the-fly during build**
  - Pros: Single source of truth, impossible for drift, cleaner repo
  - Cons: Requires templating tooling in CI/CD, harder to debug build failures

Initial recommendation: Commit generated files (Option A) for traceability and easier debugging, with CI checks to ensure templates and generated files stay in sync.

## Consequences

### Positive
- Reduced duplication across Containerfiles
- Easier maintenance: changes to common patterns apply across all variants
- Lower risk of inconsistencies between variants
- Improved consistency in build configuration
- Clearer separation between variant-specific and common configuration

### Negative/Risks
- Additional complexity in the build process
- Learning curve for contributors unfamiliar with the templating system
- Risk of template bugs affecting multiple Containerfiles simultaneously
- Need to maintain tooling/scripts for template generation
- If committing generated files: need CI validation to catch drift
- If generating on-the-fly: build failures harder to debug without seeing the final Containerfile

### Mitigations
- Start with the simplest solution (Containerfile.in) and only move to more complex templating as needed
- Document templating approach clearly in the repository
- Implement CI checks to validate generated Containerfiles
- Provide clear error messages in templating scripts
- Keep templates as simple and readable as possible
- Consider a hybrid approach: commit generated files but validate against templates in CI

### Previous work

- <https://gitlab.cee.redhat.com/astonebe/notebook-utils>
- [RHOAIENG-16969 Remove specific instances of code duplication in odh/notebooks](https://issues.redhat.com/browse/RHOAIENG-16969)
- [RHOAIENG-19047 Deduplicate files that get included in workbench images](https://issues.redhat.com/browse/RHOAIENG-19047)
- [RHOAIENG-19046 Remove reliance on "chained builds" in notebooks repo](https://issues.redhat.com/browse/RHOAIENG-19046)
- [fix(makefile): standardized image targets #1015](https://github.com/opendatahub-io/notebooks/pull/1015)
  - [RHOAIENG-16587: fix(test): ensure papermill tests run successfully for all supported notebooks #834](https://github.com/opendatahub-io/notebooks/pull/834)
  - <https://redhat-internal.slack.com/archives/C060A5FJEAD/p1738786041914139>
- [📦 Consolidate duplicate bootstrapper implementations across Python 3.12 runtime environments #1349](https://github.com/opendatahub-io/notebooks/issues/1349)
- [improve and simplify docker multistage build in jupyter/datascience/ubi9-python-3.12/Dockerfile.cpu #2467](https://github.com/opendatahub-io/notebooks/issues/2467)
- [Refactor notebooks-release workflow to eliminate code duplication using reusable workflows #1185](https://github.com/opendatahub-io/notebooks/issues/1185)
