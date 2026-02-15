#!/usr/bin/env python3
"""
Manage CVE due dates and find overdue trackers.

This script:
1. Finds CVE tracker issues in RHAIENG
2. Extracts due dates from linked RHOAIENG child issues
3. Updates trackers missing due dates
4. Reports on overdue trackers

Usage:
    # List overdue trackers
    python scripts/cve/cve_due_dates.py --list-overdue

    # Show trackers missing due dates
    python scripts/cve/cve_due_dates.py --list-missing-dates

    # Update trackers with due dates from linked issues (dry run)
    python scripts/cve/cve_due_dates.py --sync-dates --dry-run

    # Update trackers with due dates from linked issues
    python scripts/cve/cve_due_dates.py --sync-dates

Requires:
    - JIRA_URL environment variable (or defaults to Red Hat Jira)
    - JIRA_TOKEN environment variable for authentication
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, date

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    import urllib.parse
    HAS_REQUESTS = False


@dataclass
class TrackerInfo:
    """Information about a CVE tracker and its linked issues."""
    key: str
    summary: str
    cve_id: str | None = None
    due_date: date | None = None
    linked_issues: list = field(default_factory=list)
    earliest_child_due_date: date | None = None
    status: str = ""

    @property
    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        return self.due_date < date.today()

    @property
    def days_overdue(self) -> int:
        if not self.due_date:
            return 0
        delta = date.today() - self.due_date
        return max(0, delta.days)

    @property
    def needs_due_date_sync(self) -> bool:
        """True if tracker has no due date but linked issues do."""
        return self.due_date is None and self.earliest_child_due_date is not None


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

            with urllib.request.urlopen(req) as resp:
                content = resp.read().decode()
                if content:
                    return json.loads(content)
                return {}

    def search_issues(self, jql: str, fields: str = "key,summary,status,labels,duedate,issuelinks",
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

    def get_issue(self, issue_key: str, fields: str = "key,summary,status,duedate,issuelinks") -> dict:
        """Get a single issue."""
        params = {"fields": fields}
        return self._request("GET", f"/rest/api/2/issue/{issue_key}", params=params)

    def update_issue(self, issue_key: str, fields: dict) -> None:
        """Update an issue's fields."""
        data = {"fields": fields}
        self._request("PUT", f"/rest/api/2/issue/{issue_key}", data=data)


def extract_cve_id(text: str) -> str | None:
    """Extract CVE ID from text."""
    match = re.search(r'CVE-\d{4}-\d+', text)
    return match.group() if match else None


