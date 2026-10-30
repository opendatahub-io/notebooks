"""Configuration for the Notebook status report."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseConfig:
    version: str
    jql: str
    jira_filter_id: int | None
    code_freeze: str | None


RELEASES: dict[str, ReleaseConfig] = {
    "2.25": ReleaseConfig(
        version="2.25",
        jql=(
            "project IN (RHAI, RHOAIENG) AND issuetype = Vulnerability "
            'AND component = "Notebooks Images" AND affectedVersion = rhoai-2.25 '
            "AND statusCategory != Done"
        ),
        jira_filter_id=115488,
        code_freeze=None,
    ),
    "3.3": ReleaseConfig(
        version="3.3",
        jql=(
            "project = RHAI AND issuetype in (Bug, Vulnerability, Weakness) "
            "AND resolution = Unresolved AND labels = SecurityTracking "
            'AND component = "Notebooks Images" AND summary ~ "\\"[rhoai-3.3]\\""'
        ),
        jira_filter_id=None,
        code_freeze="2026-01-16",
    ),
    "3.4": ReleaseConfig(
        version="3.4",
        jql=(
            "project IN (RHAI, RHOAIENG) AND issuetype = Vulnerability "
            'AND component = "Notebooks Images" AND affectedVersion = rhoai-3.4 '
            "AND statusCategory != Done"
        ),
        jira_filter_id=115490,
        code_freeze=None,
    ),
    "3.5": ReleaseConfig(
        version="3.5",
        jql=(
            "project IN (RHAI, RHOAIENG) AND issuetype = Vulnerability "
            'AND component = "Notebooks Images" '
            'AND affectedVersion = "3.5 GA RHOAI RELEASE" '
            "AND statusCategory != Done"
        ),
        jira_filter_id=115489,
        code_freeze=None,
    ),
    "3.6": ReleaseConfig(
        version="3.6",
        jql=(
            "project = RHAI AND issuetype in (Bug, Vulnerability, Weakness) "
            "AND resolution = Unresolved AND labels = SecurityTracking "
            'AND component = "Notebooks Images" AND summary ~ "\\"[rhoai-3.6]\\""'
        ),
        jira_filter_id=None,
        code_freeze=None,
    ),
}
