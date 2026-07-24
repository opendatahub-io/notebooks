from __future__ import annotations

from odh_ci_agent import agent_context


def test_is_agent_meta_path() -> None:
    assert agent_context.is_agent_meta_path(".agents/plugins/github/SKILL.md") is True
    assert agent_context.is_agent_meta_path(".agents/skills/foo/SKILL.md") is True
    assert agent_context.is_agent_meta_path("ci/agentic-reviewer/src/odh_ci_agent/review_pr.py") is False
    assert agent_context.is_agent_meta_path("jupyter/minimal/Dockerfile") is False


def test_filter_changed_files_counts_omitted() -> None:
    files = [
        {"filename": "ci/foo.py"},
        {"filename": ".agents/plugins/github/SKILL.md"},
        {"filename": ".agents/skills/review/SKILL.md"},
        {"filename": "Makefile"},
    ]

    kept, omitted = agent_context.filter_changed_files(files)

    assert [file_info["filename"] for file_info in kept] == ["ci/foo.py", "Makefile"]
    assert omitted == 2


def test_prepare_review_context_excludes_agent_meta_files() -> None:
    files = [
        {"filename": "ci/foo.py", "patch": "@@ diff", "additions": 1, "deletions": 0, "status": "modified"},
        {
            "filename": ".agents/plugins/github/SKILL.md",
            "patch": "@@ plugin",
            "additions": 1,
            "deletions": 0,
            "status": "added",
        },
    ]

    kept, omitted = agent_context.filter_changed_files(files)

    assert [file_info["filename"] for file_info in kept] == ["ci/foo.py"]
    assert omitted == 1
