"""Coverage for tests.with_subtests.with_subtests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.with_subtests import with_subtests

if TYPE_CHECKING:
    import pytest
    from pytest import Subtests

pytest_plugins = ("pytester",)


def test_with_subtests_quiet_runs_all_items(subtests: Subtests) -> None:
    seen: list[int] = []

    @with_subtests(subtests, range(3), quiet=True)
    def _(u: int) -> None:
        seen.append(u)
        assert u < 3

    assert seen == [0, 1, 2]


def test_with_subtests_noisy_runs_all_items(subtests: Subtests) -> None:
    seen: list[int] = []

    @with_subtests(subtests, range(3), quiet=False)
    def _(u: int) -> None:
        seen.append(u)
        assert u < 3

    assert seen == [0, 1, 2]


def test_with_subtests_quiet_pytest_fail_continues(pytester: pytest.Pytester) -> None:
    """pytest.fail.Exception is not Exception; quiet mode must still wrap and continue."""
    pytester.makepyfile(
        # language=Python
        """
        import pytest
        from tests.with_subtests import with_subtests

        def test_inner(subtests):
            seen = []

            @with_subtests(subtests, (0, 1, 2), quiet=True)
            def _(u):
                seen.append(u)
                if u == 0:
                    pytest.fail("intentional quiet-mode fail")

            assert seen == [0, 1, 2]
        """
    )
    result = pytester.runpytest("-p", "no:cacheprovider")
    # Subtest failure + parent "contains failed subtests" → two failed outcomes.
    # Later items still ran: seen assert passed (no AssertionError about seen).
    result.assert_outcomes(failed=2)
    out = result.stdout.str()
    assert "Failed: intentional quiet-mode fail" in out
    assert "SUBFAILED(item=0)" in out
    assert "assert seen ==" not in out
    assert "assert [0] ==" not in out
