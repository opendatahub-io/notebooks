#!/usr/bin/env python3
"""Classify a Jira CVE ticket for the /fix-cve skill.

Deterministic gate: package type, ticket role, and recommended action.
The skill must run this before any git or PR step.

Usage:
    python scripts/cve/classify_ticket.py RHAIENG-6341
    python scripts/cve/classify_ticket.py --issue-json ticket.json
    python scripts/cve/classify_ticket.py --dry-run RHAIENG-6341
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.cve.jira_client import JiraClient

PACKAGE_TYPES = ("python", "rpm", "go", "java", "npm", "unknown")
TICKET_ROLES = ("rhaieng_parent", "rhoaieng_child", "other")
ACTIONS = ("autofix", "rpm_check", "skip", "needs_info")
VERDICTS = (
    "not_fixable",
    "needs_info",
    "already_fixed",
    "not_a_bug",
    "committed",
    "no_changes",
    "blocked",
    "research",
)

GO_MODULE_RE = re.compile(
    r"(?:github\.com|golang\.org|gopkg\.in|go\.etcd\.io)/[\w./-]+",
    re.IGNORECASE,
)
MAVEN_COORD_RE = re.compile(r"^[\w.-]+:[\w.-]+(?::[\w.-]+)?$")
RPM_NEVRA_RE = re.compile(
    r"\b\d+:\d[\w.+-]+-\d[\w.+-]+(?:\.el\d|\.module\+)",
    re.IGNORECASE,
)
BRANCH_RE = re.compile(r"\[(rhoai-\d+\.\d+)\]", re.IGNORECASE)
CVE_IDS_RE = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)

JAVA_PACKAGE_HINTS = (
    "jackson",
    "log4j",
    "com.fasterxml",
    "org.apache.maven",
    "org.apache.logging",
    "org.slf4j",
)
GO_PACKAGE_HINTS = (
    "github.com/docker/docker",
    "github.com/moby",
    "github.com/containerd",
    "github.com/opencontainers/runc",
    "golang.org/x/crypto",
    "x/crypto",
    "skopeo",
    "moby",
    "containerd",
    "runc",
)
NPM_PACKAGE_HINTS = ("codeserver", "code-server", "node_modules", "npm/")


@dataclass(frozen=True)
class Classification:
    """Result of classify_ticket()."""

    issue_key: str
    package_type: str
    ticket_role: str
    action: str
    reason: str
    package: str | None = None
    branch: str | None = None
    cve_ids: tuple[str, ...] = ()
    verdict: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["cve_ids"] = list(self.cve_ids)
        return data


def _labels(issue: dict[str, Any]) -> list[str]:
    fields = issue.get("fields") or {}
    return [str(label) for label in fields.get("labels") or []]


def _summary(issue: dict[str, Any]) -> str:
    return str((issue.get("fields") or {}).get("summary") or "")


def _description(issue: dict[str, Any]) -> str:
    return str((issue.get("fields") or {}).get("description") or "")


def _issue_type(issue: dict[str, Any]) -> str:
    issuetype = (issue.get("fields") or {}).get("issuetype") or {}
    return str(issuetype.get("name") or "")


def _project_key(issue: dict[str, Any]) -> str:
    project = (issue.get("fields") or {}).get("project") or {}
    return str(project.get("key") or issue.get("key", "").split("-")[0])


def _ecosystem_label(labels: list[str]) -> str | None:
    for label in labels:
        if label.startswith("ecosystem:"):
            return label.split(":", 1)[1].lower()
    return None


def _extract_branch(summary: str, description: str) -> str | None:
    for text in (summary, description):
        match = BRANCH_RE.search(text)
        if match:
            return match.group(1).lower()
        branch_match = re.search(r"branch:\s*(rhoai-\d+\.\d+)", text, re.IGNORECASE)
        if branch_match:
            return branch_match.group(1).lower()
    return None


def _extract_cve_ids(summary: str, description: str, labels: list[str]) -> tuple[str, ...]:
    found: list[str] = []
    for text in (summary, description):
        found.extend(CVE_IDS_RE.findall(text))
    for label in labels:
        if label.upper().startswith("CVE-"):
            found.append(label.upper())
    # Preserve order, dedupe case-insensitively.
    seen: set[str] = set()
    ordered: list[str] = []
    for cve_id in found:
        normalized = cve_id.upper()
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return tuple(ordered)


def _has_blocked_children(description: str, issue_links: list[dict[str, Any]] | None) -> bool:
    if "Blocked Issues" in description:
        return True
    for link in issue_links or []:
        outward = link.get("outwardIssue") or {}
        outward_key = str(outward.get("key") or "")
        if outward_key.startswith("RHOAIENG-"):
            return True
    return False


def classify_ticket_role(issue: dict[str, Any]) -> str:
    project = _project_key(issue)
    summary = _summary(issue)
    description = _description(issue)
    labels = _labels(issue)
    issue_type = _issue_type(issue)
    issue_links = (issue.get("fields") or {}).get("issuelinks")

    if project == "RHOAIENG":
        if issue_type == "Vulnerability":
            return "rhoaieng_child"
        if any(label.startswith("pscomponent:") for label in labels):
            return "rhoaieng_child"
        if "rhoai/" in summary.lower() or "odh-wb-" in summary.lower():
            return "rhoaieng_child"

    if project == "RHAIENG" and "CVE" in labels:
        if _has_blocked_children(description, issue_links):
            return "rhaieng_parent"

    return "other"


def _extract_python_package(summary: str) -> str | None:
    # CVE-2026-59205 Pillow: description [rhoai-3.4]
    match = re.match(
        r"^CVE-\d{4}-\d+\s+([A-Za-z][\w.-]*)\s*:",
        summary,
    )
    if match:
        return match.group(1).lower()
    return None


def _extract_package_name(summary: str, package_type: str) -> str | None:
    if package_type == "python":
        python_name = _extract_python_package(summary)
        if python_name:
            return python_name
        # Fallback: first token before version suffix.
        head = summary.split("[", 1)[0].strip()
        token = head.split()[0] if head else ""
        if token and not token.upper().startswith("CVE-"):
            return token.lower()

    if package_type == "go":
        match = GO_MODULE_RE.search(summary)
        if match:
            return match.group(0).lower()
        return summary.split("[", 1)[0].strip().split()[0].lower() or None

    if package_type == "java":
        head = summary.split("[", 1)[0].strip()
        if ":" in head:
            return head.split()[0].lower()
        for hint in JAVA_PACKAGE_HINTS:
            if hint in head.lower():
                return hint
        return head.split()[0].lower() or None

    if package_type == "rpm":
        head = summary.split("[", 1)[0].strip()
        return head.split()[0].lower() if head else None

    if package_type == "npm":
        lowered = summary.lower()
        for hint in NPM_PACKAGE_HINTS:
            if hint in lowered:
                return hint
        return None

    return None


def classify_package_type(issue: dict[str, Any]) -> str:
    summary = _summary(issue)
    description = _description(issue)
    labels = _labels(issue)
    text = f"{summary}\n{description}".lower()
    ecosystem = _ecosystem_label(labels)

    if ecosystem in {"golang", "go"}:
        return "go"
    if ecosystem == "rpm":
        return "rpm"
    if ecosystem in {"maven", "java"}:
        return "java"
    if ecosystem in {"npm", "nodejs"}:
        return "npm"
    if ecosystem in {"pypi", "python"}:
        return "python"

    if GO_MODULE_RE.search(summary) or any(hint in text for hint in GO_PACKAGE_HINTS):
        return "go"
    if RPM_NEVRA_RE.search(summary) or (
        "ecosystem:** rpm" in description.lower() or "**ecosystem:** rpm" in description.lower()
    ):
        return "rpm"
    if MAVEN_COORD_RE.match(summary.split("[", 1)[0].strip()) or any(hint in text for hint in JAVA_PACKAGE_HINTS):
        return "java"
    if any(hint in text for hint in NPM_PACKAGE_HINTS):
        return "npm"

    if _extract_python_package(summary):
        return "python"

    return "unknown"


def classify_action(
    package_type: str,
    ticket_role: str,
    *,
    issue_key: str,
) -> tuple[str, str | None, str]:
    if ticket_role == "rhoaieng_child":
        return (
            "skip",
            "not_fixable",
            "Per-image RHOAIENG tracker — fix via the RHAIENG parent for this release.",
        )

    if ticket_role != "rhaieng_parent":
        return (
            "needs_info",
            "needs_info",
            f"{issue_key} is not a RHAIENG parent CVE tracker.",
        )

    if package_type == "python":
        return ("autofix", None, "Python RHAIENG parent — apply constraints.txt fix.")

    if package_type == "rpm":
        return (
            "rpm_check",
            None,
            "RHEL RPM RHAIENG parent — check RHSA/VEX before any PR (see references/03-rpm-rhsa-vex.md).",
        )

    if package_type == "go":
        return (
            "skip",
            "not_fixable",
            "Go module CVE (oc/skopeo/moby/containerd/runc) — not fixable via pip constraints.",
        )

    if package_type == "java":
        return (
            "skip",
            "not_fixable",
            "Java/Maven transitive CVE — not fixable via pip constraints.",
        )

    if package_type == "npm":
        return (
            "skip",
            "not_fixable",
            "npm/codeserver CVE — outside Python pip autofix scope.",
        )

    return (
        "needs_info",
        "needs_info",
        "Could not determine package type — gather ecosystem details before proceeding.",
    )


def classify_ticket(issue: dict[str, Any]) -> Classification:
    issue_key = str(issue.get("key") or "")
    ticket_role = classify_ticket_role(issue)
    package_type = classify_package_type(issue)
    action, verdict, reason = classify_action(package_type, ticket_role, issue_key=issue_key)
    summary = _summary(issue)
    labels = _labels(issue)
    description = _description(issue)

    package = _extract_package_name(summary, package_type)
    branch = _extract_branch(summary, description)

    if action == "autofix" and (not package or not branch):
        action = "needs_info"
        verdict = "needs_info"
        reason = "Missing package or branch — cannot group for autofix."

    return Classification(
        issue_key=issue_key,
        package_type=package_type,
        ticket_role=ticket_role,
        action=action,
        verdict=verdict,
        reason=reason,
        package=package,
        branch=branch,
        cve_ids=_extract_cve_ids(summary, description, labels),
    )


def _issue_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.issue_json:
        with open(args.issue_json, encoding="utf-8") as handle:
            return json.load(handle)

    if not args.issue_key:
        raise SystemExit("issue key or --issue-json is required")

    # Offline replay: minimal fixture lookup for local tests without Jira.
    fixture_root = args.fixture_dir.resolve()
    fixture_path = (fixture_root / f"{args.issue_key}.json").resolve()
    if fixture_path.parent != fixture_root:
        raise SystemExit("issue key must resolve to a direct fixture file")
    if fixture_path.is_file():
        with open(fixture_path, encoding="utf-8") as handle:
            return json.load(handle)

    client = JiraClient.from_env()
    return client.get_issue(
        args.issue_key,
        "summary,description,labels,issuetype,issuelinks,project",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue_key", nargs="?", help="Jira issue key, e.g. RHAIENG-6341")
    parser.add_argument("--issue-json", help="Path to a Jira issue JSON export")
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/unit/scripts/cve/fixtures/classify"),
        help="Directory of offline issue fixtures keyed by issue key",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print classification only; never mutate git/Jira (default behavior)",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    issue = _issue_from_args(args)
    result = classify_ticket(issue)
    payload = result.to_dict()
    payload["dry_run"] = bool(args.dry_run)
    indent = 2 if args.pretty else None
    print(json.dumps(payload, indent=indent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
