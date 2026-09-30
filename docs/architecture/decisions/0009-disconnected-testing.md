# 9. Disconnected (air-gapped) application testing

Date: 2026-09-27

## Status

Proposed — investigation in progress; no topology or implementation selected.

## Context

Workbench images need to behave correctly when outbound connections to the public Internet are unavailable.
We want to exercise this locally and in CI while retaining access from the host's
browser and test runner to the workbench, including its interactive features.
The setup should work on Linux and on developer laptops running macOS with Podman
Machine.

For these tests, **disconnected** means that the application under test cannot
initiate connections to the internet. Host-initiated application connections and
their replies must work. Access to explicitly provided internal services (in the same OpenShift cluster) may also
be necessary. This simulates an aspect of an air-gapped cluster or Kubernetes
deny-egress NetworkPolicy; it does not establish that the whole laptop, Podman VM,
or test deployment is air-gapped, or reproduce every NetworkPolicy semantic.

Images and supporting tools can be downloaded before the isolated runtime phase.
The host and any bastion may retain internet access. Elevated privileges in a
bastion are acceptable for this test: the isolation requirement applies to the
application container. The application must not gain an unrestricted egress path
through the bastion.

Quay.io images are preferred to avoid depending on Docker Hub pull quotas. Image
availability, size, architecture support, and maintenance are considerations, but
do not determine the network topology by themselves.

## Decision

Deferred. This ADR records candidate topologies, exploratory results, and the
validation needed to choose an approach. It does not mandate a particular
bastion, firewall, image, or change to the test framework.

## Investigation results

The macOS experiments used Podman 6.1.2, an AppleHV Podman Machine with user-mode
networking, rootful containers, and Netavark bridge networking. These observations
describe that environment, not a compatibility guarantee for other versions,
providers, rootless configurations, or Linux hosts.

| Experiment | Observation |
| --- | --- |
| Publish a container port on the default regular `podman` bridge | Host localhost access worked. |
| Publish a port for an application attached only to an `--internal` bridge | Host access failed. |
| Use `--network=none` with published ports | Port mappings were discarded. |
| Publish a port on a regular custom bridge | Host access timed out, including after experimental firewall rules were removed. |
| Connect from macOS directly to an internal container IP | Timed out; the VM itself could reach the application. |
| Connect from macOS to the VM IP and a VM listener bound to all interfaces | Timed out in this setup. |
| SSH local forwarding through Podman Machine to the internal application IP | Host access worked. |
| Dual-network bastion running a Python HTTP relay | Host received the application response; application internet TCP connection failed with `Network is unreachable`. |
| Dual-network bastion using nftables DNAT and masquerade | Host received the application response without a userspace network listener in the bastion; application internet TCP connection failed with `Network is unreachable`. |
| Per-container nftables output filtering on a regular network | Host HTTP returned 200; outbound TCP was dropped and the drop counter increased. |
| VM-level firewall filtering on the default bridge | Host HTTP returned 200 and outbound TCP timed out, but rule counters stayed zero. The proposed filtering mechanism was not conclusively verified. |

These were exploratory checks, not an automated compatibility suite. In
particular, success on the default bridge must not be generalized to custom
bridges. No specific upstream bug was established as the cause of the internal
network publishing failure.

### macOS networking boundary

On macOS, containers and their bridges live inside a Linux VM. Published ports
need a working path from macOS into the VM and then to the container. Discovering
the VM or container IP does not establish that macOS can route to it. Using the
VM IP instead of `127.0.0.1` did not solve access in the tested configuration.

Two paths worked: run a bastion container attached to the default regular bridge
and publish one of its ports to macOS, or open an SSH tunnel through Podman
Machine's host-accessible SSH endpoint. The client can use a localhost endpoint
with either path.

The repository already implements the latter pattern in
[`open_ssh_tunnel`](../../../tests/containers/podman_machine_utils.py). It obtains
the SSH identity, port, and username from `podman machine inspect` and accepts a
remote destination address. The
[`test_ipv6_only` test](../../../tests/containers/workbenches/workbench_image_test.py)
matches the machine to the active API socket and tunnels to a container IPv6
address on macOS; on rootful Linux it connects directly to that address. That
test uses an IPv6-only network, **not** an internal network. Its linked Podman
issues concern IPv6 publishing and are not evidence of an internal-network bug.

## Candidate topologies

### 1. Internal application network with direct port publishing

```text
Host localhost:published-port -> Podman port publishing -> app on internal bridge
```

An application attached only to `podman network create --internal ...` has no
ordinary route to the internet. Ideally, `-p 127.0.0.1:HOST_PORT:APP_PORT` would
provide ingress with no additional component. However, that combination failed
in the tested macOS environment. It remains a candidate only if the required
platform matrix demonstrates reliable publishing or a suitable fix is found.

`--network=none` is a stronger disconnection primitive, but ordinary publishing
did not supply ingress in the experiment. It is not a complete solution for a
browser-accessible workbench by itself.

