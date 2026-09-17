# check-payload

Pre-built container image for [openshift/check-payload](https://github.com/openshift/check-payload), the FIPS compliance scanner used in CI.

## Why build our own image?

**Compiling from source on every CI run is costly.** The Go module tree is large (~535 lines of go.sum), compilation takes time, and caching `GOCACHE`/`GOMODCACHE` across runners is fiddly. Worse, the transitive dependencies trigger CVE findings against *this* repo, not check-payload upstream.

**Existing pre-built images don't work for us:**

- **`registry.ci.openshift.org/ci/check-payload:latest`**: The only tag OpenShift CI publishes (no semver tags, no commit SHA tags). Requires Red Hat SSO authentication — not available to the public opendatahub-io GitHub Actions runners.
- **`quay.io/konflux-ci/konflux-test:latest`**: Bundles check-payload alongside many other Konflux tools in a full UBI9 image. 1.3 GB compressed — too large to pull on every notebook build job.

This image is ~50 MB compressed (`ubi9-minimal` base for `rpm` + static binary).

## Version management

The version is pinned as `CHECK_PAYLOAD_VERSION: "0.3.17"` in the workflows and passed to the Dockerfile as a build arg. The effective scan config is composed at runtime by `make check-payload-config`: it concatenates the upstream `config.toml` for that version with `.overlay.toml`. To bump, update the version in both workflows.

The upstream config is not inherited when `--config` is used, so the overlay target always fetches and concatenates the pinned upstream file before adding repository-specific rules.

Releases: https://github.com/openshift/check-payload/releases
