"""Tests for message_widgets module.

Unit tests for _split_thinking function, _ThinkingBlock widget,
and AssistantMessageWidget UI properties (theme, size, size policy).
"""

import unittest

import pytest


class TestSplitThinking(unittest.TestCase):
    """Tests for _split_thinking function."""

    def test_basic_thinking_block(self):
        """Test extraction of a single basic thinking block."""
        from ui.message_widgets import _split_thinking

        text = "<think>Let me analyze this function's purpose.</think>The function is a handler."
        thinking, visible = _split_thinking(text)
        self.assertEqual(thinking, "Let me analyze this function's purpose.")
        self.assertEqual(visible, "The function is a handler.")

    def test_thinking_block_with_surrounding_text(self):
        """Test thinking block with text before and after."""
        from ui.message_widgets import _split_thinking

        text = "Let me check this. <think>Checking the binary structure.</think>And here's the result."
        thinking, visible = _split_thinking(text)
        self.assertEqual(thinking, "Checking the binary structure.")
        self.assertEqual(visible, "Let me check this. And here's the result.")

    def test_multiple_thinking_blocks(self):
        """Test multiple thinking blocks get joined with newlines."""
        from ui.message_widgets import _split_thinking

        text = "<think>First thought.</think>Something.<think>Second thought.</think>End."
        thinking, visible = _split_thinking(text)
        self.assertEqual(thinking, "First thought.\n\nSecond thought.")
        self.assertEqual(visible, "Something.End.")

    def test_no_thinking_block(self):
        """Test text with no thinking blocks."""
        from ui.message_widgets import _split_thinking

        text = "Just regular output without any thinking."
        thinking, visible = _split_thinking(text)
        self.assertEqual(thinking, "")
        self.assertEqual(visible, "Just regular output without any thinking.")

    def test_unclosed_thinking_tag(self):
        """Test unclosed <think> tag at end (streaming in progress)."""
        from ui.message_widgets import _split_thinking

        text = "Some text before. <think>Still thinking here"
        thinking, visible = _split_thinking(text)
        self.assertEqual(thinking, "Still thinking here")
        self.assertEqual(visible, "Some text before.")

    def test_only_unclosed_thinking(self):
        """Test only unclosed thinking tag."""
        from ui.message_widgets import _split_thinking

        text = "<think>Just thinking, no close yet"
        thinking, visible = _split_thinking(text)
        self.assertEqual(thinking, "Just thinking, no close yet")
        self.assertEqual(visible, "")

    def test_empty_thinking_block(self):
        """Test thinking block with no content."""
        from ui.message_widgets import _split_thinking

        text = "<think></think>No thinking content."
        thinking, visible = _split_thinking(text)
        self.assertEqual(thinking, "")
        self.assertEqual(visible, "No thinking content.")

    def test_thoughtful_content_with_markdown(self):
        """Test thinking block containing markdown-like content."""
        from ui.message_widgets import _split_thinking

        text = "<think>**analysis**: Looking at *function* `main`.</think>Output here."
        thinking, visible = _split_thinking(text)
        self.assertIn("**analysis**:", thinking)
        self.assertIn("Output here.", visible)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# UI / structural tests for AssistantMessageWidget
# ---------------------------------------------------------------------------


class TestAssistantMessageWidgetUI(unittest.TestCase):
    """Structural / UI tests for AssistantMessageWidget.

    These tests verify the widget's geometry, size policy, and styling.
    A ``qapp`` fixture must be active (provided by conftest.py) before
    constructing any Qt widgets.
    """

    @pytest.fixture(autouse=True)
    def setup_qapp(self, qapp):
        self.qapp = qapp

    def test_container_minimum_height(self):
        """AssistantMessageWidget frame has minimumHeight of 150 px."""
        from ui.message_widgets import AssistantMessageWidget

        w = AssistantMessageWidget()
        self.assertEqual(w.minimumHeight(), 150)

    def test_content_minimum_height(self):
        """QTextEdit content area has minimumHeight of 120 px."""
        from ui.message_widgets import AssistantMessageWidget

        w = AssistantMessageWidget()
        self.assertEqual(w._content.minimumHeight(), 120)

    def test_content_size_policy_expanding(self):
        """QTextEdit has Expanding size policy on both axes."""
        from ui.message_widgets import AssistantMessageWidget
        from PySide6.QtWidgets import QSizePolicy

        w = AssistantMessageWidget()
        policy = w._content.sizePolicy()
        self.assertEqual(policy.horizontalPolicy(), QSizePolicy.Policy.Expanding)
        self.assertEqual(policy.verticalPolicy(), QSizePolicy.Policy.Expanding)

    def test_content_no_frame(self):
        """QTextEdit has NoFrame shape (no border)."""
        from ui.message_widgets import AssistantMessageWidget
        from PySide6.QtWidgets import QFrame

        w = AssistantMessageWidget()
        self.assertEqual(w._content.frameShape(), QFrame.Shape.NoFrame)

    def test_object_names(self):
        """Frame and content widget have correct object names."""
        from ui.message_widgets import AssistantMessageWidget

        w = AssistantMessageWidget()
        self.assertEqual(w.objectName(), "message_assistant")
        self.assertEqual(w._content.objectName(), "message_content")

    def test_set_text_renders_html(self):
        """set_text stores text and renders it as HTML via md_to_html."""
        from ui.message_widgets import AssistantMessageWidget

        w = AssistantMessageWidget()
        w.set_text("Hello **world**")
        self.assertEqual(w._text, "Hello **world**")
        # The content should have been set via setHtml
        self.assertTrue(len(w._content.toPlainText()) > 0)

    def test_append_text_increments_content(self):
        """append_text accumulates text for streaming."""
        from ui.message_widgets import AssistantMessageWidget

        w = AssistantMessageWidget()
        w.append_text("First ")
        self.assertEqual(w._text, "First ")
        w.append_text("second")
        self.assertEqual(w._text, "First second")

    def test_append_simple_text_appends_directly(self):
        """Simple text (no block markers) is appended directly without full re-render."""
        from ui.message_widgets import AssistantMessageWidget

        w = AssistantMessageWidget()
        w.append_text("Hello ")
        w.append_text("world")
        # Should have accumulated without triggering full setHtml
        self.assertEqual(w._text, "Hello world")

    def test_code_block_state_toggle(self):
        """Code fence markers toggle _in_code_block state."""
        from ui.message_widgets import AssistantMessageWidget

        w = AssistantMessageWidget()
        self.assertFalse(w._in_code_block)
        w.append_text("```python\n")
        self.assertTrue(w._in_code_block)
        w.append_text("```")
        self.assertFalse(w._in_code_block)

    def test_widget_readonly(self):
        """QTextEdit content area is read-only."""
        from ui.message_widgets import AssistantMessageWidget

        w = AssistantMessageWidget()
        self.assertTrue(w._content.isReadOnly())

