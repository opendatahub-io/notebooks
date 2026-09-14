---
marp: true
theme: default
paginate: true
size: 16:9
---

<!-- _class: lead -->

# Notebooks × Bodies of Water

### The Stream → Lake → Ocean release flow — team training

**RHAIENG-1264** · docs PR [opendatahub-io/notebooks#4583](https://github.com/opendatahub-io/notebooks/pull/4583)

<!-- notes:
Setup: this is the in-team training for the Bodies of Water adoption (epic RHAIENG-1273).
Goal after 20 min: everyone can say what goes where, which gates protect each transition,
and what to do when a train freezes. Source of truth after this deck:
docs/bodies-of-water.md (workflow) + docs/bodies-of-water-troubleshooting.md (fixes).
-->

---

# Why "Bodies of Water"

One release strategy, all RHOAI components — **three stages, quality gates, explicit transitions**:

| Stage | Meaning | For us |
|---|---|---|
| **Stream** | Component-owned dev trunk | `main` in `opendatahub-io/notebooks` |
| **Lake** (ODH) | ODH stable — first joint deliverable | `stable` — **ODH Nightly builds here** |
| **Ocean** (RHOAI) | Product-releasable | `rhoai-X.Y` trains in `red-hat-data-services/notebooks` — **RHOAI Nightly + RC/GA** |

<!-- notes:
Canonical design doc: "Release Strategy – The Bodies Of Water" (Andrew Ballantyne) — foundational
design, not actively maintained; live phase status is RHOAIENG-28641.
Our signoff (in the cross-team signoff table): Notebooks · Jiri Daněk · 2025-08-05 ·
Stream=main, Lake=stable, Ocean=rhoai, RHDS branch=main.
Mechanism deep-dive (verified live): docs/code-flow-odh-to-rhoai.md.
-->

---

# Branch map

```
opendatahub-io/notebooks                     red-hat-data-services/notebooks
  main        (Stream) — all dev lands here   main         (Ocean) — DevOps-owned
  stable      (Lake) ─── ODH nightly build ─▶ rhoai-X.Y    (trains) — auto-synced
  2025a/…     (ODH GA branches)                         └─ RHOAI nightly + RC/GA
```

- `main` → `stable`: **fast-forward only**, via the "Merge main into stable" GHA (`dry_run` first)
- `stable` → train: **DevOps auto-sync** (`rhods-devops-infra` GitHub Actions)
- We **never commit directly** to `stable` or to any RHDS branch

<!-- notes:
Key invariant: stable is an ancestor of main. If it isn't, something was committed to stable
by hand and the fast-forward GHA will (correctly) refuse.
ODH nightly is built from stable by Konflux (open-data-hub-tenant); kickoff = make kickoff-release
or the Release Kickoff Action GHA (versions_config.yml).
-->

---

# ⚠️ The train-divergence rule

When a **new train is onboarded**, auto-merge from `stable` **switches to it**:

```
before:  stable ──auto-merge──▶ rhoai-3.6-ea.1
after 3.6-ea.2 onboarded:
  stable ──auto-merge──▶ rhoai-3.6-ea.2        ✅ automatic
  stable ──✋───────────▶ rhoai-3.6-ea.1        ❌ manual, by us
```

- Work on `main`/`stable` after the cut reaches **only the newest train** automatically
- Anything still needed on an **older (frozen) train**: **we cherry-pick downward — DevOps will not**
- First real occurrence: **2026-08-24 EA1/EA2 onboarding**

<!-- notes:
This is the single most important slide — the EA1 code freeze moved Aug 21 → Aug 31 and EA2 was
onboarded, so EA1 stopped receiving auto-merge. Ask the room: "if a fix lands on main today and
EA1 is still open, what happens?" Answer: nothing, unless we cherry-pick.
-->

---

# Cherry-picking downward, cleanly

1. Branch **from the older train** — never merge a newer train into it
2. Cherry-pick **product commits only** (Dockerfiles, lockfiles, `ci/`, `scripts/`, `manifests/`)
3. **`.tekton/` stays byte-identical to that train** — PipelineRuns are synced per-branch from
   konflux-central and *differ between trains*
4. PR against the older train; review + approve before freeze
5. Verify train builds (expect branch-locked dep fallout)

**The #2806 → #2807 lesson:** an EA2→EA1 merge PR was dirty (foreign `.tekton/` + tag retargets;
GitHub cannot retarget a PR head) → closed. A *new branch from EA1* with cherry-picks → merged.

