"""Tests for the height-cached label optimisation that prevents layout cascade.

Background: ``AssistantMessageWidget._content`` is a word-wrapped label whose
``setText`` triggers Qt's ``heightForWidth()`` protocol. In a chat with many
long messages, every layout pass walks every sibling label and pays
``O(text_length)`` per sibling — this is the root cause of "whole-IDA lag when
the conversation grows large".

``_HeightCachedLabel`` opts out of the protocol (``hasHeightForWidth -> False``)
and pins its height once per render, reducing layout cost to ``O(1)`` for the
widget. These tests assert that the optimisation is actually wired into the
live streaming path, not just defined as dead code.
"""

from __future__ import annotations

import unittest

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

from rikugan.ui import message_widgets as _mw  # noqa: E402
from rikugan.ui.message_widgets import (  # noqa: E402
    AssistantMessageWidget,
    _HeightCachedLabel,
)


class TestHeightCachedLabelContract(unittest.TestCase):
    """The label class itself must opt out of the heightForWidth protocol."""

    def test_has_height_for_width_returns_false(self):
        # If this returns True, Qt will call heightForWidth() on every layout
        # pass — the exact O(N x msg_length) cascade we are avoiding.
        label = _HeightCachedLabel()
        self.assertFalse(label.hasHeightForWidth())

    def test_pin_height_sets_fixed_height_from_height_for_width(self):
        # pin_height() must translate heightForWidth(width) into a fixed
        # height so the widget no longer participates in the protocol.
        # pin_height() calls ``QLabel.heightForWidth(self, w)`` explicitly
        # on the base class, so we patch the class attribute — not the
        # instance — to inject a deterministic return value.
        label = _HeightCachedLabel()
        label.width = lambda: 400  # type: ignore[method-assign]
        captured: dict[str, int] = {}
        label.setFixedHeight = lambda h: captured.__setitem__("h", int(h))  # type: ignore[method-assign]

        original = _mw.QLabel.heightForWidth
        try:
            _mw.QLabel.heightForWidth = lambda self, w: 24  # type: ignore[assignment]
            label.pin_height()
        finally:
            _mw.QLabel.heightForWidth = original  # type: ignore[assignment]

        self.assertEqual(captured.get("h"), 24)

    def test_pin_height_noop_when_width_zero(self):
        # Before the widget is laid out, width() may return 0. pin_height()
        # must not pin a bogus fixed height in that case (otherwise the
        # label collapses to 0px on first render).
        label = _HeightCachedLabel()
        label.width = lambda: 0  # type: ignore[method-assign]
        called: list[int] = []
        label.setFixedHeight = lambda h: called.append(h)  # type: ignore[method-assign]

        label.pin_height()
        self.assertEqual(called, [])


class TestAssistantMessageWidgetUsesCachedLabel(unittest.TestCase):
    """The live streaming widget must use the height-cached label."""

    def test_content_label_is_height_cached_label(self):
        # This is the wire-in assertion. If _content is a plain QLabel,
        # the layout-cascade optimisation is dead code and the lag bug
        # regresses.
        widget = AssistantMessageWidget()
        self.assertIsInstance(
            widget._content,
            _HeightCachedLabel,
            "AssistantMessageWidget._content must be a _HeightCachedLabel to "
            "opt out of the O(N x msg_length) heightForWidth layout cascade.",
        )


class TestThinkingBlockUsesCachedLabel(unittest.TestCase):
    """``_ThinkingBlock._content`` is a sibling of the assistant content label.

    ``set_thinking`` calls ``setText`` every ~100ms during streaming (the
    same hot path as ``_content``). If it stays a plain ``QLabel``, the
    cascade still fires from the thinking side even after the content side
    was fixed — which is why fixing only ``_content`` reduced but did not
    eliminate the lag.
    """

    def test_thinking_content_label_opts_out_of_height_for_width(self):
        # We assert the *behaviour* (hasHeightForWidth -> False) rather than
        # the type identity (isinstance _HeightCachedLabel) because the
        # QLabel base class is resolved at import time and differs between
        # the stubbed and real-Qt test environments. The contract that
        # actually matters for performance is the protocol opt-out.
        from rikugan.ui.message_widgets import _ThinkingBlock

        block = _ThinkingBlock()
        self.assertFalse(
            block._content.hasHeightForWidth(),
            "_ThinkingBlock._content shares the streaming hot path with "
            "AssistantMessageWidget._content and must opt out of the "
            "heightForWidth protocol to avoid the layout cascade.",
        )


class TestToolCallWidgetUsesCachedLabel(unittest.TestCase):
    """Tool-call labels fire ``setText`` once per tool call (args + result).

    Agentic loops (explore/modify modes) emit dozens of tool calls per
    turn. Each call's ``set_arguments``/``set_result`` does ``setText`` on
    word-wrapped labels that sit in a shared ``QVBoxLayout`` — the same
    cascade trigger. All three must opt out of the ``heightForWidth``
    protocol.
    """

    def test_tool_call_labels_opt_out_of_height_for_width(self):
        from rikugan.ui.tool_widgets import ToolCallWidget

        widget = ToolCallWidget("get_function_info", "tc_1")
        for attr in ("_preview_label", "_args_label", "_result_label"):
            self.assertFalse(
                getattr(widget, attr).hasHeightForWidth(),
                f"ToolCallWidget.{attr} must opt out of the heightForWidth "
                f"protocol to avoid the layout cascade triggered by "
                f"set_arguments/set_result.",
            )


if __name__ == "__main__":
    unittest.main()
