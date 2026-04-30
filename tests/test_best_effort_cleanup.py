"""Tests for BestEffortCleanup context manager.

See the class docstring in docker_utils.py for design rationale.
"""

from __future__ import annotations

import pytest

from tests.containers.docker_utils import BestEffortCleanup


class TestBestEffortCleanup:
    """Verifies the two core behaviors:
    - cleanup errors propagate when nothing else is failing
    - cleanup errors are suppressed when another exception is active
    """

    def test_body_runs_normally(self):
        executed = False
        with BestEffortCleanup():
            executed = True
        assert executed

    def test_error_propagates_when_no_active_exception(self):
        with pytest.raises(RuntimeError, match="cleanup boom"):
            with BestEffortCleanup():
                raise RuntimeError("cleanup boom")

    def test_error_suppressed_when_exc_type_signals_active(self):
        # exc_type=ValueError tells the CM that a ValueError is being handled,
        # so the RuntimeError from cleanup should be suppressed
        with BestEffortCleanup(exc_type=ValueError):
            raise RuntimeError("cleanup boom")

    def test_successful_cleanup_with_exc_type(self):
        executed = False
        with BestEffortCleanup(exc_type=ValueError):
            executed = True
        assert executed

    def test_auto_detects_active_exception_in_except_block(self):
        suppressed = False
        try:
            raise ValueError("original")
        except ValueError:
            with BestEffortCleanup():
                raise RuntimeError("cleanup boom") from None
            suppressed = True
        assert suppressed

    def test_auto_detects_no_active_exception_outside_except(self):
        with pytest.raises(RuntimeError, match="cleanup boom"):
            with BestEffortCleanup():
                raise RuntimeError("cleanup boom")

    def test_finally_with_body_exception(self):
        """The primary use case: body raises, cleanup also raises, body error wins."""
        cleanup_ran = False
        with pytest.raises(ValueError, match="body boom"):
            try:
                raise ValueError("body boom")
            finally:
                with BestEffortCleanup():
                    cleanup_ran = True
                    raise RuntimeError("cleanup boom")
        assert cleanup_ran

    def test_finally_without_body_exception(self):
        """Cleanup error propagates when body succeeded."""
        with pytest.raises(RuntimeError, match="cleanup boom"):
            try:
                pass
            finally:
                with BestEffortCleanup():
                    raise RuntimeError("cleanup boom")
