## Available runners

List for
[public repositories](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#standard-github-hosted-runners-for-public-repositories)
and for
[private repositories](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#standard-github-hosted-runners-for--private-repositories).

- **Linux**: `ubuntu-latest`, `ubuntu-24.04`, `ubuntu-24.04-arm`

We have [IBM PowerPC and Z runners](https://community.ibm.com/community/user/blogs/elizabeth-k-joseph1/2025/05/19/expanding-open-source-access-hosted-github-actions) available through

* https://github.com/IBM/actionspz/issues/63

- **Linux**: `ubuntu-24.04-ppc64le`, `ubuntu-24.04-s390x`

We have considered investigating custom runners, either just plain containers/VMs, or something fronting an OpenShift cluster, in

* https://github.com/opendatahub-io/notebooks/issues/1389
* https://github.com/opendatahub-io/notebooks/pull/2627
