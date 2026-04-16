"""Tests for rikugan.ui.qt_compat — Qt compatibility shim."""

from __future__ import annotations

import unittest

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()
import rikugan.ui.qt_compat as qt_compat  # noqa: E402


class TestQtCompat(unittest.TestCase):
    def test_is_pyside6_returns_true(self):
        self.assertTrue(qt_compat.is_pyside6())

    def test_qt_binding_constant(self):
        self.assertEqual(qt_compat.QT_BINDING, "PySide6")

    def test_qt_core_symbols_exported(self):
        for name in ("Signal", "Qt", "QObject", "QTimer"):
            self.assertTrue(hasattr(qt_compat, name), f"missing {name}")
        self.assertTrue(qt_compat.is_pyside6())

    def test_qt_widget_symbols_exported(self):
        for name in (
            "QApplication", "QWidget", "QVBoxLayout", "QHBoxLayout",
            "QLabel", "QPushButton", "QPlainTextEdit", "QScrollArea",
            "QDialog", "QComboBox", "QLineEdit", "QCheckBox",
            "QMenu", "QMessageBox",
        ):
            self.assertTrue(hasattr(qt_compat, name), f"missing {name}")


if __name__ == "__main__":
    unittest.main()
