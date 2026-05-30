# AI Agents Guide for OpenDataHub Notebooks

This file is the short entry point for AI agents working in this repository. Keep it lean,
and follow linked documents for topic-specific detail.

## Start here

| Read this | When |
|-----------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | You need the system map: image layout, key directories, build modes, platform integration |
| [CONTRIBUTING.md](CONTRIBUTING.md) | You are changing code or docs and need local workflow, review expectations, or local testing gotchas |
| [docs/ci.md](docs/ci.md) | You need to understand which CI system owns a failure |
| [docs/konflux.md](docs/konflux.md) | You are touching `.tekton/`, Konflux builds, or upstream/downstream pipeline behavior |
| [docs/subscribed-builds.md](docs/subscribed-builds.md) | You need local AIPCC / subscribed builds |
| [docs/uv-guide.md](docs/uv-guide.md) | You are changing Python dependencies beyond the quick path in `CONTRIBUTING.md` |
| [docs/cves/python.md](docs/cves/python.md) / [docs/cves/nodejs.md](docs/cves/nodejs.md) | You are fixing CVEs or lockfile-driven security updates |
| [`.github/AGENTS.md`](.github/AGENTS.md) | You are editing GitHub Actions or action metadata |
| [`tests/browser/AGENTS.md`](tests/browser/AGENTS.md) | You are editing Playwright tests or browser tooling |
| [docs/ai-coding-assistant-project-config.md](docs/ai-coding-assistant-project-config.md) | You need the cross-tool `AGENTS.md` / `CLAUDE.md` / skills layout |

Follow-up issue [#3174](https://github.com/opendatahub-io/notebooks/issues/3174) is expected to add
`docs/agents/testing.md`. Until that lands, use `CONTRIBUTING.md` for local testing traps.

## Baseline tools

- Python 3.14
- `uv`
- Podman or Docker
- `make`
- `pinact` when editing `.github/`

On macOS, install Homebrew GNU Make so `make` resolves to GNU Make 4.x
(see [CONTRIBUTING.md](CONTRIBUTING.md) for the exact setup).

## Repo model

This repository builds container images for:

- Jupyter workbenches under `jupyter/`
- Elyra runtime images under `runtimes/`
- Code-Server workbenches under `codeserver/`
- Base images under `base-images/`

See [ARCHITECTURE.md](ARCHITECTURE.md) for the authoritative directory map.

### Multi-stage Dockerfiles, not image inheritance

Each notebook image is a self-contained multi-stage Dockerfile that starts from `${BASE_IMAGE}`
and rebuilds every ancestor stage internally. No notebook image `FROM`s another notebook image.

When you change an earlier logical stage such as minimal or datascience, check every leaf Dockerfile
that embeds that stage. Do not assume there is one shared parent image definition to update.

### ODH vs RHOAI builds

`KONFLUX` selects the product variant (ODH midstream vs RHOAI downstream), not whether
the build runs on Konflux/Tekton. See [ARCHITECTURE.md](ARCHITECTURE.md) for details and
[CONTRIBUTING.md](CONTRIBUTING.md) for local-build gotchas.

## Common commands

```bash
uv venv --python "$(which python3.14)"
uv sync --locked
make test
make test-unit
make test-integration PYTEST_ARGS="--image=<image>"
make refresh-lock-files
```

## Agent conduct

- Make the smallest correct change and follow existing conventions.
- Prefer existing docs over guesswork. Read the linked doc before inventing process or policy.
- Verify bulk edits after scripting them. This repo has generated files and repeated patterns.
- Do not comment out tests to make failures disappear. Fix the root cause or add a justified skip.
- Keep public docs free of internal-only links, hostnames, or Slack threads.
- Update nearby documentation when behavior changes, especially build, dependency, and CI workflows.

## Repo-specific reminders

- Use `uv` and `make refresh-lock-files`. Keep dependency guidance aligned with current repo tooling.
- For local testing gotchas such as worktree naming, `pyfakefs`, `KONFLUX` matching, and CI `-n` metadata,
  see [CONTRIBUTING.md](CONTRIBUTING.md).
- For GitHub Actions changes, run the SHA pinning flow in [`.github/AGENTS.md`](.github/AGENTS.md).
- For browser tests, follow [`tests/browser/AGENTS.md`](tests/browser/AGENTS.md) instead of inventing local conventions.

## Local-only notes

If present, `CLAUDE.local.md` is gitignored and may contain personal preferences or internal-only
RHDS/Konflux operating notes. Do not copy its internal details into committed files.