### 2. Internal application network with host/VM access

```text
macOS localhost:local-port -> SSH into Podman Machine -> app internal-IP:port
Linux host                -> app internal-IP:port (where routing permits)
```

The application remains on an internal bridge, and the host reaches it through
an explicit access path. SSH forwarding worked on macOS and could reuse the
existing helper. Machine SSH connection details and application addresses must
be discovered at runtime; they are not stable configuration constants.

This avoids a bastion image and application firewall changes. It introduces an
SSH process to manage on macOS, platform-specific access handling, readiness and
cleanup requirements, and possible tunnel recreation after address changes.
Direct Linux access depends on the container networking mode and must be tested;
the existing rootful IPv6 test does not establish all Linux configurations.

### 3. Internal application network with a dual-network bastion

```text
Host localhost:published-port
              |
       Podman port publishing
              |
     regular bridge network
              |
   +---------------------------+
   | Bastion container         |
   |                           |
   | regular-network interface |
   |            |              |
   |     relay / nftables      |
   |            |              |
   | internal interface        |
   +---------------------------+
              |
     --internal bridge network
              |
     app on internal bridge only
```

The bastion is a container attached to both networks. Podman publishes one of
that container's ports on the host.
The application attaches **only** to the internal network. Both variants below
worked with the default regular `podman` bridge in the macOS experiment.

The bastion exposes a fixed application destination, not an unrestricted forward
proxy or application egress gateway. Its own internet access is acceptable. Both
variants add container lifecycle, service discovery, and readiness coordination.

#### Userspace forwarding

A relay or reverse proxy accepts host traffic and opens a connection to the
application on the internal bridge. A Python HTTP relay verified this topology;
the candidate packaged implementations below were not tested end to end.

- **Caddy:** convenient HTTP reverse proxy; standard `caddy reverse-proxy` does
  not provide arbitrary TCP forwarding. Additional modules would need evaluation
  if protocol-independent forwarding is required.
- **HAProxy:** TCP or HTTP forwarding, with configurable timeouts and checks.
- **NGINX:** HTTP forwarding, or TCP forwarding if the image includes the needed
  stream module and configuration.
- **socat:** a simple TCP relay that passes protocol bytes without interpreting
  HTTP or WebSocket traffic.

HTTP-aware forwarding needs validation for redirects, headers, WebSockets, and
long-lived workbench sessions. TCP forwarding reduces HTTP-specific configuration
but still requires appropriate connection lifecycle and timeout behavior.

#### Kernel forwarding inside the bastion

The bastion can install nftables rules in **its own network namespace**, enable
IPv4 forwarding, and then keep that namespace alive without a userspace data
relay. The experiment used `--user 0 --cap-add=NET_ADMIN` and
`--sysctl net.ipv4.ip_forward=1`. A privileged bastion is also acceptable within
this test's scope; it is not required by the demonstrated rules.

`--network=host` is not needed for this topology: it changes the bastion's network
namespace and publishing model (on macOS, the host here is the VM). It does not
by itself remove the isolation of a separate application container.

The verified IPv4/TCP rule structure was:

```nft
table ip bastion {
  chain prerouting {
    type nat hook prerouting priority dstnat; policy accept;
    iifname "eth0" tcp dport 8080 dnat to 10.93.0.2:8000
  }
  chain forward {
    type filter hook forward priority filter; policy drop;
    ct state established,related accept
    iifname "eth0" oifname "eth1" ip daddr 10.93.0.2 tcp dport 8000 accept
  }
  chain postrouting {
    type nat hook postrouting priority srcnat; policy accept;
    oifname "eth1" ip daddr 10.93.0.2 tcp dport 8000 masquerade
  }
}
```

Here `eth0` was the regular interface and `eth1` the internal interface. These
names, addresses, and ports are experiment values, not portable defaults.
Masquerading makes replies return through the bastion despite the application's
lack of a default route; the application sees the bastion's internal address as
the peer. The forward chain allows the selected inbound service and established
replies without opening general forwarding from the internal network.

The experiment explicitly assigned the application the network alias
`codex-nft-app.dns.podman`. Name resolution in the bastion returned `10.93.0.2`,
which was then used in the rules. The suffix was not assumed to exist
automatically. nftables stores numeric destinations; a future implementation
would need startup resolution and a strategy for address changes. Automatic DNS
refresh was not tested. Interface discovery, IPv6, UDP, multiple ports, and
rootless operation also remain unverified.

### 4. Regular network with application or network egress filtering

```text
Host -> ordinary published port -> app on regular bridge
                                   |
                            egress firewall -> internet blocked
```

Per-container nftables output filtering preserved host access and demonstrably
dropped outbound TCP in one prototype. It requires firewall setup in the
application network namespace and rules that retain replies to host-initiated
connections. This may require extra tools or capabilities around the application
and must cover every enabled address family and egress path.

