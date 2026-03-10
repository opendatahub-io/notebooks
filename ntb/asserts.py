"""Shared test assertion helpers."""

from __future__ import annotations


# see also https://pypi.org/project/pytest-assert-utils/
def assert_subdict(subdict: dict[str, str], superdict: dict[str, str]):
    """Assert that subdict is a subset of superdict (matching keys have equal values)."""
    __tracebackhide__ = True
    assert subdict == {k: superdict[k] for k in subdict if k in superdict}
