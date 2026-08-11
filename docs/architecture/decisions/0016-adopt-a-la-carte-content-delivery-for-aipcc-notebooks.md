# 16. Adopt "À La Carte" Content Delivery Model for Notebook Images

Date: 2026-08-11

## Status

Proposed

## Context

Historically, this repository consumes AIPCC content — Python package indexes and
RHAIBI base images — pinned to RHAI product release versions (e.g.
`rhoai/3.6-EA1` plus a variant such as `cuda12.9-ubi9`). That coupling has caused
concrete problems for notebook image builds:

* **Obscured ABI boundaries.** In the RHOAI 3.5 cycle, `cuda12.9` shipped torch
  2.9.1 at EA and torch 2.10 at GA under the same index path. Teams that could
  not absorb the bump had no fallback until the Stable channel shipped
  ([AIPCC-13781](https://redhat.atlassian.net/browse/AIPCC-13781)).
* **No home for out-of-cycle content.** Content that lands after code freeze, or a
  torch version a consumer needs early, cannot ship on the product cadence.
* **Growing maintenance tax.** Per-release branches and full index sets, against
  ~100 active CVEs, do not scale as the accelerator and framework matrix grows.
* **Opaque base-image tags.** AIPCC base images use product-version tags such as
  `quay.io/aipcc/base-images/cuda:3.0` that do not expose accelerator, torch, or
  RHEL versions — unlike this repository's descriptive image names (e.g.
  `cuda-jupyter-pytorch-ubi9-python-3.12`). The Notebooks team raised this in
  [RHAIENG-569](https://redhat.atlassian.net/browse/RHAIENG-569); AIPCC declined
  to enrich those tags under the old model (closed Won't Do, May 2026).

AIPCC is formalizing an **à la carte** content-delivery model
([AIPCC-27889](https://redhat.atlassian.net/browse/AIPCC-27889),
[team-docs MR !263](https://gitlab.com/redhat/rhel-ai/core/team-docs/-/merge_requests/263))
that decouples content identity from RHAI product versions. The proposal aligns
with RHOAI leadership's direction for a rolling developer preview and fast-track
component delivery (e.g. vLLM).

This ADR records how the **notebooks repository** adopts that model. It does not
define AIPCC-wide policy; the canonical ADR and RFD live in AIPCC's team-docs.

## Decision

### Align with AIPCC channel-based content identity

We will consume AIPCC content by **channel** — accelerator plus torch version
plus OS suffix (e.g. `cuda13.0-torch2.12-ubi9`, `cpu-notorch-ubi9`) — instead
of RHAI-versioned index paths (`rhoai/3.6-EA1/cuda12.9-ubi9`).

Concrete naming changes:

| Aspect | Before | After |
|--------|--------|-------|
| Python package index | `rhoai/3.6-EA1/cuda12.9-ubi9` | `cuda13.0-torch2.12-ubi9` |
| Index URL | `.../public-rhai/rhoai/3.6-EA1/cuda12.9-ubi9/simple/` | `.../public-rhai/rhoai/cuda13.0-torch2.12-ubi9/simple/` |
| RHAIBI base image tag | `base-image-cuda-12.9-rhel9:3.5.0` | `base-image-cuda-12.9-torch-2.11-rhel9:<timestamp>` |
| CPU without torch | N/A | `cpu-notorch-ubi9` channel |

The accel+torch token is the primary identity; the `-ubi9` (or future OS) suffix
scopes the channel to a base OS. Multiple OSes are **not** combined in one
channel. Maturity (`rolling` / `stable`) is a Pulp metadata label on the
repository, not part of the index URL path.

**One index per consumer.** Platform-independent wheels (`py3-none-any`) and
compiled no-torch packages are built once into internal Pulp caches and
**blended by reference** into each user-facing channel's index ([fromager#1064](https://github.com/python-wheel-build/fromager/issues/1064)).
Notebooks does not configure or merge multiple indexes — a `cuda13.0-torch2.12`
build resolves all packages from that single channel URL.

Channel identity is fixed for the lifetime of a pin; a torch ABI change creates a
**new** channel instead of a silent swap under an existing path.

This channel model provides the **descriptive naming** [RHAIENG-569](https://redhat.atlassian.net/browse/RHAIENG-569)
asked for: accelerator and torch version are explicit in the channel name and
base-image identity (e.g. `cuda13.0-torch2.12`, `rocm7.14-torch2.11`), rather
than buried under an opaque product-version tag like `cuda:3.0`.

#### Per-image channel selection (not one channel per release)

A RHOAI release does **not** require every notebook image family to consume the
same channel. Each image Dockerfile picks the channel that matches its
accelerator and framework needs; the release contract is the **set of lockfiles
and base-image pins** across those images, not a single shared index path.

This is already how Notebooks is structured today and remains valid under à la
carte. For example, a single RHOAI 3.6 release may simultaneously ship:

| Image family | Channel |
|--------------|---------|
| jupyter-pytorch, pytorch+llmcompressor | `cuda13.0-torch2.11-ubi9` |
| jupyter-tensorflow | `cuda12.9-torch2.11-ubi9` |
| jupyter/rocm pytorch | `rocm7.14-torch2.11-ubi9` |
| minimal, datascience | `cpu-torch2.11-ubi9` |
| trustyai | `cpu-notorch-ubi9` |

GA registration with AIPCC is per channel adopted, not a single channel for the
whole product. `packages.redhat.com` lists which release(s) consume each channel.

Notebooks must **communicate channel adoption to AIPCC** for each GA release
(which channels we ship on) and **maintain a durable record** of which channel
and lockfile snapshot each image family used — the operational visibility
[RHAIENG-569](https://redhat.atlassian.net/browse/RHAIENG-569) asked for, now
addressed through channel identity rather than richer Quay tags. This is beyond
the git pins in this repository and aligned with the GA registration process in
the RFD (mechanism TBD with Release Engineering).

### Two maturity labels (not three)

The AIPCC proposal originally described three tiers (Stable / Current / Rolling).
Cross-team review showed Current and Stable behaved almost identically, so the
model was simplified to **two labels**:

* **Rolling** — default. Ecosystem packages (vllm, llm-compressor, CVE fixes,
  etc.) flow continuously with no RHAI code-freeze constraints. AIPCC does not
  pre-validate Rolling content; any team can adopt a channel once it has done its
  own testing (including for a GA release).
* **Stable** — a channel this repository (or a RHOAI release) has **adopted and
  supports**, with a capped support window. Content is not frozen: CVE and bug
  fixes keep flowing within the channel's ABI ceiling.

The label is **not** part of channel identity or URL, so promotion from Rolling
to Stable does not invalidate pinned references.

#### Rolling is delivery cadence, not a floating torch

**Rolling does not mean torch or accelerator versions float.** Channel identity
always includes both in the name (e.g. `cuda13.0-torch2.11`). That anchor is
fixed for every channel regardless of maturity label. A torch ABI change creates
a **new** channel (`cuda13.0-torch2.12`), not an in-place upgrade under the
same path — that is the fix for the silent 2.9 → 2.10 swap in RHOAI 3.4/3.5.

What differs between Rolling and Stable is **cadence and support**, not the
torch/accel anchor:

| | Rolling | Stable |
|---|---------|--------|
| Torch + accelerator (channel name) | Fixed | Fixed (same URL) |
| Ecosystem packages within channel | Continuous updates | Continuous updates within ABI |
| AIPCC pre-validation | No | Yes — a release validated and shipped on it |
| Support commitment | None until adopted | Capped window (release EOL, base-image support, upstream torch) |

#### Stable adoption and communication

The Rolling → Stable flip is triggered by **GA registration**, not by EA
milestones or code freeze. There is no AIPCC-internal promotion gate (no EA-1/EA-2
validation step on the AIPCC side).

| Phase | Channel label | What happens |
|-------|---------------|--------------|
| Pre-GA (development, EA testing) | **Rolling** | Notebooks builds from a channel (e.g. `cuda13.0-torch2.11`), tests against it, and pins a lockfile. AIPCC keeps publishing compatible package versions into the channel. |
| GA | **Stable** (after registration) | RHOAI validates the release on that channel, ships it, and **registers the GA with AIPCC**. That event flips the maturity label. |
| Post-GA (z-streams, EUS) | **Stable** | Same channel URL. Lockfile bumps for CVE fixes; the channel head keeps moving within the torch ABI. |

**EA is not a formal Rolling trigger.** During a traditional release that still
runs EA1/EA2 milestones, the channel will *usually* be Rolling through those
phases simply because GA has not happened yet — but that is coincidence, not
policy. The RFD explicitly removes EA-1/EA-2 as separate content groups on
`packages.redhat.com` and replaces the old "AIPCC validates at EA" gate with
"your release's GA validates it." A team may also ship a GA directly from a
Rolling channel (after its own testing) under the rolling dev-preview direction
RHOAI leadership is proposing — there is no requirement to pass through EA
milestones first.

**How adoption is recorded and communicated:**

1. **In this repository** — the lockfile plus timestamp-tagged `BASE_IMAGE` in
   `build-args/konflux.*.conf`. That is the reproducible record of what a release
   shipped.
2. **With AIPCC** — RHOAI release management registers GA-on-channel. This flips
   the maturity label. The exact registration mechanism is not yet defined in the
   RFD (tracked with Release Engineering).
3. **On `packages.redhat.com`** — each channel shows its maturity label
   (`rolling` or `stable`, a Pulp metadata label not part of the index URL),
   consuming release(s) (e.g. "RHOAI 3.6"), and a deprecation timeline.

**What Stable means in practice:** a support and deprecation commitment from
AIPCC, not a frozen snapshot. CVE and bug fixes keep flowing within the channel's
torch/accel anchor. "Validated" applies to the **snapshot each release pinned**
(lockfile + base-image timestamp), not to the channel head, which keeps moving.

### Lockfile plus base image is the release contract

"What did RHOAI 3.6 GA ship?" is answered by **this repository's lockfile**
(Renovate/Dependabot-managed, on `main` or a stable branch) plus the immutable
timestamp-tagged RHAIBI base image referenced in `build-args/konflux.*.conf`.
AIPCC builds every compatible package version in a channel and retains published
versions for the channel's supported lifecycle; the lockfile pins exactly what a
release shipped and is fully reproducible against the channel.

Post-GA, ABI-compatible fixes (qualified CVEs and urgent bug fixes) flow through
channel updates. This team bumps its lockfile; RHOAI release management approves
each z-stream re-pin.

### Channel support follows consumption

A channel is supported while **any** product version that consumes it is
supported. Support duration is **capped** to the shortest of: the consuming
release branch's lifetime, base-image content support, and upstream torch
support — so consumers may be asked to move to a newer-torch channel at the next
release rather than maintaining aged-out torch streams indefinitely. Its end date
is the maximum of its consumers' EOLs. For LTS/EUS consumers, a channel they
consume is maintained to the LTS timeline (18 months). Channels no supported
release adopts are deprecated quickly, with a minimum deprecation notice (exact
window TBD with Release Engineering).

EUS is tracked via the **retained channel plus the release lockfile**, not a
`rhoai/<release>` index.

**ABI ceiling.** When the only fix for a vulnerability requires a newer torch than
a Stable channel provides, consumers must upgrade to a newer-torch channel,
carry a custom backport, or accept no fix. This cost is explicit rather than
hidden.

### What changes in this repository

* `BASE_IMAGE` references in `build-args/konflux.*.conf` move to channel identity
  with timestamp tags.
* Python index URLs derived from `BASE_IMAGE` follow channel naming.
* `channel: fast` / `channel: stable` resolution in
  `scripts/update_build_args_from_versions.py` and
  `docs/base_image_versions_update_configuration.md` will be redesigned to match
  the à la carte model.
* Lockfiles become the authoritative per-release pin; Renovate manages bumps.

Legacy `rhoai/<release>` references keep resolving during the transition.

### Non-goals

* **No new customer-facing workbench images or RHOAI Dashboard UX.** À la carte
  changes how we build workbenches (which index and base image we consume, and
  how we pin what we ship), not what customers pick in the Dashboard.
  Workbench image names and ImageStreams stay as they are today unless we
  explicitly choose to expose a new variant.
* **Day-0 Torch Dashboard workbench is out of scope.** That is a separate product
  RFE. Day-0 Torch images may consume a Rolling channel later; à la carte is the
  delivery substrate that makes that easier, but this ADR neither requires nor
  delivers any Dashboard change.
* **AIPCC `packages.redhat.com` catalog UX** becomes channel-based. That is the
  AIPCC content catalog, not the RHOAI Dashboard.

## Mapping from AIPCC Release Plan

AIPCC maintains an [AIPCC Development Platform Release Plan](https://docs.google.com/spreadsheets/d/1cFIL4klt4uRflIsTH2pigls1_3RdzyGx8sXZ6F2UtQ0/edit?gid=1540266814#gid=1540266814)
spreadsheet with **CUDA**, **ROCm**, and **CPU** tabs. Under the legacy model,
each tab uses **columns for RHAI milestones** (3.4 EA1 → 3.4 GA → 3.5 → 3.6) and
**row blocks for accelerator stacks** (CUDA 12.9, 13.0, 13.2; ROCm 6.4, 7.14;
CPU), with cells listing package versions at that release.

That layout encodes the coupling this ADR removes. On the CUDA 12.9 block, torch
moves from 2.9.1 at EA to 2.10 at GA to 2.11 in 3.5 — all under the same
`rhoai/<release>/cuda12.9-ubi9` path. Under à la carte, each row block becomes
one or more **channels**; release columns no longer redefine torch or accelerator
identity. They record **which channel(s) a release adopted** and what lockfile
snapshot it shipped.

| Legacy spreadsheet concept | À la carte equivalent |
|----------------------------|----------------------|
| Column (e.g. RHAI 3.6 GA) | Release adoption event + lockfile snapshot |
| Row block (e.g. CUDA 13.0) | Channel family (`cuda13.0-torch2.11-ubi9`) |
| Cell (e.g. vllm 0.24.0) | Package version AIPCC builds in the channel; Notebooks pins in lockfile |
| "Stable" column divider | Replaced by Stable label on an adopted channel |
| Torch bump within a row | New channel (e.g. `cuda12.9-torch2.10` → `cuda12.9-torch2.11`) |

### Channel mapping for this repository

The spreadsheet's accelerator blocks map to AIPCC channels. This repository's
current `versions_config.yml` preferences align as follows (torch 2.11 at 3.6
planning time):

| Spreadsheet row block | Notebook image families | AIPCC channel |
|-----------------------|-------------------------|---------------|
| CUDA 13.0 | jupyter-pytorch, pytorch+llmcompressor (workbench and runtime) | `cuda13.0-torch2.11-ubi9` |
| CUDA 12.9 | jupyter-tensorflow, runtime-tensorflow | `cuda12.9-torch2.11-ubi9` |
| CUDA 13.2 | Planned in 3.5 EA1+; not yet a Notebooks default | `cuda13.2-torch2.11-ubi9` (when adopted) |
| ROCm 7.14 | jupyter/rocm pytorch and tensorflow, runtimes | `rocm7.14-torch2.11-ubi9` |
| ROCm 6.4 | Retired after 3.4 in the plan | Channel retires when last consumer EOLs |
| CPU (with torch) | minimal, datascience, codeserver | `cpu-torch2.11-ubi9` |
| CPU (no torch) | trustyai and other non-GPU stacks | `cpu-notorch-ubi9` |

Multiple accelerator generations coexist as **parallel channels**, not as
successive renames of a single `rhoai/<release>` index. RHOAI 3.5 on
`cuda12.9-torch2.11-ubi9` and 3.6 on `cuda13.0-torch2.11-ubi9` can run simultaneously
without per-release index branches.

### Package versions: what AIPCC builds vs what Notebooks ships

Sub-rows in each spreadsheet block (vllm, tensorflow, triton, llm-compressor,
nvshmem, etc.) describe the **package matrix AIPCC maintains in a channel**.
AIPCC builds every compatible version; this repository's lockfile selects the
exact versions validated for a release. For example, the CUDA 13.0 block at 3.6
EA1 may list vllm 0.26.0 and llm-compressor 0.12.0 — those are available in the
channel, but "what 3.6 GA shipped" is whatever the release lockfile pins after
QE sign-off, not the spreadsheet column header.

### ABI ceiling example

The CUDA 13.0 block notes `llm-compressor 0.10.0.2 [torch2.10]` at 3.5 EA2 — a
build tied to a specific torch ABI. If a later CVE fix requires a package built
against torch 2.12, a Stable `cuda13.0-torch2.11` consumer must move to
`cuda13.0-torch2.12`, accept a custom backport, or accept no fix. The
spreadsheet can no longer imply a silent torch upgrade under the same index path.

### Expected `versions_config.yml` evolution

Today, release stream and accelerator version are coupled:

```yaml
release:
  full_version: "3.6.0"
artifacts:
  base_image:
    cuda:
      pytorch:
        acc_version: "13.0"
        rhds:
          channel: fast
```

Under à la carte, configuration will reference an explicit AIPCC channel and
immutable base-image timestamp per image family, with ecosystem package versions
carried in per-image lockfiles rather than implied by `full_version`. The
spreadsheet remains a **planning view of which channels exist and what AIPCC
builds**; releases consume from channels instead of defining them.

## Consequences

### Positive

* **Explicit ABI boundaries.** Torch version is visible in the channel name,
  preventing silent mid-cycle swaps.
* **Out-of-cycle content has a home.** Rolling channels accept content without
  waiting for the next RHAI code freeze.
* **Self-service updates.** Teams pick the channel and maturity label that match
  their stability needs and manage pins via lockfiles.
* **Reduced CI duplication.** Consolidating wheel delivery across channels
  replaces per-release stable-branch rebuilds of the same torch stacks.
* **Strategic alignment.** Supports rolling dev preview and fast-track component
  tracks without tying notebook builds to monolithic release indexes.

### Negative

* **Migration overhead.** Pipelines, `build-args` configs, and
  `update_build_args_from_versions.py` policies that rely on `rhoai/3.x` tagging
  and `channel: fast`/`stable` must migrate to channel-based references.
* **Increased tag matrix.** More accelerator, torch, and timestamp combinations
  require robust automation and registry lifecycle policies.
* **Release-contract shift.** QE, Release Engineering, and Support must treat
  lockfiles (not `rhoai/<release>` index paths) as the source of truth for what
  a release shipped, and understand the ABI-ceiling trade-off for long-lived
  Stable channels.

## References

* [AIPCC-27889: À la carte content delivery](https://redhat.atlassian.net/browse/AIPCC-27889)
* [team-docs MR !263 (ADR + RFD)](https://gitlab.com/redhat/rhel-ai/core/team-docs/-/merge_requests/263) — includes review feedback from architecture review (Doug Hellmann, Aug 2026) that drove the two-tier model, support cap, Pulp-blended indexes, and GA registration
* [AIPCC-13781: Stable torch versions across monthly releases](https://redhat.atlassian.net/browse/AIPCC-13781)
* [RHAIENG-569: AIPCC images standardization](https://redhat.atlassian.net/browse/RHAIENG-569) — superseded by channel-based descriptive naming (accel + torch in channel/base-image identity)
* [AIPCC policy: updating packages in frozen indexes](https://gitlab.com/redhat/rhel-ai/core/team-docs/-/blob/main/docs/ecosystems/policy-updating-packages-in-frozen-indexes.md)
* [docs/subscribed-builds.md](../../subscribed-builds.md) — current AIPCC base-image consumption
* [docs/base_image_versions_update_configuration.md](../../base_image_versions_update_configuration.md) — current `channel: fast`/`stable` resolution
* [AIPCC Development Platform Release Plan](https://docs.google.com/spreadsheets/d/1cFIL4klt4uRflIsTH2pigls1_3RdzyGx8sXZ6F2UtQ0/edit?gid=1540266814#gid=1540266814) — CUDA / ROCm / CPU planning matrix
