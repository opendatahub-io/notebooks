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

Runner image repo: <https://github.com/IBM/action-runner-image-pz>

Runner image contents: <https://github.com/IBM/action-runner-image-pz/blob/main/images/ubuntu/toolsets/toolset-2404.json>

The runner images include Docker CE 28.x with buildx and compose pre-installed.
Podman comes from Ubuntu's default packages (4.9.3), not from IBM's customization.
No Homebrew is included.

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
  loop devices. Not needed anyway: IBM runners have ~100-165 GB available
  on a single disk, and we only build CPU images (no CUDA/ROCm) on
  ppc64le/s390x, so disk pressure is not an issue.
- **No `docker run --privileged`** — the QEMU binfmt setup step
  (`tonistiigi/binfmt`) won't work. Not needed anyway since the arch is native.
- **No `dmesg`** — `dmesg: read kernel buffer failed: Operation not permitted`.
- **AppArmor restrictions on s390x** — podman (rootless and rootful) fails
  to resolve DNS when pulling images, because AppArmor blocks creating UDP
  sockets inside the LXD container:
  ```
  dial udp 127.0.0.53:53: socket: permission denied
  ```
  IBM confirmed this is a known platform limitation
  ([ramdrvcs](https://github.com/IBM/actionspz/issues/63#issuecomment-3665704813)):
  > "this is a restriction related to the security measures we currently
  > have in place for the containers. We're looking into how to run a
  > privileged container setup in a future release"

  The suggestion from IBM ([pleia2](https://github.com/IBM/actionspz/issues/63#issuecomment-3662214924))
  is to use Docker instead of podman, as Docker's daemon-based networking
  model may bypass the AppArmor socket restrictions.

  There is **no dedicated issue** on `IBM/actionspz` for this — the discussion
  is only in our onboarding thread
  [IBM/actionspz#63](https://github.com/IBM/actionspz/issues/63).

  **Other projects affected:**
  - [IBM/mcp-context-forge#3632](https://github.com/IBM/mcp-context-forge/issues/3632)
    hit the same issue and solved it by switching to Docker
    ([PR #3775](https://github.com/IBM/mcp-context-forge/pull/3775))
  - [containers/podman#22500](https://github.com/containers/podman/issues/22500) —
    same `socket: permission denied` in LXD
  - [Ubuntu bug #2118824](https://bugs.launchpad.net/bugs/2118824) —
    AppArmor denying socket creation in unprivileged LXD containers

  **Root cause:** [CVE-2025-52881](https://github.com/opencontainers/runc/issues/4968) —
  an fd reopening issue in runc that breaks AppArmor profiles in nested containers.
  Fixed in Incus 6.19+ and lxc-pve 6.0.5-2, but IBM's LXD version may not
  have the fix yet.

  **Important:** podman works fine on the ppc64le runners — only s390x is
  affected. This confirms it's an infrastructure configuration inconsistency
  on IBM's side, not a podman bug. The s390x hosts likely have stricter
  AppArmor enforcement (common for IBM Z mainframes targeting high-compliance
  environments like banking).

  **Workarounds:**
  1. Use Docker instead of podman on s390x (proven by IBM/mcp-context-forge).
     Docker's daemon runs as a privileged system service, so client commands
     talk via Unix socket and the daemon handles the actual network sockets.
  2. Ask IBM to match the s390x AppArmor config to ppc64le (our best ask)
  3. `lxc.apparmor.profile: unconfined` (requires IBM to change their LXD config)
  4. Wait for IBM to update their LXD/runner images with the runc fix

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

### CI container engine matrix

Due to infrastructure-level security profiles on IBM's LXD runners,
container engine support varies by architecture:

| Architecture | Engine | Notes |
|---|---|---|
| amd64 / arm64 | Podman | Default, via Homebrew |
| ppc64le (IBM Power) | Podman | Distro podman 4.9.3 works natively for builds |
| s390x (IBM Z) | **Docker** (required) | Podman is fundamentally broken (see below) |

### Why podman fails on s390x (but works on ppc64le)

The AppArmor profiles on IBM's s390x LXD hosts block **all** network
socket creation (`socket()` syscall) inside `CLONE_NEWUSER`/`CLONE_NEWNET`
namespaces. Podman relies on these namespaces for isolation, so both
rootless and rootful podman fail with:

```
dial udp 127.0.0.53:53: socket: permission denied   # Go native resolver
dial tcp 127.0.0.53:53: socket: permission denied   # with options use-vc
Temporary failure in name resolution                  # with GODEBUG=netdns=cgo
```

Tested workarounds that **do not work** on s390x:
- `options use-vc` in resolv.conf (TCP DNS) — TCP sockets also blocked
- `GODEBUG=netdns=cgo` (glibc resolver) — glibc can't create sockets either
- `GODEBUG=netdns=cgo` + public DNS (`8.8.8.8`) — same, namespace-level block
- `podman system service` daemon mode — socket permissions still denied
- `sudo podman` — rootful podman also creates namespaces

Python and curl work fine because they run in the LXD container's primary
namespace, not in podman's nested namespaces.

Docker works because `dockerd` runs as a system service in the primary
namespace and handles all network I/O there. Client commands talk to
dockerd via a Unix socket.

Docker CE 28.x with buildx is pre-installed on the IBM runners
([toolset config](https://github.com/IBM/action-runner-image-pz/blob/main/images/ubuntu/toolsets/toolset-2404.json)).

The ppc64le runners do **not** have this restriction — podman builds
work natively there. This confirms the issue is an infrastructure
configuration difference between IBM's s390x and ppc64le hosts, not
a podman bug.

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
# NOTE: the /logs API can return 404 after force-pushes or when the run
# is superseded. Use `gh run view --log` as fallback (needs --all perms
# for cache writes):
gh api repos/opendatahub-io/notebooks/actions/jobs/<JOB_ID>/logs 2>&1 \
  | grep -E "##\[error" | head -5

# Fallback when the API returns 404:
gh run view <RUN_ID> --repo opendatahub-io/notebooks --log 2>&1 \
  | grep "search term"

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

## Kubernetes on IBM runners

### kubeadm is the only option

No lightweight k8s distribution supports ppc64le/s390x:

| Distribution | ppc64le | s390x |
|---|---|---|
| k3s | No support | Dropped Nov 2023 |
| k0s | Never supported | No info |
| kind | Dropped Mar 2023 | Dropped Mar 2023 |
| minikube `none` driver | Basically kubeadm | Basically kubeadm |
| kubeadm | Packages available | Packages available |

### LXD namespace capabilities (probed May 2026)

| Capability | ppc64le | s390x |
|---|---|---|
| User + PID namespace (`unshare --user --pid`) | OK | OK |
| Network namespace (`unshare --net`) | **BLOCKED** | **BLOCKED** |
| Mount namespace (`unshare --mount`) | **BLOCKED** | **BLOCKED** |
| `modprobe br_netfilter` | BLOCKED (no `/lib/modules`) | BLOCKED |
| `modprobe overlay` | BLOCKED | BLOCKED |
| `iptables -L` | OK | OK |
| `sysctl ip_forward` | OK | OK |

### kubeadm init result: FAILED on both arches

```
[ERROR SystemVerification]: failed to parse kernel config: unable to load
kernel module: "configs", output: "modprobe: FATAL: Module configs not found
in directory /lib/modules/6.12.0-222.el10.ppc64le"
```

Even with `--ignore-preflight-errors=SystemVerification`, kubeadm would fail
because **network namespace creation is blocked on both arches**. Kubelet and
kube-proxy need network namespaces to isolate pods. This is a fundamental
LXD container limitation — IBM would need to enable `security.nesting: true`
and provide `/lib/modules` matching the host kernel.

The kubeadm unprivileged LXD mode (k8s >= 1.32.4, `KubeletInUserNamespace`
feature gate) requires at minimum `security.nesting: true` on the LXD
profile, which IBM does not currently provide.

### Consequence for testing

IBM runners can only do **build + testcontainers** testing (no k8s):

| Test type | ppc64le | s390x |
|---|---|---|
| Docker build | OK | OK |
| Testcontainers (pytest) | OK (via Docker) | OK (via Docker) |
| Makefile k8s tests | **Not possible** | **Not possible** |
| Trivy image scan | OK | OK |

The Makefile k8s tests (deploy StatefulSet, run papermill) must remain on
amd64 GitHub-hosted runners. The architecture-specific validation ("does the
image build and does Jupyter start") is covered by testcontainers.

## Python package availability on IBM arches

Many Python packages with C extensions lack pre-built wheels for ppc64le
and/or s390x on PyPI. Our `pyproject.toml` sets `no-build = true` to
reject source distributions on amd64/arm64 (where all wheels should exist),
but this must be overridden on IBM arches.

### Wheel availability (as of May 2026)

| Package | PyPI ppc64le | PyPI s390x | IBM index ppc64le |
|---|---|---|---|
| PyYAML | none | yes | yes (6.0.3) |
| pydantic-core | yes | yes | yes |
| cffi | yes | yes | yes |
| cryptography | yes | none | yes |
| greenlet | yes | yes | — |
| MarkupSafe | none | none | yes |
| ruamel.yaml.clib | none | none | yes |
| prek | none | yes | — |

### Pre-built wheel sources

**IBM Developer First** — ppc64le only (no s390x index):
```
https://wheels.developerfirst.ibm.com/ppc64le/linux/+simple/
```
DevPi server with wheels for Power9/10/11. Versions use
`+ppc64le1` local version suffix. Blog:
<https://community.ibm.com/community/user/blogs/janani-janakiraman/2025/09/10/developing-apps-using-python-packages-on-ibm-power>

Usage with pip:
```bash
pip install --prefer-binary <package> --extra-index-url https://wheels.developerfirst.ibm.com/ppc64le/linux
```

Usage with uv (env var):
```bash
UV_EXTRA_INDEX_URL=https://wheels.developerfirst.ibm.com/ppc64le/linux/+simple/
```

**conda-forge** — has ppc64le and s390x packages but in conda format (not
pip-installable wheels).

### CI workaround

On IBM runners, override `no-build = true` to allow source builds for
packages without wheels:

```yaml
env:
  UV_NO_BUILD: "false"
```

This is acceptable because the missing packages are small C extensions
(PyYAML, MarkupSafe, ruamel.yaml.clib) that build in seconds.

Optionally, add IBM's ppc64le index for pre-built wheels:

```yaml
env:
  UV_EXTRA_INDEX_URL: "https://wheels.developerfirst.ibm.com/ppc64le/linux/+simple/"
```

## Pipeline architecture on IBM runners

Since Docker is the only viable container engine (podman blocked on s390x,
k8s not possible in LXD), the IBM runner pipeline differs from the amd64 pipeline:

```
amd64/arm64 (GitHub-hosted):   Homebrew podman -> podman build -> CRI-O k8s -> test
IBM ppc64le/s390x:             Docker CE (pre-installed) -> docker build -> testcontainers -> test
```

### What works without changes

- **Makefile**: auto-detects Docker when podman is absent (`CONTAINER_ENGINE=docker`)
- **`sandbox.py`**: engine-agnostic build wrapper
- **GHCR push**: `docker push` works same as `podman push`
- **`docker/login-action`**: already used for GHCR login
- **Testcontainers (pytest)**: uses docker-py, works natively with Docker socket

### What must be skipped on IBM runners

| Step | Reason |
|---|---|
| Install Podman (Homebrew) | Not needed, Docker is pre-installed |
| LVM overlay (`gha_lvm_overlay.sh`) | No `losetup` in LXD; not needed (CPU images, 100+ GB disk) |
| QEMU binfmt setup | Not needed (native arch) |
| Trivy image scan (`--image-src podman`) | Podman-specific; needs adaptation for Docker |
| FIPS / check-payload (`podman image mount`) | Podman-specific |
| Playwright browser tests | amd64-only |
| kubeadm k8s tests | No net/mount namespaces in LXD |

### What must be adapted

| Step | Change |
|---|---|
| `CONTAINER_HOST` env var | Unset (Docker uses `DOCKER_HOST`, and dockerd is already running) |
| Testcontainers env | `DOCKER_HOST=unix:///var/run/docker.sock` instead of podman socket |
| `actions/setup-go` | Add `architecture: ppc64le` workaround |

## Experiment history

| Date | What | Outcome |
|---|---|---|
| Nov 2025 | Onboarding request filed | IBM/actionspz#63 |
| Dec 2025 | App installed, repo approved | Runners available |
| Dec 2025 | First experiment (PR #2774) | ppc64le: old podman, s390x: DNS blocked |
| Jan 2026 | PR #2774 merged | JSON runner mapping infrastructure |
| May 2026 | Second experiment (PR #3525) | Jobs queued 24h (missing org setting), then setup-go ppc64le bug, then Homebrew failure |
| May 2026 | Org runner group fixed | Queue times ~13-18s, all jobs reach Install Podman step |
| May 2026 | Podman investigation | ppc64le: works, s390x: blocked by AppArmor in user namespaces |
| May 2026 | Docker confirmed | Docker builds work on both arches |
| May 2026 | Kubernetes probed | kubeadm fails on both arches (no net/mount ns, no /lib/modules) |
