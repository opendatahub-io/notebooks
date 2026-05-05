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

## Base images

Base image pipelines (cuda, rocm) have version-specific filenames but version-agnostic component names. Multiple files share one component, so `trigger-pac-build` can't disambiguate them. These are triggered by `pathChanged()` on real pushes.

## RHDS

The downstream `red-hat-data-services/notebooks` repo has its own `README.md` in `.tekton/` — those files are synced from [konflux-central](https://github.com/red-hat-data-services/konflux-central) and should not be edited directly.

## History

The `-odh-main-` infix that was previously in main-branch filenames was introduced to avoid filename collisions with existing stable push files ([Slack thread](https://redhat-internal.slack.com/archives/C0961HQ858Q/p1768219590576299)). With the `-ci` suffix making stable filenames unique, the collision concern no longer applies and the naming was unified.
