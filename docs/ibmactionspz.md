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

The IBM runners are **LXD containers**, not VMs. This has significant implications.

IBM has confirmed they are working on **VM-based runners** that would
allow privileged workflows
([dale-fu, May 2026](https://github.com/IBM/actionspz/issues/63#issuecomment-4397336518)):
> "the team is working on implementing VM-based runners where it would
> allow for more privileged workflows to be ran. We hope to have this
> feature available sometime in the following months."

VM-based runners would eliminate all LXD/AppArmor limitations documented
below.

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

- **ppc64le**: Ubuntu 24.04's podman 4.9.3 does not support Dockerfile
  HEREDOCs (`RUN /bin/bash <<'EOF' ... EOF`). Our Dockerfiles use this
  syntax extensively. HEREDOC support requires buildah >= 1.35 / podman
  >= 5.0. Ubuntu 24.04 patched it out of their buildah 1.33 package
  ([buildah#5474](https://github.com/containers/buildah/issues/5474)).
- **s390x**: podman is completely broken for any network operation
  (both Go-level pulls and glibc tools inside `RUN` steps). See the
  detailed analysis below.

See <https://github.com/IBM/actionspz/issues/63#issuecomment-3654738467> for
the original investigation.

### Getting podman 5.x on IBM runners (for HEREDOC support)

Ubuntu 24.04 ships podman 4.9.3 which lacks Dockerfile HEREDOC support.
No pre-built podman 5.x packages exist for ppc64le/s390x on Ubuntu 24.04:

| Source | Status |
|---|---|
| Kubic/OBS repo | Deprecated (Kubic retired June 2022) |
| teward PPA (`ppa:teward/podman`) | Broken (0/6 builds succeeded), amd64-only |
| Fedora COPR (`rhcontainerbot/podman-next`) | RPM-only, not usable on Ubuntu |
| Homebrew | Does not support ppc64le/s390x |
| Static binaries (GitHub releases) | amd64/arm64 only |
| pipx/cargo/nix | Not applicable (Go + C project) |

**Viable alternatives:**

1. **Podman-in-docker** (implemented) — run `make` inside
   `docker run --privileged` with a Fedora 44 container (podman 5.x +
   Python 3.14). Controls the exact podman version and brings in the
   latest Fedora packages. See the pipeline architecture section below.

2. **Build buildah from source** — buildah is simpler than podman and
   is what actually needs HEREDOC support. Build natively on the runner:
   ```bash
   sudo apt-get install -y make golang git go-md2man \
     libgpgme-dev libseccomp-dev libdevmapper-dev libglib2.0-dev \
     libbtrfs-dev libassuan-dev pkg-config
   git clone --branch v1.39.3 https://github.com/containers/buildah.git
   cd buildah && make && sudo make install
   ```
   Upstream buildah includes HEREDOC support (Ubuntu strips it out).
   Adds ~2-3 min to CI but avoids the docker wrapper entirely.

3. **Wait for Ubuntu 25.04+** — ships podman 5.4.1 and buildah 1.39.3
   with ppc64le/s390x packages. IBM controls the runner image OS; this
   would need them to upgrade from 24.04 to 25.04+.

### CI container engine matrix

Due to infrastructure-level security profiles on IBM's LXD runners,
container engine support varies by architecture:

| Architecture | Engine | Notes |
|---|---|---|
| amd64 / arm64 | Podman | Default, via Homebrew |
| ppc64le (IBM Power) | Podman (in Docker) | Podman-in-docker via `docker run --privileged` with Fedora 44 |
| s390x (IBM Z) | **Docker only** | Podman is completely broken for any network operation |

### Why podman fails on s390x (but works on ppc64le)

Podman on s390x cannot perform **any** network operation — not image
pulls, and not `RUN` steps inside `podman build` that need DNS. This
applies even inside a `docker run --privileged --network=host` container
with all capabilities.

**Podman pull fails** (Go resolver):

```
dial tcp: lookup quay.io: Temporary failure in name resolution
```

**Podman build `RUN` steps also fail** (glibc/curl inside build container):

```
(microdnf:2): librepo-WARNING: Curl error (6): Couldn't resolve host name
for https://mirrors.centos.org/metalink [Could not resolve host: mirrors.centos.org]
```

This means `--network=host` on `podman build` does **not** propagate
functional DNS into podman's build containers on this architecture.
The issue is not specific to Go's DNS resolver — glibc-based tools
(`microdnf`, `curl`) inside podman build `RUN` steps also fail.

**What does work** in the same environment (inside `docker run --privileged`):

| Operation | Result |
|---|---|
| `python3 socket.getaddrinfo("quay.io")` | OK |
| `nslookup quay.io` | OK (via 127.0.0.53) |
| `getent hosts quay.io` | OK |
| `unshare --user` + UDP socket | OK |
| `dnf install` (in outer Fedora container) | OK |
| `podman load < tarball` | OK |
| `podman build --pull=never` with offline `RUN echo` | OK |

So the host network, DNS, and even raw user namespaces all work.
The issue is specific to podman's container runtime — it creates a
combination of namespaces (user + mount + net + pid + ipc) and/or
applies a runtime configuration that breaks DNS inside the resulting
environment. The `--network=host` flag is insufficient to fix this.

**Exhaustive list of workarounds that do NOT fix s390x:**

| Attempt | Result |
|---|---|
| `options use-vc` in resolv.conf (TCP DNS) | FAILED |
| `GODEBUG=netdns=cgo` (force Go cgo resolver) | FAILED |
| Public DNS (`8.8.8.8`) written to `/etc/resolv.conf` | FAILED |
| `podman system service` daemon mode | FAILED |
| `sudo podman` (rootful) | FAILED |
| `podman build --userns=host` | FAILED |
| `podman build --isolation=chroot` | FAILED |
| `podman` with `storage.driver = "vfs"` | FAILED |
| `docker run --privileged` (outer container) | FAILED |
| `docker run --privileged --network=host` (outer) | FAILED |
| `podman build --network=host` (inner) | FAILED |

**Conclusion:** Podman on s390x is only usable for offline operations
(`podman load`, `podman build --pull=never` with offline `RUN` steps).
Any operation requiring network access must use Docker.

### Source code analysis: why does rootful podman break DNS?

Investigated the `containers/storage` and `buildah` source code to
understand the namespace creation path:

**`MaybeReexecUsingUserNamespace(false)`** (containers/storage):
Called from `buildah/cmd/buildah/main.go` `before()`. With `evenForRoot=false`
and `CAP_SYS_ADMIN` present (which we have in `docker --privileged`),
it **returns immediately without re-execing**. So `containers/storage`
is NOT creating user namespaces in our scenario.

**`setupNamespaces()`** (buildah `run_linux.go`):
For `RUN` steps, this function decides whether to create user+network
namespaces. With `--network=host`, `specifiedNetwork=true` and the
automatic network namespace creation is skipped. With `--isolation=chroot`,
the OCI runtime is bypassed entirely.

**The mystery:** Despite `MaybeReexecUsingUserNamespace` skipping,
`--network=host` being set, and `--isolation=chroot` being used,
podman still fails DNS on s390x. The failure occurs both during
`podman pull` (which shouldn't use namespaces at all when rootful with
`CAP_SYS_ADMIN`) and during `podman build` `RUN` steps (even with chroot
isolation). Since `unshare --user` + socket works in the same environment,
the issue is specific to podman's process setup, not a general namespace
restriction.

**Strace results (May 2026):** Definitive syscall-level analysis shows:
- All 7 `clone3()` calls are plain Go thread creation (`CLONE_VM|CLONE_FS|
  CLONE_FILES|CLONE_THREAD`). **No `CLONE_NEWUSER`, `CLONE_NEWNET`, or
  `CLONE_NEWNS` anywhere.**
- No `unshare()` or `setns()` calls at all.
- Only one `execve("/usr/bin/podman", ...)` — no re-exec via memfd.
- `socket(AF_INET, SOCK_DGRAM) = -1 EACCES (Permission denied)` in the
  main podman process (PID 140).

**Cross-binary comparison:**

| Binary | DNS | Implication |
|---|---|---|
| `/usr/bin/podman` | EACCES on socket() | Blocked |
| `/usr/bin/buildah` | EACCES on socket() | Blocked |
| `/usr/bin/skopeo` | OK | Same containers/image library, works |
| `/tmp/dnstest` (Go) | OK | Go runtime DNS works fine |
| `/usr/bin/python3` | OK | glibc getaddrinfo works |
| `nslookup` | OK | bind-utils works |

**Likely root cause: Ubuntu host AppArmor profile for `/usr/bin/podman`.**

Ubuntu ships an AppArmor profile at `/etc/apparmor.d/podman` that
restricts what the podman binary can do. The LXD host kernel enforces
AppArmor based on the **binary path**, regardless of Docker `--privileged`.
When the Fedora container runs `/usr/bin/podman`, the host kernel matches
it against the podman profile and blocks `socket()` creation.

Evidence:
- [Ubuntu bug #2118824](https://bugs.launchpad.net/bugs/2118824):
  AppArmor denies socket operations in nested containers
- [Proxmox forum](https://forum.proxmox.com/threads/156426/): rootless
  podman + AppArmor in unprivileged containers shows
  `apparmor="DENIED" operation="create" class="net"`
- [podman-static#111](https://github.com/mgoltzsche/podman-static/issues/111):
  AppArmor profile path-matches `/usr/bin/podman` specifically

**Confirmed fix: rename the podman binary** to bypass the AppArmor
path match. Tested May 2026:

| Binary | Result |
|---|---|
| `/usr/bin/podman pull` | FAILED (EACCES on socket) |
| `/usr/bin/podman-noaa pull` (copy) | **OK** |
| `/usr/local/bin/podman-local pull` (symlink) | FAILED (AppArmor resolves symlinks) |
| `/usr/bin/buildah pull` | FAILED |
| `/usr/bin/buildah-noaa pull` (copy) | **OK** |

**Implementation**: in the CI workflow, after `dnf install podman`:
```bash
cp /usr/bin/podman /usr/bin/podman-build
# use podman-build instead of podman for all operations
```

This is specific to IBM's s390x LXD hosts. The ppc64le hosts do not
have this AppArmor restriction.

Docker works because `dockerd` runs as a system service in the primary
namespace and handles all network I/O there. Client commands talk to
dockerd via a Unix socket.

Docker CE 28.x with buildx is pre-installed on the IBM runners
([toolset config](https://github.com/IBM/action-runner-image-pz/blob/main/images/ubuntu/toolsets/toolset-2404.json)).

The ppc64le runners do **not** have this restriction — podman works
natively there (including inside `docker run --privileged`). This
confirms the issue is an infrastructure configuration difference
between IBM's s390x and ppc64le hosts, not a podman bug.

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

`pyproject.toml` sets `no-build = true` globally, which cannot be negated
via env var (`UV_NO_BUILD=false` does not work — it's a flag, not a toggle).
Use `--no-binary-package` per package to allow source builds:

```yaml
- run: |
    uv sync --group dev --locked \
      --no-binary-package pyyaml \
      --no-binary-package markupsafe \
      --no-binary-package ruamel-yaml-clib
```

These are small C extensions that build in seconds.

**Future consideration:** uv workspaces could let each workspace member
(`notebooks-ci`, `notebooks-test`, `notebooks-lint`) have its own `no-build`
and `required-environments` settings while sharing a single lockfile. This
would allow strict wheel enforcement for amd64/arm64-only members while
permitting source builds in IBM-arch-facing members. Not worth the
restructuring cost today, but useful if the project grows.

Optionally, add IBM's ppc64le index for pre-built wheels:

```yaml
env:
  UV_EXTRA_INDEX_URL: "https://wheels.developerfirst.ibm.com/ppc64le/linux/+simple/"
```

## Hermetic builds on IBM runners

Both ODH (`Dockerfile.*`) and RHOAI (`Dockerfile.konflux.*`) builds are
**hermetic** — they require pre-fetched dependencies from `cachi2/output/`.
The Makefile detects `prefetch-input/` directories (git submodules) and
requires `cachi2/output/` to exist, failing with:

```
Prefetch required for hermetic build. Run: scripts/lockfile-generators/prefetch-all.sh
```

For IBM runners, the full hermetic build pipeline needs:
1. Checkout with `submodules: recursive` (to get `prefetch-input/` dirs)
2. Run `scripts/lockfile-generators/prefetch-all.sh --component-dir <dir>`
   to populate `cachi2/output/` with pip wheels, RPMs, and Go modules
3. The prefetch step itself downloads packages and needs network access
   (which works — it runs in the host namespace, not inside podman)

Without prefetch, builds can still work for testing purposes by skipping
submodule checkout (`submodules: false`), which removes the `prefetch-input/`
dirs and lets the Makefile fall through to a non-hermetic build. The
Dockerfiles then pull dependencies directly from PyPI/dnf repos at build
time.

## Container image arch availability for prefetch

The hermetic prefetch pipeline runs container tools (hermeto, UBI9) to
download RPMs, npm packages, and Go modules. Not all images are multiarch:

| Image | amd64 | arm64 | ppc64le | s390x |
|---|---|---|---|---|
| `ghcr.io/hermetoproject/hermeto:0.46.2` | yes | yes | **no** | **no** |
| `registry.access.redhat.com/ubi9/ubi` | yes | yes | yes | yes |
| `quay.io/opendatahub/odh-base-image-cpu-py312-c9s:latest` | yes | yes | yes | yes |

**Hermeto** (the RPM/npm/gomod prefetch tool) has no ppc64le or s390x
builds. This means the hermetic RPM prefetch step (step 4/5 in
`prefetch-all.sh`) cannot run natively on IBM runners.

**Can hermeto be pip-installed instead?** Hermeto is pure Python (setuptools)
but is not published to PyPI ("We do not distribute Hermeto as a standalone
package"). Its dependency `createrepo-c` (C extension for RPM repo metadata)
also lacks ppc64le/s390x wheels. Building from source would need cmake +
createrepo_c C headers.

**How Konflux handles this:** The `prefetch-dependencies` task runs on
**amd64 regardless of target platform**. It downloads artifacts (wheels,
RPMs, tarballs) without executing them. The target-arch build task then
consumes the prefetched output. Our GHA CI should follow the same pattern.

Workarounds:
1. **Run hermeto in UBI9 instead of the hermeto image** — UBI9 is fully
   multiarch (amd64, arm64, ppc64le, s390x) and ships `python3-createrepo_c`
   as a system package. Install hermeto from git inside UBI9:
   `dnf install -y python3-createrepo_c python3-pip && pip install
   git+https://github.com/hermetoproject/hermeto`. This lets the prefetch
   step run natively on IBM runners without a separate amd64 job.
2. **Run prefetch on amd64, build on IBM** — the Konflux approach. Use a
   two-job GHA workflow: amd64 job runs prefetch-all.sh, uploads
   `cachi2/output/` as artifact, IBM job downloads and builds.
3. Skip RPM prefetch and use network-based `dnf install` in the Dockerfile
   (non-hermetic for RPMs, but pip/generic artifacts are still hermetic)
4. Ask the hermeto project to add ppc64le/s390x builds

Jira: [RHAIENG-4956](https://redhat.atlassian.net/browse/RHAIENG-4956) —
update hermeto version in GHA CI scripts.

The pip download step (step 2/5) works fine — it's pure Python, no container.
Generic artifacts (step 1/5, GPG keys) also work — just `wget`.

## Docker `--privileged` container escape (both arches)

Inside the LXD container, network and mount namespaces are blocked on
both ppc64le and s390x. Running a step inside a **`docker run --privileged`**
Docker container lifts all restrictions on **both architectures**.

Results from May 2026 testing (ppc64le and s390x are identical):

| Capability | Directly on LXD | `docker --privileged` | `docker apparmor=unconfined` |
|---|---|---|---|
| User + PID namespace | OK | **OK** | OK |
| Network namespace | **BLOCKED** | **OK** | BLOCKED |
| Mount namespace | **BLOCKED** | **OK** | BLOCKED |
| mount tmpfs | BLOCKED | **OK** | BLOCKED |
| unshare all (user+pid+net+mount) | BLOCKED | **OK** | BLOCKED |
| Capabilities (CapEff) | limited | `000001ffffffffff` (all) | limited |
| Workspace mount | N/A | **OK** | N/A |

**Key finding:** `docker run --privileged` grants **all capabilities and
all namespace types** on both ppc64le and s390x. This is a complete
escape from the LXD AppArmor restrictions on both architectures.

`--security-opt apparmor=unconfined` alone is **insufficient** on both
arches. On s390x it allows user+pid ns but blocks net/mount. On ppc64le
it blocks all namespace creation (`Operation not permitted`). Only
`--privileged` works.

**Implementation approach:** Wrap the `make` build step in
`docker run --privileged --network=host` with a Fedora 44 container
(podman 5.x + Python 3.14). The workspace is mounted so host-compiled
tools (`bin/buildinputs`, `cachi2/output`) are reused. After build,
`podman save | docker load` transfers the image to Docker.

```bash
sudo docker run --rm --privileged --network=host \
  -v $GITHUB_WORKSPACE:/workspace:z \
  -w /workspace \
  registry.fedoraproject.org/fedora:44 \
  bash -c "
    dnf install -y podman make which python3 python3-pip
    pip install structlog
    export PYTHONPATH=/workspace
    make jupyter-minimal-ubi9-python-3.12 CONTAINER_ENGINE=podman ...
    podman save --format docker-archive -o /workspace/image.tar IMAGE
  "
docker load < image.tar
```

**Caveat:** This works on **ppc64le only**. On s390x, podman inside the
privileged container still fails DNS (`socket: permission denied`)
because podman creates user namespaces for the build process, and
AppArmor blocks `socket()` inside those user namespaces regardless of
`--privileged` or `--network=host` on the outer container.

## Docker Hub rate limiting on IBM runners

IBM runners share outbound IPs across all onboarded projects. Unauthenticated
Docker Hub pulls hit rate limits quickly:

```
toomanyrequests: You have reached your unauthenticated pull rate limit.
```

This affects both podman and Docker pulls from `docker.io`. Mitigations:
- **Authenticate to Docker Hub** (`docker login` / `podman login`) — raises
  the rate limit from 100 pulls/6h (anonymous) to 200 pulls/6h (free account)
- **Use GHCR or quay.io** for base images instead of `docker.io`
- **Pull once and reuse** — avoid re-pulling the same image in multiple steps
- **Cache images** with GHA cache actions

### ppc64le runner job duration

The ppc64le podman test job runs significantly longer than s390x because
podman actually works there — each test step pulls images and builds
containers instead of failing fast. The test workflow accumulated many
experimental steps during investigation and should be trimmed for
production use. A build + testcontainers job on ppc64le takes ~15-20 min
(image pull + build + test), compared to ~2 min on s390x where podman
fails immediately.

## Pipeline architecture on IBM runners

The IBM runner pipeline differs from the amd64 pipeline:

```
amd64/arm64 (GitHub-hosted):   Homebrew podman -> podman build -> CRI-O k8s -> test
IBM ppc64le:                   docker run --privileged -> podman build (--volume works) -> podman save | docker load -> testcontainers
IBM s390x:                     Docker CE -> docker build (non-hermetic*) -> testcontainers
```

*s390x hermetic builds require the `--build-context` migration (replacing
`--volume` with BuildKit named contexts in both the Makefile and Dockerfiles).
See the `--volume` limitation section below.

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

### Docker limitation: no `--volume` on build

The Makefile mounts `cachi2/output` into the build container via
`--volume` flags for hermetic builds:

```
docker build --volume /path/cachi2/output:/cachi2/output:Z ...
```

**`docker build` (buildx) does not support `--volume`.** This is a
podman-only feature. Docker buildx uses BuildKit which has a different
model for build-time mounts (`RUN --mount=type=bind,...` in Dockerfiles).

Our Dockerfiles already use `RUN --mount` for some operations, but the
top-level `cachi2/output` and RPM `repos.d` mounts are passed by the
Makefile as build command flags, not as Dockerfile directives.

Workarounds:
1. **Build with podman inside `docker run --privileged`** (implemented,
   **ppc64le only**) — run the `make` build step inside a privileged
   Fedora 44 container with podman 5.x (supports `--volume` and
   Dockerfile HEREDOCs). The workspace is mounted so pre-compiled
   `bin/buildinputs` and `cachi2/output` are reused from the host.
   After build, `podman save --format docker-archive -o image.tar`
   followed by `docker load < image.tar` transfers the image to
   Docker for testcontainers. No Makefile or Dockerfile changes needed.
   Requirements inside the container: `dnf install podman make which
   python3 python3-pip && pip install structlog` + `PYTHONPATH=/workspace`.

   **Does NOT work on s390x**: even inside `docker run --privileged
   --network=host`, podman creates user namespaces for the build
   and the AppArmor-blocked `socket()` syscall prevents DNS resolution.
   The `--network=host` flag on both the outer docker and inner podman
   build is insufficient — the user namespace is the problem, not the
   network namespace.

2. **Use `docker buildx build --build-context`** — BuildKit named contexts
   can map external directories: `--build-context cachi2=/path/cachi2/output`.
   Podman also supports this flag (since buildah PR #3978, May 2022).
   Requires Dockerfile changes to use `RUN --mount=type=bind,from=cachi2,...`
   but would unify both engines on a single syntax. Works with Docker
   on both arches. Future migration path.
3. **Copy `cachi2/output` into the build context** — make it available
   via `COPY` instead of `--volume`. Increases context size but works
   with both engines.
4. **Use `DOCKER_BUILDKIT=0`** (legacy builder) — deprecated, does not
   actually support `--volume` either, and lacks multi-stage caching.

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
| May 2026 | `--volume` blocker | Docker buildx rejects `--volume`; ppc64le solved via podman-in-docker |
| May 2026 | s390x podman deep dive | Exhaustive testing: 11 workarounds failed; strace showed `socket()` returns `EACCES` in main process; skopeo works, podman doesn't; root cause: Ubuntu AppArmor profile blocks `/usr/bin/podman` by path; **fix: rename binary** (`cp podman podman-build`) |
