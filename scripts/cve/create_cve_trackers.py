#!/usr/bin/env python3
"""
Create CVE tracker issues in RHAIENG project.

This script finds CVE issues in RHOAIENG that don't have a parent tracker in RHAIENG,
analyzes the versions from linked issues, and creates tracker issues with accurate
version suffixes (e.g., [rhoai-2.25, rhoai-3.0]).

New trackers always get the literal label ``CVE`` (plus the CVE id and ``security``)
so they are distinguishable from other Bugs, and the Jira **Team** field set to
**AAIET Notebooks** (``customfield_10001``), matching RHAIENG process.

Usage:
    # Dry run - show what would be created
    python scripts/cve/create_cve_trackers.py --dry-run

    # Create trackers for all orphan CVEs
    python scripts/cve/create_cve_trackers.py

    # Create tracker for specific CVE
    python scripts/cve/create_cve_trackers.py --cve CVE-2025-12345

Requires:
    - JIRA_URL environment variable (default: https://redhat.atlassian.net)
    - JIRA_EMAIL + JIRA_API_TOKEN  for API-token auth (recommended)
    - JIRA_OAUTH_CLIENT_SECRET     for OAuth 2.0 browser flow
    - JIRA_TOKEN                   for legacy Bearer-token auth
    - requests library: pip install requests
"""

import argparse
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from scripts.cve.jira_auth import JiraAuthError
from scripts.cve.jira_client import JIRA_DEFAULT_URL, JiraClient

# Jira "Team" on RHAIENG (verified via RHAIENG-3752 changelog).
RHAIENG_TEAM_CUSTOM_FIELD = "customfield_10001"
# Option id for team name "AAIET Notebooks" (override if Jira admin changes teams).
RHAIENG_TEAM_OPTION_ID_DEFAULT = "ec74d716-af36-4b3c-950f-f79213d08f71-62"


def build_tracker_labels(cve_id: str) -> list[str]:
    """Labels for new CVE trackers: keep literal ``CVE`` first (team Jira hygiene)."""
    return ["CVE", cve_id, "security"]


def build_tracker_team_extra_fields() -> dict[str, str]:
    """REST ``fields`` fragment for Team = AAIET Notebooks.

    Jira expects a **plain Team ID string** on create/update, not ``{\"id\": ...}``.
    See https://developer.atlassian.com/platform/teams/components/team-field-in-jira-rest-api/
    """
    option_id = os.environ.get("JIRA_RHAIENG_TEAM_OPTION_ID", RHAIENG_TEAM_OPTION_ID_DEFAULT).strip()
    return {RHAIENG_TEAM_CUSTOM_FIELD: option_id}


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


def extract_cve_id(text: str) -> str | None:
    """Extract CVE ID from text."""
    match = re.search(r"CVE-\d{4}-\d+", text)
    return match.group() if match else None


def extract_version(summary: str) -> str | None:
    """Extract version suffix from issue summary."""
    match = re.search(r"\[rhoai-(\d+\.\d+)]", summary)
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
    desc = re.sub(r"^EMBARGOED\s+", "", desc)

    # Remove component prefix (e.g., "rhoai/odh-xxx:")
    desc = re.sub(r"^rhoai/[^:]+:\s*", "", desc)

    # Remove version suffix
    desc = re.sub(r"\s*\[rhoai-[\d.]+]\s*$", "", desc)

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


def _adf_text(text: str, marks: list[dict] | None = None) -> dict:
    """Create an ADF text node."""
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _adf_paragraph(*content: dict) -> dict:
    """Create an ADF paragraph node."""
    return {"type": "paragraph", "content": list(content)}


def _adf_link(text: str, href: str) -> dict:
    """Create an ADF text node with a link mark."""
    return _adf_text(text, marks=[{"type": "link", "attrs": {"href": href}}])


def _adf_code_block(text: str) -> dict:
    """Create an ADF code block node."""
    return {"type": "codeBlock", "content": [_adf_text(text)]}


