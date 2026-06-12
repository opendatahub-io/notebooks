# 15. Adopt inline-snapshot for approval-style testing

Date: 2026-06-12

## Status

Proposed

## Context

This repository's test suite relies on hand-written assertions for complex
structured outputs: Jira ADF documents, CI summary JSON payloads, GitHub API
request bodies, and generated Dockerfile fragments. These tests share a common
problem:

- **Tedious to write.** Manually constructing the expected dict for a 60-line
  ADF document is slow and error-prone. Developers tend to assert only a few
  fields and silently ignore the rest.
- **Hard to review.** Deeply nested dict literals obscure what the output
  actually looks like. A reviewer cannot tell at a glance whether the Jira
  description will render correctly.
- **Painful to maintain.** When the output changes (new field, reworded text,
  different URL encoding), every affected test must be updated by hand.

These problems are well-understood in the testing community. Jane Street
pioneered [expect tests][janestreet] in OCaml — tests where you write code that
produces output, place an empty expected-output block next to it, and let
tooling fill in the value. The workflow feels "like a REPL session, or like
exploratory programming in a Jupyter notebook." Rust's `expect-test`, Jest's
inline snapshots, and Mercurial's cram tests all implement the same idea.

In the Python ecosystem, Emily Bache and Llewelyn Falco popularized
[approval testing][approvaltests] — capturing complex output as a
human-reviewed golden master. The key insight is that a dedicated **test
printer** transforms raw data structures into scannable, domain-meaningful text.
When the printer is well-designed, reading the snapshot is easier than reading a
wall of `assert` statements.

Dave Farley [characterizes][farley] approval tests as maintenance tools for
freezing existing behavior — characterization tests in Michael Feathers'
terminology ([*Working Effectively with Legacy Code*][feathers]). That framing
is fair: snapshot tests do not drive software design the way TDD does. Our
adoption is explicitly for the characterization-test use case — protecting
existing complex outputs — not replacing test-driven development.

Martin Fowler's [change-detector test][fowler-cdt] critique is the strongest
objection: snapshot tests can couple tests to implementation details rather than
behavior, and any change — intentional or not — shows up as a diff. The
standard mitigation is the **test printer**: by projecting wire formats into
domain-meaningful text, the snapshot captures *what the output means*, not *how
it is serialized*. A change in JSON key ordering doesn't break the snapshot; a
change in the Jira description text does — which is the signal we want.

## Decision

### Use `inline-snapshot` for structured-output tests

New tests that verify complex structured outputs (ADF documents, JSON payloads,
API request bodies) should use `inline-snapshot` with `snapshot()` assertions.
The expected value lives directly in the test source file, not in a separate
`.approved.txt` or `.ambr` file.

The dependency is declared in `pyproject.toml`:

```toml
[dependency-groups]
dev = [
    ...
    "inline-snapshot>=0.34.1",
]
```

The formatter is configured to use ruff (matching the project's existing
formatter):

```toml
[tool.inline-snapshot]
format-command = "ruff format --stdin-filename {filename}"
```

### Write test printers for domain objects

When the raw data structure is hard to scan (e.g., Atlassian Document Format
JSON), write a small projection function that renders it as readable text. The
snapshot then captures what the output *looks like*, not the wire format.

Example from `tests/unit/scripts/cve/test_create_cve_trackers.py`:

```python
def adf_to_text(doc: dict) -> str:
    """Render ADF as scannable markdown-like text for snapshot comparison."""
    ...

def test_build_description_with_version() -> None:
    info = cct.CVEInfo(cve_id="CVE-2026-8643", version="rhoai-2.25", ...)
    assert adf_to_text(cct.build_description(info)) == snapshot("""\
Tracker for CVE-2026-8643 - Path traversal flaw affecting Notebooks Images components.
Fix should be applied to: [https://...](https://...) (branch: rhoai-2.25)
**Blocked Issues (2): **RHOAIENG-64025, RHOAIENG-64026
...\
""")
```

Compare this to the previous 60-line nested dict assertion it replaced.

### Snapshot workflow

1. Write the test with an empty `snapshot()`.
2. Run `uv run pytest --inline-snapshot=create` — the library fills in the
   value, formatted by ruff.