def parse_date(date_str: str | None) -> date | None:
    """Parse a Jira date string to a date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_linked_issue_keys(issue: dict, link_type: str = "Blocks") -> list[str]:
    """Get keys of issues that this issue blocks (outward links)."""
    linked = []
    issuelinks = issue.get("fields", {}).get("issuelinks", [])
    for link in issuelinks:
        if link.get("type", {}).get("name") == link_type:
            if "outwardIssue" in link:
                linked.append(link["outwardIssue"]["key"])
    return linked


def find_cve_trackers(client: JiraClient, max_results: int = 500) -> list[TrackerInfo]:
    """Find CVE tracker issues in RHAIENG."""
    print("Searching for CVE trackers in RHAIENG...")

    # Get RHAIENG CVE issues (trackers)
    jql = 'project = RHAIENG AND labels in ("CVE") AND resolution = unresolved ORDER BY duedate ASC'
    issues = client.search_issues(jql, max_results=max_results)
    print(f"Found {len(issues)} RHAIENG CVE tracker issues")

    trackers = []
    for issue in issues:
        key = issue["key"]
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        due_date = parse_date(fields.get("duedate"))
        status = fields.get("status", {}).get("name", "")

        tracker = TrackerInfo(
            key=key,
            summary=summary,
            cve_id=extract_cve_id(summary),
            due_date=due_date,
            status=status,
        )

        # Get linked child issues
        linked_keys = get_linked_issue_keys(issue)
        tracker.linked_issues = linked_keys

        trackers.append(tracker)

    return trackers


def fetch_child_due_dates(client: JiraClient, trackers: list[TrackerInfo]) -> None:
    """Fetch due dates from linked child issues and find earliest."""
    print("\nFetching due dates from linked child issues...")

    # Collect all unique child issue keys
    all_child_keys = set()
    for tracker in trackers:
        all_child_keys.update(tracker.linked_issues)

    if not all_child_keys:
        print("No linked child issues found")
        return

    print(f"Fetching {len(all_child_keys)} child issues...")

    # Fetch child issues in batches
    child_due_dates: dict[str, date | None] = {}

    # Build JQL to fetch all child issues
    keys_list = list(all_child_keys)
    batch_size = 50

    for i in range(0, len(keys_list), batch_size):
        batch_keys = keys_list[i:i + batch_size]
        jql = f"key in ({','.join(batch_keys)})"
        issues = client.search_issues(jql, fields="key,duedate", max_results=len(batch_keys))

        for issue in issues:
            key = issue["key"]
            due_date = parse_date(issue.get("fields", {}).get("duedate"))
            child_due_dates[key] = due_date

    # Assign earliest due date to each tracker
    for tracker in trackers:
        child_dates = []
        for child_key in tracker.linked_issues:
            if child_key in child_due_dates and child_due_dates[child_key]:
                child_dates.append(child_due_dates[child_key])

        if child_dates:
            tracker.earliest_child_due_date = min(child_dates)


def list_overdue_trackers(trackers: list[TrackerInfo]) -> list[TrackerInfo]:
    """List trackers that are overdue."""
    overdue = [t for t in trackers if t.is_overdue]
    overdue.sort(key=lambda t: t.days_overdue, reverse=True)
    return overdue


def list_missing_due_dates(trackers: list[TrackerInfo]) -> list[TrackerInfo]:
    """List trackers missing due dates but with child due dates available."""
    missing = [t for t in trackers if t.needs_due_date_sync]
    missing.sort(key=lambda t: t.earliest_child_due_date or date.max)
    return missing


def sync_due_dates(client: JiraClient, trackers: list[TrackerInfo], dry_run: bool = False) -> int:
    """Sync due dates from child issues to trackers."""
    to_sync = [t for t in trackers if t.needs_due_date_sync]

    if not to_sync:
        print("\nNo trackers need due date sync")
        return 0

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Syncing due dates for {len(to_sync)} trackers...")

    synced = 0
    for tracker in to_sync:
        new_due_date = tracker.earliest_child_due_date
        if not new_due_date:
            continue

        date_str = new_due_date.strftime("%Y-%m-%d")
        print(f"  {tracker.key}: Setting due date to {date_str} (from child issues)")

        if not dry_run:
            try:
                client.update_issue(tracker.key, {"duedate": date_str})
                synced += 1
            except Exception as e:
                print(f"    ERROR: {e}")
        else:
            synced += 1

    return synced


def print_tracker_table(trackers: list[TrackerInfo], title: str) -> None:
    """Print a formatted table of trackers."""
    if not trackers:
        print(f"\n{title}: None found")
        return

    print(f"\n{title} ({len(trackers)} total):")
    print("-" * 100)
    print(f"{'Key':<15} {'CVE ID':<18} {'Due Date':<12} {'Overdue':<10} {'Status':<15} {'Summary':<30}")
    print("-" * 100)

    for t in trackers:
        due_str = t.due_date.strftime("%Y-%m-%d") if t.due_date else "None"
        overdue_str = f"{t.days_overdue}d" if t.is_overdue else "-"
        cve_str = t.cve_id or "-"
        summary_short = t.summary[:28] + "..." if len(t.summary) > 30 else t.summary

        print(f"{t.key:<15} {cve_str:<18} {due_str:<12} {overdue_str:<10} {t.status:<15} {summary_short:<30}")

    print("-" * 100)


def print_sync_preview(trackers: list[TrackerInfo]) -> None:
    """Print preview of due date sync."""
    to_sync = [t for t in trackers if t.needs_due_date_sync]

    if not to_sync:
        print("\nNo trackers need due date sync")
        return

    print(f"\nTrackers needing due date sync ({len(to_sync)} total):")
    print("-" * 100)
    print(f"{'Key':<15} {'CVE ID':<18} {'Current Due':<12} {'Child Due':<12} {'Summary':<40}")
    print("-" * 100)

    for t in to_sync:
        current_str = t.due_date.strftime("%Y-%m-%d") if t.due_date else "None"
        child_str = t.earliest_child_due_date.strftime("%Y-%m-%d") if t.earliest_child_due_date else "None"
        cve_str = t.cve_id or "-"
        summary_short = t.summary[:38] + "..." if len(t.summary) > 40 else t.summary

        print(f"{t.key:<15} {cve_str:<18} {current_str:<12} {child_str:<12} {summary_short:<40}")

    print("-" * 100)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage CVE due dates and find overdue trackers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List overdue trackers
  python scripts/cve_due_dates.py --list-overdue

  # Show trackers missing due dates
  python scripts/cve_due_dates.py --list-missing-dates

  # Preview due date sync
  python scripts/cve_due_dates.py --sync-dates --dry-run

  # Sync due dates from child issues to trackers
  python scripts/cve_due_dates.py --sync-dates

  # Show summary of all trackers
  python scripts/cve_due_dates.py --summary

Environment variables:
  JIRA_URL      Jira server URL (default: https://issues.redhat.com)
  JIRA_TOKEN    Personal access token for authentication
"""
    )
    parser.add_argument("--list-overdue", action="store_true",
                        help="List trackers that are past their due date")
    parser.add_argument("--list-missing-dates", action="store_true",
                        help="List trackers missing due dates but with child due dates")
    parser.add_argument("--sync-dates", action="store_true",
                        help="Sync due dates from child issues to trackers")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    parser.add_argument("--summary", action="store_true",
                        help="Show summary statistics")
    parser.add_argument("--max-results", type=int, default=500,
                        help="Maximum trackers to fetch (default: 500)")
    return parser.parse_args()


