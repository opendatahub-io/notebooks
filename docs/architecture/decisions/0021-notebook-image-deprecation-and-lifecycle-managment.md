# Architecture Decision Record (ADR): Notebook Image Deprecation & Lifecycle Management

**Status:** Accepted
**Date:** November 11, 2026
**Deciders / Stakeholders:** Engineering & Product Architecture
**Context / Reference Tickets:**

* Feature / Epic: `RHAIRFE-3459` (Timeline & Milestones)
* Strategy References: `RHAISTRAT-2841` (Part 1 - 3.6), `RHAISTRAT-2897` (Part 2)

-----

## 1 Context and Problem Statement

The notebook workbench images and runtime ecosystem expanded significantly, leading to increased maintenance overhead, elevated build pipeline load, and wider Common Vulnerabilities and Exposures (CVE) support exposure. By release **3.6**, the environment encompasses **20 active build pipelines**, requiring substantial compute, CI maintenance, and ongoing patching effort.

To streamline the notebook catalog, reduce security exposure, and optimize build resources, we require a standardized, phased deprecation lifecycle policy for workbench images across upcoming releases (**3.6**, **3.7**, **3.8**, and **3.9**).

-----

## 2 Decision Drivers

* **CVE & Security Surface Reduction:** Drastically decrease CVE scanning, triaging, and patching overhead across legacy image variants.
* **CI/CD Resource Optimization:** Reduce Tekton build pipeline execution times and codebase maintenance.
* **User Experience & Predictable Grace Periods:** Provide users with transparent notices before images become unavailable, preventing unexpected workflow disruption.
* **Streamlined Catalog:** Replace legacy multi-flavor stacks with standard, maintained foundational runtimes (e.g., Python 3.12 stacks, Jupyter Universal CPU/CUDA, CodeServer CPU).

-----

## 3 Deprecation Lifecycle Model

A multi-stage deprecation process is adopted across consecutive releases:

1. **Stage 1 – Deprecation Announcement (**`Version N`**):**
   * Apply a visible `"Deprecated"` label in the UI / workbench selector.
     * Full operational support, security fixes, and build maintenance remain active.
2. **Stage 2 – UI Hiding & Pipeline Offboarding (**`Version N+1`**):**
   * Stop generating new versioned `latest` tags for the image.
     * Hide image from the default dashboard UI creation dropdowns (prevent new workbench creation while preserving existing ones).
     * Offboard build jobs from Tekton CI pipelines.
     * Clean up source codebase and associated build automation.
3. **Stage 3 – Sunset / Outdated / Deletion (**`Version N+2` **& beyond):**
   * Mark manifests with the red `"Outdated"` label or execute permanent manifest deletion from cluster registries.

-----

## 4 Release Milestones & Rollout Plan

```
Release Timeline & Milestone Matrix:
+-------------------------------------------------------------------------------------------------+

| Release | Wave 1 Images             | Wave 2 Images             | Introduced New Images         |
+---------+---------------------------+---------------------------+-------------------------------+
| 3.6     | • Apply "Deprecated" label|                           | • Jupyter CPU                 |
|         | • Maintain support        |                           | • CodeServer CPU              |
+---------+---------------------------+---------------------------+-------------------------------+
| 3.7     | • No new 3.7 latest tag   | • Apply "Deprecated" label| • Jupyter CUDA                |
| (17 Feb)| • Hide from dashboard UI  | • Maintain support in 3.7 |                               |
|         | • Tekton offboarding      |   (RHAIENG-7769)          |                               |
|         | • Clean up codebase       |                           |                               |
|         |   (RHAIENG-7755)          |                           |                               |
+---------+---------------------------+---------------------------+-------------------------------+
| 3.8     | • Delete manifests OR     | • No new 3.8 latest tag   |                               |
| (26 May)|   apply "Outdated" label  | • Hide from dashboard UI  |                               |
|         |                           | • Tekton offboarding      |                               |
|         |                           | • Clean up codebase       |                               |
|         |                           |   (RHAIENG-7981)          |                               |
+---------+---------------------------+---------------------------+-------------------------------+
| 3.9     | • Final manifest deletion | • Delete manifests OR     | Baseline maintained           |
| (TBD)   |   or Outdated state       |   apply "Outdated" label  |                               |
+-------------------------------------------------------------------------------------------------+

```

### Milestone Details

### Release 3.6 (Baseline & Wave 1 Deprecation)

* **Wave 1 Action:** Apply the `"Deprecated"` label to Wave 1 legacy images while maintaining full runtime support.
* **New Introductions:** Introduce modernized runtimes:
  * `Jupyter CPU`
  * `CodeServer CPU`
* **Pipeline Impact:** Pipeline count transitions from `18 + 2 → 20 pipelines` (initial +111% CVE support baseline).

### Release 3.7 (17 Feb GA Release)

* **Wave 1 Action (RHAIENG-7755):**
  * Cease new `3.7 latest` tag publishing.
  * Hide Wave 1 images from the Dashboard workbench selection UI.
  * Offboard Tekton CI pipelines and clean up source repositories.
* **Wave 2 Action (RHAIENG-7769):**
  * Apply `"Deprecated"` label to Wave 2 images.
  * Maintain runtime support for 3.7.
* **New Introductions:**
  * `Jupyter CUDA`
* **Pipeline Impact:** `20 - 5 + 1 → 16 pipelines` (**-20% CVE support exposure**).

### Release 3.8 (26 May GA Release)

* **Wave 1 Action:** Decision point: either complete manifest deletion or assign the persistent red `"Outdated"` tag.
* **Wave 2 Action (RHAIENG-7981):**
  * Cease new `3.8 latest` tag publishing.
  * Hide Wave 2 images from the dashboard UI.
  * Offboard Tekton pipelines and clean up codebase.
* **Pipeline Impact:** `16 - 13 → 3 pipelines` (**-81% CVE support exposure**).

### Release 3.9 (TBD)

* **Wave 2 Action:** Finalize manifest deletion or mark as `"Outdated"`.
* **Steady State:** `3 → 3 pipelines` (**0% delta**, fully consolidated core runtime catalog).

-----

## 5 Metrics & Consequences

### Expected Outcomes

| Milestone | Active Pipelines | Pipeline Delta                            | CVE Support Footprint Delta               |
| :-------- | :--------------- | :---------------------------------------- | :---------------------------------------- |
| **3.6**   | 20               | 2 (Introduced Jupyter & CodeServer CPU)   | Baseline (+111% support overhead)         |
| **3.7**   | 16               | 5 (Wave 1 offboarding) + 1 (Jupyter CUDA) | **-20%** CVE support footprint            |
| **3.8**   | 3                | 13 (Wave 2 offboarding)                   | **-81%** cumulative CVE support footprint |
| **3.9**   | 3                | 0 (Consolidated baseline)                 | Stable long-term maintenance state        |

### Positive Consequences

* **Substantial Maintenance Reduction:** Build pipeline surface drops by **85%** (from 20 pipelines down to 3 pipelines by 3.8).
* **Focused Security Surface:** CVE triage time is concentrated exclusively on standard, actively supported base images.
* **Clear User Path:** Users receive at least one full release cycle of deprecation notice before an image is hidden or sunset.

### Operational Risks & Mitigations

* **Impacted User Notebooks:** Existing pods running deprecated tags will not be forcibly killed upon UI hiding; only creation of *new* workbenches from the UI will be restricted.
* **Documentation & Migration Guides:** Clear migration paths from legacy images (e.g., legacy multi-framework images) to the new Python 3.12, CUDA, and CPU core images must accompany releases 3.7 and 3.8.
