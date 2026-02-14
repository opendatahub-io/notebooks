# Node.js (npm, yarn, pnpm) CVE Resolution Guide

## Overview

Node.js vulnerabilities may come from
* tests and developer utilities in `tests/containers` (false positive, Component Not Present)
* css minifier in `jupyter/utils/addon` (false positive, Component Not Present)
* RStudio components replacement hack in `rstudio/utils` (needs investigation, probably true finding)
* the codeserver or RStudio IDEs themselves (needs investigation, probably true finding)

## Determine where the vulnerability came from

Determining what the ProdSec tooling finds offensive may not be straightforward.
We have Node.js packages installed in our images from RHEL/C9S RPMs, but these CVEs are handled by the RHEL team.
Our responsibility is to keep up with RPM package updates and if updated RPM does not exist, the issue is "unfixable" and should not be even reported to us.

Rely on the `manifest-box` vulnerability reports to determine where the vulnerability came from.
For example, here is a vulnerability about a "php" package:

```json
{
  "SPDXID": "SPDXRef-Package-npm-php-ea611cd4f328f0ac",
  "copyrightText": "NOASSERTION",
  "description": "%description%",
  "downloadLocation": "https://github.com/microsoft/vscode.git",
  "externalRefs": [
    {
      "referenceCategory": "SECURITY",
      "referenceLocator": "cpe:2.3:a:microsoft:php:1.0.0:*:*:*:*:*:*:*",
      "referenceType": "cpe23Type"
    },
    {
      "referenceCategory": "PACKAGE_MANAGER",
      "referenceLocator": "pkg:npm/php@1.0.0",
      "referenceType": "purl"
    }
  ],
  "filesAnalyzed": false,
  "licenseConcluded": "NOASSERTION",
  "licenseDeclared": "MIT",
  "name": "php",
  "sourceInfo": "acquired package info from installed node module manifest file: /usr/lib/code-server/lib/vscode/extensions/php/package.json",
  "supplier": "NOASSERTION",
  "versionInfo": "1.0.0"
}
```

Use the `scripts/sbom_analyze.py` to analyze the manifest-box sbom, or use Ctrl+F in your IDE of choice, that works too.

```
❯ uv run scripts/sbom_analyze.py rhoai_odh-workbench-codeserver-datascience-cpu-py312-rhel9@sha256_56572.json php

=== Searching for 'php' ===
  Found 2 matching package(s):

  php@1.0.0
    Type: npm
    Locations:
      - /usr/lib/code-server/lib/vscode/extensions/php/package.json
    Source: acquired package info from installed node module manifest file: /usr/lib/code-server/lib/vscode/extensions/php/package.json
    PURL: pkg:npm/php@1.0.0

  php-language-features@1.0.0
    Type: npm
    Locations:
      - /usr/lib/code-server/lib/vscode/extensions/php-language-features/package.json
    Source: acquired package info from installed node module manifest file: /usr/lib/code-server/lib/vscode/extensions/php-language-features/package.json
    PURL: pkg:npm/php-language-features@1.0.0
```

This tells us that we need to investigate codeserver extensions for a Node.js package, and not for example look for any PHP binary coming from a RPM package in /usr/bin.

## Resolution

### False positive findings

Close the Jira issue with a "Not a Bug" resolution and a VEX justification.

The false-positive findings should still eventually be addressed during regular maintenance.
This however can happen independently of the product release cycle.

In the directory with `package.json`, run:

    pnpm update --latest

### True findings

Update the component bringing in the vulnerable package.
