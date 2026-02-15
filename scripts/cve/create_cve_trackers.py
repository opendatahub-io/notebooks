#!/usr/bin/env python3
"""
Create CVE tracker issues in RHAIENG project.

This script finds CVE issues in RHOAIENG that don't have a parent tracker in RHAIENG,
analyzes the versions from linked issues, and creates tracker issues with accurate
version suffixes (e.g., [rhoai-2.25, rhoai-3.0]).

Usage:
    # Dry run - show what would be created
    python scripts/create_cve_trackers.py --dry-run

    # Create trackers for all orphan CVEs
    python scripts/create_cve_trackers.py

    # Create tracker for specific CVE
    python scripts/create_cve_trackers.py --cve CVE-2025-12345

Requires:
    - JIRA_URL environment variable (or defaults to Red Hat Jira)
    - JIRA_TOKEN environment variable for authentication
    - requests library: pip install requests
"""

import argparse
import json
import os
import re
import ssl
import sys
import urllib.parse
from dataclasses import dataclass, field

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error

    HAS_REQUESTS = False


# Create SSL context for urllib - handles macOS certificate issues
def _create_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that works on macOS with system certificates."""
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        # On macOS, try to use the system certificates
        import subprocess
        import tempfile
        try:
            # Try to get certificates from security command on macOS
            result = subprocess.run(
                ["security", "find-certificate", "-a", "-p",
                 "/System/Library/Keychains/SystemRootCertificates.keychain"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
                    f.write(result.stdout)
                    ctx.load_verify_locations(f.name)
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            pass  # Fall back to default behavior
    return ctx


_SSL_CONTEXT = _create_ssl_context() if not HAS_REQUESTS else None


@dataclass
class CVEInfo:
    """Information about a CVE for a specific version."""
    cve_id: str
    version: str = ""
    description: str = ""
    issues: list = field(default_factory=list)
    has_tracker: bool = False
    tracker_key: str | None = None

    @property
    def version_suffix(self) -> str:
        """Get the version suffix for the tracker summary."""
        if not self.version:
            return ""
        return f"[{self.version}]"

    @property
    def issue_count(self) -> int:
        return len(self.issues)


class JiraClient:
    """Simple Jira REST API client."""

    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {"Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _request(self, method: str, endpoint: str, params: dict | None = None, data: dict | None = None) -> dict:
        """Make a request to the Jira API."""
        url = f"{self.base_url}{endpoint}"

        if HAS_REQUESTS:
            response = requests.request(
                method,
                url,
                params=params,
                json=data,
                headers=self.headers
            )
            response.raise_for_status()
            if response.text:
                return response.json()
            return {}
        else:
            if params:
                query_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
                url = f"{url}?{query_string}"

            req = urllib.request.Request(url, headers=self.headers, method=method)
            if data:
                req.data = json.dumps(data).encode("utf-8")

            with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
                content = resp.read().decode()
                if content:
                    return json.loads(content)
                return {}

    def search_issues(self, jql: str, fields: str = "key,summary,status,labels,components,issuelinks",
                      max_results: int = 500) -> list[dict]:
        """Search for issues using JQL."""
        all_issues = []
        start_at = 0

        while len(all_issues) < max_results:
            params = {
                "jql": jql,
                "maxResults": min(100, max_results - len(all_issues)),
                "startAt": start_at,
                "fields": fields
            }

            data = self._request("GET", "/rest/api/2/search", params=params)
            issues = data.get("issues", [])
            all_issues.extend(issues)

            if len(all_issues) >= data.get("total", 0) or not issues:
                break

            start_at += len(issues)

        return all_issues

    def create_issue(self, project_key: str, summary: str, issue_type: str,
                     description: str = "", labels: list[str] | None = None,
                     components: list[str] | None = None,
                     security_level: str | None = None) -> dict:
        """Create a new Jira issue."""
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        if description:
            fields["description"] = description

        if labels:
            fields["labels"] = labels

        if components:
            fields["components"] = [{"name": c} for c in components]

        if security_level:
            fields["security"] = {"name": security_level}

        data = {"fields": fields}
        result = self._request("POST", "/rest/api/2/issue", data=data)
        return result

    def create_issue_link(self, link_type: str, inward_key: str, outward_key: str) -> None:
        """Create a link between two issues."""
        data = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key}
        }
        self._request("POST", "/rest/api/2/issueLink", data=data)

    def get_issue(self, issue_key: str, fields: str = "key,summary,status,labels,issuelinks") -> dict:
        """Get a single issue."""
        params = {"fields": fields}
        return self._request("GET", f"/rest/api/2/issue/{issue_key}", params=params)

    def update_issue(self, issue_key: str, fields: dict) -> None:
        """Update fields on an existing issue."""
        self._request("PUT", f"/rest/api/2/issue/{issue_key}", data={"fields": fields})


def extract_cve_id(text: str) -> str | None:
    """Extract CVE ID from text."""
    match = re.search(r'CVE-\d{4}-\d+', text)
    return match.group() if match else None


def extract_version(summary: str) -> str | None:
    """Extract version suffix from issue summary."""
    match = re.search(r'\[rhoai-(\d+\.\d+)\]', summary)
    if match:
        return f"rhoai-{match.group(1)}"
    return None


def extract_description(summary: str, cve_id: str) -> str:
    """Extract the CVE description from the summary."""
    # Remove CVE ID prefix
    desc = summary
    if cve_id in desc:
        desc = desc.split(cve_id, 1)[1].strip()

    # Remove EMBARGOED prefix if present
    desc = re.sub(r'^EMBARGOED\s+', '', desc)

    # Remove component prefix (e.g., "rhoai/odh-xxx:")
    desc = re.sub(r'^rhoai/[^:]+:\s*', '', desc)

    # Remove version suffix
    desc = re.sub(r'\s*\[rhoai-[\d.]+\]\s*$', '', desc)

    return desc.strip()


def get_blocking_issues(issue: dict) -> list[str]:
    """Get list of issue keys that block this issue (parent trackers)."""
    blockers = []
    issuelinks = issue.get("fields", {}).get("issuelinks", [])
    for link in issuelinks:
        if link.get("type", {}).get("name") == "Blocks":
            if "inwardIssue" in link:
                blockers.append(link["inwardIssue"]["key"])
    return blockers


JIRA_BASE_URL = "https://issues.redhat.com"


def build_description(cve_info: CVEInfo, tracker_key: str | None = None) -> str:
    """Build a Jira wiki markup description for a CVE tracker issue.

    Includes a static JQL link listing child issue keys explicitly, a plain-text
    list of blocked issues, and (when tracker_key is provided) a dynamic
    ``linkedIssues()`` JQL link.
    """
    child_keys = sorted(issue["key"] for issue in cve_info.issues)
    count = len(child_keys)

    lines: list[str] = []
    lines.append(
        f"Tracker for {cve_info.cve_id} - {cve_info.description} "
        f"affecting Notebooks Images components."
    )

    if child_keys:
        lines.append("")
        lines.append(f"*Blocked Issues ({count}):*")
        lines.append(", ".join(child_keys))

        # Static JQL link with explicit issue keys
        keys_csv = ", ".join(child_keys)
        static_jql = f"key in ({keys_csv}) ORDER BY key ASC"
        static_url = f"{JIRA_BASE_URL}/issues/?jql={urllib.parse.quote(static_jql)}"
        lines.append("")
        lines.append("*JQL Query to View All Blocked Issues:*")
        lines.append("")
        lines.append(f"[View all {count} blocked issues|{static_url}]")

    if tracker_key and child_keys:
        # Dynamic JQL link using linkedIssues function
        dynamic_jql = f'issue in linkedIssues({tracker_key}, "blocks") ORDER BY key ASC'
        dynamic_url = f"{JIRA_BASE_URL}/issues/?jql={urllib.parse.quote(dynamic_jql)}"
        lines.append("")
        lines.append("{code}")
        lines.append(dynamic_jql)
        lines.append("{code}")
        lines.append("")
        lines.append(f"[View blocked issues (dynamic)|{dynamic_url}]")

    return "\n".join(lines)


def find_orphan_cves(client: JiraClient, max_results: int = 1000) -> dict[tuple[str, str], CVEInfo]:
    """Find CVEs in RHOAIENG that don't have a parent tracker in RHAIENG.

    Returns a dict keyed by (cve_id, version) tuples, one entry per version.
    Issues without a version are grouped under version="" (no version).
    """
    print("Searching for CVE issues in RHOAIENG...")

    # NOTE: Identifying CVE tracker issues in RHOAIENG
    #
    # Product Security files CVE issues with varying patterns over time:
    # - Older issues (2023): Used generic "CVE" label
    # - Newer issues (2025+): Use "SecurityTracking" label + issue type Vulnerability/Bug/Weakness
    #
    # We filter by:
    # - issuetype: Vulnerability, Bug, or Weakness (security-related issue types)
    # - labels: SecurityTracking (Product Security's tracking label)
    # - component: "Notebooks Images" (only process CVEs for our team)
    #
    # This ensures we only create parent trackers for Notebooks-related CVEs.

    # Get all RHOAIENG CVE issues
    jql = 'project = RHOAIENG AND issuetype in (Bug, Vulnerability, Weakness) AND resolution = Unresolved AND labels = SecurityTracking AND component = "Notebooks Images" ORDER BY created DESC'
    issues = client.search_issues(jql, max_results=max_results)
    print(f"Found {len(issues)} RHOAIENG CVE issues")

    # Group by (CVE ID, version)
    cve_groups: dict[tuple[str, str], CVEInfo] = {}

    for issue in issues:
        key = issue["key"]
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        labels = fields.get("labels", [])

        # Extract CVE ID
        cve_id = None
        for label in labels:
            extracted = extract_cve_id(label)
            if extracted:
                cve_id = extracted
                break

        if not cve_id:
            cve_id = extract_cve_id(summary)

        if not cve_id:
            continue

        # Check if this issue has a parent tracker (is blocked by RHAIENG issue)
        blockers = get_blocking_issues(issue)
        has_rhaieng_blocker = any(b.startswith("RHAIENG-") for b in blockers)

        # Extract version from summary
        version = extract_version(summary) or ""

        group_key = (cve_id, version)

        if group_key not in cve_groups:
            cve_groups[group_key] = CVEInfo(cve_id=cve_id, version=version)

        info = cve_groups[group_key]

        # Extract description if not already set
        if not info.description:
            desc = extract_description(summary, cve_id)
            if desc:
                info.description = desc

        info.issues.append({
            "key": key,
            "summary": summary,
            "has_parent": has_rhaieng_blocker
        })

        if has_rhaieng_blocker:
            info.has_tracker = True
            for b in blockers:
                if b.startswith("RHAIENG-"):
                    info.tracker_key = b
                    break

    # Filter to only orphans (CVE+version combos where no issues have a parent tracker)
    orphans = {}
    for group_key, info in cve_groups.items():
        if not info.has_tracker:
            orphans[group_key] = info

    return orphans


def create_tracker_issue(client: JiraClient, cve_info: CVEInfo, dry_run: bool = False) -> str | None:
    """Create a tracker issue for a CVE."""
    summary = f"{cve_info.cve_id} {cve_info.description} {cve_info.version_suffix}"

    # Truncate summary if too long (Jira limit is 255 chars)
    if len(summary) > 250:
        max_desc_len = 250 - len(cve_info.cve_id) - len(cve_info.version_suffix) - 3
        summary = f"{cve_info.cve_id} {cve_info.description[:max_desc_len]}... {cve_info.version_suffix}"

    description = build_description(cve_info)

    labels = ["CVE", cve_info.cve_id, "security"]

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Creating tracker for {cve_info.cve_id}:")
    print(f"  Summary: {summary}")
    print(f"  Version: {cve_info.version}")
    print(f"  Child issues: {cve_info.issue_count}")

    if dry_run:
        return None

    try:
        result = client.create_issue(
            project_key="RHAIENG",
            summary=summary,
            issue_type="Bug",
            description=description,
            labels=labels,
            components=["Notebooks"],
            security_level="Red Hat Employee"
        )
        tracker_key = result.get("key")
        print(f"  Created: {tracker_key}")
        return tracker_key
    except Exception as e:
        print(f"  ERROR creating issue: {e}")
        return None


def link_issues(client: JiraClient, tracker_key: str, child_keys: list[str], dry_run: bool = False) -> int:
    """Link tracker issue to child issues (tracker blocks children)."""
    linked = 0
    for child_key in child_keys:
        if dry_run:
            print(f"  [DRY RUN] Would link {tracker_key} blocks {child_key}")
            linked += 1
            continue

        try:
            client.create_issue_link("Blocks", tracker_key, child_key)
            print(f"  Linked: {tracker_key} blocks {child_key}")
            linked += 1
        except Exception as e:
            print(f"  ERROR linking {child_key}: {e}")

    return linked


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Create CVE tracker issues in RHAIENG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - show what would be created
  python scripts/create_cve_trackers.py --dry-run

  # Create trackers for all orphan CVEs
  python scripts/create_cve_trackers.py

  # Create tracker for specific CVE
  python scripts/create_cve_trackers.py --cve CVE-2025-12345

  # List orphans without creating
  python scripts/create_cve_trackers.py --list-only

Environment variables:
  JIRA_URL      Jira server URL (default: https://issues.redhat.com)
  JIRA_TOKEN    Personal access token for authentication
"""
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created without making changes")
    parser.add_argument("--cve", help="Create tracker for specific CVE ID only")
    parser.add_argument("--list-only", action="store_true",
                        help="List orphan CVEs without creating trackers")
    parser.add_argument("--max-results", type=int, default=1000,
                        help="Maximum issues to fetch (default: 1000)")
    parser.add_argument("--no-link", action="store_true",
                        help="Create trackers but don't link to child issues")
    return parser.parse_args()


