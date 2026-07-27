# 16. Property-based testing and contracts for pure helpers

Date: 2026-07-27

## Status

Accepted

## Context

The repository has ~3 kLOC of pure Python helper logic (URL/tag parsers, patch
excerpt truncation, SARIF sanitization, CI matrix generators) covered by
hand-written example-based pytest. These tests are effective for known cases but
cannot find edge cases in string splitting, line counting, or nested dict
traversal — areas where subtle semantics (e.g. `str.splitlines` treating `\r`
as a line break) cause real bugs.

We evaluated property-based testing (PBT) and contract verification tools to
strengthen coverage of these pure helpers without adding heavy infrastructure.

### Tools evaluated

| Tool | Verdict | Rationale |
|------|---------|-----------|
| **Hypothesis** | **Adopted** | Open source, Python 3.14 wheels, strategies + properties, integrates with existing pytest |
| **CrossHair** (SMT via Z3) | **Adopted as opt-in** | Finds hard-to-reach branches Hypothesis misses; ~37 MB z3 dep kept out of default CI |
| **HypoFuzz** | Rejected | Proprietary license (commercial use requires paid seats); needs Hypothesis corpus first |
| **Google Atheris** | Rejected | Targets native C extensions / memory corruption; wrong threat model for pure Python |
| **PythonFuzz** | Rejected | Byte-blob crash-oracle fuzzing; overlaps Hypothesis poorly for structured invariants |
| **icontract** (decorator contracts) | Rejected for now | Single-maintainer (Ossuary risk ~70), adds runtime dep; IDE autocomplete benefit not worth bus-factor risk |
| **deal** (decorator contracts + test gen) | Rejected for now | Single-maintainer (Ossuary risk ~73), 8 months dormant, Python 3.14 unconfirmed |
| **PEP 316 docstring contracts** | **Adopted** | Zero runtime deps; verified by `crosshair check`; no bus-factor exposure |

### Key findings during evaluation

1. **Hypothesis immediately found a real bug**: `capped_patch_excerpt(None, max_lines=0)` returned `None` instead of raising — the empty-patch path short-circuited before the `max_lines` guard. Fixed: validate `max_lines` first.

2. **CrossHair found two more**: `'\r'` inside patch content treated as a line break (from `str.splitlines`), and blank-line truncation producing fewer lines than expected. Fixed: production now splits on `\n` only via `_patch_lines()`.

3. **CrossHair had one spurious counterexample** on the `all('\n' not in line ...)` contract during development (claimed `_patch_lines('\n')` returned `['\n']`). A follow-up 20-run flakiness test (10 on `_patch_lines` alone, 10 on both functions) produced **0 failures** — the original hit was a one-off. The contract was kept out of the committed PEP 316 annotations because the simpler contracts already capture the useful guarantees, not because of confirmed flakiness.

4. **Neither icontract nor deal is discussed in internal Slack**; Hypothesis has organic traction across several teams.

## Decision

1. **Hypothesis** is a default dev dependency. Property tests live in `tests/unit/test_property_helpers.py` and run in the existing `make test` / `make test-unit` / `pytest-tests` CI job with `max_examples=100`.

2. **CrossHair** is an optional dependency group (`crosshair`). `make test-crosshair` runs existing `@given` tests under the `backend="crosshair"` Hypothesis profile. Not part of default CI.

3. **PEP 316 docstring contracts** (`pre:`/`post:`) annotate pure helpers for verification by `crosshair check --analysis_kind=PEP316`. Zero runtime cost.

4. **No decorator-contract library** (icontract/deal) until either (a) the repo has enough contracted functions to justify `deal.cases()`-style auto-test-gen, or (b) one of the libraries confirms Python 3.14 support and improves bus-factor.

5. **No separate GitHub Actions workflow** for PBT/CrossHair. Default Hypothesis examples are fast enough for PR gating; CrossHair is a local/exploratory tool.

## Usage

### Hypothesis (default — runs in CI)

```bash
# Run all property tests (included in make test / make test-unit)
uv run pytest tests/unit/test_property_helpers.py -q --no-cov

# Run with more examples locally for deeper exploration
uv run pytest tests/unit/test_property_helpers.py --hypothesis-seed=0 \
    -s --hypothesis-settings='max_examples=1000'

# Run a single property
uv run pytest tests/unit/test_property_helpers.py::test_capped_patch_excerpt_properties -q
```

### CrossHair as Hypothesis backend (opt-in — not CI)

```bash
# Install the optional crosshair group (pulls z3 ~37 MB)
uv sync --locked --group crosshair

# Run property tests under the SMT backend (~50 examples, slower but finds harder bugs)
make test-crosshair
# equivalent:
uv run pytest tests/unit/test_property_helpers.py \
    --hypothesis-profile=crosshair --no-cov
```

### CrossHair standalone contract verification (opt-in)

