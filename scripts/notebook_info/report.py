"""Generate and optionally post the Notebook status report."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .config import RELEASES, ReleaseConfig
from .jira import jira_client_from_env
from .org_pulse import org_pulse_client_from_env
from .slack import post_report

EASTERN = ZoneInfo("America/New_York")


def jira_link(config: ReleaseConfig, base_url: str) -> str:
    if config.jira_filter_id is not None:
        return f"{base_url.rstrip('/')}/issues?filter={config.jira_filter_id}"
    return f"{base_url.rstrip('/')}/issues/?jql={quote(config.jql, safe='')}"


def org_pulse_link(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/#/releases/reports?report=container-health-index"


def format_date(value: str | None) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%b/%d") if value else "—"


def format_grades(grades: dict[str, int]) -> str:
    ordered = [grade for grade in ("A", "B", "C", "D", "E", "F", "Unknown") if grades.get(grade, 0) > 0]
    return ", ".join(f"{grade}:{grades[grade]}" for grade in ordered) if ordered else "—"


def format_grades_summary(grades: dict[str, dict[str, int]]) -> str:
    return "\n".join(f"{release}: {format_grades(grade_counts)}" for release, grade_counts in grades.items())


def build_report(
    counts: dict[str, int],
    freezes: dict[str, str | None],
    grades: dict[str, dict[str, int]],
    jira_base_url: str,
    org_pulse_base_url: str,
) -> str:
    now = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M ET")
    lines = [f"Notebook Status — {now}", "- Release - Open - CF - Grade"]
    for release, config in RELEASES.items():
        count = counts[release]
        count_text = f"<{jira_link(config, jira_base_url)}|{count}>" if count else str(count)
        lines.append(
            f"- {release} · {count_text} · {format_date(freezes.get(release))} · {format_grades(grades[release])}"
        )
    lines.append(f"- <{org_pulse_link(org_pulse_base_url)}|Org Pulse Container Health Index>")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chi-only", action="store_true", help="Print CHI grades only")
    parser.add_argument("--dry-run", action="store_true", help="Do not post to Slack")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--slack-channel", help="Slack channel ID")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    dry_run = args.dry_run or os.getenv("DRY_RUN", "").lower() in {"1", "true", "yes"}
    org_pulse = org_pulse_client_from_env()
    grades = org_pulse.chi_grades(RELEASES)
    if args.chi_only:
        print(format_grades_summary(grades))
        return

    counts = {release: jira_client_from_env().count(config.jql) for release, config in RELEASES.items()}
    freezes = org_pulse.code_freezes(RELEASES)
    jira_base_url = os.getenv("JIRA_URL")
    org_pulse_base_url = os.getenv("ORG_PULSE_UI_URL")
    if not jira_base_url or not org_pulse_base_url:
        raise SystemExit("Missing environment variables: JIRA_URL, ORG_PULSE_UI_URL")
    report = build_report(counts, freezes, grades, jira_base_url, org_pulse_base_url)
    print(report)
    if not dry_run:
        channel = args.slack_channel or os.getenv("SLACK_CHANNEL")
        if not channel:
            raise SystemExit("Missing environment variable: SLACK_CHANNEL")
        post_report(report, channel)


if __name__ == "__main__":
    main()
