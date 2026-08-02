# AI Agents Guide for OpenDataHub Notebooks

This repository builds containerized Jupyter, Code-Server, and runtime images for the
OpenDataHub ecosystem. Stack: Python 3.14, `uv`, Podman/Docker, GNU Make, building
multi-stage Dockerfiles on Centos 9 Stream (ODH) and RHEL 9.6 EUS (RHOAI) with Python
3.12 virtual env inside.

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
| [docs/cves/agents-cve-autofix.md](docs/cves/agents-cve-autofix.md) | You are an automated CVE fix agent (jira-autofix) |
| [`.github/AGENTS.md`](.github/AGENTS.md) | You are editing GitHub Actions or action metadata |
| [`ci/agentic-reviewer/AGENTS.md`](ci/agentic-reviewer/AGENTS.md) | You are editing Antigravity PR review / CI summary agents |
| [`tests/browser/AGENTS.md`](tests/browser/AGENTS.md) | You are editing Playwright tests or browser tooling |
| [docs/agents/testing.md](docs/agents/testing.md) | You need the test catalog: types, markers, commands, CI parity |
| `ci/security-scan/` | You need Quay vulnerability scan results or the weekly security workflow |
| [docs/ai-coding-assistant-project-config.md](docs/ai-coding-assistant-project-config.md) | You need the cross-tool `AGENTS.md` / `CLAUDE.md` / skills layout |
| [`.agents/skills/`](.agents/skills/) | You are authoring or discovering Agent Skills |

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

`PRODUCT` selects the product variant (ODH midstream vs RHOAI downstream), not whether
the build runs on Konflux/Tekton. ODH workbenches stack on c9s odh-base-images;
RHOAI stacks on RHEL 9.6 AIPCC bases (`ubi9-python-*` paths are EL9 naming only).
See [ARCHITECTURE.md](ARCHITECTURE.md) for details and
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
- Update nearby documentation when behavior changes, especially build, dependency, and CI workflows.
- Stage explicitly: `git add <file1> <file2> ...`. For genuine bulk-regen output where
  hand-listing every path is impractical (lockfiles from `make refresh-lock-files`, `.tekton/`
  pipeline regen, imagestream manifest updates), a scoped pathspec is fine — but only right
  after checking `git status`/`git diff --stat` for that scope so you know exactly what it
  matches, using a tight pattern anchored to a shared prefix and suffix (e.g.
  `git add .tekton/odh-*-pull-request.yaml`, not `git add .tekton/*` or `git add .`). Before
  committing, re-run `git status` and skim `git diff --cached` for the staged paths —
  `git status` only shows which paths are staged, not which hunks, so a file you explicitly
  staged can still carry an unrelated edit. If the changed set is short enough to read at a
  glance, just spell out the filenames — a glob earns its keep only when the set is too large
  to enumerate by hand.

## Boundaries

- **Always:** Run `make test` after Dockerfile or dependency changes. Keep `PRODUCT`
  consistent across `make <target>` and `make test-<target>`. Override the entrypoint
  when inspecting images (`podman run --rm -it --entrypoint="" <image> bash`).
- **Ask first:** Adding new base images, changing CI workflow structure, modifying
  `.tekton/` pipelines, or renaming image labels in `ci/` metadata files.
- **Never:** Comment out tests to silence failures. Copy internal-only links or
  hostnames into public docs. Modify `.tekton/` in `red-hat-data-services/notebooks`
  directly (PipelineRuns are synced from `konflux-central`). Bump container OS bases
  to RHEL/UBI/CentOS 10 or accept MintMaker PRs that do — the project stays on EL9;
  see [base-images/README.md](base-images/README.md#os-version-policy-el9-only).
  Stage with `git add -A`, `git add .`, or `git add --all` — these sweep in whatever
  else is sitting in the tree (scratch files, unrelated in-progress edits, generated
  artifacts) with no chance to notice until it's already committed.

## Communication

English, terse.
Use formatting: bold, italics and code blocks.

## Operational notes

- To inspect an image without starting Jupyter, override the entrypoint:
  `podman run --rm -it --entrypoint="" <image> bash`.
  Without this, arguments are ignored and Jupyter starts.
- One-off commands (no interactive shell):
  `podman run --rm --entrypoint="" <image> rpm -qa | sort`
- `PRODUCT` must match between `make <target>` and `make test-<target>`.
  Mismatches cause version assertion failures because the test reads the
  imagestream manifest selected by `PRODUCT`.
- Python 3.14: `except ExcA, ExcB:` (no parentheses) is valid when there is no
  `as` clause (PEP 758). Ruff format enforces this style. Parentheses are still
  required when binding: `except (ExcA, ExcB) as e:`.
- CI pytest runs force `FORCE_COLOR=1`, so their console output contains ANSI
  color codes. Don't grep/process that text directly. Prefer the
  `pytest-logs.txt` artifact instead (uploaded by the `pytest-tests` job's
  "Upload pytest debug log" step) — it's written by pytest's `log_file`
  handler, a plain `logging.FileHandler` independent of the colorized
  terminal writer, so pytest itself never colors it. It can still contain
  color if a logged message embeds its own escape codes (e.g.
  `scripts/update_build_args_from_versions.py`'s `ANSI_RED`-style warnings),
  so don't assume it's *guaranteed* ANSI-free — check with `grep -c $'\x1b'`
  if it matters. If you do need to strip ANSI codes from console/log text,
  reuse the pattern already in `code-quality.yaml`'s `prek` step:
  `sed -E 's/\x1B\[([0-9]{1,2}(;[0-9]{1,2})*)?[mGK]//g'`.

## Commit and PR title style

Preferred format: `TICKET: scope: description in imperative mood`

Scope follows [Conventional Commits](https://www.conventionalcommits.org/)
(`chore`, `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, etc.), optionally
with a directory hint like `chore(.tekton/)` or `fix(jupyter/trustyai)`.
Most dependency/CVE work is `chore`. See `.coderabbit.yaml` for validation rules.

## Repo-specific reminders

- Use `uv` and `make refresh-lock-files`. Keep dependency guidance aligned with current repo tooling.
- For local testing gotchas such as worktree naming, `pyfakefs`, `PRODUCT` matching, and CI `-n` metadata,
  see [CONTRIBUTING.md](CONTRIBUTING.md).
- For GitHub Actions changes, run the SHA pinning flow in [`.github/AGENTS.md`](.github/AGENTS.md).
- For browser tests, follow [`tests/browser/AGENTS.md`](tests/browser/AGENTS.md) instead of inventing local conventions.

## Local-only notes

If present, `CLAUDE.local.md` is gitignored and may contain personal preferences or internal-only
RHDS/Konflux operating notes. Do not copy its internal details into committed files.
