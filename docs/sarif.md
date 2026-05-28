# SARIF (Static Analysis Results Interchange Format)

[Introduction from Microsoft](https://github.com/microsoft/sarif-tutorials).

SARIF is a format based on JSON, used to capture warning messages from software tools that work with sourcecode.
Most importantly it can hold compiler warnings and findings from security scanners.
GitHub can then import these and maintain a browsable database of outstanding ones.

## Helpful tooling

- [SARIF validator](https://sarifweb.azurewebsites.net/Validation)
- [SARIF multitool for merging and manipulating .sarif files](https://github.com/microsoft/sarif-sdk/blob/main/docs/multitool-usage.md)
  - [GitHub action to invoke the tool](https://github.com/marketplace/actions/sarif-multitool)
- [GitHub documentation about importing SARIF results](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github)

## Gitleaks SARIF upload in this repo

The [Gitleaks workflow](../.github/workflows/gitleaks.yaml) runs `scripts/ci/sanitize_gitleaks_sarif.py` before `upload-sarif` because Gitleaks 8.30.x can emit `endColumn: 0`, which GitHub rejects (`endColumn` must be ≥ 1).
