"""conftest — shared pytest fixtures for Rikugan UI tests."""

from __future__ import annotations

import pytest

# Detect the Qt binding without requiring the full 'rikugan' package prefix.
# The panel runs in hosts (IDA / Binary Ninja) that already load a Qt binding;
# we reuse the same compatibility layer that the panel uses.
try:
    from rikugan.ui.qt_compat import QApplication
except ModuleNotFoundError:
    # Fallback: assume PySide6 is available in the test environment
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        from PyQt5.QtWidgets import QApplication


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
