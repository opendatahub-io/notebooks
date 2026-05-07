# IBM GitHub Actions Runners for Power and Z

IBM provides free self-hosted GitHub Actions runners for open-source projects
through the [actionspz](https://github.com/IBM/actionspz) project. We use these
for native ppc64le (IBM Power) and s390x (IBM Z / LinuxONE) builds, replacing
qemu-user cross-compilation on amd64 GitHub-hosted runners.

## Runner labels

| Label | Architecture | Hardware |
|---|---|---|
| `ubuntu-24.04-ppc64le` | ppc64le | IBM POWER9 |
| `ubuntu-24.04-ppc64le-p10` | ppc64le | IBM POWER10 (may be deprecated) |
| `ubuntu-24.04-s390x` | s390x | IBM Z / LinuxONE |

Full list: <https://github.com/IBM/actionspz/blob/main/docs/supported-images.txt>

Runner image contents: <https://github.com/IBM/action-runner-image-pz/blob/main/images/ubuntu/toolsets/toolset-2404.json>

## Onboarding

- Our onboarding issue: <https://github.com/IBM/actionspz/issues/63>
- GitHub tracking issue: <https://github.com/opendatahub-io/notebooks/issues/2675>
- Jira: [RHAIENG-4858](https://redhat.atlassian.net/browse/RHAIENG-4858)

The GitHub App ([Power Z GHA Runner](https://github.com/apps/power-z-gha-runner))
is installed at the `opendatahub-io` org level. IBM approved `opendatahub-io/notebooks`
in Dec 2025.

### Org-level settings required

The `opendatahub-io` org admin must configure
**Organization Settings > Actions > Runner groups > Default**:

- [x] "Allow public repositories" — required for public repos
- [x] "Repository access" set to "All repositories" (or notebooks specifically)

This requirement was [added to the onboarding guide](https://github.com/IBM/actionspz/commit/4a8cb5b08246675db9c8934b42f279f908cf9656)
in Feb 2026, after our initial onboarding. Our jobs sat in `queued` for 24 hours
until this was fixed.

## Architecture: containers, not VMs

The IBM runners are **LXD containers**, not VMs. This has significant implications:

### No privileged operations

- **No `losetup`** — our `ci/cached-builds/gha_lvm_overlay.sh` cannot create
  loop devices. The LVM overlay step must be skipped or replaced.
- **No `docker run --privileged`** — the QEMU binfmt setup step
  (`tonistiigi/binfmt`) won't work. Not needed anyway since the arch is native.
- **No `dmesg`** — `dmesg: read kernel buffer failed: Operation not permitted`.
- **AppArmor restrictions on s390x** — podman's DNS resolution fails with
  `socket: permission denied` because AppArmor blocks creating network sockets
  in certain contexts
  ([details](https://github.com/IBM/actionspz/issues/63#issuecomment-3662214924)).

### No Homebrew

Homebrew for Linux only supports x86_64 and ARM64:

```
Homebrew on Linux is only supported on Intel x86_64 and ARM64 processors!
```

Our `install-podman-action` relies on Homebrew to install a recent podman.
On IBM runners, we must use the distro-provided podman (Ubuntu 24.04 ships
podman 4.x) or switch to Docker.

### Podman limitations

- **ppc64le**: Ubuntu 24.04's podman 4.x does not support Dockerfile HEREDOCs
  (`RUN <<EOF ... EOF`). Our Dockerfiles use this syntax extensively.
- **s390x**: podman fails to pull images from quay.io due to AppArmor blocking
  DNS socket creation. Docker may work as an alternative.

See <https://github.com/IBM/actionspz/issues/63#issuecomment-3654738467> for
the original investigation.

### Docker as alternative

IBM's team [suggested](https://github.com/IBM/actionspz/issues/63#issuecomment-3662214924)
that Docker may work where podman doesn't, since Docker uses a different
networking model (daemon-based) that may not hit the AppArmor restrictions.
The runners have containerd pre-installed.

## GitHub Actions compatibility issues

### `actions/setup-go` — ppc64 vs ppc64le

Node.js `os.arch()` returns `"ppc64"` for both big-endian and little-endian
PowerPC. The `setup-go` action downloads the wrong (big-endian) Go binary,
causing `Exec format error`.

**Workaround**: explicitly pass `architecture: ppc64le`:

```yaml
- uses: actions/setup-go@v6
  with:
    go-version: "stable"
    architecture: ${{ inputs.platform == 'linux/ppc64le' && 'ppc64le' || '' }}
```

Upstream issues:
- <https://github.com/actions/setup-go/issues/517>
- <https://github.com/actions/setup-go/issues/648>

Other `actions/setup-*` actions likely have the same problem. Check any action
that auto-detects architecture via Node.js `os.arch()`.

## Runner hardware specs (observed May 2026)

### ppc64le (IBM Power)

| Field | Value |
|---|---|
| Runner name pattern | `prodWdc06*`, `ghaProdDal10*` (Washington DC, Dallas) |
| Runner version | 2.334.0 |
| OS | Ubuntu 24.04.4 LTS |
| Image | `ubuntu-24.04` version `20260426` |
| Memory | 14 GiB total |
| Disk | 137 GB LVM volume (`/dev/vg_lxc/containers_*`), ~113 GB available |
| Swap | None |
| Container runtime | LXC (LXD-managed) |
| Kernel | 6.12.0-222.el10.ppc64le |

### s390x (IBM Z / LinuxONE)

| Field | Value |
|---|---|
| Runner name pattern | `ProdUsEastZ*` (US East) |
| Runner version | 2.333.1 |
| OS | Ubuntu 24.04.4 LTS |
| Image | `ubuntu-24.04` version `20260421` |
| CPUs | 8 (cpu0–cpu7) |
| Memory | 14 GiB total |
| Disk | 200 GB (`/dev/vdd1`), ~165 GB available |
| Swap | None |
| Container runtime | LXC (LXD-managed) |
| Kernel | 6.8.0-110-generic |

## Queue times

The runners are shared infrastructure for all onboarded open-source projects.
Queue times vary significantly:

| Scenario | Typical wait |
|---|---|
| Normal load | seconds to ~5 min |
| After incidents / webhook issues | 1+ hours |
| Worst observed | 12+ hours (multiple reports) |

Tracked in <https://github.com/IBM/actionspz/issues/87>.

IBM has said they are "working on updating our queuing system and expanding
hardware capacity." For PR CI where fast feedback matters, keeping qemu
cross-compilation on GitHub-hosted runners as a fallback may be prudent.

### Observed queue times (May 2026, PR #3525)

| Job | Queue wait |
|---|---|
| ppc64le [odh] | ~18s |
| ppc64le [rhoai] | ~15s |
| s390x [odh] | ~13s |
| s390x [rhoai] | ~13s |

### Observed checkout (clone + submodules) times

The full clone with `fetch-depth: 0` and `submodules: recursive` is slower
on IBM runners due to external network. The `microsoft/vscode` sub-submodule
(via `codeserver/ubi9-python-3.12/prefetch-input/code-server/lib/vscode`)
dominates clone time in all cases.

| Runner | Total checkout | vscode submodule |
|---|---|---|
| amd64 (GitHub-hosted) | ~117s | ~101s |
| ppc64le (IBM) | 104s – 225s (variable) | 88s – 159s |
| s390x (IBM) | 103s – 106s | ~69–74s |

Targets that don't need submodules (e.g. `jupyter-minimal`) could benefit
from skipping `submodules: recursive` and using a shallow clone.

## Useful `gh` commands for checking CI

```bash
# List recent runs on the PR branch
gh run list --repo opendatahub-io/notebooks --branch jd_ibm_runners \
  --workflow "Build Notebooks (pr)" --limit 3 \
  --json databaseId,status,conclusion,headSha,createdAt \
  --jq '.[] | {id: .databaseId, status: .status, conclusion: .conclusion, sha: .headSha[:8]}'

# Check IBM runner jobs from a specific run
gh run view <RUN_ID> --repo opendatahub-io/notebooks \
  --json jobs --jq '.jobs[] | select(.name | contains("ppc64le") or contains("s390x")) | {name: .name, status: .status, conclusion: .conclusion}'

# Find which step failed
gh api repos/opendatahub-io/notebooks/actions/runs/<RUN_ID>/jobs \
  --jq '.jobs[] | select(.name | contains("ppc64le") and contains("odh")) | .steps[] | select(.conclusion == "failure") | {name: .name, number: .number}'

# Get job ID for log download
gh api repos/opendatahub-io/notebooks/actions/runs/<RUN_ID>/jobs \
  --jq '.jobs[] | select(.name | contains("ppc64le") and contains("odh")) | .id'

# Extract error lines from a job log
gh api repos/opendatahub-io/notebooks/actions/jobs/<JOB_ID>/logs 2>&1 \
  | grep -E "##\[error" | head -5

# Get full error context around the failure
gh api repos/opendatahub-io/notebooks/actions/jobs/<JOB_ID>/logs 2>&1 \
  | grep -B 3 -A 8 "exit code 125"

# Check runner machine details (near top of log)
gh api repos/opendatahub-io/notebooks/actions/jobs/<JOB_ID>/logs 2>&1 \
  | grep -E "Runner name|Runner version|Operating System|Runner Image|Included Software" | head -10

# Check checkout/clone timing
gh api repos/opendatahub-io/notebooks/actions/jobs/<JOB_ID>/logs 2>&1 \
  | grep -E "Syncing repository|Submodule path.*checked out"
```

## Experiment history

| Date | What | Outcome |
|---|---|---|
| Nov 2025 | Onboarding request filed | IBM/actionspz#63 |
| Dec 2025 | App installed, repo approved | Runners available |
| Dec 2025 | First experiment (PR #2774) | ppc64le: old podman, s390x: DNS blocked |
| Jan 2026 | PR #2774 merged | JSON runner mapping infrastructure |
| May 2026 | Second experiment (PR #3525) | Jobs queued 24h (missing org setting), then setup-go ppc64le bug, then Homebrew failure |
| May 2026 | Org runner group fixed | Queue times ~13-18s, all jobs reach Install Podman step |
