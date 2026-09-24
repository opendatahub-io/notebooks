"""Build an executable /fix-cve plan for a CVE group."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.cve.classify_ticket import Classification, classify_ticket

if TYPE_CHECKING:
    from scripts.cve.cve_groups import CVEGroup

CONSTRAINT_LINE_RE = re.compile(
    r"^(?P<package>[a-z0-9][a-z0-9._-]*)\s*>=\s*(?P<version>[^\s#]+)",
    re.IGNORECASE,
)
BEFORE_VERSION_RE = re.compile(
    r"\bbefore\s+(?P<version>\d[\w.+-]*)\b",
    re.IGNORECASE,
)
FIXED_IN_VERSION_RE = re.compile(
    r"\bfixed in (?:version\s+)?(?P<version>\d[\w.+-]*)\b",
    re.IGNORECASE,
)


@dataclass
class FixPlan:
    group: CVEGroup
    classification: Classification
    package: str
    floor_version: str
    constraint_line: str
    pr_branch: str
    pr_title: str
    repo: str
    verdict: str | None = None
    verdict_reason: str | None = None
    existing_constraint: str | None = None
    open_pr_url: str | None = None
    dry_run: bool = True

    @property
    def comment_keys(self) -> list[str]:
        keys = list(self.group.rhoaieng_keys) + list(self.group.rhaieng_keys)
        return sorted(set(keys))

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_key": self.group.group_key,
            "cve_id": self.group.cve_id,
            "branch": self.group.branch,
            "package": self.package,
            "floor_version": self.floor_version,
            "constraint_line": self.constraint_line,
            "pr_branch": self.pr_branch,
            "pr_title": self.pr_title,
            "repo": self.repo,
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "rhoaieng_count": len(self.group.rhoaieng_keys),
            "rhaieng_count": len(self.group.rhaieng_keys),
            "comment_keys": self.comment_keys,
            "existing_constraint": self.existing_constraint,
            "open_pr_url": self.open_pr_url,
            "dry_run": self.dry_run,
            "classification": self.classification.to_dict(),
        }


def normalize_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def parse_fixed_version(*texts: str) -> str | None:
    for text in texts:
        if not text:
            continue
        before = BEFORE_VERSION_RE.search(text)
        if before:
            return before.group("version")
        fixed = FIXED_IN_VERSION_RE.search(text)
        if fixed:
            return fixed.group("version")
    return None


def parse_constraints_text(text: str) -> dict[str, str]:
    floors: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = CONSTRAINT_LINE_RE.match(stripped)
        if match:
            floors[normalize_package_name(match.group("package"))] = match.group("version")
    return floors


def read_constraints_for_branch(
    branch: str,
    *,
    repo_root: Path | None = None,
    remote: str = "downstream",
) -> str:
    root = repo_root or Path.cwd()
    rel = "dependencies/constraints.txt"
    for ref in (f"{remote}/{branch}", f"origin/{branch}", branch):
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{rel}"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError, FileNotFoundError:
            continue

    local = root / rel
    if local.is_file():
        return local.read_text(encoding="utf-8")
    return ""


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in re.split(r"[.+-]", version):
        if piece.isdigit():
            parts.append(int(piece))
    return tuple(parts) if parts else (0,)


def constraint_satisfied(existing: str | None, required: str) -> bool:
    if not existing:
        return False
    return _version_tuple(existing) >= _version_tuple(required)


def find_open_pr(
    repo: str,
    cve_id: str,
    branch: str,
) -> str | None:
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--base",
                branch,
                "--search",
                cve_id,
                "--json",
                "url,title",
                "--limit",
                "5",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError, FileNotFoundError:
        return None

    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    for item in items:
        title = str(item.get("title") or "")
        if cve_id in title:
            return str(item.get("url") or "") or None
    return None


def build_fix_plan(
    group: CVEGroup,
    *,
    anchor_issue: dict[str, Any],
    repo: str = "red-hat-data-services/notebooks",
    repo_root: Path | None = None,
    dry_run: bool = True,
) -> FixPlan:
    classification = classify_ticket(anchor_issue)
    if classification.action not in {"autofix", "rpm_check"}:
        return FixPlan(
            group=group,
            classification=classification,
            package=classification.package or "",
            floor_version="",
            constraint_line="",
            pr_branch="",
            pr_title="",
            repo=repo,
            verdict=classification.verdict or "not_fixable",
            verdict_reason=classification.reason,
            dry_run=dry_run,
        )

    if classification.action == "rpm_check":
        return FixPlan(
            group=group,
            classification=classification,
            package=classification.package or "",
            floor_version="",
            constraint_line="",
            pr_branch="",
            pr_title="",
            repo=repo,
            verdict="research",
            verdict_reason="RPM CVE — run RHSA/VEX check before any PR.",
            dry_run=dry_run,
        )

    package = classification.package
    branch = classification.branch or group.branch
    if not package:
        return FixPlan(
            group=group,
            classification=classification,
            package="",
            floor_version="",
            constraint_line="",
            pr_branch="",
            pr_title="",
            repo=repo,
            verdict="needs_info",
            verdict_reason="Could not determine Python package name.",
            dry_run=dry_run,
        )

    fields = anchor_issue.get("fields") or {}
    description = str(fields.get("description") or "")
    summary = str(fields.get("summary") or "")
    floor_version = parse_fixed_version(summary, description)
    if not floor_version:
        return FixPlan(
            group=group,
            classification=classification,
            package=package,
            floor_version="",
            constraint_line="",
            pr_branch="",
            pr_title="",
            repo=repo,
            verdict="needs_info",
            verdict_reason="Could not determine fixed version from ticket text.",
            dry_run=dry_run,
        )

    normalized_package = normalize_package_name(package)
    constraint_line = f"{normalized_package}>={floor_version}"
    pr_branch = f"fix/cve-{group.cve_id}-{branch}"
    pr_title = f"fix(cve): {group.cve_id} bump {normalized_package} on {branch}"

    constraints_text = read_constraints_for_branch(branch, repo_root=repo_root)
    floors = parse_constraints_text(constraints_text)
    existing = floors.get(normalized_package)
    open_pr_url = find_open_pr(repo, group.cve_id, branch)

    verdict = None
    verdict_reason = None
    if constraint_satisfied(existing, floor_version):
        verdict = "already_fixed"
        verdict_reason = f"{normalized_package}>={existing} already in constraints.txt on {branch}"
    elif open_pr_url:
        verdict = "already_fixed"
        verdict_reason = f"Open PR already exists for {group.cve_id} on {branch}"

    return FixPlan(
        group=group,
        classification=classification,
        package=normalized_package,
        floor_version=floor_version,
        constraint_line=constraint_line,
        pr_branch=pr_branch,
        pr_title=pr_title,
        repo=repo,
        verdict=verdict,
        verdict_reason=verdict_reason,
        existing_constraint=existing,
        open_pr_url=open_pr_url,
        dry_run=dry_run,
    )


def format_plan(plan: FixPlan) -> str:
    action = plan.verdict or "commit"
    lines = [
        "┌─ Fix plan ───────────────────────────────────────────┐",
        f"│ Group:     {plan.group.group_key:<43} │",
        f"│ Package:   {plan.package or '-':<43} │",
        f"│ Floor:     {plan.constraint_line or '-':<43} │",
        f"│ Branch:    {plan.group.branch:<43} │",
        f"│ Repo:      {plan.repo:<43} │",
        f"│ PR branch: {plan.pr_branch or '-':<43} │",
        f"│ PR title:  {(plan.pr_title or '-')[:43]:<43} │",
        f"│ RHOAIENG:  {len(plan.group.rhoaieng_keys):<43} │",
        f"│ RHAIENG:   {len(plan.group.rhaieng_keys):<43} │",
        f"│ Verdict:   {action:<43} │",
    ]
    if plan.verdict_reason:
        reason = plan.verdict_reason[:43]
        lines.append(f"│ Reason:    {reason:<43} │")
    if plan.existing_constraint:
        lines.append(f"│ Existing:  {plan.package}>={plan.existing_constraint:<33} │")
    if plan.open_pr_url:
        url = plan.open_pr_url[:43]
        lines.append(f"│ Open PR:   {url:<43} │")
    if plan.comment_keys:
        preview = ", ".join(plan.comment_keys[:3])
        if len(plan.comment_keys) > 3:
            preview += f", … (+{len(plan.comment_keys) - 3})"
        lines.append(f"│ Tickets:   {preview[:43]:<43} │")
    if plan.dry_run and not plan.verdict:
        lines.append("│ Action:    would commit, open PR, comment tickets   │")
    lines.append("└──────────────────────────────────────────────────────┘")
    return "\n".join(lines)
