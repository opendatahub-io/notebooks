# Workbench trust boundaries

Short answer to [FIND-015 / RHAIENG-5656](https://redhat.atlassian.net/browse/RHAIENG-5656):
we do **not** validate platform env vars inside workbench images before nginx startup.

## Who sets these env vars?

The ODH / OpenShift AI platform sets them when it creates the workbench pod — for example
`NB_PREFIX` and `NOTEBOOK_ARGS`. They are **not** taken from user HTTP requests.

Startup scripts (such as `codeserver/.../run-nginx.sh`) use `envsubst` to plug those values
into nginx config.

## Why we don't validate them in the container

If someone can set a malicious `NB_PREFIX`, they can already change the pod spec itself:
command, other env vars, volumes, and so on. Checking characters inside the image does not
stop that person — they already control the pod.

The security audit marked this **informational** and said **no immediate action required**.

## What we do instead

- Trust the platform (notebook controller, dashboard, cluster RBAC) to set env vars correctly.
- Fix real user-facing issues in nginx config (for example relative redirects — see
  [Gateway API migration guide](../gateway-api-migration-guide.md)).

Revisit this if env vars ever come from untrusted input without going through the controller.
