# Investigation notes — root cause analysis

> **Summary:** The AIPCC Simple API (Pulp/DRF) does not respect HTTP Accept header quality values (RFC 9110 §12.5.1). When uv sends `Accept: application/vnd.pypi.simple.v1+json;q=1, text/html;q=0.01`, the server returns `text/html` because DRF's renderer list in pulp_python puts HTML first. The HTML response lacks `data-upload-time` (PEP 700), causing uv's `--exclude-newer` to fail.

> **Workaround found:** Appending `?format=json` to the index URL forces DRF to return PEP 691 JSON regardless of Accept header. uv preserves query parameters when constructing per-package URLs, so `--exclude-newer` works correctly with this workaround.

---

## Evidence: curl tests comparing content negotiation

**Exclusive JSON Accept — works:**

```bash
curl -H 'Accept: application/vnd.pypi.simple.v1+json' \
  'https://console.redhat.com/api/pypi/public-rhai/rhoai/3.4/cpu-ubi9-test/simple/debugpy/'
# → content-type: application/vnd.pypi.simple.v1+json ✓
# → upload-time present on every file entry
```

**Content-negotiated (what uv sends) — broken:**

```bash
curl -D - -o /dev/null \
  -H 'Accept: application/vnd.pypi.simple.v1+json;q=1, text/html;q=0.01' \
  'https://console.redhat.com/api/pypi/public-rhai/rhoai/3.4/cpu-ubi9-test/simple/debugpy/'
# → content-type: text/html ✗ (should be JSON per RFC 9110)
```

**?format=json workaround — works:**

```bash
curl -D - -o /dev/null \
  'https://console.redhat.com/api/pypi/public-rhai/rhoai/3.4/cpu-ubi9-test/simple/debugpy/?format=json'
# → content-type: application/vnd.pypi.simple.v1+json ✓
```

---

## Evidence: uv verbose output

**uv 0.10.9 with --exclude-newer against AIPCC index (no workaround):**

```
warning: debugpy-1.8.20-2-cp312-cp312-linux_aarch64.whl is missing an upload date, but user provided: 2026-03-23T20:00:00Z
warning: debugpy-1.8.20-2-cp312-cp312-linux_ppc64le.whl is missing an upload date, but user provided: 2026-03-23T20:00:00Z
warning: debugpy-1.8.20-2-cp312-cp312-linux_s390x.whl is missing an upload date, but user provided: 2026-03-23T20:00:00Z
warning: debugpy-1.8.20-2-cp312-cp312-linux_x86_64.whl is missing an upload date, but user provided: 2026-03-23T20:00:00Z
× No solution found when resolving dependencies:
╰─▶ Because debugpy==1.8.20 has no publish time...
```

**uv 0.10.9 with ?format=json workaround — succeeds:**

```
TRACE Fetching metadata for debugpy from .../simple/debugpy/?format=json
DEBUG Searching for a compatible version of debugpy (*)
TRACE Found candidate for package debugpy with range * after 1 steps: 1.8.20 version
# No warnings, no errors — upload-time correctly parsed from JSON response
```

---

## Root cause in pulp_python source code

In pulp_python's SimpleView (`pulp_python/app/pypi/views.py`), the renderer list is ordered: TemplateHTMLRenderer (text/html), PyPISimpleHTMLRenderer, PyPISimpleJSONRenderer. DRF's DefaultContentNegotiation iterates renderers in order and picks the first one whose media type appears anywhere in the Accept header — it does not compare quality values. Since text/html is listed first and uv includes `text/html;q=0.01` in its Accept header, HTML always wins.

```python
# pulp_python/app/pypi/views.py — SimpleView.get_renderers()
def get_renderers(self):
    if self.action in ["list", "retrieve"]:
        return [TemplateHTMLRenderer(), PyPISimpleHTMLRenderer(), PyPISimpleJSONRenderer()]
        #       ^^^^ HTML first = always wins when Accept includes text/html
    else:
        return [JSONRenderer(), BrowsableAPIRenderer()]
```

---

## uv source: Accept header is hardcoded, no override available

uv hardcodes the Accept header in `crates/uv-client/src/registry_client.rs` (MediaType::pypi()). No env var, CLI flag, or config to change it:

```
Accept: application/vnd.pypi.simple.v1+json, application/vnd.pypi.simple.v1+html;q=0.2, text/html;q=0.01
```

The `text/html;q=0.01` fallback is always present.

---

## uv source: where 'no publish time' error originates

In `crates/uv-distribution-types/src/prioritized_distribution.rs`, when `upload_time_utc_ms` is `None` and `--exclude-newer` is set:

```rust
IncompatibleWheel::ExcludeNewer(ts) => match ts {
    Some(_) => f.write_str("published after the exclude newer time"),
    None => f.write_str("no publish time"),  // ← this message
},
```

`upload_time_utc_ms` is populated from PEP 691 JSON `upload-time` or PEP 700 HTML `data-upload-time`. AIPCC HTML has neither → every file gets `None` → "no publish time".

---

## ?format=json workaround details

DRF's `URL_FORMAT_OVERRIDE` setting (enabled by default) allows `?format=<renderer_format>` to bypass Accept header negotiation. PyPISimpleJSONRenderer inherits `format='json'` from DRF's JSONRenderer, so `?format=json` selects it directly.

uv preserves query parameters from the index URL when constructing per-package URLs:

```
Index URL: https://console.redhat.com/.../simple/?format=json
Per-package: https://console.redhat.com/.../simple/debugpy/?format=json  ← preserved ✓
```

This workaround can be applied in `build-args/*.conf` or in the lock generator script without any changes to uv or Pulp.

---

## References

- [opendatahub-io/notebooks#3179](https://github.com/opendatahub-io/notebooks/issues/3179) — upstream issue
- [astral-sh/uv#10394](https://github.com/astral-sh/uv/issues/10394) — --exclude-newer with non-PyPI indexes
- [astral-sh/uv#18681](https://github.com/astral-sh/uv/issues/18681) — uv pip compile --check feature request
- [Slack #tsd-ui thread](https://redhat-internal.slack.com/archives/C09MQNXHECQ/p1770747686370319?thread_ts=1770747429.599249) — confirms Pulp requires exclusive Accept for JSON
- [PEP 691](https://peps.python.org/pep-0691/) — JSON Simple API
- [PEP 700](https://peps.python.org/pep-0700/) — upload-time in Simple API
- [RFC 9110 §12.5.1](https://httpwg.org/specs/rfc9110.html#field.accept) — Accept header quality values
