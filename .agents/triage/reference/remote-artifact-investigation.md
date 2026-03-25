# Remote Artifact Investigation

When manifest-box SBOMs are large (5-8 MB each), release tarballs need inspection, or
repeated `curl`/Python probes are needed, use a remote host with good network access
instead of running everything locally.

## When to Use a Remote Host

- Manifest-box LFS downloads time out or are slow locally
- You need to inspect multiple release tarballs (e.g., sweeping code-server versions)
- Repeated SSH + Python probes are needed for batch SBOM checks across many images
- Local certificate chain issues block GitLab access (internal CA)

## SSH Pattern for Manifest-box SBOM Inspection

Upload a small Python probe script and run it on the remote host:

```bash
ssh root@<host> 'python3 - <<"PY"
import json, ssl, urllib.parse, urllib.request

ctx = ssl._create_unverified_context()
name = "<sbom_filename>.json"
path = "manifests/konflux/openshift-ai/" + name
encoded = urllib.parse.quote(path, safe="")
raw_url = f"https://gitlab.cee.redhat.com/api/v4/projects/product-security%2Fmanifest-box/repository/files/{encoded}/raw?ref=main"
pointer = urllib.request.urlopen(raw_url, context=ctx).read().decode().splitlines()
oid = pointer[1].split()[1].split(":", 1)[1]
size = int(pointer[2].split()[1])
payload = json.dumps({"operation":"download","transfers":["basic"],"objects":[{"oid":oid,"size":size}]}).encode()
req = urllib.request.Request(
    "https://gitlab.cee.redhat.com/product-security/manifest-box.git/info/lfs/objects/batch",
    data=payload,
    headers={"Accept":"application/vnd.git-lfs+json","Content-Type":"application/vnd.git-lfs+json"},
)
lfs = json.load(urllib.request.urlopen(req, context=ctx))
href = lfs["objects"][0]["actions"]["download"]["href"]
sbom = json.load(urllib.request.urlopen(href, context=ctx))
print(sbom.get("build_component"))
for c in sbom["build_manifest"]["manifest"]["components"]:
    if c.get("name") == "<package>":
        print(c.get("versionInfo"), c.get("sourceInfo"))
PY'
```

Replace `<sbom_filename>`, `<host>`, and `<package>` with actual values.

## SSH Pattern for Release Tarball Inspection

Inspect upstream release artifacts without downloading them locally:

```bash
ssh root@<host> 'url="https://github.com/<org>/<repo>/releases/download/<tag>/<tarball>"; \
curl -L -s "$url" | tar -xOzf - "<path_inside_tarball>" | \
python3 -c "import sys,json; d=json.load(sys.stdin); print(d[\"version\"])"'
```

## Tips

- Pipe `cat <<'PY' | ssh <host> python3 -` for longer scripts to avoid shell quoting issues
- For batch checks across many images, upload a helper script to `/tmp/` on the remote host
  first, then call it repeatedly with different arguments
- Always verify `build_component` after download to confirm the right product version
- If the remote host has `podman`, you can also pull and inspect container images directly
