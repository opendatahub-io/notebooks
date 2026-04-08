# Copr Package Rebuild Tool

Rebuilds Fedora source RPMs for EL9 on [Copr](https://copr.fedorainfracloud.org/coprs/aaiet-notebooks/rhelai-el9/), so our CentOS Stream 9 base images can install newer system libraries (e.g. HDF5 1.14.x) that AIPCC Python wheels need at runtime.

See [spec.md](spec.md) for the full requirements document.

## Quick start

```shell
# Show the build plan without submitting
uv run --package copr-rebuild copr-rebuild --dry-run

# Submit all builds to Copr
uv run --package copr-rebuild copr-rebuild

# Verbose logging
uv run --package copr-rebuild copr-rebuild --dry-run --verbose
```

## Setup

1. Install [copr-cli](https://developer.fedoraproject.org/deployment/copr/copr-cli.html) and authenticate:
   ```shell
   # Fedora/RHEL
   sudo dnf install copr-cli
   # macOS
   pip install copr-cli

   # Get your API token from https://copr.fedorainfracloud.org/api/
   # and save it to ~/.config/copr
   ```

2. Request build permissions on the [aaiet-notebooks/rhelai-el9](https://copr.fedorainfracloud.org/coprs/aaiet-notebooks/rhelai-el9/permissions/) project, or fork it into your own account for experimentation.

## Adding a package

Edit [`src/copr_rebuild/packages.yaml`](src/copr_rebuild/packages.yaml):

```yaml
packages:
  - name: my-package
    nvr: my-package-1.2.3-4.fc43
    note: "why this package is needed"
```

That's it. The tool automatically:
- Queries [Koji](https://koji.fedoraproject.org/) for the SRPM URL, provides, and BuildRequires
- Computes the build order (topological sort into parallel waves)
- Submits builds with correct sequencing via Copr batch ordering

Run `--dry-run` first to verify the plan.

### Manifest fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Source package name |
| `nvr` | yes | Fedora Name-Version-Release (e.g. `hdf5-1.14.6-6.fc43`) |
| `note` | no | Why this package is needed |
| `skip_tests` | no | Skip `%check` section (default: false) |

Top-level manifest fields: `copr_project`, `koji_tag`, `chroots`, `chroot_packages`, `build_timeout`.

### Skipping tests

Some packages have test suites that are too slow or fail on EL9. Set `skip_tests: true` to inject `exit 0` after `%check` in the spec file via Copr custom builds.

## How it works

1. **Resolve** -- queries Koji XML-RPC for each package's metadata (SRPM URL, provides, BuildRequires)
2. **Plan** -- builds a dependency graph among manifest packages, topological sort into waves
3. **Submit** -- sends all waves to Copr in one pass using batch ordering (`--with-build-id` for parallel, `--after-build-id` for sequential)
4. **Wait** -- polls all builds round-robin with exponential backoff (30s to 5min), fails fast on any build failure

## Project structure

```
base-images/copr/
  pyproject.toml          # workspace member config + CLI entry point
  spec.md                 # product requirements
  src/copr_rebuild/
    packages.yaml         # the manifest
    manifest_schema.json  # JSON schema (generated from Pydantic models)
    rebuild.py            # CLI orchestrator
    copr_client.py        # Copr build submission and polling
    koji_client.py        # Koji XML-RPC queries
    dependency_resolver.py # topological sort into build waves
    models.py             # Pydantic models + schema generator
```