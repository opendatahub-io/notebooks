# 4. Adopt the 2026 Q1 TestOps quality improvement plan

Date: 2026-02-10

## Status

Accepted

## Context

This document summarizes what the Notebooks team must do, should do, and could do
in response to the TestOps quality plan documents (E2E TestOps Ecosystem, Infrastructure & Quality Gates,
Nightly Triage, Redefining Quality Gates, Component Pipelines, Downstream Release Testing,
Reporting System, and CI Build Test Failure Response Framework).

The TestOps team is rolling out multiphase standardization of test infrastructure, quality gates,
reporting, and failure handling across all RHOAI/ODH component teams. The Notebooks team has already
signed off on the infrastructure strategy (Nov 13, 2025), the nightly triage process (Nov 6, 2025),
and the overall TestOps ecosystem design (Nov 13, 2025). These sign-offs create binding commitments.

Several other documents (Redefining Quality Gates, Component Pipelines, Downstream Release Testing,
Reporting, CI Build Test Failure Response Framework) do not yet have an explicit Notebooks sign-off
but describe processes that will apply to all component teams.

- **Source:** <https://docs.google.com/document/d/1LNkQDDN1g--3UYmLzi_c8WZjNSNudzDmhRrqQ7IaDeM/edit?tab=t.0#heading=h.ef6799ef5ld5>

## Decision

### MUST do (committed or mandatory obligations)

These are items the Notebooks team has signed off on or that are non-optional per the new framework.

#### 1. Participate in ODH nightly on-call rotation

- **Source:** ODH Nightly Smoke Pipeline – Ownership and Triage Process Guide (signed off Nov 6)
- One Notebooks QE member is assigned weekly for the ODH nightly smoke pipeline triage rotation.
- Daily obligation: ~10–20 minutes reviewing failures, posting a summary in `#wg-odh-nightly`.
- If a team member is on PTO >3 days, notify TestOps to add them to the exclusion list.
- Keep the rotation YAML up to date when people join/leave the team.

#### 2. Own all test failures in Stream (PR gating)

- **Source:** CI Build Test Failure Response Framework
- In the Stream stage (dev fork → component main), the Notebooks team owns environment failures,
  deployment failures, and test failures entirely.
- Tests must gate PR merges. The team decides what tests to run and maintains them.

#### 3. Own notebooks test failures in Lake and Ocean

- **Source:** CI Build Test Failure Response Framework
- In Lake→Ocean, TestOps owns env/infra, Platform owns deployment, but test failures
  for the Notebooks component are owned by the Notebooks team.
- The team must triage failures flagged by TestOps in ReportPortal/Jira/Slack and act on them.

#### 4. Follow the CI Build Test Failure Response SLAs

- **Source:** CI Build Test Failure Response Framework
- **Automation issues** (flaky/broken test): triage and fix within 24 hours.
  If no fix/workaround is provided within 24h, the gate stays blocking and the issue is escalated.
- **Product issues** (real defect): debug, decide fix vs. revert. If a quick fix is not feasible,
  revert the PR to return the build to green. RCA continues after revert.
- Before Lake: revert blocking PRs to prevent unstable code from entering Lake.
- After Lake: joint decision, but revert remains preferred when a fix is not feasible within SLA.

#### 5. Follow the Stream → Lake → Ocean branch flow

- **Source:** Test Infrastructure & Quality Gate Strategy (signed off with specific branch naming)
- The committed flow for notebooks is: `odh-io/rhoai` (Ocean) -> `RHDS main` -> `RHOAI release branch`.
- Hotfixes for Sev1/Sev2 bypass the flow and go directly to release branches (manual cherry-pick).

#### 6. Classify existing tests into the new quality gate tiers

- **Source:** Redefining CI Quality Gate Strategy (Fail-Fast Build Validation)
- The new gate model is: Cluster Health → BVT → Component Smoke → Integration/Sanity → Tier1 → Tier2.
- Each component team must classify its existing tests into these tiers.
- If a component's smoke tests fail, its integration/system tests (Sanity/Tier1/Tier2) will not run.
- This is a prerequisite for the fail-fast strategy to work; without classification, the new gate
  model cannot be applied to notebooks.