```bash
# Verify PEP 316 pre:/post: contracts in a module (no pytest needed)
uv sync --locked --group crosshair
uv run crosshair check ci/agentic-reviewer/src/odh_ci_agent/patch_excerpt.py \
    --analysis_kind=PEP316

# Verify a single function
uv run crosshair check \
    ci/agentic-reviewer/src/odh_ci_agent/patch_excerpt.capped_patch_excerpt \
    --analysis_kind=PEP316 --per_condition_timeout=20

# Verbose mode (shows SMT decisions on stderr)
uv run crosshair check ci/agentic-reviewer/src/odh_ci_agent/patch_excerpt.py \
    --analysis_kind=PEP316 --verbose
```

### Bootstrapping new property tests with Ghostwriter

Hypothesis ships a ghostwriter that inspects a function's name, types, and
docstring to generate a starter property test. No extra install needed:

```bash
# Generate a "fuzz" test (no-error-on-valid-input) for a function
uv run hypothesis write scripts.ci.sanitize_gitleaks_sarif.sanitize_sarif

# Round-trip test (encode/decode pairs)
uv run hypothesis write --roundtrip json.dumps json.loads

# Idempotency test
uv run hypothesis write --idempotent sorted

# Pipe to a file, then refine strategies and assertions
uv run hypothesis write scripts.index_url_resolver.parse_accelerator \
    > tests/unit/test_parse_accelerator_ghost.py
```

The output is valid pytest source — edit it, add real invariants, rename, commit.

### Writing new property tests (by hand)

```python
from hypothesis import given, settings, strategies as st

@settings(max_examples=100, deadline=None)
@given(x=st.integers(min_value=1, max_value=100))
def test_my_invariant(x: int) -> None:
    result = my_function(x)
    assert result >= 0  # the property
```

### Writing new PEP 316 contracts

```python
def my_function(x: int) -> int:
    """Do something.

    pre: x >= 1
    post: __return__ >= 0
    """
    ...
```

## Consequences

- Pure helper bugs are caught earlier by Hypothesis in the PR loop.
- CrossHair provides deeper (but slower, opt-in) verification locally.
- Contracts in docstrings document invariants without adding deps.
- The `crosshair` dep group adds ~37 MB (z3) — kept out of default lock.
- Teams can adopt `--hypothesis-profile=crosshair` incrementally per-function.
- If CrossHair's false-positive rate on string operations proves problematic, the PEP 316 contracts can be removed without affecting CI.

## Prior exploration

Earlier sessions explored the broader formal verification / testing tooling landscape
and identified CrossHair, Hypothesis, and contract libraries as candidates for this repo:

- [Formal methods NER survey](b15e6eb4) (May 2026): identified CrossHair, Z3, Kani,
  Gobra, Dafny, TLA+, KLEE, Haybale, and concolic/symbolic execution approaches;
  extracted icontract/deal/Imandra as contract-based tools; mapped competing approaches
  (DSE vs. PBT vs. model checking) and institutions (Microsoft Research, ETH Zurich, AWS).
- [Taint analyzer feasibility](d852249e) (Jul 2026): evaluated whether Semgrep taint
  mode, CodeQL dataflow, Bandit, or pytype taint tracking would find bugs in this repo's
  Python helpers and CI scripts. Concluded existing Semgrep + CodeQL coverage is adequate;
  taint analysis adds most value for web-facing code (not this infra repo).
- [Neurosymbolic tooling](02d4e415) (Jul 2026): investigated LLM-powered neurosymbolic
  development tooling (DSPy, SymbolicAI, Guardrails, Chiasmus MCP Z3 bridge). Concluded
  the repo already uses LLM agents for PR review with deterministic policy hooks;
  neurosymbolic verification adds value only for the contract/property layer — which
  this ADR now addresses via CrossHair.
- [Security/SAST evaluation](f0e1b85c) (Jul 2026): evaluated Bearer, Qodana, Semgrep
  alongside existing repo tooling; user recalled "that hypothesis style tester that
  checks preconditions" (CrossHair) and initiated this investigation thread.
- This session (Jul 2026): full implementation — Hypothesis properties, production
  `\n`-split fix, CrossHair spike, PEP 316 contracts, icontract/deal comparison,
  Ossuary governance risk scoring of candidate contract libraries.

## References

- [Hypothesis docs](https://hypothesis.readthedocs.io/)
- [CrossHair](https://github.com/pschanely/CrossHair) — PEP 316 / icontract / deal / assert contracts
- [hypothesis-crosshair](https://github.com/pschanely/hypothesis-crosshair) — SMT backend for Hypothesis
- [PEP 316](https://peps.python.org/pep-0316/) — Programming by Contract for Python (deferred)
- [Ossuary Risk](https://github.com/anicka-net/ossuary-risk) — OSS governance risk scoring methodology
- [OOPSLA 2025: Empirical Evaluation of PBT in Python](https://cseweb.ucsd.edu/~mcoblenz/assets/pdf/OOPSLA_2025_PBT.pdf)
