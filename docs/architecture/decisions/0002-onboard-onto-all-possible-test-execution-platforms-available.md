# 2. Onboard onto all possible test execution platforms available

Date: 2025-10-29

## Status

Accepted

## Context

We as the Notebooks team need to be responsible for the test execution on our code.
To do that, we need to explore options available and decide which ones to use.

## Decision

We will onboard and create some quick-start style test on all platforms available to us.
This will provide us with sufficient knowledge to talk to Red Hat DevTestOps team on equal footing about what we actually need.

### Execution platforms to consider for onboarding

* OpenShift CI (already onboarded)
* GitHub Actions (already onboarded)
* Konflux [E2E test execution](https://developers.redhat.com/articles/2024/10/28/ephemeral-openshift-clusters-konflux-ci-using-cluster-service-operator)
* Travis CI Partner Queue
* Packit.dev
* Testing-Farm.io nested virtualization
* https://github.com/jiridanek/rhoai-in-kind
* Hydra trigger such as /test-e2e that will run something on Red Hat internal CI
* Machine under @jiridanek's table in Brno
* Virtual machines under our management on ITUP.scale platform in Red Hat

## Consequences

This is related to [E2E Testing Platform Evaluation - Periodic Review #1389](https://github.com/opendatahub-io/notebooks/issues/1389).

We'll need to maintain the test execution platforms we choose to use.
We'll need to eventually offboard from the platforms we decide not to use, to avoid confusion.