---

### SHOULD do (strongly recommended, high impact)

These are not yet formally committed but are either in progress across RHOAI or will become
mandatory soon.

#### 1. Set up PR-level gating tests (shift-left)

- **Source:** E2E TestOps Ecosystem across ODH & RHOAI (ecosystem objective: "shift-left enablement"), Test Infrastructure & Quality Gate Strategy (Stream stage)
- The quality plan expects component teams to run unit/e2e tests on PR branches, ideally on
  kind/OpenShift local clusters.
- Currently, notebooks has Konflux builds and some CI checks, but the plan calls for
  enforcing unit testing and code coverage as gating criteria on feature branches.
- This is the single highest-impact action: catching regressions before they reach Lake
  reduces nightly failures and on-call burden.

#### 2. Enforce unit testing and code coverage on feature branches

- **Source:** E2E TestOps Ecosystem across ODH & RHOAI ("Enforce unit testing and code coverage on feature branches as a gating criteria")
- This is explicitly listed as an ecosystem objective. The Notebooks team should define
  minimum coverage thresholds and enforce them in CI.

#### 3. Participate in the quality gates workgroup

- **Source:** Redefining CI Quality Gate Strategy (Fail-Fast Build Validation) (Next Steps and Workgroup Proposal)
- A cross-team workgroup will co-define quality gates, maintain test-to-gate mappings,
  and keep gate definitions aligned with coverage needs.
- Notebooks should have a representative in this workgroup to ensure notebooks-specific
  concerns (e.g., GPU workbench testing, multi-image matrix) are represented.

#### 4. Ensure test output is compatible with the reporting stack

- **Source:** RHOAI TestOps: End-to-End Test Reporting System Across Release Phases
- ReportPortal is the primary system of record. Test results must be in the standard JUnit XML format.
- Results must be tagged with standard attributes: `rhoai_version`, `fbc_image`, `quality_gate`,
  `component_name`.
- If notebooks tests do not produce these artifacts/tags today, they need to be updated
  before the Reporting Bot can cover notebooks.

#### 5. Define BVT (Build Verification Test) scope for notebooks

- **Source:** Redefining CI Quality Gate Strategy (Fail-Fast Build Validation)
- BVT validates minimal RHOAI functionality after deployment. Each component should define
  what "notebooks is basically working" means at the BVT level.
- Likely: notebook controller is running, a default notebook can be spawned, the notebook
  pod reaches Ready state.

#### 6. Evaluate requesting a component-based Jenkins pipeline

