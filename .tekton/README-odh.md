# .tekton/ — ODH Pipeline Conventions

This directory contains [Pipelines-as-Code](https://pipelinesascode.com/) PipelineRun definitions for Konflux builds. Each notebook image component has separate pipelines for push (post-merge) and pull-request (pre-merge) builds.

## File naming

Most files follow the pattern `<component>-push.yaml` and `<component>-pull-request.yaml`, where `<component>` is the Konflux component name from the `appstudio.openshift.io/component` label inside the file. Base-image pipelines use version-specific legacy filenames (see [Base images](#base-images) below).

## Main vs stable branch pipelines

Each notebook image has two Konflux components — one building from `main` and one from `stable`:

| Component | Branch | Filename example |
|---|---|---|
| `odh-pipeline-runtime-minimal-cpu-py312-ubi9` | `main` | `odh-pipeline-runtime-minimal-cpu-py312-ubi9-push.yaml` |
| `odh-pipeline-runtime-minimal-cpu-py312-ubi9-ci` | `stable` | `odh-pipeline-runtime-minimal-cpu-py312-ubi9-ci-push.yaml` |

The `-ci` suffix distinguishes stable components. Both sets of files live on `main` — PaC reads `.tekton/` from the component's configured branch, so stable pipelines take effect once they reach the `stable` branch via merge.

## metadata.name contract

`metadata.name` in each file must be `<component>-on-push` or `<component>-on-pull-request`. This is how `trigger-pac-build` finds the right pipeline via PaC's `/incoming` webhook (see [docs/konflux.md](../docs/konflux.md#how-trigger-pac-build-works-internally)).

## Shared prefetch-input/ not watched in CEL triggers

The `prefetch-input/odh/` directory at the repo root contains shared RPM and generic artifact inputs used by hermetic builds across all images. This directory is **intentionally not watched** in any pipeline's `pathChanged()` CEL expression.

Watching it would trigger rebuilds of every single image whenever any shared prefetch input changes. Instead, changes to shared prefetch inputs should be rebuilt via `/kfbuild all` or `trigger-pac-build`. See [PR #3232 (RHAIENG-4234)](https://github.com/opendatahub-io/notebooks/pull/3232) which centralized prefetch inputs and explicitly removed them from triggers.

## Base images

Base image pipelines (cuda, rocm) have version-specific filenames but version-agnostic component names. Multiple files share one component, so `trigger-pac-build` can't disambiguate them. These are triggered by `pathChanged()` on real pushes.

## Service account naming

Service accounts (`taskRunTemplate.serviceAccountName`) in the stable push files (`*-ci-push.yaml`) do **not** follow a single convention. There are three patterns:

| Pattern | Count | Example SA | Notes |
|---|---|---|---|
| Main-branch SA (no `-ci`) | 15 | `build-pipeline-...-ubi9` | Uses the main component's SA for the stable build |
| `-poc` suffix | 3 | `build-pipeline-...-poc` | Leftover from initial PoC onboarding |
| `-ci` suffix | 0 | — | No stable file uses its own component's SA |

The `-poc` SAs exist in the cluster alongside the `-ubi9` SAs — both work. This was [documented as intentional in PR #3463](https://github.com/opendatahub-io/notebooks/pull/3463) when stable pipelines were moved to `.tekton/` on `main`. Andriana requested removing the `-poc` suffix in a [DevTestOps thread](https://redhat-internal.slack.com/archives/C07SBP17R7Z/p1756972225109469), but this requires cross-team coordination with the Konflux onboarding team (Mohammadi) who manages SAs in the tenant. We don't have permissions to create or rename SAs ourselves.

The build-service controller auto-creates SAs named `build-pipeline-<component>` when components are onboarded. Both `-ubi9` and `-ubi9-ci` SAs exist and have equivalent permissions, so the mismatch is cosmetic. Tracked in [#3517](https://github.com/opendatahub-io/notebooks/issues/3517).

## RHDS

The downstream `red-hat-data-services/notebooks` repo has its own `README.md` in `.tekton/` — those files are synced from [konflux-central](https://github.com/red-hat-data-services/konflux-central) and should not be edited directly.

## History

The `-odh-main-` infix that was previously in main-branch filenames was introduced to avoid filename collisions with existing stable push files ([Slack thread](https://redhat-internal.slack.com/archives/C0961HQ858Q/p1768219590576299)). With the `-ci` suffix making stable filenames unique, the collision concern no longer applies and the naming was unified.
