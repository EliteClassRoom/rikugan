"""Tests for rikugan.ui.chat_view — pure logic helpers."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

# Stub all heavy submodules that chat_view imports
for _mod_name in [
    "rikugan.agent.turn",
    "rikugan.core.types",
]:
    if _mod_name not in sys.modules:
        _stub = types.ModuleType(_mod_name)
        # Add commonly-needed attrs
        for _attr in [
            "PlanView", "TurnEvent",
            "TurnEventType", "Message", "Role",
        ]:
            setattr(_stub, _attr, MagicMock())
        sys.modules[_mod_name] = _stub

from rikugan.ui.chat_view import _is_hidden_system_user_message, _TOOL_GROUP_MIN_CALLS  # noqa: E402


# ---------------------------------------------------------------------------
# _is_hidden_system_user_message
# ---------------------------------------------------------------------------

class TestIsHiddenSystemUserMessage(unittest.TestCase):
    def test_empty_string_returns_false(self):
        self.assertFalse(_is_hidden_system_user_message(""))

    def test_none_equivalent_empty_returns_false(self):
        self.assertFalse(_is_hidden_system_user_message(""))

    def test_system_prefix_returns_true(self):
        self.assertTrue(_is_hidden_system_user_message("[SYSTEM] some hint"))

    def test_system_prefix_with_leading_whitespace(self):
        self.assertTrue(_is_hidden_system_user_message("   [SYSTEM] some hint"))

    def test_regular_message_returns_false(self):
        self.assertFalse(_is_hidden_system_user_message("Hello world"))

    def test_lowercase_system_returns_false(self):
        self.assertFalse(_is_hidden_system_user_message("[system] hint"))

    def test_partial_system_keyword_returns_false(self):
        self.assertFalse(_is_hidden_system_user_message("SYSTEM"))

    def test_system_in_middle_returns_false(self):
        self.assertFalse(_is_hidden_system_user_message("not [SYSTEM] hint"))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestChatViewConstants(unittest.TestCase):
    def test_tool_group_min_calls_is_positive(self):
        self.assertGreater(_TOOL_GROUP_MIN_CALLS, 0)

    def test_tool_group_min_calls_value(self):
        self.assertEqual(_TOOL_GROUP_MIN_CALLS, 2)


if __name__ == "__main__":
    unittest.main()
