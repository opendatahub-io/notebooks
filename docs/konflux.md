# Konflux

## ODH-io

project: `open-data-hub-tenant`

* [konflux ui](https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/ns/open-data-hub-tenant/applications/opendatahub-release/components)
* [openshift console](https://console-openshift-console.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/k8s/cluster/projects/open-data-hub-tenant)
* [configs](https://github.com/opendatahub-io/odh-konflux-central):
  [pipelines](https://github.com/opendatahub-io/odh-konflux-central/tree/main/pipelines/notebooks),
  [gitops](https://github.com/opendatahub-io/odh-konflux-central/tree/main/gitops) (components, e2e tests)

## RHDS

project: `rhoai-tenant`

* [konflux ui](https://konflux-ui.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/ns/rhoai-tenant/applications)
* [openshift console](https://console-openshift-console.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/k8s/cluster/projects/rhoai-tenant)
* [configs](https://github.com/red-hat-data-services/konflux-central):
  [pipelineruns](https://github.com/red-hat-data-services/konflux-central/tree/main/pipelineruns/notebooks/.tekton)

## Automations

* [ODH-io -> RHDS auto-merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/upstream-auto-merge.yaml)
* [RHDS/main -> rhoai-* auto-merge](https://github.com/red-hat-data-services/rhods-devops-infra/actions/workflows/main-release-auto-merge.yaml)
