"""Resolve CVE work units from Jira for /fix-cve (RHAIENG-7190).

Groups ProdSec per-image tickets from RHOAIENG and RHAI by (CVE id, release
branch). RHAIENG parents are optional legacy context — fixes target one PR per
CVE per release branch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from scripts.cve.classify_ticket import _extract_branch, _extract_cve_ids, _labels, _summary
from scripts.cve.common import extract_cve_id

if TYPE_CHECKING:
    from scripts.cve.jira_client import JiraClient

NOTEBOOKS_IMAGES_COMPONENT = "Notebooks Images"
PRODSEC_PROJECTS = ("RHOAIENG", "RHAI")
BRANCH_SUFFIX_RE = re.compile(r"\[rhoai-(\d+\.\d+)]", re.IGNORECASE)
CVE_ID_RE = re.compile(r"^CVE-\d{4}-\d+$", re.IGNORECASE)
BRANCH_VALUE_RE = re.compile(r"^rhoai-\d+\.\d+$", re.IGNORECASE)

SEARCH_FIELDS = "key,summary,status,labels,description,issuetype,issuelinks,project,components,due"


@dataclass
class CVEGroup:
    """All Jira tickets for one CVE on one release branch."""

    cve_id: str
    branch: str
    rhoaieng_keys: list[str] = field(default_factory=list)
    rhai_keys: list[str] = field(default_factory=list)
    rhaieng_keys: list[str] = field(default_factory=list)
    summaries: dict[str, str] = field(default_factory=dict)

    @property
    def group_key(self) -> str:
        return f"{self.cve_id}:{self.branch}"

    @property
    def source_keys(self) -> list[str]:
        return list(self.rhoaieng_keys) + list(self.rhai_keys)

    @property
    def ticket_count(self) -> int:
        return len(self.source_keys) + len(self.rhaieng_keys)

    @property
    def anchor_key(self) -> str:
        if self.rhoaieng_keys:
            return self.rhoaieng_keys[0]
        if self.rhai_keys:
            return self.rhai_keys[0]
        if self.rhaieng_keys:
            return self.rhaieng_keys[0]
        return ""


def extract_version(summary: str) -> str | None:
    match = BRANCH_SUFFIX_RE.search(summary)
    if match:
        return f"rhoai-{match.group(1)}"
    return None


def get_blocking_issues(issue: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for link in (issue.get("fields") or {}).get("issuelinks") or []:
        if link.get("type", {}).get("name") == "Blocks" and "inwardIssue" in link:
            blockers.append(str(link["inwardIssue"]["key"]))
    return blockers


def _issue_cve_id(issue: dict[str, Any]) -> str | None:
    summary = _summary(issue)
    for label in _labels(issue):
        cve_id = extract_cve_id(label)
        if cve_id:
            return cve_id.upper()
    return extract_cve_id(summary)


def _is_notebooks_prodsec(issue: dict[str, Any]) -> bool:
    components = (issue.get("fields") or {}).get("components") or []
    for component in components:
        if component.get("name") == NOTEBOOKS_IMAGES_COMPONENT:
            return True
    summary = _summary(issue).lower()
    return "odh-workbench-jupyter" in summary or "odh-pipeline-runtime" in summary


def _validate_cve_id(cve_id: str) -> str:
    normalized = cve_id.strip().upper()
    if not CVE_ID_RE.match(normalized):
        raise ValueError(f"invalid CVE id: {cve_id!r}")
    return normalized


def _validate_branch(branch: str) -> str:
    normalized = branch.strip().lower()
    if not BRANCH_VALUE_RE.match(normalized):
        raise ValueError(f"invalid release branch: {branch!r}")
    return normalized


def _escape_jql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def notebooks_prodsec_jql(*, extra: str = "", unresolved_only: bool = True) -> str:
    """JQL for ProdSec Notebooks Images vulnerabilities in RHOAIENG and RHAI."""
    resolution = "AND resolution = Unresolved " if unresolved_only else ""
    projects = ", ".join(PRODSEC_PROJECTS)
    base = (
        f"project in ({projects}) AND issuetype in (Bug, Vulnerability, Weakness) "
        f"AND labels = SecurityTracking {resolution}"
        f'AND component = "{NOTEBOOKS_IMAGES_COMPONENT}"'
    )
    if extra:
        return f"{base} AND {extra} ORDER BY created DESC"
    return f"{base} ORDER BY created DESC"


# Backward-compatible alias used by older callers/tests.
notebooks_rhoaieng_jql = notebooks_prodsec_jql


def group_issues(issues: list[dict[str, Any]]) -> dict[tuple[str, str], CVEGroup]:
    groups: dict[tuple[str, str], CVEGroup] = {}

    for issue in issues:
        key = str(issue.get("key") or "")
        if not key:
            continue

        cve_id = _issue_cve_id(issue)
        summary = _summary(issue)
        branch = extract_version(summary) or _extract_branch(summary, "")
        if not cve_id or not branch:
            continue

        group_key = (cve_id.upper(), branch.lower())
        if group_key not in groups:
            groups[group_key] = CVEGroup(cve_id=cve_id.upper(), branch=branch.lower())

        group = groups[group_key]
        group.summaries[key] = summary

        project = str(((issue.get("fields") or {}).get("project") or {}).get("key") or "")
        if project == "RHOAIENG":
            if key not in group.rhoaieng_keys:
                group.rhoaieng_keys.append(key)
        elif project == "RHAI":
            if key not in group.rhai_keys:
                group.rhai_keys.append(key)
        elif project == "RHAIENG" and key not in group.rhaieng_keys:
            group.rhaieng_keys.append(key)

        for blocker in get_blocking_issues(issue):
            if blocker.startswith("RHAIENG-") and blocker not in group.rhaieng_keys:
                group.rhaieng_keys.append(blocker)

    for group in groups.values():
        group.rhoaieng_keys.sort()
        group.rhai_keys.sort()
        group.rhaieng_keys.sort()

    return groups


def fetch_prodsec_siblings(
    client: JiraClient,
    cve_id: str,
    branch: str,
    *,
    max_results: int = 500,
) -> list[dict[str, Any]]:
    cve_id = _validate_cve_id(cve_id)
    branch = _validate_branch(branch)
    jql = notebooks_prodsec_jql(
        extra=(f'labels = "{_escape_jql_string(cve_id)}" AND summary ~ "{_escape_jql_string(branch)}]"'),
    )
    return client.search_issues(jql, fields=SEARCH_FIELDS, max_results=max_results)


# Backward-compatible alias.
fetch_rhoaieng_siblings = fetch_prodsec_siblings


def fetch_groups_for_cve(
    client: JiraClient,
    cve_id: str,
    *,
    branch: str | None = None,
    max_results: int = 500,
) -> list[CVEGroup]:
    cve_id = _validate_cve_id(cve_id)
    extra = f'labels = "{_escape_jql_string(cve_id)}"'
    if branch:
        branch = _validate_branch(branch)
        extra += f' AND summary ~ "{_escape_jql_string(branch)}]"'
    issues = client.search_issues(
        notebooks_prodsec_jql(extra=extra),
        fields=SEARCH_FIELDS,
        max_results=max_results,
    )
    groups = list(group_issues(issues).values())
    if branch:
        groups = [g for g in groups if g.branch == branch]
    return sorted(groups, key=lambda g: (-len(g.source_keys), g.cve_id))


def group_from_issue(client: JiraClient, issue: dict[str, Any]) -> CVEGroup:
    key = str(issue.get("key") or "")
    cve_ids = _extract_cve_ids(_summary(issue), "", _labels(issue))
    branch = extract_version(_summary(issue)) or _extract_branch(_summary(issue), "")
    if not cve_ids or not branch:
        raise ValueError(f"{key}: missing CVE id or release branch in summary")

    cve_id = cve_ids[0]
    siblings = fetch_prodsec_siblings(client, cve_id, branch)
    by_key = {str(item.get("key")): item for item in siblings}
    by_key[key] = issue
    groups = group_issues(list(by_key.values()))
    group_key = (cve_id.upper(), branch.lower())
    if group_key not in groups:
        groups[group_key] = CVEGroup(
            cve_id=cve_id.upper(),
            branch=branch.lower(),
            rhoaieng_keys=[key] if key.startswith("RHOAIENG-") else [],
            rhai_keys=[key] if key.startswith("RHAI-") else [],
            rhaieng_keys=[key] if key.startswith("RHAIENG-") else [],
            summaries={key: _summary(issue)},
        )
    return groups[group_key]


def resolve_input(
    client: JiraClient,
    token: str,
    *,
    branch: str | None = None,
) -> list[CVEGroup]:
    token = token.strip()
    upper = token.upper()

    if upper.startswith("CVE-"):
        return fetch_groups_for_cve(client, upper, branch=branch)

    issue = client.get_issue(token, SEARCH_FIELDS)
    project = str(((issue.get("fields") or {}).get("project") or {}).get("key") or "")

    if project in PRODSEC_PROJECTS:
        group = group_from_issue(client, issue)
        if branch and group.branch != _validate_branch(branch):
            raise ValueError(f"{token} is on {group.branch}, not {branch}")
        return [group]

    if project == "RHAIENG":
        cve_ids = _extract_cve_ids(_summary(issue), "", _labels(issue))
        resolved_branch = extract_version(_summary(issue)) or _extract_branch(_summary(issue), "")
        if branch:
            resolved_branch = branch
        if not cve_ids or not resolved_branch:
            raise ValueError(f"{token}: missing CVE id or release branch")
        groups = fetch_groups_for_cve(client, cve_ids[0], branch=resolved_branch)
        if not groups:
            groups = [
                CVEGroup(
                    cve_id=cve_ids[0],
                    branch=resolved_branch.lower(),
                    rhaieng_keys=[token],
                    summaries={token: _summary(issue)},
                )
            ]
        elif token not in groups[0].rhaieng_keys:
            groups[0].rhaieng_keys.append(token)
        return groups

    raise ValueError(f"Unsupported issue project for /fix-cve: {project or token}")


def discover_open_groups(client: JiraClient, *, max_results: int = 500) -> list[CVEGroup]:
    issues = client.search_issues(
        notebooks_prodsec_jql(),
        fields=SEARCH_FIELDS,
        max_results=max_results,
    )
    groups = list(group_issues(issues).values())
    return sorted(groups, key=lambda g: (-len(g.source_keys), g.cve_id))
