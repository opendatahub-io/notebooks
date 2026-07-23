"""Regression coverage for shell-unquoted-var-in-dangerous-cmd in semgrep.yaml."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SEMGREP_YAML = ROOT / "semgrep.yaml"
RULE_ID = "shell-unquoted-var-in-dangerous-cmd"


def _dangerous_cmd_pattern() -> re.Pattern[str]:
    doc = yaml.safe_load(SEMGREP_YAML.read_text())
    for rule in doc["rules"]:
        if rule.get("id") == RULE_ID:
            return re.compile(rule["pattern-regex"])
    raise AssertionError(f"{RULE_ID} not found in {SEMGREP_YAML}")


@pytest.fixture(scope="module")
def pattern() -> re.Pattern[str]:
    return _dangerous_cmd_pattern()


@pytest.mark.parametrize(
    "line",
    [
        "rm $FILE",
        "rm\t$FILE",
        "rm ${FILE}",
        "cp $SRC $DST",
        "rm $FILE && echo ok",
        "rm $FILE || echo ok",
        "echo ok && rm $FILE",
        "echo ok || rm $OTHER",
    ],
)
def test_flags_unquoted_var_in_dangerous_cmd(pattern: re.Pattern[str], line: str) -> None:
    assert pattern.search(line), f"expected match for {line!r}"


@pytest.mark.parametrize(
    "line",
    [
        'rm "$FILE"',
        "rm '$FILE'",
        "rmdir $FILE",
        'rm "$FILE"\necho $OTHER',
        # Quoted rm must not match $OTHER after shell command separators.
        'rm "$FILE" && echo $OTHER',
        'rm "$FILE" || echo $OTHER',
        'rm "$FILE"; echo $OTHER',
        'rm "$FILE" | echo $OTHER',
        'rm "$FILE" & echo $OTHER',
    ],
)
def test_ignores_safe_or_other_command_vars(pattern: re.Pattern[str], line: str) -> None:
    assert not pattern.search(line), f"unexpected match for {line!r}"
