# Fetching the Red Hat Container Image Index (Pyxis API)

This document describes how to query the Red Hat Ecosystem Catalog (catalog.redhat.com) for container image metadata using the Pyxis REST and GraphQL APIs. The catalog is the authoritative source for Red Hat and certified third-party container images.

## Pyxis API Overview

Pyxis exposes two API surfaces:

- **REST API**: `https://catalog.redhat.com/api/containers/v1`
- **GraphQL API**: `https://catalog.redhat.com/api/containers/graphql/` (POST, `Content-Type: application/json`)
- **Documentation**: https://catalog.redhat.com/api/containers/docs/
- **Filter language docs**: https://catalog.redhat.com/api/containers/docs/filtering-language.html
- Some endpoints require an [API key](https://catalog.redhat.com/api/containers/docs/api-key.html); the read-only queries below do not.

The catalog web UI itself uses the **GraphQL API** as its primary backend, supplemented by the Red Hat Hydra search API for faceted search. The REST API is equally functional for programmatic use and is simpler for scripting.

## Catalog Web UI

The web UI at `https://catalog.redhat.com/en/software/containers/` is built with **Next.js** using React Server Components (`_rsc` query parameters). While it does server-side render, fetching those pages with a simple HTTP client like `curl` returns only the shell HTML with navigation chrome and no useful container metadata. Always use the Pyxis REST or GraphQL API for programmatic access.

URL pattern for a specific repository page:

```text
https://catalog.redhat.com/en/software/containers/{namespace}/{repository}/{_id}
```

For example:

```text
https://catalog.redhat.com/en/software/containers/rhoai/odh-workbench-jupyter-pytorch-cuda-py311-rhel9/688d13bc3afbd5eb7202d00d
```

The `{_id}` at the end is the Pyxis repository `_id` field (a hex string).

## Useful REST API Endpoints

### List repositories (with filtering)

```text
GET /v1/repositories?filter=<RSQL>&page_size=<N>&page=<P>
```

### Get images for a repository

```text
GET /v1/repositories/registry/{registry}/repository/{repository}/images?page_size=<N>&page=<P>&sort_by=<field>&include=<fields>
```

### Get tag history

```text
GET /v1/tag-history/registry/{registry}/repository/{repository}/tag/{tag}
```

## GraphQL API

The catalog web UI uses the GraphQL endpoint at `https://catalog.redhat.com/api/containers/graphql/` (POST). This is the same data as the REST API but accessed through GraphQL queries.

Example query the UI makes for tag history:

```graphql
query GET_REPOSITORY_BY_ID_IMAGES_HISTORY($id: String!, $page: Int, $page_size: Int, $filter: ContainerImageFilter, $sort_by: [SortBy]) {
  get_repository_by_id(id: $id) {
    repository
    registry
    ...
  }
  find_container_images(page: $page, page_size: $page_size, filter: $filter, sort_by: $sort_by) {
    data {
      architecture
      repositories {
        tags { name }
        push_date
        repository
      }
    }
  }
}
```

With variables like:

```json
{
  "id": "688d13bc8bd4d1d30c5aba53",
  "page": 0,
  "page_size": 10,
  "filter": {
    "and": [{
      "repositories_elemMatch": {
        "and": [{
          "repository": { "eq": "rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9" }
        }]
      }
    }]
  },
  "sort_by": [
    { "field": "repositories.push_date", "order": "DESC" },
    { "field": "repositories.repository", "order": "ASC" }
  ]
}
```

The GraphQL API returns richer data in a single call (vulnerability info, RPM manifests, freshness grades, advisory links) compared to multiple REST calls. For simple scripting the REST API is easier; for complex queries the GraphQL API is more efficient.

## Hydra Search API

The catalog also queries the Red Hat Hydra search API for faceted search:

```
GET https://access.redhat.com/hydra/rest/search/kcs?redhat_client=ecosystem-catalog&fq=language:(en)&fq=-documentKind:Cve&fq=documentKind:"ContainerRepository"&q=id:{repository_id}&wt=json&facet=true&facet.field={!ex=architecture_tag}architecture
```

This provides architecture facets and other search metadata. It's mainly used by the UI for filtering; the Pyxis REST API is sufficient for most programmatic needs.

## Filter Language (RSQL)

The API uses an RSQL-based filter language. Key operators:

| Operator | Syntax | Example |
|----------|--------|---------|
| Equal | `==` | `repository=='rhoai/foo'` |
| Not equal | `!=` | `repository!='rhoai/bar'` |
| Regex | `=regex=` or `~=` | `repository=regex=rhoai/odh-workbench.*py312` |
| In | `=in=` | `architecture=in=(amd64,arm64)` |
| And | `;` or `and` | `field1==a;field2==b` |
| Or | `,` or `or` | `field1==a,field2==b` |

**Important**: URL-encode filter values when using special characters. Quoted strings are recommended for regex patterns.

## Practical Examples

### 1. Find all py312 workbench repositories

```bash
curl -s 'https://catalog.redhat.com/api/containers/v1/repositories?filter=repository=regex=rhoai/odh-workbench.*py312&page_size=50&page=0&include=data.repository,data._id,data.display_data.name' | python3 -m json.tool
```

This returns a JSON response like:

```json
{
  "data": [
    {
      "repository": "rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9",
      "_id": "688d13bb8bd4d1d30c5aba4e",
      "display_data": {
        "name": "RHOAI Workbench Jupyter Minimal CPU PY312"
      }
    }
  ]
}
```

### 2. Get the latest image tags for a specific repository

The `{registry}` in the Pyxis REST API path is `registry.access.redhat.com`. The `{repository}` is the full namespace/name (e.g. `rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9`).

> **Note**: The API uses `registry.access.redhat.com` in its URL paths, but the actual pull registry shown in the UI is `registry.redhat.io`. Both registries serve the same images; `registry.redhat.io` is the one to use in pull commands (see [Registries](#registries) below).

```bash
curl -s 'https://catalog.redhat.com/api/containers/v1/repositories/registry/registry.access.redhat.com/repository/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9/images?page_size=5&page=0&sort_by=last_update_date%5Bdesc%5D&include=data.repositories.tags.name,data.architecture,data.last_update_date' | python3 -m json.tool
```

Response:

```json
{
  "data": [
    {
      "repositories": [
        {
          "tags": [
            {"name": "v3.2"},
            {"name": "v3.2.0"},
            {"name": "v3.2.0-1768253544"}
          ]
        }
      ],
      "architecture": "amd64",
      "last_update_date": "2026-02-12T23:09:51.294000+00:00"
    }
  ]
}
```

### 3. Combine: list all repos, then fetch the latest tags for each

```bash
#!/usr/bin/env bash
# Fetch all py312 workbench repos and their latest tags

REGISTRY="registry.access.redhat.com"
API="https://catalog.redhat.com/api/containers/v1"

# Step 1: Get all matching repository names
repos=$(curl -s "${API}/repositories?filter=repository=regex=rhoai/odh-workbench.*py312&page_size=50&page=0&include=data.repository" \
  | python3 -c "import sys,json; [print(r['repository']) for r in json.load(sys.stdin)['data']]")

# Step 2: For each repo, get the latest image tags (amd64)
for repo in $repos; do
  echo "=== $repo ==="
  curl -s "${API}/repositories/registry/${REGISTRY}/repository/${repo}/images?page_size=1&page=0&sort_by=last_update_date%5Bdesc%5D&filter=architecture==amd64&include=data.repositories.tags.name,data.last_update_date" \
    | python3 -m json.tool
  echo
done
```

## Query Parameters Reference

| Parameter | Description | Example |
|-----------|-------------|---------|
| `filter` | RSQL filter expression | `filter=repository=regex=rhoai/.*py312` |
| `page_size` | Number of results per page (max 200) | `page_size=50` |
| `page` | Zero-based page index | `page=0` |
| `sort_by` | Sort field with optional `[asc]`/`[desc]` | `sort_by=last_update_date[desc]` |
| `include` | Comma-separated dot-paths to include (projection) | `include=data.repository,data._id` |

The `include` parameter is useful for reducing response size. Without it, the full repository or image object is returned, which can be very large.

## Registries

Red Hat container images are available through two registries that mirror the same content:

| Registry | Authentication | Usage |
|----------|---------------|-------|
| `registry.redhat.io` | Required (Red Hat account or service account token) | **Primary pull registry** -- use this in Dockerfiles, deployments, and pull commands |
| `registry.access.redhat.com` | Not required | Used in Pyxis API URL paths; also works for pulls but `registry.redhat.io` is preferred |

The catalog UI shows pull commands using `registry.redhat.io`:

```bash
podman pull registry.redhat.io/rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9:v3.2
```

Or by digest:

```bash
podman pull registry.redhat.io/rhoai/odh-workbench-jupyter-pytorch-cuda-py312-rhel9@sha256:<digest>
```

## Tag Naming Conventions

Red Hat workbench images typically carry three tags per build:

| Tag format | Example | Purpose |
|------------|---------|---------|
| Floating major.minor | `v3.2` | Points to the latest build in that release stream |
| Exact version | `v3.2.0` | Specific release version |
| Version + build ID | `v3.2.0-1768253544` | Fully pinned, includes the Konflux/Tekton build timestamp |

## Architecture Support

Not all images support all architectures:

| Image type | Architectures |
|------------|--------------|
| CPU images (minimal, datascience, trustyai) | amd64, arm64, ppc64le, s390x |
| CUDA images | amd64, arm64 |
| ROCm images | amd64 only |

## Catalog UI Page Structure

The container detail page in the web UI has these tabs:

| Tab | Content |
|-----|---------|
| **Overview** | Description, products using this container, health index, digest |
| **Security** | CVE information and linked Red Hat Security Advisories (RHSA) |
| **Technical information** | Technical specifications |
| **Packages** | List of installed RPM packages |
| **Containerfile** | The Dockerfile/Containerfile used to build the image |
| **Get this image** | Pull commands, registry auth instructions, service account setup |

The **Tag History** section shows all published tags with push dates, architectures, and digests. Repositories can be "multi-stream" (e.g. carrying both v2.x and v3.x release streams simultaneously, with content stream tags like `v2.16`, `v2.19`, `v2.8`).

Images also have a **freshness grade** (A through F) that degrades over time since the last rebuild, encouraging regular updates.

## Image Digest Types

Each per-architecture image entry in the API carries two digest fields:

| Field | Scope | Example |
|-------|-------|---------|
| `manifest_list_digest` | **Multi-arch** manifest (same value across all architectures) | `sha256:60de33dc00fa...` |
| `manifest_schema2_digest` | **Per-architecture** image digest (unique per arch) | `sha256:0c9fc3392f2d...` |

When pulling by digest, use `manifest_list_digest` for multi-arch references (the container runtime picks the right architecture automatically) or `manifest_schema2_digest` when pinning to a specific architecture.

To get the multi-arch digest from the API, query any architecture entry for the tag -- the `manifest_list_digest` is identical on all of them:

```bash
# No architecture filter needed -- just grab the first result and read manifest_list_digest
curl -s 'https://catalog.redhat.com/api/containers/v1/repositories/registry/registry.access.redhat.com/repository/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9/images?page_size=1&page=0&filter=repositories.tags.name==v3.2&include=data.repositories.manifest_list_digest,data.repositories.manifest_schema2_digest,data.architecture' | python3 -m json.tool
```

## Image Labels

The full image object contains parsed labels under `parsed_data.labels`. These can be fetched via `include=data.parsed_data.labels` in the REST API. Useful labels for RHOAI workbench images:

| Label | Example value | Purpose |
|-------|---------------|---------|
| `vcs-ref` | `fff85944723a67d4b1e9daa952a8e43d80b4cacb` | Git commit hash of the source |
| `git.commit` | `fff85944723a67d4b1e9daa952a8e43d80b4cacb` | Same as `vcs-ref` (duplicate label) |
| `version` | `v3.2.0` | Image version |
| `release` | `1768253544` | Build ID (Konflux timestamp) |
| `com.redhat.aiplatform.index_version` | `3.2` | RHOAI release stream |
| `com.redhat.aiplatform.repo_version` | `3.0` | Source repo branch version |
| `com.redhat.aiplatform.accelerator` | `cpu`, `cuda`, `rocm` | Accelerator type |
| `com.redhat.aiplatform.python` | `3.12` | Python version |
| `com.redhat.aiplatform.cuda_version` | `12.9.1` | CUDA version (CUDA images only) |
| `com.redhat.aiplatform.rocm_version` | `6.4.3` | ROCm version (ROCm images only) |
| `com.redhat.component` | `odh-workbench-jupyter-minimal-cpu-py312-rhel9` | Component name |
| `image_advisory_id` (on repository entry) | `RHSA-2026:1027` | Linked Red Hat Security Advisory |

### Verifying commit.env values via the API

The `vcs-ref` label provides the full 40-character git commit hash. The `commit.env` file uses the first 7 characters. This means you can verify commit.env values purely through the Pyxis API without needing `skopeo`:

```bash
# Get the vcs-ref label for a specific image
curl -s 'https://catalog.redhat.com/api/containers/v1/repositories/registry/registry.access.redhat.com/repository/rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9/images?page_size=1&page=0&filter=architecture==amd64;repositories.tags.name==v3.2&include=data.parsed_data.labels' \
  | python3 -c "
import sys, json
labels = json.load(sys.stdin)['data'][0]['parsed_data']['labels']
vcs_ref = next(l['value'] for l in labels if l['name'] == 'vcs-ref')
print(f'vcs-ref: {vcs_ref}')
print(f'commit.env value (7-char): {vcs_ref[:7]}')
"
```

### Not all images in a release share the same source commit

Within a single RHOAI version (e.g. v3.2), images may be built from different source commits. For v3.2.0, there are two distinct builds:

| Build ID (`release` label) | Source commit (`vcs-ref`) | Images |
|---------------------------|--------------------------|--------|
| `1768253544` | `fff8594...` | minimal-cpu, minimal-cuda, datascience-cpu, trustyai-cpu |
| `1767946734` | `0f8616e...` | minimal-rocm, pytorch-cuda, pytorch-rocm, tensorflow-cuda, tensorflow-rocm, codeserver, llmcompressor |

This happens because the images are built by separate Konflux pipelines that may pick up different commits from the source repo.

## Repository Name Mapping

The Red Hat catalog uses `rhel9` in repository names, while the upstream ODH/params.env convention uses `ubi9`. RStudio images use `c9s` (CentOS Stream 9) and are **not published to the Red Hat catalog** at all.

| Catalog repository | params.env variable name | Notes |
|-------------------|--------------------------|-------|
| `rhoai/odh-workbench-jupyter-minimal-cpu-py312-rhel9` | `odh-workbench-jupyter-minimal-cpu-py312-ubi9` | `rhel9` → `ubi9` |
| `rhoai/odh-workbench-codeserver-datascience-cpu-py312-rhel9` | `odh-workbench-codeserver-datascience-cpu-py312-ubi9` | `rhel9` → `ubi9` |
| *(not in catalog)* | `odh-workbench-rstudio-minimal-cpu-py312-c9s` | quay.io only |
| *(not in catalog)* | `odh-workbench-rstudio-minimal-cuda-py312-c9s` | quay.io only |

The `params.env` value format is `registry.redhat.io/rhoai/<catalog-repo-name>@sha256:<digest>` -- note the value still uses the `rhel9` catalog name, only the variable name on the left side uses `ubi9`.

## Scripting Tool

The script `manifests/tools/generate_envs.py` automates querying the catalog for all py312 workbench images at a given RHOAI version and generating `params.env` / `commit.env` output. Run it from the `manifests/` directory:

```bash
# Default: version v3.3, suffix 2025-2
cd manifests && ../uv run tools/generate_envs.py

# Specify a different RHOAI version tag
cd manifests && ../uv run tools/generate_envs.py --version-tag v3.2

# Specify both version and suffix
cd manifests && ../uv run tools/generate_envs.py --version-tag v3.3 --suffix 2025-2
```

Options:

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--version-tag` | `-v` | `v3.3` | RHOAI version tag to query (e.g. `v3.2`, `v3.3`) |
| `--suffix` | `-s` | `2025-2` | Suffix appended to variable names in the output |

The script handles the `rhel9` → `ubi9` variable name mapping automatically and reminds about the RStudio images that must be added manually from quay.io.

## Gotchas and Pitfalls

1. **The web UI is a Next.js app**: `curl` or simple HTTP fetches of `catalog.redhat.com/en/software/containers/...` return only navigation chrome with no container metadata. The actual data is loaded via React Server Components and GraphQL. Use the API for programmatic access.

2. **Filter syntax is RSQL, not SQL LIKE**: There is no `=like=` operator. Use `=regex=` for pattern matching. Wildcards like `*` work inside `==` comparisons but not as a general glob -- prefer `=regex=` with proper regex syntax.

3. **URL-encode `sort_by` brackets**: `sort_by=last_update_date[desc]` must be sent as `sort_by=last_update_date%5Bdesc%5D`, otherwise the brackets may be misinterpreted.

4. **Registry name in API paths vs pull commands**: The REST API `{registry}` path component must be `registry.access.redhat.com`. However, the pull registry shown in the UI (and recommended for use) is `registry.redhat.io`. They serve the same images but `registry.redhat.io` requires authentication.

5. **`/repositories/id/{id}` exists but `/repositories/id/{id}/images` does not**: To get images for a repo, you must use the `/repositories/registry/{registry}/repository/{repository}/images` form. The ID-based path only returns the repository metadata itself.

6. **Multiple release streams coexist and `last_update_date` ordering is unreliable for version comparison**: A single repository may contain images from multiple release streams (e.g. v2.24.x, v2.25.x, v3.0.x, and v3.2.x all in one repo). These are labeled as "multi-stream repositories" with content stream tags. Sorting by `last_update_date[desc]` does **not** give you the highest version -- the dates can be nearly identical (within seconds) due to bulk re-indexing. For example, the CodeServer py312 repo returns `v2.24.0` as the "most recently updated" image even though `v3.2.0` exists in the same repo. You must parse and compare tag version strings yourself to find the actual latest release.

7. **The catalog UI "Updated image available" banner can be misleading for multi-stream repos**: When viewing a specific image version (e.g. v3.2.0), the UI may show an "Updated image available" banner pointing to an older release stream (e.g. v2.25.2) if that stream has a more recent `last_update_date`. This appears to be a UI bug or limitation in how multi-stream repositories are handled -- the banner compares update timestamps rather than semantic versions. This is worth flagging to the team if it causes confusion.

8. **`include` uses dot-path notation**: Nested fields are accessed with dots, and the top-level must start with `data.` (e.g. `data.repositories.tags.name`).

9. **GraphQL filter syntax differs from REST RSQL**: The GraphQL API uses a structured JSON filter format with `eq`, `and`, `repositories_elemMatch`, etc. -- not the RSQL string syntax used by the REST API. See the [GraphQL API](#graphql-api) section for examples.

10. **`manifest_list_digest` vs `manifest_schema2_digest`**: Each image entry has both. `manifest_list_digest` is the multi-arch manifest (same on all arch entries for a tag). `manifest_schema2_digest` is the per-architecture digest. For multi-platform deployments, use `manifest_list_digest`. There is no top-level `docker_image_digest` field in the `include` projection -- it won't be returned even if requested; use the two fields above instead.

11. **RStudio images are not in the Red Hat catalog**: The `odh-workbench-rstudio-*-c9s` images use CentOS Stream 9 and are only published to `quay.io/opendatahub`. They must be handled separately from the catalog-based workflow.

12. **Filtering by tag name is more reliable than sorting by date**: To find images for a specific RHOAI version, filter with `repositories.tags.name==v3.2` rather than sorting by `last_update_date[desc]` and hoping the first result is the right version. This avoids the multi-stream ordering issues described in gotcha #6.
