"""Tests for pure-logic helpers in rikugan.ui.tool_widgets.

Isolates the testable business-logic functions from Qt widget code
by installing PySide6 stubs before importing the module.
"""

from __future__ import annotations

import json
import unittest

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

from rikugan.ui.tool_widgets import (  # noqa: E402
    _DEFAULT_TOOL_COLOR,
    _KW_NAMES,
    _format_tool_group_label,
    _format_tool_summary,
    _PythonHighlighter,
    _strip_mcp_prefix,
    _tool_color,
    _truncate_preview,
)

# ---------------------------------------------------------------------------
# _strip_mcp_prefix
# ---------------------------------------------------------------------------

class TestStripMcpPrefix(unittest.TestCase):
    def test_plain_name_unchanged(self):
        self.assertEqual(_strip_mcp_prefix("decompile_function"), "decompile_function")

    def test_strips_mcp_prefix(self):
        self.assertEqual(_strip_mcp_prefix("mcp__myserver__decompile_function"), "decompile_function")

    def test_strips_only_first_segment(self):
        self.assertEqual(_strip_mcp_prefix("mcp__a__b__c"), "b__c")

    def test_mcp_without_double_underscore(self):
        # "mcp__" present but no trailing "__" — should return as-is after "mcp__"
        result = _strip_mcp_prefix("mcp__notrailing")
        self.assertEqual(result, "mcp__notrailing")

    def test_empty_string(self):
        self.assertEqual(_strip_mcp_prefix(""), "")


# ---------------------------------------------------------------------------
# _tool_color
# ---------------------------------------------------------------------------

class TestToolColor(unittest.TestCase):
    def test_known_analysis_tool(self):
        color = _tool_color("decompile_function")
        self.assertEqual(color, "#4ec9b0")  # teal

    def test_known_mutation_tool(self):
        color = _tool_color("rename_function")
        self.assertEqual(color, "#c586c0")  # magenta

    def test_unknown_tool_gets_default(self):
        color = _tool_color("zzz_unknown_tool")
        self.assertEqual(color, _DEFAULT_TOOL_COLOR)

    def test_mcp_prefixed_tool(self):
        color = _tool_color("mcp__myserver__decompile_function")
        self.assertEqual(color, "#4ec9b0")  # still teal after stripping prefix


# ---------------------------------------------------------------------------
# _format_tool_group_label
# ---------------------------------------------------------------------------

