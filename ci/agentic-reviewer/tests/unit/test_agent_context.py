from __future__ import annotations

from odh_ci_agent.agent_context import filter_changed_files


def test_filter_changed_files_keeps_agents_paths() -> None:
    files = [
        {"filename": "src/main.py", "status": "modified"},
        {"filename": ".agents/plugins/foo/SKILL.md", "status": "added"},
        {"filename": ".agents/skills/bar/SKILL.md", "status": "added"},
    ]

    kept, omitted = filter_changed_files(files)

    assert omitted == 0
    assert [entry["filename"] for entry in kept] == [
        "src/main.py",
        ".agents/plugins/foo/SKILL.md",
        ".agents/skills/bar/SKILL.md",
    ]
