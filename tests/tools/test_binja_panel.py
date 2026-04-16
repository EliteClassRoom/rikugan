"""Tests for rikugan.binja.ui.panel — Binary Ninja QWidget wrapper."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock

from tests.qt_stubs import ensure_pyside6_stubs, _qt_class
ensure_pyside6_stubs()

# Stub out binaryninja and the heavy rikugan modules panel.py imports
sys.modules.setdefault("binaryninja", types.ModuleType("binaryninja"))

_panel_core_mod = types.ModuleType("rikugan.ui.panel_core")
_panel_core_mod.RikuganPanelCore = _qt_class("RikuganPanelCore")
sys.modules.setdefault("rikugan.ui.panel_core", _panel_core_mod)

_session_mod = types.ModuleType("rikugan.binja.ui.session_controller")
_session_mod.BinaryNinjaSessionController = MagicMock()
sys.modules["rikugan.binja.ui.session_controller"] = _session_mod

from rikugan.binja.ui.panel import RikuganPanel  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_panel() -> RikuganPanel:
    """Create a RikuganPanel bypassing __init__ and inject a mock _core."""
    panel = object.__new__(RikuganPanel)
    panel._core = MagicMock()
    panel.parent = MagicMock(return_value=None)
    panel.setParent = MagicMock()
    return panel


# ---------------------------------------------------------------------------
# explicit delegation methods
# ---------------------------------------------------------------------------

class TestRikuganPanelDelegation(unittest.TestCase):
    def test_prefill_delegates_to_core(self):
        panel = _make_panel()
        panel.prefill_input("hello", auto_submit=True)
        panel._core.prefill_input.assert_called_once_with("hello", auto_submit=True)

    def test_prefill_defaults_auto_submit_false(self):
        panel = _make_panel()
        panel.prefill_input("text")
        panel._core.prefill_input.assert_called_once_with("text", auto_submit=False)

    def test_shutdown_delegates_to_core(self):
        panel = _make_panel()
        core = panel._core
        panel.shutdown()
        core.shutdown.assert_called_once()
        self.assertIsNone(panel._core)

    def test_on_database_changed_delegates_to_core(self):
        panel = _make_panel()
        panel.on_database_changed("/path/to/new.bndb")
        panel._core.on_database_changed.assert_called_once_with("/path/to/new.bndb")


# ---------------------------------------------------------------------------
# mount — layout integration logic
# ---------------------------------------------------------------------------

class TestRikuganPanelMount(unittest.TestCase):
    def test_mount_adds_to_existing_layout_when_not_in_it(self):
        panel = _make_panel()
        parent = MagicMock()
        mock_layout = MagicMock()
        mock_layout.indexOf.return_value = -1
        parent.layout.return_value = mock_layout
        panel.mount(parent)
        mock_layout.addWidget.assert_called_once_with(panel)

    def test_mount_skips_addWidget_when_already_in_layout(self):
        panel = _make_panel()
        parent = MagicMock()
        mock_layout = MagicMock()
        mock_layout.indexOf.return_value = 2  # already present
        parent.layout.return_value = mock_layout
        panel.mount(parent)
        mock_layout.addWidget.assert_not_called()

    def test_mount_sets_parent_when_different(self):
        panel = _make_panel()
        parent = MagicMock()
        parent.__ne__ = lambda self, other: True  # parent() != parent
        mock_parent_widget = MagicMock()
        panel.parent = MagicMock(return_value=mock_parent_widget)
        mock_layout = MagicMock()
        mock_layout.indexOf.return_value = -1
        parent.layout.return_value = mock_layout
        panel.setParent = MagicMock()
        panel.mount(parent)
        panel.setParent.assert_called_once_with(parent)


if __name__ == "__main__":
    unittest.main()
