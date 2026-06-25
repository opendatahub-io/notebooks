# Build profile investigation results (#3928)

Branch: `investigate/build-permissions-3928`  
GHA run (authoritative): [28159912769](https://github.com/opendatahub-io/notebooks/actions/runs/28159912769)  
Platform: `linux/amd64`, cold `podman build --no-cache`, hermetic `cachi2` mount  
Harness: `ci/build-profile/run-investigation.sh` + `.github/workflows/investigate-build-profile.yaml`

## Executive summary

| Finding | Impact |
|---------|--------|
| **PDF/texlive `dnf` dominates minimal install time** | 26s vs 5s `uv pip` — not permissions |
| **Permission fixup on minimal is cheap** | 2s `chmod` + 1s `fix-permissions` = **3s** (~2% of 126s build) |
| **`chmod -R g+w site-packages` is highly redundant** | Touches 18,626 paths; `fix-permissions` then only needs 723 extra `g+rw` outside that set |
| **Root `uv` install creates 19,351 root-owned paths** | `fix-permissions` must `chown` almost all of `site-packages` |
| **`USER 1001:0` for `uv` eliminates mass `chown`** | `chown_before` drops **19,351 → 30**; `fix-permissions` still ~2s |
| **`USER 1001:0` does not eliminate `chmod g+w`** | Still **18,626** paths lack `g+w` (uv creates `664` files; many entries are dirs/special) |
| **Union RPM repo is large** | **869** x86_64 RPMs prefetched; targeted `dnf install` still **7s** for 5 packages |
| **Pytorch perm profile incomplete** | Stripped profile Dockerfile failed resolver (missing datascience wheel set in stage) |

Prefetch (host, not in podman): ~3 min for minimal (pip + 2.9G RPM union download).

---

## 1. Minimal cold build — step timings (root install, production pattern)

Measured with split `RUN` blocks in `ci/build-profile/dockerfiles/minimal-timing.Dockerfile.cpu`.

| Step | Seconds | Notes |
|------|--------:|-------|
| `dnf_cpu_base_stage` | **7** | 5 packages via `dnf-helper` |
| `pdf_deps` | **26** | texlive + pandoc via `install_pdf_deps.sh` |
| `uv_pip_install` | **5** | 114 packages, `--compile-bytecode`, `UV_LINK_MODE=copy` |
| `jupyter_config` | **4** | labextension, sed, cp, addons |
| `chmod_gw` (site-packages) | **2** | 18,626 paths changed |
| `fix_permissions` (/opt/app-root) | **1** | see counts below |
| **Total podman build** | **126** | remainder: base pull, COPY, layer commit |

**Takeaway:** On minimal, optimizing permissions saves **~3 seconds**. Optimizing PDF/texlive or avoiding repeated ancestor rebuilds is a larger lever.

---

## 2. Permission counts — root install vs `USER 1001:0`

### Root `uv pip install` (current production pattern)

```
BUILD_PROFILE_CHMOD_GW path=site-packages total=19729 already_gw=1103 changed=18626
BUILD_PROFILE_FIX_PERMS path=/opt/app-root total_paths=20479 chown_before=19351 chgrp_before=0 chmod_g_rw_before=723
```

- **`chmod -R g+w site-packages`** updates **18,626** paths.
- **`fix-permissions /opt/app-root`** then `chown`s **19,351** paths (root-owned after `uv` as root).
- Only **723** paths still need `g+rw` after `chmod` — mostly **outside** `site-packages` (e.g. `etc/jupyter`, `share/jupyter` written during config).
- **`chmod` and `fix-permissions` overlap heavily** on `site-packages`; keeping both is redundant work.

### `USER 1001:0` for `uv` + jupyter config (`FIXUP_MODE=full`)

```
BUILD_PROFILE_FIX_PERMS chown_before=30 chmod_g_rw_before=723
BUILD_PROFILE_CHMOD_GW changed=18626  (unchanged)
```

- Installing as **1001:0** removes the **19k `chown`** pass — the main win from structural change.
- **`chmod g+w` on site-packages is still required** (same 18,626 changes).
- Sample ownership after user install: dir `1001:0 775`, files `1001:0 664` (group-writable, but tree walk still finds many entries without `g+w` bit as tested by `find -perm`).

### Why ~18k paths “lack `g+w`” (not a 664 bug)

The counter uses GNU find `! -perm -g+w`, which requires **both** group-read **and** group-write (`g+r` **and** `g+w`). That is stricter than “group can write”.

| Mode | Group bits | Matches `-perm -g+w`? | OpenShift needs |
|------|------------|----------------------|-----------------|
| **644** file | `r--` | **No** (no `g+w`) | `g+w` for arbitrary UID pip writes |
| **664** file | `rw-` | **Yes** | OK |
| **755** dir | `r-x` | **No** (no `g+w`) | `g+w` on dirs for create/unlink in tree |
| **775** dir | `rwx` | **Yes** | OK |

**uv does not create 664/775 for OpenShift.** It unpacks wheels with **ZIP-stored modes** (typically **644** files, **755** dirs), independent of `useradd` `UMASK=0007` — verified in a slim container: root and uid **1001** both produced `f644=96`, `d755=10`, `f664_lacks_gw=0` for packaging+requests.

So the ~18,626 `chmod g+w` changes are almost entirely:

1. **~644 files** — including `.py`, `.pyc` from `--compile-bytecode` / `compileall` (also 644)
2. **~755 directories** — package trees, `__pycache__`, `.dist-info`

Occasional **664** samples in logs are outliers (e.g. specific dist-info paths), not the bulk.

**`chmod g+w` vs `fix-permissions`:** production script uses `chmod g+rw` and `chmod g+x` on dirs; our counter only adds `g+w`. The 723 post-chmod `g+rw` gaps are paths outside `site-packages` (jupyter config trees).

**Implication:** umask / `USER 1001:0` alone will not fix this — uv applies wheel modes. Options: post-install `chmod` (current), `fix-permissions` scoped rules, or upstream uv hook to install with `g+rw`/`g+rwx` (no such flag today).

Also run arbitrary-UID smoke on production-style `minimal-timing` image.

### Arbitrary UID smoke / container tests

Earlier runs used UID **1000880000** (realistic OpenShift) but **rootless podman cannot `setresuid` to that value** on GHA (`crun: Invalid argument`). That was a **harness false negative**, not a permission regression.

Smoke test now uses **4321:0** (same as `tests/containers/workbenches/jupyterlab/`) and writes under `$HOME` (`/opt/app-root/src`, mode 770, gid 0). Re-run needed for user1001 variant verdict.

User1001 variant builds returned **exit 141** (SIGPIPE from `head` in ownership sample + `pipefail`) so images were **not tagged**; smoke tests and pytest targeted a missing image. **Fix committed** on branch (`set +o pipefail` around sample). Re-run needed for OpenShift parity tests.

`minimal-timing` image **built successfully** (`exit=0`) and is suitable for container tests.

---

## 3. DNF — union repo vs targeted install

From `dnf-benchmark` (same hermetic repo, 869 RPMs under `cachi2/output/deps/rpm/x86_64`):

| Step | Seconds |
|------|--------:|
| `dnf_cpu_base` (5 packages) | **7** |
| `dnf_pdf_deps` (texlive set) | **26** |

`rpm -Uvh --noscripts` benchmark **not completed** — naive `find` matched wrong `perl-*` subpackage RPM; needs exact NEVRA list from lockfile.

**Takeaway:** Union repo metadata does not make a 5-package `dnf install` catastrophic on minimal (**7s**). Texlive bulk install dominates OS package time. Per-image RPM slices would help prefetch size (2.9G) more than single-transaction install time on minimal.

---

## 4. Pytorch permission profiling

`pytorch-perm.Dockerfile.cuda` failed at `uv pip install`:

```
No solution found … aiohttp-cors==0.8.1
```

The profile Dockerfile omits production datascience/python stages; resolver expects wheels not present in the pytorch-only prefetch context. **Permission counts for pytorch were not captured.**

**Extrapolation from minimal:** chmod touched **19,729** paths in **2s**. Pytorch site-packages is several× larger → expect **~10–30s** for chmod+fix-permissions combined on cold builds (still secondary to `uv` unpack/bytecode for torch).

**Recommendation:** Instrument production `jupyter/pytorch/.../Dockerfile.cuda` pytorch-stage `RUN` in a follow-up run, or build via `make cuda-jupyter-pytorch-ubi9-python-3.12` with a post-build container step that runs counters.

---

## 5. Recommendations (ordered)

1. **Drop redundant `chmod -R g+w site-packages`** when `fix-permissions /opt/app-root` follows in the same `RUN` (saves ~2s minimal, more on large envs) — see #3007.
2. **Run `uv pip install` + jupyter config as `USER 1001:0`** after root-only `dnf` stages — eliminates **~19k `chown`** in `fix-permissions`; keep scoped `fix-permissions` on paths root mutates (`etc/jupyter`, `share/jupyter`).
3. **Investigate uv/file mode** — why **18,626** paths lack `g+w` even when files are `664`; possible `umask` or dir/file bit pattern fix to avoid chmod entirely.
4. **Do not prioritize `UV_LINK_MODE`** for hermetic volume builds — wheels are on bind-mount; install always materializes into the image layer.
5. **PDF deps** — largest OS install bucket on minimal/datascience ancestors; only pay on images that need PDF export.
6. **Re-run harness** after SIGPIPE fix to validate arbitrary UID + `pytest tests/containers` on `minimal-user1001-chmod-only` vs production.

---

## Reproduce

```bash
scripts/lockfile-generators/prefetch-all.sh --component-dir jupyter/minimal/ubi9-python-3.12 --flavor cpu
ci/build-profile/run-investigation.sh minimal-timing
# or push branch to trigger GHA workflow
```

Logs: GHA artifact `build-profile-logs-all-*`.