Alternatively, rules in the Linux host or Podman VM could match a dedicated
network's interface/subnet, leaving the application image untouched. A Podman
network is not itself a process namespace in which to run nftables; such rules
would be managed in the namespace routing that network's traffic. This introduces
shared firewall state, interactions with Podman's generated rules, and cleanup
and concurrency concerns. The VM-level experiment's zero counters leave its
effectiveness unresolved. Custom bridge publishing also needs separate macOS
validation.

### 5. Kubernetes with an actual deny-egress NetworkPolicy

A cluster-based test could validate the intended deployment policy using a CNI
that enforces NetworkPolicy, with ingress through the usual cluster access path.
It offers deployment fidelity but requires a cluster and more setup than a local
Podman test. This option was not exercised in the investigation and may complement
rather than replace developer-laptop tests.

## Bastion image candidates

The following Quay.io runtime images were pulled and inspected on Linux amd64.
Sizes are **unpacked image sizes**, not compressed download sizes, from the
September 2026 investigation. Mutable `latest` tags and other architectures may
differ. No image is selected by this ADR.

| Image inspected | Reported version | Size (decimal MB / MiB) |
| --- | --- | --- |
| `quay.io/hummingbird/caddy:latest` | 2.11.4 | 81.6 / 77.8 |
| `quay.io/hummingbird/nginx:latest` | 1.30.5 | 52.8 / 50.3 |
| `quay.io/hummingbird/haproxy:latest` | 3.0.27 | 52.2 / 49.8 |
| `quay.io/platform9/socat:latest` | 1.8.0.3 | 16.0 / 15.3 |

Hummingbird distributes these images separately from the upstream projects;
these are not claims of upstream official image status. **Caddy is available on
Quay.io through Hummingbird**, correcting the earlier research assumption that
using Caddy would require Docker Hub. The Hummingbird versions came from tag
metadata; `socat -V` was executed successfully. Forwarding configurations and
native arm64 availability still need validation.

The inspected `quay.io/iovisor/bpftrace:latest`,
`quay.io/openshift/origin-network-tools:latest`,
`quay.io/centos/centos:stream9`, and `quay.io/fedora/fedora:latest` did not contain
`nft`. The nftables prototype installed the package into an existing workbench
image; a prepared dedicated image remains an option. Runtime package installation
would be moved into preparation for a repeatable disconnected test.

No usable `ghcr.io/quickwit-oss/pingora-proxy:latest` image or its proposed YAML
configuration was verified. Pingora is a framework, so that earlier suggested
command is not an established alternative to a working packaged bastion.

## Evaluation criteria and remaining work

Before accepting a topology, an automated experiment should establish:

1. **Usable ingress:** host tests and a browser can reach the workbench, including
   authenticated requests, redirects, WebSockets, and long-lived sessions.
2. **Observable egress denial:** a known-reachable external endpoint works in a
   connected baseline and fails from the isolated application. Check direct IP
   connections separately from hostname resolution so DNS failure alone cannot
   masquerade as network isolation. For firewall options, verify the intended
   rule path using counters or equivalent traffic evidence.
3. **Defined isolation scope:** decide whether internal peers, DNS, host/VM
   services, IPv6, and UDP are allowed or denied; prevent an unintended path to
   the internet through any of them. An internal bridge may still expose local
   services, so absence of an internet route is not a complete deny-all policy.
4. **Platform coverage:** Linux CI and macOS developer machines, relevant Podman
   versions/providers, rootful/rootless modes, and amd64/arm64 images. Existing
   results do not cover this matrix.
5. **Repeatable lifecycle:** isolated resource names, parallel test execution,
   readiness, startup without external downloads, application restarts/address
   changes, and cleanup after failure. Firewall or tunnel setup must complete
   before exercising the disconnected application behavior.

Open design questions include whether HTTP forwarding is enough or TCP passthrough
is needed; whether reusing SSH helpers is preferable to managing a bastion; and
whether kernel forwarding justifies its rule, image, and discovery management
compared with a userspace relay. The eventual decision should record which
platforms and traffic types are supported and which observations justify it.

## Consequences

No test behavior changes as a result of this proposed ADR. The investigation
provides several feasible access paths, with different maintenance costs, and
identifies the platform and isolation checks needed before implementation.

## References

- [Podman network create](https://docs.podman.io/en/latest/markdown/podman-network-create.1.html)
- [Podman run](https://docs.podman.io/en/latest/markdown/podman-run.1.html)
- [Podman machine inspect](https://docs.podman.io/en/latest/markdown/podman-machine-inspect.1.html)
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Hummingbird Caddy](https://quay.io/repository/hummingbird/caddy)
- [Hummingbird NGINX](https://quay.io/repository/hummingbird/nginx)
- [Hummingbird HAProxy](https://quay.io/repository/hummingbird/haproxy)
- [Platform9 socat](https://quay.io/repository/platform9/socat)
