# FIPS Compliance Status

Workbench images and 3rd-party accelerator runtime images are **not** part of
"Designed for FIPS." This was decided by Sherard Griffin (Director of Engineering)
and confirmed by Nick Ommen (PM) on Apr 28, 2026. The decision applies to RHOAI
3.4 and all prior releases, and extends beyond 3.4.

Release notes are being updated to reflect this:
[RHOAIENG-60236](https://redhat.atlassian.net/browse/RHOAIENG-60236).

## What fails check-payload and why

The `check-payload` FIPS scanner flags binaries that are not dynamically linked
(`ErrNotDynLinked`). Three binaries in workbench images trigger this:

| Binary | Path | Why it's in the image | Crypto? |
|--------|------|-----------------------|---------|
| pandoc | `/usr/local/pandoc/bin/pandoc` | PDF export from JupyterLab (notebook to LaTeX to PDF) | Yes (see below) |
| py-spy | `/opt/app-root/bin/py-spy` | Python profiler; transitive dep from Ray/CodeFlare | No |
| rg (ripgrep) | `/usr/lib/code-server/lib/vscode/node_modules/@vscode/ripgrep/bin/rg` | IDE search, required by code-server | No |

Tracked under [RHOAIENG-58626](https://redhat.atlassian.net/browse/RHOAIENG-58626).

## Pandoc deep dive

The workbench images ship pandoc 3.7.0.2, a **statically linked** prebuilt binary
downloaded from GitHub releases. Inspecting the binary reveals it contains the
full Haskell-native TLS stack:

```bash
strings /usr/local/pandoc/bin/pandoc | grep -E 'tls-|http-client-tls|crypton'
# tls-2.1.10          — Haskell native TLS (not OpenSSL)
# http-client-tls     — HTTP client using the tls library
# crypton-connection   — crypto primitives (bundled C, not OpenSSL)
```

Pandoc uses the Haskell `tls` package with `crypton` for cryptographic
primitives. This is a pure-Haskell + bundled-C implementation — it does **not**
link to OpenSSL/libcrypto/libssl. Even rebuilding pandoc from source and
dynamically linking would pass `check-payload` but would not make it "Designed
for FIPS" since the crypto is not delegated to a FIPS-validated module.

Gerard Ryan raised this point:
[DevTestOps thread](https://redhat-internal.slack.com/archives/C07SBP17R7Z/p1776862720676049?thread_ts=1776778459.956129).

### Is the TLS code path exercised?

**No, not in the standard JupyterLab PDF export flow.**

JupyterLab uses `nbconvert` which calls pandoc via:
```python
p = subprocess.Popen(["pandoc", "-f", fmt, "-t", to], stdin=PIPE, stdout=PIPE)
out, _ = p.communicate(source.encode())
```
Source: [nbconvert/utils/pandoc.py](https://github.com/jupyter/nbconvert/blob/main/nbconvert/utils/pandoc.py)

Pandoc only fetches remote resources when:
1. A URL is passed as a command-line input argument
2. `--embed-resources` (or `--self-contained`) flag is passed

Neither applies in the nbconvert code path. Remote URLs in notebook content
(e.g. `![img](https://example.com/image.png)`) are passed through to LaTeX as
`\includegraphics{https://...}` without pandoc fetching them.

```bash
# No fetch — URL passes through:
echo '![test](https://httpbin.org/get)' | pandoc -f markdown -t html
# <img src="https://httpbin.org/get" .../>

# Fetch happens — image inlined as data URI:
echo '![test](https://httpbin.org/image/png)' | pandoc -f markdown -t html --embed-resources --standalone
# <img src="data:image/png;base64,..." .../>
```

### Pandoc http flag (3.9.0.2+)

Pandoc 3.9.0.2 introduced a build flag `http` (default: `True`) that controls
whether HTTP/TLS support is compiled in. Building with `-f -http` removes all
TLS dependencies (`tls`, `crypton`, `http-client-tls`) from the binary entirely.
This flag does not exist in 3.7.0.2.

## Exception mechanisms

### Konflux release pipeline

The FBC FIPS check in Konflux scans all component images and cannot exclude
specific components ([EC-1796](https://redhat.atlassian.net/browse/EC-1796)).
A blanket exception is maintained in
[konflux-release-data](https://gitlab.cee.redhat.com/releng/konflux-release-data)
ECP config. DevOps (Chris Kodama) manages these exceptions and extends them
for each release. Example:
[MR #17077](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/merge_requests/17077)
(extended to May 15, 2026 for 3.3.2/3.4.0).

### Local and CI scans

The file [`scripts/check-payload/config.toml`](../scripts/check-payload/config.toml)
contains suppressions for the three binaries. This config is used when running
`check-payload` locally or in CI (e.g. the `fips-check` GitHub Actions job) but
does **not** affect the Konflux release pipeline.

### ProdSec guidance

JP Jung (ProdSec, #forum-ocp-fips) confirmed that binaries performing no
cryptographic operations are "cleartext equivalent" and qualify for permanent
exception:
[Slack thread](https://redhat-internal.slack.com/archives/C05U13J3LLS/p1777327233695709?thread_ts=1777326908.529319).

## Long-term roadmap

| Item | Status | Target |
|------|--------|--------|
| Build pandoc from source with `-f -http` | In progress ([AIPCC-7795](https://redhat.atlassian.net/browse/AIPCC-7795)) | 3.5 EA1+ |
| Add pandoc/py-spy/rg to check-payload global exceptions | PR open ([check-payload #327](https://github.com/openshift/check-payload/pull/327)) | Pending review |
| Granular FBC FIPS exceptions in Konflux | RFE filed ([EC-1796](https://redhat.atlassian.net/browse/EC-1796)) | TBD |

## References

- [RHOAIENG-58626](https://redhat.atlassian.net/browse/RHOAIENG-58626) — Address FIPS check-payload scan failures (umbrella)
- [RHOAIENG-60236](https://redhat.atlassian.net/browse/RHOAIENG-60236) — Update release notes re: workbench FIPS exclusion
- [AIPCC-7795](https://redhat.atlassian.net/browse/AIPCC-7795) — Build pandoc from source (AIPCC wheels)
- [EC-1796](https://redhat.atlassian.net/browse/EC-1796) — RFE: Granular FBC FIPS scan exceptions
- [check-payload #327](https://github.com/openshift/check-payload/pull/327) — Global exceptions for pandoc, py-spy, rg
- [Slack: 3.3.3 release FIPS discussion (May 5, 2026)](https://redhat-internal.slack.com/archives/C0AU47VSVSN/p1777977041600609) — Thread with full technical analysis
- [Slack: forum-ocp-fips discussion](https://redhat-internal.slack.com/archives/C05U13J3LLS/p1777326908529319) — ProdSec guidance on exceptions
- [Slack: pandoc removal discussion](https://redhat-internal.slack.com/archives/C0961HQ858Q/p1776946326109889) — Why removing pandoc is not preferred
- [Slack: Len DiMaggio FIPS status summary](https://redhat-internal.slack.com/archives/C05NXTEHLGY/p1776873935325119?thread_ts=1776859899.201459) — Konflux FIPS scan limitations
