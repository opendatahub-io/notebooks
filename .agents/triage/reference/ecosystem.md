# Ecosystem: Related Repositories

The notebooks repo does not live in isolation. This guide helps the triage agent decide when to consult external repos.

## Tightly Coupled Repos

| Repository | What it does | When to check |
|-----------|-------------|---------------|
| [opendatahub-io/kubeflow](https://github.com/opendatahub-io/kubeflow) | Notebooks controller — manages Notebook CRD lifecycle | Notebook spawn/stop failures, CRD changes, controller reconciliation bugs |
| [opendatahub-io/odh-dashboard](https://github.com/opendatahub-io/odh-dashboard) | UI that launches and manages notebooks | Spawner UI issues, image selection, workbench configuration |
| [opendatahub-io/opendatahub-operator](https://github.com/opendatahub-io/opendatahub-operator) | Deploys the whole ODH/RHOAI stack | Manifest deployment issues, operator reconciliation |
| [opendatahub-io/elyra](https://github.com/opendatahub-io/elyra) | Pipeline editor for Jupyter notebooks | Elyra extension issues, pipeline execution failures |
| [opendatahub-io/odh-ide-extensions](https://github.com/opendatahub-io/odh-ide-extensions) | JupyterLab extensions | Extension loading, custom UI components |
| [AIPCC base images](https://gitlab.com/redhat/rhel-ai/core/base-images/app) | Base container images for RHOAI | Base image CVEs, package availability, FIPS compliance. Uses GitLab — auth via https://red.ht/GitLabSSO |

## External Test Suites

These test our images from the outside. Regressions may surface there first.

| Suite | Framework | What it tests | Repo |
|-------|-----------|---------------|------|
| odh-dashboard | Cypress (TypeScript) | Workbench creation/deletion, image selection, status transitions | [odh-dashboard/.../workbenches](https://github.com/opendatahub-io/odh-dashboard/tree/main/packages/cypress/cypress/tests/e2e/dataScienceProjects/workbenches) |
| ods-ci | Robot Framework | Image spawning, GPU/CUDA validation, Elyra pipelines, stability | [ods-ci/.../0500__ide](https://github.com/red-hat-data-services/ods-ci/tree/master/ods_ci/tests/Tests/0500__ide) |
| opendatahub-tests | Pytest (Python) | ImageStream health, Notebook CR spawning, package availability | [opendatahub-tests/.../workbenches](https://github.com/opendatahub-io/opendatahub-tests/tree/main/tests/workbenches) |

## Context Repositories

| Repository | Purpose |
|-----------|---------|
| [opendatahub-io/architecture-context](https://github.com/opendatahub-io/architecture-context) | AI-generated architecture docs for cross-component understanding |

## Decision Guide

When triaging a bug:

1. **Is the root cause in this repo?** If yes, proceed with triage normally.
2. **Is the root cause in a tightly coupled repo?** Mark as `ai-nonfixable` in this repo. Add a comment noting which repo likely owns the fix.
3. **Is the root cause in a base image?** Check AIPCC base images. If it's a base image CVE, it's AIPCC's responsibility — mark `ai-nonfixable` with a note.
4. **Did an external test suite catch it?** Check the test suite repo for details on what's failing and why.
