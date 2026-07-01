"""Tests for rikugan.ui.chat_view — pure logic helpers."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

# Stub all heavy submodules that chat_view imports.
# Reinstall them unconditionally because other tests may have left behind
# incomplete stubs in sys.modules.  Each stub has a ``__getattr__``
# fallback so any missing attribute resolves to a fresh MagicMock,
# keeping this test file resilient to new names added by the
# production code.


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        m = MagicMock()
        object.__setattr__(self, name, m)
        return m


for _mod_name in [
    "rikugan.agent.turn",
    "rikugan.core.types",
]:
    _stub = _StubModule(_mod_name)
    # Add commonly-needed attrs
    for _attr in [
        "PlanView", "TurnEvent",
        "TurnEventType", "Message", "Role",
        "ToolCall", "ToolResult",
    ]:
        setattr(_stub, _attr, MagicMock())
    sys.modules[_mod_name] = _stub

# Other tests may leave stubbed UI modules behind; force fresh imports.
# Note: we must also pop the parent package ``rikugan.ui.theme`` so
# that Python can re-import its submodules from disk — a stub parent
# (a ``types.ModuleType`` without ``__path__``) would otherwise block
# the relative ``from .theme.manager import ...`` resolution that
# ``markdown.py`` performs at import time.
for _mod_name in [
    "rikugan.ui.chat_view",
    "rikugan.ui.message_widgets",
    "rikugan.ui.plan_view",
    "rikugan.ui.tool_widgets",
    "rikugan.ui.styles",
    "rikugan.ui.theme",
    "rikugan.ui.theme.manager",
    "rikugan.ui.theme.tokens",
    "rikugan.ui.markdown",
]:
    sys.modules.pop(_mod_name, None)

from rikugan.ui.bulk_renamer import BulkRenamerWidget  # noqa: E402
from rikugan.ui.chat_view import _TOOL_GROUP_MIN_CALLS, _is_hidden_system_user_message  # noqa: E402

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


class TestBulkRenamerLookup(unittest.TestCase):
    def test_find_row_iterates_table(self):
        """``_find_row_for_address`` walks the table rows; verify
        the stub's item() / data() contract is honored."""
        # ``BulkRenamerWidget`` is a QWidget subclass; constructing it via
        # ``__new__`` skips the Qt widget initialization (which would
        # require a live ``QApplication`` and a fully-built UI tree) so we
        # can unit-test the table-row lookup logic in isolation.
        widget = BulkRenamerWidget.__new__(BulkRenamerWidget)

        # Build a 2-row stub table where row 1 holds our address.
        row1_item = MagicMock()
        row1_item.data.return_value = 0x401000
        table = MagicMock()
        table.rowCount.return_value = 2
        table.item.side_effect = lambda r, c: row1_item if r == 1 else None
        widget._table = table
        self.assertEqual(widget._find_row_for_address(0x401000), 1)
        table.rowCount.assert_called()


if __name__ == "__main__":
    unittest.main()