class TestFormatToolGroupLabel(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(_format_tool_group_label([]), "0 tools called")

    def test_single_generic_tool(self):
        self.assertEqual(_format_tool_group_label(["some_tool"]), "1 tool called")

    def test_multiple_generic_tools(self):
        self.assertEqual(_format_tool_group_label(["a", "b", "c"]), "3 tools called")

    def test_single_known_tool_singular(self):
        result = _format_tool_group_label(["decompile_function"])
        self.assertEqual(result, "Decompiled 1 function")

    def test_single_known_tool_plural(self):
        result = _format_tool_group_label(["decompile_function", "decompile_function"])
        self.assertEqual(result, "Decompiled 2 functions")

    def test_mixed_tools_no_label(self):
        result = _format_tool_group_label(["rename_function", "decompile_function"])
        self.assertEqual(result, "2 tools called")

    def test_mcp_prefixed_known(self):
        result = _format_tool_group_label(["mcp__myserver__decompile_function"])
        self.assertEqual(result, "Decompiled 1 function")


# ---------------------------------------------------------------------------
# _format_tool_summary
# ---------------------------------------------------------------------------

class TestFormatToolSummary(unittest.TestCase):
    def test_decompile_with_address(self):
        args = json.dumps({"address": "0x1000"})
        result = _format_tool_summary("decompile_function", args)
        self.assertEqual(result, "0x1000")

    def test_rename_function(self):
        args = json.dumps({"old_name": "sub_1000", "new_name": "process_data"})
        result = _format_tool_summary("rename_function", args)
        self.assertEqual(result, "sub_1000 → process_data")

    def test_rename_single_variable(self):
        args = json.dumps({"variable_name": "var_0", "new_name": "count", "function_name": "main"})
        result = _format_tool_summary("rename_single_variable", args)
        self.assertEqual(result, "main: var_0 → count")

    def test_set_comment_truncation(self):
        long_comment = "A" * 60
        args = json.dumps({"address": "0x1000", "comment": long_comment})
        result = _format_tool_summary("set_comment", args)
        self.assertIn("...", result)
        self.assertLessEqual(len(result), 120)

    def test_search_strings(self):
        args = json.dumps({"pattern": "hello"})
        result = _format_tool_summary("search_strings", args)
        self.assertEqual(result, '"hello"')

    def test_execute_python_first_line(self):
        code = "print('hello')\nprint('world')"
        args = json.dumps({"code": code})
        result = _format_tool_summary("execute_python", args)
        self.assertEqual(result, "print('hello')")

    def test_invalid_json_returns_empty(self):
        result = _format_tool_summary("decompile_function", "not json")
        self.assertEqual(result, "")

    def test_empty_args(self):
        result = _format_tool_summary("decompile_function", "")
        self.assertEqual(result, "")

    def test_summary_truncated_at_80(self):
        args = json.dumps({"address": "x" * 100})
        result = _format_tool_summary("decompile_function", args)
        self.assertLessEqual(len(result), 80)
        self.assertTrue(result.endswith("..."))

    def test_mcp_prefixed_tool(self):
        args = json.dumps({"address": "0x400"})
        result = _format_tool_summary("mcp__myserver__decompile_function", args)
        self.assertEqual(result, "0x400")

    def test_phase_transition(self):
        args = json.dumps({"to_phase": "execute", "reason": "all targets identified"})
        result = _format_tool_summary("phase_transition", args)
        self.assertIn("execute", result)

    def test_generic_fallback_address(self):
        args = json.dumps({"address": "0xdeadbeef"})
        result = _format_tool_summary("unknown_tool_xyz", args)
        self.assertEqual(result, "0xdeadbeef")


# ---------------------------------------------------------------------------
# _truncate_preview
# ---------------------------------------------------------------------------

class TestTruncatePreview(unittest.TestCase):
    def test_short_text_unchanged(self):
        text = "line1\nline2\nline3"
        self.assertEqual(_truncate_preview(text, max_lines=3), text)

    def test_single_line_unchanged(self):
        self.assertEqual(_truncate_preview("hello", max_lines=3), "hello")

    def test_truncated_shows_count(self):
        text = "\n".join(f"line{i}" for i in range(10))
        result = _truncate_preview(text, max_lines=3)
        self.assertIn("… +7 lines", result)
        self.assertIn("line0", result)
        self.assertIn("line2", result)
        self.assertNotIn("line3", result)

    def test_exactly_at_limit_unchanged(self):
        text = "a\nb\nc"
        self.assertEqual(_truncate_preview(text, max_lines=3), text)

    def test_custom_max_lines(self):
        text = "a\nb\nc\nd\ne"
        result = _truncate_preview(text, max_lines=2)
        self.assertIn("… +3 lines", result)


# ---------------------------------------------------------------------------
# _PythonHighlighter palettes
# ---------------------------------------------------------------------------

# Token categories that must be present in every palette. Locking the keys
# down here means adding/renaming a token forces a test failure rather than
# silently producing an unhighlighted class.
_REQUIRED_TOKENS: tuple[str, ...] = (
    "keyword",
    "builtin",
    "number",
    "string",
    "comment",
    "decorator",
    "self",
)


class TestPythonHighlighterPalettes(unittest.TestCase):
    def test_dark_palette_has_all_tokens(self):
        palette = _PythonHighlighter._dark_palette()
        for token in _REQUIRED_TOKENS:
            self.assertIn(token, palette, f"dark palette missing {token!r}")
            self.assertRegex(palette[token], r"^#[0-9a-fA-F]{6}$")

    def test_light_palette_has_all_tokens(self):
        palette = _PythonHighlighter._light_palette()
        for token in _REQUIRED_TOKENS:
            self.assertIn(token, palette, f"light palette missing {token!r}")
            self.assertRegex(palette[token], r"^#[0-9a-fA-F]{6}$")

    def test_dark_and_light_palettes_differ(self):
        # Locking this in prevents a future refactor from accidentally
        # aliasing one palette to the other.
        dark = _PythonHighlighter._dark_palette()
        light = _PythonHighlighter._light_palette()
        self.assertNotEqual(dark, light)
        # At least the keyword colour must differ — they're the most
        # semantically loaded token and the easiest to misread.
        self.assertNotEqual(dark["keyword"], light["keyword"])

    def test_build_rules_uses_palette_colours(self):
        # The keyword colour from the palette must flow through to the
        # QTextCharFormat attached to the keyword rule.
        palette = {"keyword": "#abcdef", "builtin": "#111111", "number": "#222222",
                   "string": "#333333", "comment": "#444444", "decorator": "#555555",
                   "self": "#666666"}
        rules = _PythonHighlighter._build_rules(palette)
        # First rule is the first keyword in _KW_NAMES ("and"). Its format
        # must carry the keyword colour from the palette.
        self.assertGreater(len(rules), 0)
        kw_pattern, kw_fmt = rules[0]
        self.assertEqual(kw_pattern.pattern, r"\band\b")
        # QTextCharFormat stores foreground as a QColor in the stub —
        # inspect its name. The stub's QColor stores the hex as `_name`.
        self.assertEqual(kw_fmt.foreground()._name.lower(), "#abcdef")

    def test_kw_and_builtin_lists_cover_python_keywords(self):
        # Sanity check that the keyword list contains the most common ones.
        # If a future refactor drops one of these, the test forces the author
        # to confirm the omission is intentional.
        for kw in ("def", "class", "if", "else", "return", "import", "for", "while"):
            self.assertIn(kw, _KW_NAMES)


if __name__ == "__main__":
    unittest.main()