def build_description(cve_info: CVEInfo, base_url: str = JIRA_DEFAULT_URL, tracker_key: str | None = None) -> dict:
    """Build an ADF (Atlassian Document Format) description for a CVE tracker issue.

    Returns a dict suitable for the API v3 ``description`` field.
    """
    child_keys = sorted(issue["key"] for issue in cve_info.issues)
    count = len(child_keys)

    content: list[dict] = [_adf_paragraph(
        _adf_text(
            f"Tracker for {cve_info.cve_id} - {cve_info.description} "
            f"affecting Notebooks Images components."
        )
    )]

    if child_keys:
        content.append(_adf_paragraph(
            _adf_text(f"Blocked Issues ({count}): ", marks=[{"type": "strong"}]),
            _adf_text(", ".join(child_keys)),
        ))

        keys_csv = ", ".join(child_keys)
        static_jql = f"key in ({keys_csv}) ORDER BY key ASC"
        static_url = f"{base_url}/issues/?jql={urllib.parse.quote(static_jql)}"

        content.append(_adf_paragraph(
            _adf_text("JQL Query to View All Blocked Issues: ", marks=[{"type": "strong"}]),
        ))
        content.append(_adf_paragraph(
            _adf_link(f"View all {count} blocked issues", static_url),
        ))

    if tracker_key and child_keys:
        dynamic_jql = f'issue in linkedIssues({tracker_key}, "blocks") ORDER BY key ASC'
        dynamic_url = f"{base_url}/issues/?jql={urllib.parse.quote(dynamic_jql)}"

        content.append(_adf_code_block(dynamic_jql))
        content.append(_adf_paragraph(
            _adf_link("View blocked issues (dynamic)", dynamic_url),
        ))

    return {"version": 1, "type": "doc", "content": content}


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
    issues = client.search_issues(jql, fields="key,summary,status,labels,issuelinks", max_results=max_results)
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
    orphans = {group_key: info for group_key, info in cve_groups.items() if not info.has_tracker}

    return orphans


def create_tracker_issue(client: JiraClient, cve_info: CVEInfo, jira_url: str = JIRA_DEFAULT_URL, dry_run: bool = False) -> str | None:
    """Create a tracker issue for a CVE."""
    summary = f"{cve_info.cve_id} {cve_info.description} {cve_info.version_suffix}"

    # Truncate summary if too long (Jira limit is 255 chars)
    if len(summary) > 250:
        max_desc_len = 250 - len(cve_info.cve_id) - len(cve_info.version_suffix) - 5
        summary = f"{cve_info.cve_id} {cve_info.description[:max_desc_len]}... {cve_info.version_suffix}"

    description = build_description(cve_info, base_url=jira_url)

    labels = build_tracker_labels(cve_info.cve_id)
    team_extra = build_tracker_team_extra_fields()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Creating tracker for {cve_info.cve_id}:")
    print(f"  Summary: {summary}")
    print(f"  Version: {cve_info.version}")
    print(f"  Child issues: {cve_info.issue_count}")
    print(f"  Labels: {' '.join(labels)}")
    print(f"  Team field ({RHAIENG_TEAM_CUSTOM_FIELD}): {team_extra[RHAIENG_TEAM_CUSTOM_FIELD]!r}")

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
            security_level="Red Hat Employee",
            extra_fields=team_extra,
        )
        tracker_key = result.get("key")
        print(f"  Created: {tracker_key}")
        return tracker_key
    except Exception as e:
        print(f"  ERROR creating issue: {e}")
        resp = getattr(e, "response", None)
        if resp is not None:
            text = getattr(resp, "text", None) or ""
            if text.strip():
                print(f"  API response: {text[:4000]}")
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
  JIRA_URL                  Jira server URL (default: https://redhat.atlassian.net)
  JIRA_EMAIL                User email (used with JIRA_API_TOKEN for Basic auth)
  JIRA_API_TOKEN            Atlassian API token (recommended for scripts/CI)
  JIRA_OAUTH_CLIENT_SECRET  OAuth 2.0 client secret (interactive browser flow)
  JIRA_TOKEN                Legacy Bearer token (issues.redhat.com PAT)
  JIRA_RHAIENG_TEAM_OPTION_ID  Optional. Jira Team option id for AAIET Notebooks
                            (default: RHAIENG value verified on RHAIENG-3752)
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

    try:
        client = JiraClient.from_env()
    except JiraAuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    jira_url = os.environ.get("JIRA_URL", JIRA_DEFAULT_URL)
    print(f"Connecting to {client.base_url}...")

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
            desc = info.description[:60] + "..." if len(info.description) > 60 else info.description
            print(f"    Description: {desc}")

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
        tracker_key = create_tracker_issue(client, info, jira_url=jira_url, dry_run=args.dry_run)

        if not args.no_link:
            child_keys = [issue["key"] for issue in info.issues]
            if tracker_key:
                linked += link_issues(client, tracker_key, child_keys, dry_run=False)
            elif args.dry_run:
                linked += link_issues(client, "DRY-RUN", child_keys, dry_run=True)

        # Update description to include the dynamic linkedIssues() link
        if tracker_key:
            try:
                full_description = build_description(info, base_url=jira_url, tracker_key=tracker_key)
                client.update_issue(tracker_key, {"description": full_description})
                print("  Updated description with dynamic JQL link")
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
