# `.tekton/` on `rhoai-2.25`

## konflux-central sync (push pipelines only)

The 18 `*-v2-25-push.yaml` files are synchronized from [`konflux-central`](https://github.com/red-hat-data-services/konflux-central) (`pipelineruns/notebooks/.tekton/` on branch `rhoai-2.25`). Edits to those files in this repository will be overwritten by the next sync.

`konflux-central` does not contain pull-request PipelineRuns for notebooks on the 2.25 release.

## Pull-request pipelines (local only)

The `*-pull-request.yaml` files are maintained in this repository only. They power `/build-konflux` and related PaC PR triggers for `red-hat-data-services/notebooks` on `rhoai-2.25`. Edit them here; they are not synced from `konflux-central`.

**Gap:** `odh-pipeline-runtime-pytorch-llmcompressor-cuda-py312` has a `*-v2-25-push.yaml` but no matching `*-pull-request.yaml` yet.

## Making changes

### Push pipelines (post-merge)

To modify post-merge Konflux builds:

- Clone [`konflux-central`](https://github.com/red-hat-data-services/konflux-central).
- Check out branch `rhoai-2.25`.
- Edit files under `pipelineruns/notebooks/.tekton/` (the `*-v2-25-push.yaml` set).
- Commit, push, and wait for automation to sync into this repo.

```bash
git clone git@github.com:red-hat-data-services/konflux-central.git
cd konflux-central
git checkout rhoai-2.25
cd pipelineruns/notebooks/.tekton
# edit *-v2-25-push.yaml
git commit -am "Update pipelinerun for notebooks (rhoai-2.25)"
git push origin rhoai-2.25
```

### Pull-request pipelines (pre-merge)

Edit the relevant `*-pull-request.yaml` in this repo and open a PR on `red-hat-data-services/notebooks`.
