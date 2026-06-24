## Available runners

List for
[public repositories](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#standard-github-hosted-runners-for-public-repositories)
and for
[private repositories](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#standard-github-hosted-runners-for--private-repositories).

- **Linux**: `ubuntu-26.04`, `ubuntu-26.04-arm`

We have [IBM PowerPC and Z runners](https://community.ibm.com/community/user/blogs/elizabeth-k-joseph1/2025/05/19/expanding-open-source-access-hosted-github-actions) available through

* https://github.com/IBM/actionspz/issues/63

- **Linux**: `ubuntu-24.04-ppc64le`, `ubuntu-24.04-s390x`

## Podman on CI

Notebook builds and RPM lock renewal use [`.github/actions/install-podman-action`](actions/install-podman-action/action.yml) on `ubuntu-26.04` runners.
It configures the **system Podman** package shipped on the runner image (5.7+), starts the rootful API socket, and sets `PODMAN_SOCK` / `CONTAINER_HOST`.
Linuxbrew is no longer used.

`ci/cached-builds/containers.conf` sets explicit `dns_servers` because GHA runners use
`systemd-resolved` (`127.0.0.53`), which is unreachable from container network namespaces
and breaks hermetic prefetch (`cdn.redhat.com`). See [podman #17075](https://github.com/containers/podman/issues/17075)
and pasta/systemd-resolved notes in [podman networking](https://sanj.dev/post/podman-pasta-vs-slirp4netns-networking/).

The install action also sets `iptables -P FORWARD ACCEPT` and `net.ipv4.ip_forward=1`
because Docker on GHA runners sets `FORWARD DROP`, which breaks rootful netavark egress
([podman #24486](https://github.com/containers/podman/issues/24486),
[runner-images #13422](https://github.com/actions/runner-images/issues/13422)).

`test-install-podman` validates container IP and DNS reachability (TCP `nc`, HTTP `wget`, `dig` UDP/TCP) after configure.

We have considered investigating custom runners, either just plain containers/VMs, or something fronting an OpenShift cluster, in

* https://github.com/opendatahub-io/notebooks/issues/1389
* https://github.com/opendatahub-io/notebooks/pull/2627
