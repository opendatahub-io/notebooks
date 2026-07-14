# Code-server workbench images

Hermetic **code-server** (VS Code in the browser) images for OpenShift AI / ODH
workbenches.

## Layout

```
codeserver/
├── Extensions.md              # User-facing VS Code extensions (.vsix) and update process
└── ubi9-python-3.12/          # Python 3.12 on UBI 9 (RHOAI 2.25)
    ├── Dockerfile.konflux.cpu   # Hermetic build (Konflux, GHA, local prefetch)
    ├── build-args/              # cpu.conf (GHA/local), konflux.cpu.conf (Konflux)
    ├── pyproject.toml           # Python datascience deps (source of truth)
    ├── pylock.toml              # CI lock (public PyPI; sync-python-lockfiles.sh)
    ├── requirements.cpu.txt     # Hermetic pip prefetch (Cachi2/Hermeto)
    ├── uv.lock.d/               # RH-wheel patched pylock for offline install
    ├── prefetch-input/          # RPM, npm, artifact locks + code-server submodule
    └── README.md                # Build, prefetch, and lockfile guide
```

## Quick start

| Task | Where to look |
| ---- | ------------- |
| Build locally | [ubi9-python-3.12/README.md](ubi9-python-3.12/README.md#building-locally) |
| Regenerate lockfiles | [ubi9-python-3.12/README.md](ubi9-python-3.12/README.md#regenerating-lockfiles) |
| Update VS Code extensions | [Extensions.md](Extensions.md) |
| Bump code-server / VS Code | [prefetch-input/patches/code-server-v4.112.0/README.md](ubi9-python-3.12/prefetch-input/patches/code-server-v4.112.0/README.md) |
| Lockfile generator details | [scripts/lockfile-generators/README.md](../scripts/lockfile-generators/README.md) |

## RHOAI 2.25 notes

- **Base image:** `registry.access.redhat.com/ubi9/python-312:latest` (public UBI until
  2.25 AIPCC CPU tag is available).
- **Hermetic prefetch variant:** `prefetch-input/rhds/` with public UBI + CentOS Stream
  repos — use `prefetch-all.sh --rhds` (no RHEL subscription required).
- **Python locks:** public PyPI for `pylock.toml` (CI), plus RH wheel overlay in
  `uv.lock.d/pylock.cpu.toml` for multi-arch hermetic builds.
- **GHA:** 16GB runner workarounds (`GHA_BUILD=true`, swap, reduced VS Code parallelism).
  See [patch scripts](ubi9-python-3.12/prefetch-input/patches/README.md).

Other notebook images (`jupyter/`, `runtimes/`) are **not** hermetic and do not use
`prefetch-input/` — only codeserver on this branch.
