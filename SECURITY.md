# Security Policy

The notebooks project team and community take security seriously.
We appreciate your efforts to responsibly disclose your findings and
will make every effort to acknowledge your contributions.

## Scope

This policy covers security issues in:

- Workbench and pipeline runtime container images built from this repository
- Build scripts, CI configuration, and other tooling maintained here

Vulnerabilities in third-party upstream projects (for example JupyterLab,
code-server, or base OS packages) should still be reported here when they
affect images or tooling shipped from this repository. We will coordinate
with upstream and Red Hat Product Security as needed.

## Supported Versions

Security fixes are delivered through weekly patch rebuilds of supported
release branches. Typically the two most recent `YYYYx` releases (for
example `2025a` and `2025b`) receive security updates for at least one
year. Older images may remain available in registries but are not
actively supported.

See [UPDATES.md](UPDATES.md) for the release and support model.

## Reporting a Vulnerability

Please do not report security vulnerabilities via public GitHub issues,
pull requests, or other public channels. To ensure coordinated disclosure,
report issues privately to [Red Hat Product Security](https://access.redhat.com/security/team/contact)
at **secalert@redhat.com**.

Please include the following information in your report when possible:

- A concise title and description of the vulnerability
- Steps to reproduce the issue
- Affected image name(s), tag(s), or commit SHA
- Any potential impact of the vulnerability
- Whether the issue has been disclosed elsewhere

You may encrypt your message using the Red Hat Product Security GPG key
(key ID `DCE3823597F5EAC4`, fingerprint
`77E7 9ABE 9367 3533 ED09 EBE2 DCE3 8235 97F5 EAC4`).
The key is available at
<https://security.access.redhat.com/data/97f5eac4.txt>.

## Response and Disclosure

Email sent to secalert@redhat.com is read and acknowledged with a
non-automated response within 3 working days. Any information you share
about security issues that are not yet public is kept confidential within
Red Hat and will not be shared with third parties without your permission.

Confirmed vulnerabilities are triaged, fixed, and released according to
[Red Hat's security vulnerability response policy](https://access.redhat.com/security/updates/classification/).
We coordinate public disclosure with reporters once a fix is available.

## Additional Resources

- [Red Hat Product Security](https://access.redhat.com/security/)
- [Red Hat Security Vulnerability Response Policy](https://access.redhat.com/security/updates/classification/)
