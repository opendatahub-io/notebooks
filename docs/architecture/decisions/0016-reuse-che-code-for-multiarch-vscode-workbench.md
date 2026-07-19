# 16. Reuse Dev Spaces che-code for multiarch VS Code workbench

Date: 2026-07-19

## Status

Proposed

## Context

The RHOAI notebooks project ships a code-server-based VS Code workbench for
four architectures: amd64, arm64, ppc64le, and s390x. Building code-server from
source requires patching native npm dependencies whose postinstall scripts
download platform-specific binaries from GitHub — ripgrep, agent-browser,
vsce-sign, and (as of VS Code 1.116) tsgo. Each VS Code upgrade introduces new
packages with the same pattern, requiring manual tarball patching in
`apply-patch.sh`. This is the dominant maintenance burden for the code-server
image.

Red Hat OpenShift Dev Spaces already builds a VS Code distribution (che-code)
hermetically for all four architectures via Konflux, publishing it as
`registry.redhat.io/devspaces/code-rhel9`. The image contains pre-built VS Code
binaries, bundled Node.js, and native libraries — no source compilation needed
by consumers.

However, the che-code image is designed for the Eclipse Che DevWorkspace
runtime, not Kubeflow Notebooks. The two systems have different contracts:

| Concern | DevWorkspace (Che) | Kubeflow Notebooks |
|---|---|---|
| Port | 3100 | 8888 |
| Path routing | DevWorkspace operator | `NB_PREFIX` env var |
| Idle culling | DevWorkspace operator | `/api/kernels/` endpoint |
| Auth | K8s secrets + machine-exec | OAuth proxy |
| Terminal | machine-exec daemon (port 3333) | node-pty (built-in) |

A cross-project survey found that no other VS Code distribution builds
hermetically for ppc64le and s390x:

- **code-server** (Coder): amd64/arm64 only, no hermetic builds
- **OpenVSCode Server** (Gitpod): amd64/arm64/armhf only
- **VSCodium**: ppc64le full + s390x server-only, but not hermetic
- **Eclipse Theia**: abandoned by Dev Spaces in favor of VS Code

## Decision

### Wrap the pre-built che-code image instead of building VS Code from source

Create a new image `codeserver/che-code-ubi9-python-3.12/` that:

1. **Copies pre-built VS Code binaries** from the multi-stage
   `registry.redhat.io/devspaces/code-rhel9:3.29` image into a
   `ubi9/python-312` base — no npm install, no source compilation, no
   `apply-patch.sh`.

2. **Bridges the Kubeflow contract** with NGINX (port 8888 → 3100) and a
   Python culler server (port 8080) that serves the `/api/kernels/` idle
   culling endpoint.

3. **Uses `--server-base-path`** for NB_PREFIX routing. che-code's
   `server-main.js` natively handles path-prefixed routing, eliminating the
   complex NGINX rewrite rules the current code-server image requires.

### Che extension triage

The che-code image bundles 9 Che-specific VS Code extensions. Each was audited
for behavior outside DevWorkspaces:

| Action | Extensions | Rationale |
|---|---|---|
| **Keep** | che-api, che-port, che-remote, che-resource-monitor | Self-disable when DevWorkspace env vars are absent |
| **Keep** | che-github-authentication | Provides Device Code Flow for GitHub/Copilot auth — the built-in github-authentication uses OAuth redirect which can't work in containers (CRW-4062) |
| **Replace** | che-activity-tracker | Tracks 7 VS Code events for idle culling but calls machine-exec. Replaced with kubeflow-activity-tracker that writes `/tmp/last-activity` instead |
| **Remove** | che-commands, che-telemetry, che-terminal | Throw on activation or send data to nonexistent backends |

### Product-level defaults via `configurationDefaults`

VS Code's `product.json` `configurationDefaults` field sets defaults before user
settings load. This is used to disable workspace trust prompts, telemetry, and
extension auto-updates — the same settings the code-server image applies via
runtime `settings.json`, but at a level that takes effect before the browser UI
renders.

### Replace httpd CGI with Python culler server

The code-server image uses Apache httpd (port 8080) solely to execute one CGI
script (`access.cgi`) for idle culling. A 30-line Python `http.server` replaces
the entire httpd stack, eliminating `httpd`, `mod_cgi`, `httpd.conf`, and
`codeserver-cgi.conf` from the image.

