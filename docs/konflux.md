# Konflux

This file provides an overview and quick access links to the **Konflux** environments used for building and deploying components for the **Open Data Hub (ODH)** and **Red Hat Data Services (RHDS)** projects.

## ODH-io (Open Data Hub)

This section covers the Konflux setup for the upstream **Open Data Hub** community project.

project: `open-data-hub-tenant`

* **Konflux UI:** View and monitor applications, components, and pipelines running in the ODH tenant.
    * [konflux ui](https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/ns/open-data-hub-tenant/applications/opendatahub-release/components)
* **OpenShift Console:** Access the underlying **OpenShift** cluster for deeper insights, logs, and resource management.
    * [openshift console](https://console-openshift-console.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/k8s/cluster/projects/open-data-hub-tenant)
* **Configuration Repository (`odh-konflux-central`):** The primary source of truth for the Konflux configuration (GitOps).
    * [odh-konflux-central](https://github.com/opendatahub-io/odh-konflux-central):
        * [pipelines](https://github.com/opendatahub-io/odh-konflux-central/tree/main/pipelines/notebooks): Definitions of the **Tekton** pipelines used for building and testing components (e.g., notebook images).
        * [gitops](https://github.com/opendatahub-io/odh-konflux-central/tree/main/gitops): Configuration for deployed components and End-to-End (e2e) tests.
* **Release Data (`konflux-release-data`):** Release engineering configuration for the ODH tenant.
    * [konflux-release-data](https://gitlab.cee.redhat.com/releng/konflux-release-data)
        * [stone-prd-rh01/tenants/open-data-hub-tenant](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/tree/main/tenants-config/cluster/stone-prd-rh01/tenants/open-data-hub-tenant)

## RHDS (Red Hat Data Services / RHOAI)

This section covers the Konflux setup for the enterprise downstream **Red Hat Data Services** offering (often associated with **RHOAI - Red Hat OpenShift AI**).

project: `rhoai-tenant`

* **Konflux UI:** View and monitor applications and components specific to the RHDS tenant.
    * [konflux ui](https://konflux-ui.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/ns/rhoai-tenant/applications)
* **OpenShift Console:** Access the underlying **OpenShift** cluster for the RHDS tenant.
    * [openshift console](https://console-openshift-console.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/k8s/cluster/projects/rhoai-tenant)
* **Configuration Repository (`konflux-central`):** GitOps repository for RHDS Konflux definitions.
    * [konflux-central](https://github.com/red-hat-data-services/konflux-central):
        * [pipelineruns](https://github.com/red-hat-data-services/konflux-central/tree/main/pipelineruns/notebooks/.tekton): Specific **PipelineRun** definitions used for execution.
* **Release Data (`konflux-release-data`):** Release engineering configuration for the RHDS tenant.
    * [konflux-release-data](https://gitlab.cee.redhat.com/releng/konflux-release-data)
        * [stone-prod-p02/tenants/rhoai-tenant](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/tree/main/tenants-config/cluster/stone-prod-p02/tenants/rhoai-tenant)
        * [EnterpriseContractPolicy/registry-rhoai-prod.yaml](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/blob/main/config/stone-prod-p02.hjvn.p1/product/EnterpriseContractPolicy/registry-rhoai-prod.yaml)
        * [EnterpriseContractPolicy/fbc-rhoai-stage.yaml](https://gitlab.cee.redhat.com/releng/konflux-release-data/-/blob/main/config/stone-prod-p02.hjvn.p1/product/EnterpriseContractPolicy/fbc-rhoai-stage.yaml)

## ⚙️ Automations (Upstream/Downstream Flow)

These GitHub Actions workflows manage the automated synchronization of configurations between the upstream ODH community repositories and the downstream RHDS/RHOAI repositories, ensuring a smooth flow of changes and releases.

* **ODH-io -> RHDS Auto-Merge (Upstream to Downstream):** Automatically merges approved changes from ODH upstream configurations into the RHDS central configuration repository.
    * [ODH-io -> RHDS auto-merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/upstream-auto-merge.yaml)
* **RHDS/main -> RHOAI-* Auto-Merge (Release Propagation):** Manages the promotion of changes from the main RHDS branch to specific release branches (e.g., `rhoai-vX.Y`), facilitating new product releases.
    * [RHDS/main -> rhoai-* auto-merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/main-release-auto-merge.yaml)
