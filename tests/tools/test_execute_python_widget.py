"""Tests for ExecutePythonWidget (unified execute_python lifecycle widget)."""

from __future__ import annotations

import json
import sys
import unittest

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

# Ensure the real module is loaded even if another test stubbed it.
sys.modules.pop("rikugan.ui.tool_widgets", None)

from rikugan.ui.tool_widgets import ExecutePythonWidget  # noqa: E402


class TestExecutePythonWidgetInit(unittest.TestCase):
    def test_init_idle_no_buttons_code_collapsed(self):
        w = ExecutePythonWidget("tc1")
        # No code set yet.
        self.assertEqual(w._code, "")
        # Buttons should not be shown until show_approval_buttons().
        self.assertFalse(w._buttons_visible)
        # Result block should be hidden until set_result().
        self.assertFalse(w._result_block_visible)


class TestSetArguments(unittest.TestCase):
    def test_set_arguments_extracts_code_from_json(self):
        w = ExecutePythonWidget("tc1")
        w.set_arguments(json.dumps({"code": "print(1)\nprint(2)\n"}))
        self.assertEqual(w._code, "print(1)\nprint(2)\n")

    def test_set_arguments_extracts_script_field(self):
        w = ExecutePythonWidget("tc1")
        w.set_arguments(json.dumps({"script": "x = 1"}))
        self.assertEqual(w._code, "x = 1")

    def test_set_arguments_fallback_raw_on_bad_json(self):
        w = ExecutePythonWidget("tc1")
        w.set_arguments("not valid json")
        self.assertEqual(w._code, "not valid json")


class TestDocsGateStatus(unittest.TestCase):
    def test_running_sets_status_text(self):
        w = ExecutePythonWidget("tc1")
        w.set_docs_gate_status("running", reasons=("2 IDA modules",))
        self.assertIn("Reviewing", w._status_text)
        self.assertIn("2 IDA modules", w._status_text)
        self.assertTrue(w._status_visible)

    def test_approved_sets_status_text(self):
        w = ExecutePythonWidget("tc1")
        w.set_docs_gate_status("approved")
        self.assertIn("Docs review passed", w._status_text)
        self.assertTrue(w._status_visible)

    def test_blocked_hides_buttons(self):
        w = ExecutePythonWidget("tc1")
        w.show_approval_buttons()
        self.assertTrue(w._buttons_visible)
        w.set_docs_gate_status("blocked", summary="bad API")
        self.assertFalse(w._buttons_visible)
        # Summary now lives in the collapsible detail, not the header.
        self.assertIn("bad API", w._status_detail_text)
        self.assertIn("Docs review blocked", w._status_text)

    def test_blocked_status_collapsed_by_default(self):
        """A blocked review shows a short header by default; the long
        reviewer summary must not clutter the card until the user expands."""
        w = ExecutePythonWidget("tc1")
        w.set_docs_gate_status("blocked", summary="ida_bytes.patch_qword is not a real API" * 5)
        self.assertTrue(w._status_visible)
        # Detail (full summary) hidden by default.
        self.assertFalse(w._status_detail_visible)

    def test_blocked_status_expandable(self):
        """User can expand the blocked status to read the full summary."""
        w = ExecutePythonWidget("tc1")
        w.set_docs_gate_status("blocked", summary="detailed rewrite guidance here")
        self.assertFalse(w._status_detail_visible)
        w.toggle_docs_gate_detail()
        self.assertTrue(w._status_detail_visible)
        self.assertIn("detailed rewrite guidance here", w._status_detail_text)

    def test_blocked_result_does_not_dup(self):
        """When the docs gate blocks, the loop emits TOOL_RESULT with the
        reviewer summary as an error. The widget already shows that summary
        in the status line, so set_result must NOT render a duplicate
        result block."""
        w = ExecutePythonWidget("tc1")
        w.set_docs_gate_status("blocked", summary="rewrite guidance")
        w.set_result("rewrite guidance", is_error=True)
        self.assertFalse(w._result_block_visible)

    def test_failed_shows_buttons(self):
        """FAILED (reviewer crash) still lets the user approve."""
        w = ExecutePythonWidget("tc1")
        w.show_approval_buttons()
        w.set_docs_gate_status("failed", summary="boom")
        self.assertTrue(w._buttons_visible)
        self.assertIn("review manually", w._status_text.lower())

    def test_no_status_hidden_by_default(self):
        w = ExecutePythonWidget("tc1")
        self.assertFalse(w._status_visible)


class TestApprovalButtons(unittest.TestCase):
    def test_show_approval_buttons_makes_visible(self):
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.show_approval_buttons()
        self.assertTrue(w._buttons_visible)

    def test_allow_emits_signal(self):
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.show_approval_buttons()
        captured = []
        w.approved.connect(lambda tid, decision: captured.append((tid, decision)))
        w._on_allow()
        self.assertEqual(captured, [("tc1", "allow")])

    def test_always_allow_emits_allow_all(self):
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.show_approval_buttons()
        captured = []
        w.approved.connect(lambda tid, decision: captured.append((tid, decision)))
        w._on_always_allow()
        self.assertEqual(captured, [("tc1", "allow_all")])

    def test_deny_emits_deny(self):
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.show_approval_buttons()
        captured = []
        w.approved.connect(lambda tid, decision: captured.append((tid, decision)))
        w._on_deny()
        self.assertEqual(captured, [("tc1", "deny")])


class TestSetResult(unittest.TestCase):
    def test_set_result_success_shows_result_block(self):
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.set_result("42", is_error=False)
        self.assertTrue(w._result_block_visible)
        self.assertFalse(w._is_error)

    def test_set_result_error_marks_error(self):
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.set_result("NameError: x", is_error=True)
        self.assertTrue(w._result_block_visible)
        self.assertTrue(w._is_error)

    def test_result_collapsed_by_default(self):
        """Result content is hidden by default; only the header shows so a
        long script output doesn't dominate the card."""
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.set_result("long output " * 50, is_error=False)
        self.assertTrue(w._result_block_visible)
        self.assertFalse(w._result_content_visible)

    def test_result_expandable(self):
        """User can expand the result to read the full output."""
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.set_result("the answer is 42", is_error=False)
        self.assertFalse(w._result_content_visible)
        w.toggle_result()
        self.assertTrue(w._result_content_visible)

    def test_result_error_collapsed_by_default(self):
        """Error results are also collapsed by default."""
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        w.set_result("NameError: x", is_error=True)
        self.assertTrue(w._is_error)
        self.assertFalse(w._result_content_visible)


class TestMarkDone(unittest.TestCase):
    def test_mark_done_is_safe_to_call(self):
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)")
        # mark_done must not raise whether or not result is set.
        w.mark_done()
        w.set_result("ok", is_error=False)
        w.mark_done()


class TestHidePreview(unittest.TestCase):
    def test_hide_preview_collapses_code(self):
        w = ExecutePythonWidget("tc1")
        w.set_code("print(1)\nprint(2)\n")
        w.hide_preview()
        # After hide_preview the code editor should be collapsed.
        self.assertFalse(w._code_expanded)


class TestCodeDisplayedOnce(unittest.TestCase):
    def test_no_redundant_description_label(self):
        """The widget must not carry a redundant 'Run Python code: ...'
        description — code is shown once in the code editor."""
        w = ExecutePythonWidget("tc1")
        w.set_arguments(json.dumps({"code": "import idautils\nprint(1)\n"}))
        # There should be no _description_label attribute holding a
        # duplicate of the first code line.
        self.assertFalse(getattr(w, "_description_label", None))


if __name__ == "__main__":
    unittest.main()
