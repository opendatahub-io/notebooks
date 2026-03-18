# 7. Add devcontainer configuration

Date: 2026-03-18

## Status

Proposed

## Context

The repository scored 60/100 on Build/Dependency Setup in the AI Bug Automation Readiness Report (weight: 5%).
AI agents and new contributors need a one-command dev environment bootstrap.

The repository already has:
- `.python-version` file (specifies Python 3.14)
- Setup instructions in `README.md`, `CONTRIBUTING.md`, and `AGENTS.md`
- `uv.lock` for reproducible dependency installation
- `./uv` wrapper that auto-downloads the pinned uv version (0.10.6)

The missing piece was a **devcontainer configuration** that lets Codespaces, VS Code Remote Containers,
and AI coding agents start with a fully working environment automatically.

## Decision

Use a Fedora-based `Dockerfile.dev` referenced by `devcontainer.json`.

### Base image options explored

| Option | Image | Python 3.14 | Pros | Cons |
|--------|-------|:-----------:|------|------|
| Microsoft Python devcontainer | `mcr.microsoft.com/devcontainers/python:3.14` | Yes | Pre-built, fast startup, devcontainer features work natively | Debian-based (project builds on RHEL/UBI), no podman |
| Eclipse Che UBI 9 | `quay.io/devfile/universal-developer-image:ubi9-latest` | No (3.11) | Polyglot, used by OpenShift Dev Spaces | Python too old |
| Eclipse Che UBI 10 | `quay.io/devfile/universal-developer-image:ubi10-latest` | No (3.13) | Closer to project's RHEL base | Python too old |
| Eclipse Che Fedora | `devfile/cloud-dev-images` Fedora Dockerfile | No (3.13) | Fedora-based | Not a published image, Python too old |
| **Fedora latest** | `registry.fedoraproject.org/fedora:latest` | **Yes** | Python 3.14 as system default, `dnf` matches repo Dockerfiles, podman is native | Requires custom Dockerfile, devcontainer features may not all work |

### Why Fedora

- **Python 3.14** is the system default — no need to install from external sources
- **`dnf`** package manager matches what the project's own Dockerfiles use
- **Podman** is a first-class citizen on Fedora
- Closer to the RHEL/UBI target platform than Debian
- Multi-arch support: amd64, arm64, ppc64le, s390x — works on ARM Macs

### Why Dockerfile.dev instead of image-only devcontainer

Microsoft's devcontainer features (`ghcr.io/devcontainers/features/*`) assume Debian/Ubuntu
and generally don't work on Fedora. A custom `Dockerfile.dev` lets us install system
dependencies via `dnf` directly, which is simpler and more transparent.

### What's included

- Python 3.14 (system default)
- Go toolchain (for `scripts/buildinputs/`)
- `make` (build system)
- `podman` (container builds and tests)
- `yamllint` (YAML validation)
- `git`
- `uv` — handled by the repo's `./uv` wrapper script, not installed in the image

### What's NOT included (opt-in)

- **Playwright/browsers** — only needed for `tests/browser/`, install via `cd tests/browser && pnpm install && npx playwright install --with-deps`
- **Node.js/pnpm** — only needed for browser tests
- **`hadolint`** — not in Fedora repos, download binary separately if needed

### Container engine inside the devcontainer

Building container images inside a devcontainer requires nested container support,
which varies by host environment:

| Host environment | Approach | Notes |
|-----------------|----------|-------|
| GitHub Codespaces | `--privileged` + podman | Works well, Linux VM host |
| VS Code + Docker Desktop | Docker socket mount | Uses host engine, add `"mounts"` in devcontainer.json |
| VS Code + Docker Desktop | `--privileged` + podman | Podman-in-Docker, needs cgroup v2 |
| OpenShift Dev Spaces | Che sidecar | Needs user namespace support |
| Local machine (no container) | Direct podman/docker | Devcontainer not used |

The devcontainer installs podman but building images may require `--privileged` or host
socket mounting depending on the environment. This is a known limitation of nested containers.
The default configuration does not add `--privileged` — users who need container builds
can add `"runArgs": ["--privileged"]` to their local devcontainer.json.

### Other considerations

- Fedora `latest` tag floats (currently F43) — acceptable for dev environments, not for CI
- `postCreateCommand` runs `./uv sync --locked` which auto-downloads the pinned uv version
- VS Code extensions declared: ruff (linting) and Python (language support)

## Consequences

### Positive

- AI agents and new contributors get a working environment with a single command
- Codespaces users can start contributing immediately
- Dev environment matches the project's RHEL/UBI-based build target more closely than Debian

### Negative

- Custom Dockerfile means slower first build compared to pre-built Microsoft images
- Fedora `latest` floats — dev environment may change between Fedora releases
- Some devcontainer features won't work on Fedora (Debian-specific install scripts)

## References

- Issue: <https://github.com/opendatahub-io/notebooks/issues/3122>
- AI Bug Automation Readiness: <https://github.com/opendatahub-io/notebooks/issues/3111>
- Devcontainer spec: <https://containers.dev/>
- Eclipse Che developer images: <https://github.com/devfile/developer-images>
- Eclipse Che cloud-dev-images: <https://github.com/devfile/cloud-dev-images>
