"""Decorator-style iterable subtests for static/manifest checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from pytest import Subtests


def with_subtests[T, U](
    subtests: Subtests,
    iterable: Iterable[T],
    msg: str | None = None,
    quiet: bool = False,
    **fixed_kw: object,
) -> Callable[[Callable[[T], U]], None]:
    """Decorator that immediately runs the decorated body as a subtest per item.

    Multi-statement functions can be used for iterable-driven subtests without a
    manual ``for`` / ``with subtests.test`` pair. Pass ``quiet=True`` to avoid
    opening a subtest context for passing items (less SUBPASSED noise).

    >>> @with_subtests(subtests, range(3))
    >>> def _(i: int):
    >>>     assert i < 3
    """

    def run(f: Callable[[T], U]) -> None:
        __tracebackhide__ = True

        for item in iterable:
            if not quiet:
                with subtests.test(msg=msg, item=item, **fixed_kw):
                    f(item)
            else:
                # Quiet: only open a subtest context when the body fails, so
                # successful items do not emit SUBPASSED noise.
                # pytest.fail.Exception is OutcomeException (BaseException), not Exception.
                try:
                    f(item)
                except Exception, pytest.fail.Exception:
                    with subtests.test(msg=msg, item=item, **fixed_kw):
                        # Re-raise inside subtest so pytest captures and continues.
                        raise

    return run
