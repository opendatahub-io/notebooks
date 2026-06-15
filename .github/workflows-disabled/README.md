# Disabled GitHub Actions workflows

These workflow files were moved out of `.github/workflows/` so they are **not**
registered by GitHub Actions. Only `.github/workflows/tekton-build-pr.yaml` runs
on PRs while the Konflux-aligned tekton-build path is being tested.

To restore a workflow:

```bash
git mv .github/workflows-disabled/<workflow>.yaml .github/workflows/
```

To restore everything:

```bash
git mv .github/workflows-disabled/* .github/workflows/
# Keep this README outside .github/workflows/ or delete it after restore.
```
