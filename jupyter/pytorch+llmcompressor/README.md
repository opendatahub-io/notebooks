# PyTorch + LLM Compressor workbench

CUDA-enabled Jupyter workbench for model compression with [llmcompressor](https://github.com/vllm-project/llm-compressor). The matching Elyra runtime image lives under `runtimes/pytorch+llmcompressor/`.

## Dependency alignment (RHOAI 2.25)

For RHOAI 2.25, Python package versions for the llmcompressor stack follow **RHAIIS 3.2.2** `model-opt` on branch `3.2.2` in the RHAIIS pipeline repository:

| RHAIIS file | GitLab |
|-------------|--------|
| Top-level pin (`llmcompressor==0.7.1.3`) | [requirements.txt](https://gitlab.com/redhat/rhel-ai/rhaiis/pipeline/-/blob/3.2.2/collections/model-opt/cuda-ubi9/requirements.txt) |
| Ecosystem + CVE constraint pins | [constraints.txt](https://gitlab.com/redhat/rhel-ai/rhaiis/pipeline/-/blob/3.2.2/collections/model-opt/cuda-ubi9/constraints.txt) |
| Directory overview | [cuda-ubi9/](https://gitlab.com/redhat/rhel-ai/rhaiis/pipeline/-/tree/3.2.2/collections/model-opt/cuda-ubi9) |

Repository: [redhat/rhel-ai/rhaiis/pipeline](https://gitlab.com/redhat/rhel-ai/rhaiis/pipeline/-/tree/3.2.2)

Notebooks mirror those pins in `ubi9-python-3.12/pyproject.toml`:

- **Direct dependency:** `llmcompressor==0.7.1.3` (from RHAIIS `requirements.txt`)
- **`[tool.uv].constraint-dependencies`:** mirrors RHAIIS `constraints.txt` (exact pins and `>=` CVE floors)

RHAIIS does **not** use uv-style `override-dependencies`. Fromager applies a single `constraints.txt` at wheel-build time. In notebooks, `constraint-dependencies` is the equivalent.

**`[tool.uv].override-dependencies`** is kept minimal — only where notebooks-specific deps conflict with RHAIIS floors and constraints cannot replace a transitive upper bound:

| Override | Reason |
|----------|--------|
| `urllib3>=2.7.0` (jupyter only) | `odh-elyra` caps urllib3 below the RHAIIS floor ([RHAIENG-2458](https://redhat.atlassian.net/browse/RHAIENG-2458)) |
| `black>=26.3.1` (jupyter only) | Notebooks CVE fix; not in RHAIIS model-opt |
| `pyarrow>=23.0.1,<24.0.0` (both) | `feast~=0.54.1` caps `pyarrow<=17`; RHAIIS requires `>=23` |

All other RHAIIS pins (pillow, requests, aiohttp, filelock, python-dotenv, …) resolve via `constraint-dependencies` alone. Runtime additionally pins `requests` and `urllib3` as direct deps.

`compressed-tensors==0.11.0` is not pinned in RHAIIS files; it is pulled transitively by `llmcompressor 0.7.1.x`. Do not add a bare `compressed-tensors` override — that unpins the transitive dep and breaks the stack ([RHAIENG-6035](https://redhat.atlassian.net/browse/RHAIENG-6035)).

PyTorch (`torch==2.7.1`, `torchvision~=0.22.1`) comes from the CUDA base image / AIPCC alignment, not from the RHAIIS model-opt files (torch was removed from model-opt constraints in INFERENG-1841).

## Regenerating the lockfile

```bash
bash scripts/pylocks_generator.sh public-index jupyter/pytorch+llmcompressor/ubi9-python-3.12
bash scripts/pylocks_generator.sh public-index runtimes/pytorch+llmcompressor/ubi9-python-3.12
```

Keep jupyter and runtime `pyproject.toml` constraint blocks in sync when bumping RHAIIS alignment.
