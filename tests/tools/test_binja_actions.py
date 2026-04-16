"""Tests for rikugan.binja.ui.actions — prompt-generating command handlers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from rikugan.binja.ui.actions import (
    ACTION_DEFS,
    build_context,
    handle_annotate,
    handle_clean_il,
    handle_deobfuscate_bn,
    handle_explain,
    handle_rename,
    handle_send_to,
    handle_smart_patch,
    handle_suggest_types,
    handle_vuln_audit,
    handle_xref_analysis,
)


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------

class TestBuildContext(unittest.TestCase):
    def _make_deps(self, func=None):
        get_function_at = MagicMock(return_value=func)
        get_function_name = MagicMock(return_value="my_func" if func else "")
        return get_function_at, get_function_name

    def test_ea_always_set(self):
        bv = MagicMock()
        get_fn_at, get_fn_name = self._make_deps(None)
        ctx = build_context(bv, 0x1000, get_fn_at, get_fn_name)
        self.assertEqual(ctx["ea"], 0x1000)

    def test_no_function_at_address(self):
        bv = MagicMock()
        get_fn_at, get_fn_name = self._make_deps(None)
        ctx = build_context(bv, 0x1234, get_fn_at, get_fn_name)
        self.assertIsNone(ctx["func_ea"])
        self.assertIsNone(ctx["func_name"])

    def test_function_found_sets_func_ea_and_name(self):
        bv = MagicMock()
        func = MagicMock()
        func.start = 0x1000
        get_fn_at = MagicMock(return_value=func)
        get_fn_name = MagicMock(return_value="target_func")
        ctx = build_context(bv, 0x1010, get_fn_at, get_fn_name)
        self.assertEqual(ctx["func_ea"], 0x1000)
        self.assertEqual(ctx["func_name"], "target_func")

    def test_function_without_start_falls_back_to_ea(self):
        bv = MagicMock()
        func = MagicMock(spec=[])  # no 'start' attribute
        get_fn_at = MagicMock(return_value=func)
        get_fn_name = MagicMock(return_value="func")
        ctx = build_context(bv, 0x2000, get_fn_at, get_fn_name)
        self.assertEqual(ctx["func_ea"], 0x2000)

    def test_selected_text_default_empty(self):
        bv = MagicMock()
        get_fn_at, get_fn_name = self._make_deps(None)
        ctx = build_context(bv, 0x0, get_fn_at, get_fn_name)
        self.assertEqual(ctx["selected_text"], "")


# ---------------------------------------------------------------------------
# handle_send_to
# ---------------------------------------------------------------------------

class TestHandleSendTo(unittest.TestCase):
    def test_selected_text_returned_as_is(self):
        ctx = {"selected_text": "my selection", "func_name": "func", "ea": 0x1000}
        self.assertEqual(handle_send_to(ctx), "my selection")

    def test_func_name_used_when_no_selection(self):
        ctx = {"selected_text": "", "func_name": "decrypt_data", "ea": 0x1000}
        result = handle_send_to(ctx)
        self.assertIn("decrypt_data", result)
        self.assertIn("0x1000", result)

    def test_address_only_when_no_name_and_no_selection(self):
        ctx = {"selected_text": "", "func_name": None, "ea": 0xdeadbeef}
        result = handle_send_to(ctx)
        self.assertIn("0xdeadbeef", result)
        self.assertNotIn("None", result)


# ---------------------------------------------------------------------------
# handle_explain
# ---------------------------------------------------------------------------

class TestHandleExplain(unittest.TestCase):
    def test_includes_name_and_address(self):
        ctx = {"func_name": "process_buffer", "func_ea": 0x2000, "ea": 0x2000}
        result = handle_explain(ctx)
        self.assertIn("process_buffer", result)
        self.assertIn("0x2000", result)

    def test_fallback_name_when_no_func_name(self):
        ctx = {"func_name": None, "func_ea": None, "ea": 0x1234}
        result = handle_explain(ctx)
        self.assertIn("sub_1234", result)

    def test_mentions_decompile(self):
        ctx = {"func_name": "foo", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_explain(ctx)
        self.assertIn("Decompile", result)


# ---------------------------------------------------------------------------
# handle_rename
# ---------------------------------------------------------------------------

class TestHandleRename(unittest.TestCase):
    def test_includes_func_name(self):
        ctx = {"func_name": "old_name", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_rename(ctx)
        self.assertIn("old_name", result)

    def test_mentions_rename(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_rename(ctx)
        self.assertIn("rename", result.lower())


# ---------------------------------------------------------------------------
# handle_deobfuscate
# ---------------------------------------------------------------------------

class TestHandleDeobfuscateBn(unittest.TestCase):
    def test_includes_obfuscation_patterns(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_deobfuscate_bn(ctx)
        self.assertIn("obfuscat", result.lower())

    def test_mentions_il_optimizations(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_deobfuscate_bn(ctx)
        self.assertIn("IL", result)


# ---------------------------------------------------------------------------
# handle_vuln_audit
# ---------------------------------------------------------------------------

class TestHandleVulnAudit(unittest.TestCase):
    def test_mentions_vulnerability_types(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_vuln_audit(ctx)
        self.assertIn("buffer overflow", result.lower())

    def test_mentions_severity(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_vuln_audit(ctx)
        self.assertIn("severity", result.lower())


# ---------------------------------------------------------------------------
# handle_suggest_types
# ---------------------------------------------------------------------------

class TestHandleSuggestTypes(unittest.TestCase):
    def test_mentions_types_and_structs(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_suggest_types(ctx)
        self.assertIn("type", result.lower())
        self.assertIn("struct", result.lower())


# ---------------------------------------------------------------------------
# handle_annotate
# ---------------------------------------------------------------------------

class TestHandleAnnotate(unittest.TestCase):
    def test_mentions_comments(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_annotate(ctx)
        self.assertIn("comment", result.lower())


# ---------------------------------------------------------------------------
# handle_clean_mcode
# ---------------------------------------------------------------------------

class TestHandleCleanIl(unittest.TestCase):
    def test_mentions_il(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_clean_il(ctx)
        self.assertIn("IL", result)


# ---------------------------------------------------------------------------
# handle_xref_analysis
# ---------------------------------------------------------------------------

class TestHandleXrefAnalysis(unittest.TestCase):
    def test_mentions_callers_and_callees(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_xref_analysis(ctx)
        self.assertIn("caller", result.lower())
        self.assertIn("callee", result.lower())


# ---------------------------------------------------------------------------
# handle_smart_patch
# ---------------------------------------------------------------------------

class TestHandleSmartPatch(unittest.TestCase):
    def test_includes_skill_prefix(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000}
        result = handle_smart_patch(ctx)
        self.assertIn("/smart-patch-binja", result)


# ---------------------------------------------------------------------------
# ACTION_DEFS
# ---------------------------------------------------------------------------

class TestActionDefs(unittest.TestCase):
    def test_all_actions_have_four_fields(self):
        for entry in ACTION_DEFS:
            self.assertEqual(len(entry), 4)

    def test_all_handlers_are_callable(self):
        for _, _, handler, _ in ACTION_DEFS:
            self.assertTrue(callable(handler))

    def test_auto_send_flag_is_bool(self):
        for _, _, _, auto in ACTION_DEFS:
            self.assertIsInstance(auto, bool)

    def test_ten_action_entries(self):
        self.assertEqual(len(ACTION_DEFS), 10)

    def test_handler_output_is_str(self):
        ctx = {"func_name": "fn", "func_ea": 0x1000, "ea": 0x1000, "selected_text": ""}
        for _, _, handler, _ in ACTION_DEFS:
            result = handler(ctx)
            self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
