"""Shared pytest fixtures for UI tests."""

from __future__ import annotations

import sys

import pytest

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Session-scoped QApplication. Pytest-qt equivalent without the dep."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Do not call app.quit() — other fixtures may need it.
