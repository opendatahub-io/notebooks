"""Unit tests for scripts/cve/cve_due_dates.py — date parsing, overdue logic, filtering."""

from __future__ import annotations

from datetime import date, timedelta

from scripts.cve.cve_due_dates import (
    TrackerInfo,
    extract_cve_id,
    get_linked_issue_keys,
    list_missing_due_dates,
    list_overdue_trackers,
    parse_date,
)


# ---------------------------------------------------------------------------
# extract_cve_id
# ---------------------------------------------------------------------------

class TestExtractCveId:
    def test_standard_id(self) -> None:
        assert extract_cve_id("CVE-2025-12345 some vuln") == "CVE-2025-12345"

    def test_embedded(self) -> None:
        assert extract_cve_id("Fix for CVE-2024-9999 in glibc") == "CVE-2024-9999"

    def test_no_match(self) -> None:
        assert extract_cve_id("no cve here") is None

    def test_long_id(self) -> None:
        assert extract_cve_id("CVE-2024-1234567") == "CVE-2024-1234567"


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_valid(self) -> None:
        assert parse_date("2025-03-15") == date(2025, 3, 15)

    def test_none(self) -> None:
        assert parse_date(None) is None

    def test_empty(self) -> None:
        assert parse_date("") is None

    def test_invalid(self) -> None:
        assert parse_date("not-a-date") is None

    def test_wrong_format(self) -> None:
        assert parse_date("03/15/2025") is None


# ---------------------------------------------------------------------------
# get_linked_issue_keys
# ---------------------------------------------------------------------------

class TestGetLinkedIssueKeys:
    def test_outward_blocks(self) -> None:
        issue = {
            "fields": {
                "issuelinks": [
                    {
                        "type": {"name": "Blocks"},
                        "outwardIssue": {"key": "RHOAIENG-100"},
                    }
                ]
            }
        }
        assert get_linked_issue_keys(issue) == ["RHOAIENG-100"]

    def test_inward_link_ignored(self) -> None:
        issue = {
            "fields": {
                "issuelinks": [
                    {
                        "type": {"name": "Blocks"},
                        "inwardIssue": {"key": "RHAIENG-200"},
                    }
                ]
            }
        }
        assert get_linked_issue_keys(issue) == []

    def test_different_link_type_ignored(self) -> None:
        issue = {
            "fields": {
                "issuelinks": [
                    {
                        "type": {"name": "Clones"},
                        "outwardIssue": {"key": "FOO-1"},
                    }
                ]
            }
        }
        assert get_linked_issue_keys(issue) == []

    def test_no_links(self) -> None:
        assert get_linked_issue_keys({"fields": {}}) == []

    def test_multiple_outward(self) -> None:
        issue = {
            "fields": {
                "issuelinks": [
                    {"type": {"name": "Blocks"}, "outwardIssue": {"key": "A-1"}},
                    {"type": {"name": "Blocks"}, "outwardIssue": {"key": "A-2"}},
                ]
            }
        }
        assert get_linked_issue_keys(issue) == ["A-1", "A-2"]


# ---------------------------------------------------------------------------
# TrackerInfo properties
# ---------------------------------------------------------------------------

class TestTrackerInfo:
    def test_not_overdue_when_no_due_date(self) -> None:
        t = TrackerInfo(key="X-1", summary="test")
        assert not t.is_overdue
        assert t.days_overdue == 0

    def test_overdue_past_date(self) -> None:
        t = TrackerInfo(key="X-2", summary="test", due_date=date.today() - timedelta(days=5))
        assert t.is_overdue
        assert t.days_overdue == 5

    def test_not_overdue_future_date(self) -> None:
        t = TrackerInfo(key="X-3", summary="test", due_date=date.today() + timedelta(days=1))
        assert not t.is_overdue
        assert t.days_overdue == 0

    def test_not_overdue_today(self) -> None:
        t = TrackerInfo(key="X-4", summary="test", due_date=date.today())
        assert not t.is_overdue

    def test_needs_due_date_sync(self) -> None:
        t = TrackerInfo(key="X-5", summary="test", earliest_child_due_date=date(2025, 6, 1))
        assert t.needs_due_date_sync

    def test_no_sync_when_has_due_date(self) -> None:
        t = TrackerInfo(key="X-6", summary="test", due_date=date(2025, 6, 1), earliest_child_due_date=date(2025, 6, 1))
        assert not t.needs_due_date_sync

    def test_no_sync_when_no_child_date(self) -> None:
        t = TrackerInfo(key="X-7", summary="test")
        assert not t.needs_due_date_sync


# ---------------------------------------------------------------------------
# list_overdue_trackers
# ---------------------------------------------------------------------------

class TestListOverdueTrackers:
    def test_filters_and_sorts(self) -> None:
        trackers = [
            TrackerInfo(key="A", summary="a", due_date=date.today() - timedelta(days=2)),
            TrackerInfo(key="B", summary="b", due_date=date.today() + timedelta(days=1)),
            TrackerInfo(key="C", summary="c", due_date=date.today() - timedelta(days=10)),
            TrackerInfo(key="D", summary="d"),
        ]
        result = list_overdue_trackers(trackers)
        assert [t.key for t in result] == ["C", "A"]

    def test_empty(self) -> None:
        assert list_overdue_trackers([]) == []


# ---------------------------------------------------------------------------
# list_missing_due_dates
# ---------------------------------------------------------------------------

class TestListMissingDueDates:
    def test_filters_syncable(self) -> None:
        trackers = [
            TrackerInfo(key="A", summary="a", earliest_child_due_date=date(2025, 7, 1)),
            TrackerInfo(key="B", summary="b", due_date=date(2025, 6, 1)),
            TrackerInfo(key="C", summary="c", earliest_child_due_date=date(2025, 5, 1)),
            TrackerInfo(key="D", summary="d"),
        ]
        result = list_missing_due_dates(trackers)
        assert [t.key for t in result] == ["C", "A"]

    def test_empty(self) -> None:
        assert list_missing_due_dates([]) == []