def main():
    args = parse_args()

    # Default to summary if no action specified
    if not any([args.list_overdue, args.list_missing_dates, args.sync_dates, args.summary]):
        args.summary = True

    jira_url = os.environ.get("JIRA_URL", "https://issues.redhat.com")
    jira_token = os.environ.get("JIRA_TOKEN")

    if not jira_token:
        print("ERROR: JIRA_TOKEN environment variable is required", file=sys.stderr)
        print("Set it with: export JIRA_TOKEN='your-token-here'", file=sys.stderr)
        sys.exit(1)

    client = JiraClient(jira_url, jira_token)

    print(f"Connecting to {jira_url}...")

    # Find all CVE trackers
    trackers = find_cve_trackers(client, args.max_results)

    if not trackers:
        print("\nNo CVE trackers found")
        return

    # Fetch child due dates for all trackers
    fetch_child_due_dates(client, trackers)

    # Execute requested actions
    if args.list_overdue:
        overdue = list_overdue_trackers(trackers)
        print_tracker_table(overdue, "OVERDUE CVE TRACKERS")

    if args.list_missing_dates:
        print_sync_preview(trackers)

    if args.sync_dates:
        synced = sync_due_dates(client, trackers, args.dry_run)
        action = "Would sync" if args.dry_run else "Synced"
        print(f"\n{action} due dates for {synced} trackers")

    if args.summary:
        print("\n" + "=" * 60)
        print("CVE TRACKER SUMMARY")
        print("=" * 60)

        total = len(trackers)
        with_due_date = len([t for t in trackers if t.due_date])
        without_due_date = len([t for t in trackers if not t.due_date])
        overdue = len([t for t in trackers if t.is_overdue])
        needs_sync = len([t for t in trackers if t.needs_due_date_sync])

        print(f"Total trackers:           {total}")
        print(f"With due date:            {with_due_date}")
        print(f"Without due date:         {without_due_date}")
        print(f"Overdue:                  {overdue}")
        print(f"Can sync from children:   {needs_sync}")
        print("=" * 60)

        if overdue > 0:
            print(f"\nTop 10 most overdue:")
            overdue_list = list_overdue_trackers(trackers)[:10]
            for t in overdue_list:
                print(f"  {t.key}: {t.days_overdue} days overdue - {t.cve_id or 'Unknown CVE'}")


if __name__ == "__main__":
    main()
