from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from scripts.cve import cve_due_dates

if TYPE_CHECKING:
    from pytest_subtests import SubTests


def test_extract_cve_id(subtests: SubTests) -> None:
    cases = [
        ("CVE-2025-12345", "CVE-2025-12345"),
        ("Tracker for CVE-2024-9999 in foo", "CVE-2024-9999"),
        ("no cve here", None),
        ("", None),
    ]
    for text, expected in cases:
        with subtests.test(msg=f"extract_cve_id({text!r})"):
            assert cve_due_dates.extract_cve_id(text) == expected


def test_parse_date(subtests: SubTests) -> None:
    cases: list[tuple[str | None, date | None]] = [
        ("2026-03-15", date(2026, 3, 15)),
        ("2025-12-31", date(2025, 12, 31)),
        (None, None),
        ("", None),
        ("not-a-date", None),
        ("03/15/2026", None),
    ]
    for date_str, expected in cases:
        with subtests.test(msg=f"parse_date({date_str!r})"):
            assert cve_due_dates.parse_date(date_str) == expected


def test_get_linked_issue_keys() -> None:
    issue = {
        "fields": {
            "issuelinks": [
                {
                    "type": {"name": "Blocks"},
                    "outwardIssue": {"key": "RHOAIENG-100"},
                },
                {
                    "type": {"name": "Blocks"},
                    "outwardIssue": {"key": "RHOAIENG-200"},
                },
                {
                    "type": {"name": "Relates"},
                    "outwardIssue": {"key": "RHOAIENG-300"},
                },
                {
                    "type": {"name": "Blocks"},
                    "inwardIssue": {"key": "RHAIENG-50"},
                },
            ]
        }
    }
    result = cve_due_dates.get_linked_issue_keys(issue)
    assert result == ["RHOAIENG-100", "RHOAIENG-200"]


def test_get_linked_issue_keys_empty() -> None:
    assert cve_due_dates.get_linked_issue_keys({"fields": {}}) == []
    assert cve_due_dates.get_linked_issue_keys({"fields": {"issuelinks": []}}) == []


def test_tracker_info_is_overdue() -> None:
    yesterday = date.today() - timedelta(days=1)
    tracker = cve_due_dates.TrackerInfo(key="RHAIENG-1", summary="CVE-2025-1", due_date=yesterday)
    assert tracker.is_overdue is True


def test_tracker_info_not_overdue() -> None:
    tomorrow = date.today() + timedelta(days=1)
    tracker = cve_due_dates.TrackerInfo(key="RHAIENG-1", summary="CVE-2025-1", due_date=tomorrow)
    assert tracker.is_overdue is False


def test_tracker_info_no_due_date_not_overdue() -> None:
    tracker = cve_due_dates.TrackerInfo(key="RHAIENG-1", summary="CVE-2025-1", due_date=None)
    assert tracker.is_overdue is False


def test_tracker_info_days_overdue() -> None:
    five_days_ago = date.today() - timedelta(days=5)
    tracker = cve_due_dates.TrackerInfo(key="RHAIENG-1", summary="CVE-2025-1", due_date=five_days_ago)
    assert tracker.days_overdue == 5


def test_tracker_info_days_overdue_zero_when_no_due_date() -> None:
    tracker = cve_due_dates.TrackerInfo(key="RHAIENG-1", summary="CVE-2025-1")
    assert tracker.days_overdue == 0


def test_tracker_info_needs_due_date_sync() -> None:
    tracker = cve_due_dates.TrackerInfo(
        key="RHAIENG-1",
        summary="CVE-2025-1",
        due_date=None,
        earliest_child_due_date=date(2026, 6, 1),
    )
    assert tracker.needs_due_date_sync is True


def test_tracker_info_no_sync_when_has_due_date() -> None:
    tracker = cve_due_dates.TrackerInfo(
        key="RHAIENG-1",
        summary="CVE-2025-1",
        due_date=date(2026, 1, 1),
        earliest_child_due_date=date(2026, 6, 1),
    )
    assert tracker.needs_due_date_sync is False


def test_tracker_info_no_sync_when_no_child_date() -> None:
    tracker = cve_due_dates.TrackerInfo(
        key="RHAIENG-1",
        summary="CVE-2025-1",
        due_date=None,
        earliest_child_due_date=None,
    )
    assert tracker.needs_due_date_sync is False


def test_list_overdue_trackers_sorted_by_days() -> None:
    t1 = cve_due_dates.TrackerInfo(
        key="RHAIENG-1", summary="a", due_date=date.today() - timedelta(days=3),
    )
    t2 = cve_due_dates.TrackerInfo(
        key="RHAIENG-2", summary="b", due_date=date.today() - timedelta(days=10),
    )
    t3 = cve_due_dates.TrackerInfo(
        key="RHAIENG-3", summary="c", due_date=date.today() + timedelta(days=5),
    )
    result = cve_due_dates.list_overdue_trackers([t1, t2, t3])
    assert len(result) == 2
    assert result[0].key == "RHAIENG-2"
    assert result[1].key == "RHAIENG-1"


def test_list_missing_due_dates() -> None:
    t1 = cve_due_dates.TrackerInfo(
        key="RHAIENG-1", summary="a",
        due_date=None, earliest_child_due_date=date(2026, 6, 1),
    )
    t2 = cve_due_dates.TrackerInfo(
        key="RHAIENG-2", summary="b",
        due_date=date(2026, 1, 1), earliest_child_due_date=date(2026, 3, 1),
    )
    t3 = cve_due_dates.TrackerInfo(
        key="RHAIENG-3", summary="c",
        due_date=None, earliest_child_due_date=None,
    )
    result = cve_due_dates.list_missing_due_dates([t1, t2, t3])
    assert len(result) == 1
    assert result[0].key == "RHAIENG-1"
