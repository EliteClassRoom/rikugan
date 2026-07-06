"""Tests for rikugan.ui.qt_compat — PySide6-only Qt surface."""

from __future__ import annotations

import unittest

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()
import rikugan.ui.qt_compat as qt_compat  # noqa: E402


class TestQtCompat(unittest.TestCase):
    def test_qt_core_symbols_exported(self):
        for name in ("Signal", "Qt", "QObject", "QTimer", "QEvent", "QThread"):
            self.assertTrue(hasattr(qt_compat, name), f"missing {name}")

    def test_qt_widget_symbols_exported(self):
        for name in (
            "QApplication",
            "QWidget",
            "QVBoxLayout",
            "QHBoxLayout",
            "QLabel",
            "QPushButton",
            "QPlainTextEdit",
            "QScrollArea",
            "QDialog",
            "QComboBox",
            "QLineEdit",
            "QCheckBox",
            "QMenu",
            "QMessageBox",
        ):
            self.assertTrue(hasattr(qt_compat, name), f"missing {name}")

    def test_qt_gui_symbols_exported(self):
        for name in ("QColor", "QFont", "QPalette", "QPainter", "QSyntaxHighlighter"):
            self.assertTrue(hasattr(qt_compat, name), f"missing {name}")

    def test_no_pyqt5_detection_symbols_remain(self):
        """PyQt5 detection is gone — these names must not be exported."""
        for name in ("QT_BINDING", "is_pyside6", "qt_flags", "qt_run", "_detect_binding"):
            self.assertFalse(
                hasattr(qt_compat, name),
                f"{name} should be removed (PySide6-only)",
            )

    def test_all_symbols_come_from_pyside6(self):
        """Every Qt symbol qt_compat exports must originate in PySide6."""
        import inspect

        for name in ("QWidget", "QVBoxLayout", "QTimer", "Signal", "Qt"):
            obj = getattr(qt_compat, name)
            module = inspect.getmodule(obj)
            self.assertIsNotNone(module, f"{name} has no resolvable module")
            self.assertTrue(
                module.__name__.startswith("PySide6"),
                f"{name} should come from PySide6, got {module.__name__}",
            )


if __name__ == "__main__":
    unittest.main()