<!-- notes:
Real example: red-hat-data-services/notebooks PR #2806 (closed, dirty) vs #2807 (merged, clean).
Typical fallout to pre-empt: branch-locked deps (e.g. libxkbfile-devel present on main, absent on
the train) → refresh the TRAIN's lockfiles, not main's (auto-sync won't carry it downward).
-->

---

# Quality gates per transition

| Transition | Mechanism | Must be green |
|---|---|---|
| PR → `main` | PR + Prow/Tide (`/lgtm` `/approve`), merge bot | code-quality GHAs, unit tests, testcontainers integration, Konflux PR builds |
| `main` → `stable` | FF-only GHA | `stable` ancestor of `main`; then **ODH nightly** build + smoke/ITS pass |
| `stable` → train | DevOps auto-sync | **RHOAI nightly** build + Jenkins E2E (ods-ci `0500__ide`, opendatahub-tests) |
| nightly → RC/GA | **DevOps-owned** | our job: keep the train green |

<!-- notes:
ODH nightly: Konflux open-data-hub-tenant from stable; smoke via Jenkins autotrigger-smoke;
on-demand ITS scenario its-trigger-nightly.
RHOAI nightly: scheduled Konflux pipelines from the train; Jenkins tier1/2/3 sanity+smoke against
rhoai-fbc-fragment:rhoai-X.Y-nightly. Green train build cascades into the catalog via the
operator→bundle→FBC nudge chain (code-flow doc §6).
-->

---

# Testing at each stage

| Stage | Command / system |
|---|---|
| Local | `make test` · `make test-unit` |
| Local / PR | `make test-integration PYTEST_ARGS="--image=<img>"` (testcontainers) |
| PR, automatic | code-quality GHAs + Konflux PR builds (`/retest`, `/test`) |
| Notebook smoke | `make test-<notebook>` (papermill vs deployed workbench) |
| ODH nightly | Jenkins ods-ci smokes + ITS `its-trigger-nightly` |
| RHOAI nightly | Jenkins tier1/2/3 vs `rhoai-X.Y-nightly` FBC fragment |

Full catalog: **`docs/agents/testing.md`** ← this was the training gap from last year; it's covered now.

<!-- notes:
Recall the Nov 2025 training note on RHAIENG-1264: QE had seen in-repo tests but not the
downstream IDE surface. Pointer: ods-ci 0500__ide for product E2E, per-image "what should work
once built" notes being gathered next to Dockerfiles (RHOAIENG-24093).
-->

---

# ODH release runbook (team-driven)

Recurring ticket per cycle — template [RHAIENG-6297](https://redhat.atlassian.net/browse/RHAIENG-6297), current [RHAIENG-7156](https://redhat.atlassian.net/browse/RHAIENG-7156):

1. **Verify code freeze** — release tracker + ODH Release calendar
2. **Validate image tags** — `.tekton/*.yaml` + `params-latest.env`; format `<train>-v<NN>`, **no patch version** (e.g. `3.5-v1.47`)
3. **Publish** — **"Create release"** GHA, *same tag as the image builds* (creates git tag + GitHub release)
4. **Comment the tracker** — [workbenches-operator#107](https://github.com/opendatahub-io/workbenches-operator/issues/107) ⚠️ *not* `opendatahub-community#202` (operator-only now)
5. **Post-release** — **"Update Tekton Tags"** GHA for the *next* cycle (opens a PR — merge it)
6. **Clone the ticket** for the next cycle, bump tags

<!-- notes:
Ordering gotcha: Update Tekton Tags runs AFTER publishing (the ticket's own warning).
The Update-Tekton-Tags GHA fails if it can't find exactly one previous tag in .tekton/*.yaml —
check for stale leftovers first.
-->

---

# What to do when — quick reference

| Situation | Do |
|---|---|
| New feature / normal fix | PR to `main`, land when gates are green |
| Must reach ODH nightly | Land on `main` → FF to `stable` (GHA, `dry_run` first) |
| Must reach **newest** train | Automatic after `stable` — verify via nightly |
| Must reach **older/frozen** train | Cherry-pick downward (procedure on slide 6) |
| ODH release cycle | 6-step runbook (slide 8) |
| CVE on a release branch | `docs/cves/` workflows + fix-cve agent flow |
| Something's broken | `docs/bodies-of-water-troubleshooting.md` |

<!-- notes:
This table is the training artifact — tell the team it lives in the doc, not just the deck.
Emphasize row 4: nobody else will do it for you.
-->

---

# Troubleshooting: the top 5

| Symptom | Cause → fix |
|---|---|
| `main` change missing on a train | Auto-merge only targets newest → cherry-pick down |
| FF to `stable` refuses | `stable` diverged → never commit to `stable`; use sync-through-PR |
| Green on `main`, red on train | Branch-locked deps → refresh **the train's** lockfiles |
| Flaky npm tarball in cachi2 | Clear `cachi2/output/deps/npm`, re-run |
| No Konflux build on push | `pathChanged()`/nudge guards → `docs/konflux.md` known issues |

Full table + escalation matrix (office hours Tue, `#rhoai-devtestops-requests`) in the troubleshooting doc.

<!-- notes:
Also in the doc: sbom-syft-generate StepOverride on legacy trains (escalate, don't patch .tekton/),
nudge-chain stalls (check operator→bundle→FBC nudge PRs), release tag-format mistakes.
Escalate with: PipelineRun name + branch + failing step.
-->

---

# Who owns what (DevOps knowledge transfer)

**DevOps owns** — don't edit, request changes:
- `stable` → train auto-sync (GHAs in `rhods-devops-infra`)
- Konflux pipelines: `.tekton/` synced read-only from `konflux-central` — **never hand-edit**
- Train management, RC/GA, image mirroring

**We provide** — the signoff contract:

| Component | Stream | Lake | Ocean | RHDS |
|---|---|---|---|---|
| Notebooks (signoff 2025-08-05) | `main` | `stable` | `rhoai` | `main` |

Keep the row current in the [canonical signoff table](https://docs.google.com/document/d/1LXbAylu-1rCw1gkqNuhLoPC5tzD70gg0jdGy-SBgyYI/edit) if branch names ever change.

<!-- notes:
This closes the "knowledge transfer to DevOps" AC: DevOps has everything they need (branch names,
sync config pointers, our release-branch contract) and a clear boundary for what they operate.
Questions/requests: DevTestOps office hours (Tuesdays) or #rhoai-devtestops-requests.
-->

---

# Where it all lives

- **`docs/bodies-of-water.md`** — the workflow (branch strategy, gates, releases, KT)
- **`docs/bodies-of-water-troubleshooting.md`** — symptom → fix + escalation
- **`docs/code-flow-odh-to-rhoai.md`** — mechanism deep-dive (verified live)
- **`docs/agents/testing.md`** · **`docs/konflux.md`** · **`docs/ci.md`** — test catalog, builds, CI
- Jira: [RHAIENG-1273](https://redhat.atlassian.net/browse/RHAIENG-1273) (adoption epic) ·
  [RHAIENG-1264](https://redhat.atlassian.net/browse/RHAIENG-1264) (this work)

**Next live rehearsal: the upcoming ODH release (RHAIENG-7156).**

<!-- notes:
Close with: the release ticket is the runbook; the deck is the orientation.
Suggest the team opens the quick-reference table in the doc during their next release-touching task.
-->