3. Review the generated snapshot in the diff.
4. When output changes intentionally, run `uv run pytest --inline-snapshot=update`
   to bulk-refresh all snapshots, then review the diff.

### When to use snapshots vs. targeted assertions

- **Use `snapshot()`** when the output is a complex structure where exhaustive
  hand-written assertions would be tedious and partial assertions would miss
  regressions. Examples: ADF documents, CI context JSON, generated YAML.
- **Keep targeted assertions** for simple values, boolean conditions, and cases
  where the assertion communicates intent better than a snapshot. Example:
  `assert info.is_embargoed is True`.
- **Convert to builtins before snapshotting.** Following the [Pydantic team's
  recommendation][pydantic], snapshot dataclasses and Pydantic models as dicts
  (`model_dump()` / `dataclasses.asdict()`). If a model gains a required
  parameter, the constructor fails before reaching the assertion — using
  builtins ensures the snapshot is the only thing that can fail.

## Consequences

### Positive

- Complex output tests are faster to write — `snapshot()` + one pytest run
  replaces manual dict construction.
- Snapshots are easier to review — especially with test printers that project
  wire formats into readable text.
- Bulk updates (`--inline-snapshot=update`) eliminate the toil of manually
  fixing dozens of tests after an intentional output change.
- Snapshots live in the test file, not in separate snapshot directories —
  no file-jumping during review.

### Negative / risks

- **Rubber-stamp risk.** A careless `--inline-snapshot=update` can silently
  approve a regression. Mitigations: snapshot diffs must be reviewed in PRs
  like any code change; CI runs pytest *without* `--inline-snapshot` flags, so
  a stale or wrong snapshot fails the build rather than auto-updating.
- **Change-detector coupling** ([Fowler][fowler-cdt]). Raw-structure snapshots
  can break on serialization changes that don't affect behavior. Mitigated by
  test printers that project domain-meaningful text rather than wire format.
- Snapshot tests do not drive software design the way TDD does. They are
  characterization tests ([Feathers][feathers]) that document and protect
  existing behavior.
- The `inline-snapshot` library modifies source files in place, which requires
  trust in the tooling. Misconfigured formatters can corrupt test files.

### Non-goals

- Replacing all existing assertions with snapshots. Only complex structured
  outputs benefit; simple assertions should stay as they are.
- Using file-based snapshot libraries (syrupy, pytest-snapshot). Inline
  snapshots were chosen specifically for co-location with test code.
  [Syrupy's rationale][syrupy] for file-based storage — avoiding bloated test
  files with large expected values — is valid for big outputs. If a future
  snapshot exceeds what a test printer can make scannable inline, syrupy can be
  added alongside inline-snapshot without conflict: they use different CLI flags
  (`--snapshot-update` vs `--inline-snapshot`), different storage, and different
  mechanisms (fixture vs function import). The one caveat: both use the name
  `snapshot`, so a test file using both must alias one, e.g.
  `from inline_snapshot import snapshot as isnap`.

## References

- [The Joy of Expect Tests — Jane Street][janestreet]
- [Testing with inline-snapshot — Pydantic][pydantic]
- [inline-snapshot alternatives][alternatives]
- [Approval Testing — Emily Bache][approvaltests]
- [Add APPROVAL TESTING To Your Bag Of Tricks — Dave Farley][farley]
- [ChangeDetectorTest — Martin Fowler][fowler-cdt]
- [*Working Effectively with Legacy Code* — Michael Feathers][feathers]
- [syrupy — file-based pytest snapshot plugin][syrupy]
- [inline-snapshot documentation](https://15r10nk.github.io/inline-snapshot/)

[janestreet]: https://blog.janestreet.com/the-joy-of-expect-tests/
[approvaltests]: https://medium.com/97-things/approval-testing-33946cde4aa8
[pydantic]: https://pydantic.dev/articles/inline-snapshot
[alternatives]: https://15r10nk.github.io/inline-snapshot/latest/alternatives/
[farley]: https://www.youtube.com/watch?v=UzICYJkaGsY
[fowler-cdt]: https://martinfowler.com/bliki/ChangeDetectorTest.html
[feathers]: https://www.oreilly.com/library/view/working-effectively-with/0131177052/
[syrupy]: https://github.com/syrupy-project/syrupy