def main():
    args = parse_args()

    jira_url = os.environ.get("JIRA_URL", "https://issues.redhat.com")
    jira_token = os.environ.get("JIRA_TOKEN")

    if not jira_token:
        print("ERROR: JIRA_TOKEN environment variable is required", file=sys.stderr)
        print("Set it with: export JIRA_TOKEN='your-token-here'", file=sys.stderr)
        sys.exit(1)

    client = JiraClient(jira_url, jira_token)

    print(f"Connecting to {jira_url}...")

    # Find orphan CVEs
    orphans = find_orphan_cves(client, args.max_results)

    if not orphans:
        print("\nNo orphan CVEs found - all CVEs have parent trackers!")
        return

    # Filter to specific CVE if requested
    if args.cve:
        filtered = {k: v for k, v in orphans.items() if k[0] == args.cve}
        if not filtered:
            print(f"\nCVE {args.cve} not found in orphan list.")
            print("It may already have a tracker or doesn't exist.")
            sys.exit(1)
        orphans = filtered

    print(f"\nFound {len(orphans)} orphan CVE/version trackers needed:")
    print("-" * 80)

    for (cve_id, version), info in sorted(orphans.items()):
        version_label = version or "(no version)"
        print(f"  {cve_id} {version_label}: {info.issue_count} issues")
        if info.description:
            print(f"    Description: {info.description[:60]}...")

    if args.list_only:
        return

    print("\n" + "=" * 80)
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
    else:
        print("CREATING TRACKER ISSUES")
    print("=" * 80)

    created = 0
    linked = 0

    for (_cve_id, _version), info in sorted(orphans.items()):
        tracker_key = create_tracker_issue(client, info, args.dry_run)

        if tracker_key and not args.no_link:
            child_keys = [issue["key"] for issue in info.issues]
            linked += link_issues(client, tracker_key, child_keys, args.dry_run)

        # Update description to include the dynamic linkedIssues() link
        if tracker_key:
            try:
                full_description = build_description(info, tracker_key=tracker_key)
                client.update_issue(tracker_key, {"description": full_description})
                print(f"  Updated description with dynamic JQL link")
            except Exception as e:
                print(f"  WARNING: could not update description: {e}")

        if tracker_key or args.dry_run:
            created += 1

    print("\n" + "=" * 80)
    print(f"Summary: {'Would create' if args.dry_run else 'Created'} {created} tracker issues")
    if not args.no_link:
        print(f"         {'Would link' if args.dry_run else 'Linked'} {linked} child issues")
    print("=" * 80)


if __name__ == "__main__":
    main()
