"""Tests for rikugan.binja.bootstrap — BN plugin registration and helpers."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stubs — must be installed before importing the module
# ---------------------------------------------------------------------------

# Ensure binaryninja stub exists as a real module (bootstrap imports it at top level)
_bn_stub = types.ModuleType("binaryninja")
sys.modules.setdefault("binaryninja", _bn_stub)
sys.modules.setdefault("binaryninjaui", None)  # type: ignore[assignment]

# Stub rikugan.binja.ui dependencies that require Qt
_panel_mod = types.ModuleType("rikugan.binja.ui.panel")
_panel_mod.RikuganPanel = type("RikuganPanel", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("rikugan.binja.ui.panel", _panel_mod)

_actions_mod = types.ModuleType("rikugan.binja.ui.actions")
_actions_mod.ACTION_DEFS = ()  # type: ignore[attr-defined]
_actions_mod.build_context = MagicMock(return_value={})  # type: ignore[attr-defined]
sys.modules.setdefault("rikugan.binja.ui.actions", _actions_mod)

_fn_utils_mod = types.ModuleType("rikugan.binja.tools.fn_utils")
_fn_utils_mod.get_function_at = MagicMock(return_value=None)  # type: ignore[attr-defined]
_fn_utils_mod.get_function_name = MagicMock(return_value="")  # type: ignore[attr-defined]
sys.modules.setdefault("rikugan.binja.tools.fn_utils", _fn_utils_mod)

from rikugan.binja import bootstrap as bnj  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers to manage module-level state
# ---------------------------------------------------------------------------

def _reset_globals():
    bnj._PANEL = None
    bnj._LAST_BV = None
    bnj._REGISTERED = False
    bnj._SIDEBAR_REGISTERED = False


# ---------------------------------------------------------------------------
# _navigate_cb
# ---------------------------------------------------------------------------

class TestNavigateCb(unittest.TestCase):
    def setUp(self):
        _reset_globals()

    def test_returns_false_when_no_bv(self):
        bnj._LAST_BV = None
        result = bnj._navigate_cb(0x1234)
        self.assertFalse(result)

    def test_returns_true_when_navigate_succeeds(self):
        mock_bv = MagicMock()
        mock_bv.navigate.return_value = True
        bnj._LAST_BV = mock_bv
        result = bnj._navigate_cb(0x1234)
        self.assertTrue(result)

    def test_tries_multiple_views(self):
        mock_bv = MagicMock()
        # First view fails, second succeeds
        mock_bv.navigate.side_effect = [False, True]
        bnj._LAST_BV = mock_bv
        result = bnj._navigate_cb(0x1234)
        self.assertTrue(result)

    def test_navigate_exception_continues(self):
        mock_bv = MagicMock()
        mock_bv.navigate.side_effect = [Exception("boom"), True]
        bnj._LAST_BV = mock_bv
        result = bnj._navigate_cb(0x1234)
        self.assertTrue(result)

    def test_returns_false_when_all_navigate_fail(self):
        mock_bv = MagicMock()
        mock_bv.navigate.return_value = False
        bnj._LAST_BV = mock_bv
        with patch.object(bnj, "bnui", None):
            result = bnj._navigate_cb(0x1234)
        self.assertFalse(result)

    def test_no_navigate_attr(self):
        mock_bv = MagicMock(spec=[])  # no navigate attribute
        bnj._LAST_BV = mock_bv
        with patch.object(bnj, "bnui", None):
            result = bnj._navigate_cb(0x1234)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# _update_context
# ---------------------------------------------------------------------------

class TestUpdateContext(unittest.TestCase):
    def setUp(self):
        _reset_globals()

    def test_sets_last_bv(self):
        mock_bv = MagicMock()
        with patch.object(bnj, "set_binary_ninja_context", MagicMock()), \
             patch.object(bnj, "_get_sidebar_panel", return_value=None):
            bnj._update_context(mock_bv, 0x1234)
        self.assertIs(bnj._LAST_BV, mock_bv)

    def test_calls_set_binary_ninja_context(self):
        mock_bv = MagicMock()
        mock_set_ctx = MagicMock()
        with patch.object(bnj, "set_binary_ninja_context", mock_set_ctx), \
             patch.object(bnj, "_get_sidebar_panel", return_value=None):
            bnj._update_context(mock_bv, 0x100)
        mock_set_ctx.assert_called_once()

    def test_changed_view_notifies_panel(self):
        mock_old_bv = MagicMock()
        mock_new_bv = MagicMock()
        bnj._LAST_BV = mock_old_bv
        mock_panel = MagicMock()
        mock_panel.on_database_changed = MagicMock()
        with patch.object(bnj, "set_binary_ninja_context", MagicMock()), \
             patch.object(bnj, "_get_sidebar_panel", return_value=mock_panel), \
             patch.object(bnj, "get_database_path", return_value="/path/to.bndb"):
            bnj._update_context(mock_new_bv)
        mock_panel.on_database_changed.assert_called_once_with("/path/to.bndb")

    def test_same_view_does_not_notify_panel(self):
        mock_bv = MagicMock()
        bnj._LAST_BV = mock_bv
        mock_panel = MagicMock()
        with patch.object(bnj, "set_binary_ninja_context", MagicMock()), \
             patch.object(bnj, "_get_sidebar_panel", return_value=mock_panel):
            bnj._update_context(mock_bv)
        mock_panel.on_database_changed.assert_not_called()


# ---------------------------------------------------------------------------
# _active_sidebar
# ---------------------------------------------------------------------------

class TestActiveSidebar(unittest.TestCase):
    def test_returns_none_when_bnui_is_none(self):
        with patch.object(bnj, "bnui", None):
            result = bnj._active_sidebar()
        self.assertIsNone(result)

    def test_returns_none_when_no_ui_context_class(self):
        mock_bnui = MagicMock(spec=[])  # no UIContext attr
        with patch.object(bnj, "bnui", mock_bnui):
            result = bnj._active_sidebar()
        self.assertIsNone(result)

    def test_returns_none_when_active_context_is_none(self):
        mock_bnui = MagicMock()
        mock_bnui.UIContext.activeContext.return_value = None
        with patch.object(bnj, "bnui", mock_bnui):
            result = bnj._active_sidebar()
        self.assertIsNone(result)

    def test_returns_sidebar_on_success(self):
        mock_sidebar = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.sidebar.return_value = mock_sidebar
        mock_bnui = MagicMock()
        mock_bnui.UIContext.activeContext.return_value = mock_ctx
        with patch.object(bnj, "bnui", mock_bnui):
            result = bnj._active_sidebar()
        self.assertIs(result, mock_sidebar)


# ---------------------------------------------------------------------------
# _get_sidebar_panel
# ---------------------------------------------------------------------------

class TestGetSidebarPanel(unittest.TestCase):
    def test_returns_none_when_no_sidebar(self):
        with patch.object(bnj, "_active_sidebar", return_value=None):
            result = bnj._get_sidebar_panel(create_if_missing=True)
        self.assertIsNone(result)

    def test_returns_none_when_widget_none_and_no_create(self):
        mock_sidebar = MagicMock()
        mock_sidebar.widget.return_value = None
        with patch.object(bnj, "_active_sidebar", return_value=mock_sidebar):
            result = bnj._get_sidebar_panel(create_if_missing=False)
        self.assertIsNone(result)

    def test_activates_when_create_if_missing(self):
        mock_sidebar = MagicMock()
        mock_sidebar.widget.return_value = None
        with patch.object(bnj, "_active_sidebar", return_value=mock_sidebar):
            bnj._get_sidebar_panel(create_if_missing=True)
        mock_sidebar.activate.assert_called_once_with(bnj.RIKUGAN_SIDEBAR_NAME)

    def test_returns_panel_from_widget(self):
        mock_panel = MagicMock(spec=object)
        mock_widget = MagicMock()
        mock_widget.panel = mock_panel
        mock_sidebar = MagicMock()
        mock_sidebar.widget.return_value = mock_widget
        with patch.object(bnj, "_active_sidebar", return_value=mock_sidebar):
            bnj._get_sidebar_panel()
        # sidebar.widget was called
        mock_sidebar.widget.assert_called()


# ---------------------------------------------------------------------------
# _action_callback
# ---------------------------------------------------------------------------

class TestActionCallback(unittest.TestCase):
    def setUp(self):
        _reset_globals()

    def test_callback_calls_handler(self):
        handler = MagicMock(return_value="explain this")
        mock_bv = MagicMock()
        mock_panel = MagicMock()
        cb = bnj._action_callback(handler, auto_submit=False)
        with patch.object(bnj, "_update_context"), \
             patch.object(bnj, "_ensure_panel", return_value=mock_panel), \
             patch.object(bnj, "build_context", return_value={"func": "main"}):
            cb(mock_bv, 0x1000)
        handler.assert_called_once_with({"func": "main"})

    def test_callback_prefills_panel(self):
        handler = MagicMock(return_value="explain this")
        mock_panel = MagicMock()
        cb = bnj._action_callback(handler, auto_submit=True)
        with patch.object(bnj, "_update_context"), \
             patch.object(bnj, "_ensure_panel", return_value=mock_panel), \
             patch.object(bnj, "build_context", return_value={}):
            cb(MagicMock(), 0x1000)
        mock_panel.prefill_input.assert_called_once_with("explain this", auto_submit=True)

    def test_callback_no_prefill_when_empty_text(self):
        handler = MagicMock(return_value="")
        mock_panel = MagicMock()
        cb = bnj._action_callback(handler, auto_submit=False)
        with patch.object(bnj, "_update_context"), \
             patch.object(bnj, "_ensure_panel", return_value=mock_panel), \
             patch.object(bnj, "build_context", return_value={}):
            cb(MagicMock(), 0x1000)
        mock_panel.prefill_input.assert_not_called()

    def test_callback_no_prefill_when_none_text(self):
        handler = MagicMock(return_value=None)
        mock_panel = MagicMock()
        cb = bnj._action_callback(handler, auto_submit=False)
        with patch.object(bnj, "_update_context"), \
             patch.object(bnj, "_ensure_panel", return_value=mock_panel), \
             patch.object(bnj, "build_context", return_value={}):
            cb(MagicMock(), 0x1000)
        mock_panel.prefill_input.assert_not_called()


# ---------------------------------------------------------------------------
# register_plugin / _register_sidebar idempotency
# ---------------------------------------------------------------------------

class TestRegistrationIdempotency(unittest.TestCase):
    def setUp(self):
        _reset_globals()

    def test_register_sidebar_noop_when_already_registered(self):
        bnj._SIDEBAR_REGISTERED = True
        bnj._register_sidebar()  # must not change state or raise
        self.assertTrue(bnj._SIDEBAR_REGISTERED)

    def test_register_sidebar_noop_when_bnui_none(self):
        with patch.object(bnj, "bnui", None):
            bnj._register_sidebar()
        self.assertFalse(bnj._SIDEBAR_REGISTERED)

    def test_register_plugin_noop_when_already_registered(self):
        bnj._REGISTERED = True
        bnj.register_plugin()
        self.assertTrue(bnj._REGISTERED)


if __name__ == "__main__":
    unittest.main()