This is a step toward the architecture described in
[RHAIRFE-1263](https://redhat.atlassian.net/browse/RHAIRFE-1263) ("Simplify
workbench proxy and idle-culling stack"), which proposes replacing the entire
three-process stack (NGINX + httpd + bash CGI) with a single-process solution.
The che-code wrapper achieves two thirds of that goal:

1. **httpd eliminated** — replaced by the Python culler server.
2. **NGINX simplified** — no rewrite rules, just `proxy_pass` (thanks to
   `--server-base-path`).

NGINX remains because two concerns still require a separate listener on port
8888:

- **Port bridging.** Kubeflow Notebooks hardcodes port 8888; che-code listens
  on 3100. This could be solved by running che-code on 8888 directly
  (`--port 8888`).
- **Culler endpoint routing.** The `/api/kernels/` path must be handled by the
  culler, not by che-code. With che-code on 8888, the culler would need to be
  merged into a small reverse proxy that owns port 8888 and dispatches
  `/api/kernels/` to its own handler while forwarding everything else to
  che-code.

A future iteration could merge the Python culler server into a lightweight
reverse proxy (Python `aiohttp`, or Go per RHAIRFE-1263's evaluation criteria)
that owns port 8888, handles both culler and proxy duties, and eliminates NGINX
entirely. The `kubeflow-activity-tracker` extension's file-based IPC
(`/tmp/last-activity`) is designed to work with any culler implementation —
the extension writes, the culler reads, no coupling to the transport layer.

## Consequences

### Positive

- **No more `apply-patch.sh` maintenance.** Native npm dependency patching
  (ripgrep, agent-browser, vsce-sign, tsgo) is handled by the Dev Spaces team.
  New VS Code upgrades that add postinstall-downloading packages don't require
  patches in this repo.

- **Simpler NGINX configuration.** `--server-base-path` handles all path
  routing natively. The proxy templates are plain `proxy_pass` directives
  instead of complex rewrite rules.

- **GitHub Copilot auth works out of the box.** The Device Code Flow from
  `che-github-authentication` lets users authenticate at
  `github.com/login/device` — no OAuth redirect URL needed.

- **Smaller attack surface.** No httpd in the image. The Python culler server
  runs as the same unprivileged user.

### Negative / risks

- **Dependency on Dev Spaces release cadence.** The wrapper image pins to a
  specific che-code tag (`3.29`). VS Code version updates come on the Dev
  Spaces schedule, not ours.

- **Che branding requires active removal.** The che-code image includes Che
  logos, welcome page titles, and `product.json` branding that must be stripped
  in the wrapper Dockerfile. Missing a branding artifact means Che logos appear
  in the workbench.

- **Dormant Che extensions produce log noise.** Extensions like
  `che-resource-monitor` log errors about missing `DEVWORKSPACE_POD_NAME` on
  every startup. Functionally harmless but visible in container logs.

- **`configurationDefaults` is fragile.** Deleting fields from `product.json`
  that compiled workbench JS references (e.g., `defaultChatAgent`) causes white
  screen crashes with no useful error. Changes to product.json must be tested
  visually.

- **Not hermetic yet.** The wrapper Dockerfile uses `dnf install` from
  network registries. Making it hermetic requires RPM prefetch but no npm
  prefetch — a significant simplification over the code-server image's 65 npm
  prefetch entries.

### PyPI-first Python environment (RHAISTRAT-1482)

The che-code wrapper image uses `ubi9/python-312` as its base, which ships
pip configured to use upstream PyPI by default. This is a deliberate choice
aligned with RHAISTRAT-1482 ("AIPCC Notebook Upstream Inclusion"):

- **Current RHOAI workbenches** (code-server, JupyterLab) are built with
  AIPCC base images that default to the Red Hat AI Python Index
  (`console.redhat.com/api/pypi/public-rhai/rhoai/{version}/{variant}/simple/`).
  Packages are Red Hat-built from source for supply chain security, but the
  index has limited coverage — packages not in the index fail to install.

- **The che-code wrapper** uses standard UBI9 Python with PyPI as the default
  index. Users can `pip install` any package from PyPI directly. This makes it
  the "community" image variant described in RHAISTRAT-1482: upstream package
  access with existing security expectations, traded against AIPCC's supply
  chain guarantees.

- **ppc64le/s390x benefit especially.** The Red Hat AI Python Index has limited
  coverage for these architectures. PyPI packages like PyTorch bundle
  platform-specific wheels, and users on ppc64le/s390x can install from PyPI
  or build from source without hitting missing-package errors from a curated
  index.

This means the che-code wrapper is not just a "same image, different VS Code
binary" — it represents the community/upstream image track where users opt for
package availability over Red Hat supply chain certification. Admins choose
between the images at workbench creation time; the choice determines the
package source, not a runtime configuration switch.

### Non-goals

- Replacing the existing code-server image. This is an alternative that can
  coexist. The code-server image remains the default until the wrapper is
  validated in production.

- Hermetic Konflux build in the initial PR. The Dockerfile is non-hermetic
  (`hermetic: 'false'` in the Tekton pipeline) to prove the concept. Hermetic
  RPM prefetch is a follow-up.

- Using the Red Hat AI Python Index in this image. That is the domain of the
  AIPCC-based workbench images. Mixing upstream PyPI packages with Red Hat
  index packages in the same environment is explicitly unsupported per
  RHAISTRAT-1482 requirements.

## References

- PR: [#4106](https://github.com/opendatahub-io/notebooks/pull/4106)
- Issues: [#4063](https://github.com/opendatahub-io/notebooks/issues/4063)
  (Multiarch VS Code),
  [#4093](https://github.com/opendatahub-io/notebooks/issues/4093)
  (Activity tracking for che-based VS Code)
- RHAISTRAT-1482: AIPCC Notebook Upstream Inclusion
  ([refinement doc](https://docs.google.com/document/d/1i1Xv24RIe13wmUibdTF_QIcvBOvnYL4tzQTVU6XsZ7U/edit))
- [Red Hat AI Python Package Index](https://access.redhat.com/articles/7137881)
  — curated Python index for RHOAI secure images
- Dev Spaces pipeline source: `gitlab.cee.redhat.com/codeready-workspaces/devspaces-images`
  (project 98145, branch `devspaces-3-rhel-9`)
- CRW-4062: Integrate GitHub Copilot into OpenShift DevSpaces
- CRW-10918: Improve GitHub Copilot Chat authentication flow
- che-code `server-main.js` CLI flags:
  `code/src/vs/server/node/serverEnvironmentService.ts` in
  [che-incubator/che-code](https://github.com/che-incubator/che-code)
