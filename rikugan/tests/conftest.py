"""conftest — shared pytest fixtures for Rikugan UI tests."""

from __future__ import annotations

import pytest

# Reuse the same Qt compatibility layer that the panel uses.
# Rikugan is PySide6-only; qt_compat centralizes the binding import.
from rikugan.ui.qt_compat import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Provide a singleton QApplication for UI widget tests.

    Qt requires a QApplication instance to exist before any widgets can be
    constructed.  Using ``scope="session"`` means a single instance is created
    once and shared across all tests in this session, which is the correct
    pattern for Qt test suites.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Don't quit() here — leave the singleton alive so that Qt cleans up
    # via its normal shutdown sequence when the process exits.