- **Source:** Component-Based Pipelines in Jenkins CI (already implemented as [RHOAIENG-43188](https://issues.redhat.com/browse/RHOAIENG-43188))
- Six teams already have or have requested dedicated component pipelines.
- If notebooks wants an isolated playground for validation (e.g., testing new workbench images
  without waiting for the full release pipeline), request onboarding from TestOps.
- Consideration: dedicated pipelines may need dedicated clusters; reuse existing component
  test clusters if quota is limited.

---

### COULD do (optional, future, opportunistic)

These are longer-term or nice-to-have actions that would improve the team's position
but are not yet required.

#### 1. Explore Konflux test pipelines for build verification

- **Source:** E2E TestOps Ecosystem across ODH & RHOAI (Phase 4), Component-Based Pipelines in Jenkins CI (Ken Dreyer's comment about GH Actions/Konflux
  as alternative to Jenkins)
- There is a spike ([RHOAIENG-12983](https://issues.redhat.com/browse/RHOAIENG-12983))
  to explore Konflux test pipelines for build verification tests.
- If notebooks already builds in Konflux, adding BVT as a Konflux test pipeline step
  would give faster feedback than waiting for Jenkins.

#### 2. Set up component-specific ReportPortal dashboards

- **Source:** RHOAI TestOps: End-to-End Test Reporting System Across Release Phases
- ReportPortal supports component-wise filtering. The team could create a notebooks-specific
  dashboard for tracking failure trends, flake rates, and test effectiveness over time.

#### 3. Contribute notebooks-specific failure signatures to the Knowledge Layer

- **Source:** E2E TestOps Ecosystem across ODH & RHOAI (Phase 6 - Knowledge Layer)
- As the AI-driven knowledge layer matures, notebooks could contribute known failure patterns
  (e.g., OOM in large notebook images, GPU driver mismatches, CUDA library issues)
  to improve automated triage and test selection.

#### 4. Explore AI-driven test selection for notebooks changes

- **Source:** E2E TestOps Ecosystem across ODH & RHOAI (Phase 6, TestAIOps section)
- When a PR touches, e.g., only the PyTorch image Dockerfile, AI-driven test selection
  could skip unrelated workbench tests and run only the affected subset.
- This is a Phase 6 item (long-term) but notebooks, with its large image matrix,
  would benefit significantly from intelligent test selection.

#### 5. Adopt AI for test case generation from feature docs

- **Source:** TestAIOps research items
- When new workbench features or images are added, AI could generate initial test cases
  from feature documentation or Dockerfiles. This is experimental and not yet standardized.

## Consequences

### Summary table

| Priority   | Action                                            | Effort                                        | Trigger                         |
|------------|---------------------------------------------------|-----------------------------------------------|---------------------------------|
| **MUST**   | Participate in ODH nightly on-call rotation       | Ongoing (~10-20 min/day during rotation week) | Already active                  |
| **MUST**   | Own Stream test failures (PR gating)              | Ongoing                                       | Every PR                        |
| **MUST**   | Own notebooks test failures in Lake/Ocean         | Ongoing                                       | Nightly failures                |
| **MUST**   | Follow CI failure response SLAs (24h fix/revert)  | Ongoing                                       | On failure                      |
| **MUST**   | Follow Stream->Lake->Ocean branch flow            | Already in place                              | Every change                    |
| **MUST**   | Classify tests into new quality gate tiers        | One-time                                      | Before new gate model rolls out |
| **SHOULD** | Set up PR-level gating tests (shift-left)         | Medium                                        | Soon                            |
| **SHOULD** | Enforce unit test coverage on feature branches    | Medium                                        | Soon                            |
| **SHOULD** | Join quality gates workgroup                      | Low (meetings)                                | When workgroup forms            |
| **SHOULD** | Ensure JUnit XML + standard tags for ReportPortal | Low-Medium                                    | Before Reporting Bot rollout    |
| **SHOULD** | Define BVT scope for notebooks                    | Low                                           | Before gate model rollout       |
| **SHOULD** | Evaluate component Jenkins pipeline               | Low (decision)                                | When needed                     |
| **COULD**  | Explore Konflux test pipelines                    | Medium                                        | When spike completes            |
| **COULD**  | Set up ReportPortal dashboards                    | Low                                           | Anytime                         |
| **COULD**  | Contribute failure signatures to Knowledge Layer  | Low                                           | Phase 6                         |
| **COULD**  | Explore AI-driven test selection                  | Medium                                        | Phase 6                         |
| **COULD**  | Adopt AI for test case generation                 | Medium                                        | Experimental                    |

### Key risks for the Notebooks team

1. **Test classification debt**: If the team does not classify existing tests into the new tiers
   (Smoke/Sanity/Tier1/Tier2) before the new gate model is enforced, notebooks tests may be
   miscategorized or skipped, leading to gaps in coverage or unnecessary blocking.

2. **Shift-left gap**: The quality plan heavily emphasizes shift-left (catching issues at PR time).
   If notebooks does not invest in PR-level gating, it will carry a disproportionate share of
   failures into nightly builds, increasing on-call burden and cross-team friction.

3. **Reporting compatibility**: If notebooks test results are not in the expected format
   (JUnit XML with standard tags), the team will be invisible in ReportPortal dashboards
   and the automated TFA/Jira/Slack flow will not work for notebooks failures.

4. **24h SLA pressure**: The CI Build Test Failure Response Framework requires 24h turnaround
   on automation issues. Flaky or poorly maintained tests become urgent operational issues
   under this SLA.
