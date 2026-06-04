"""Tests for rikugan.ui.theme.tokens — ThemeMode and ThemeTokens invariants."""

from __future__ import annotations

import re
import unittest
from dataclasses import asdict

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from rikugan.ui.theme.tokens import ThemeMode, ThemeTokens


class TestThemeMode(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(ThemeMode.AUTO.value, "auto")
        self.assertEqual(ThemeMode.DARK.value, "dark")
        self.assertEqual(ThemeMode.LIGHT.value, "light")
        self.assertEqual(ThemeMode.IDA_NATIVE.value, "ida")

    def test_from_string_valid(self):
        self.assertIs(ThemeMode("auto"), ThemeMode.AUTO)
        self.assertIs(ThemeMode("dark"), ThemeMode.DARK)
        self.assertIs(ThemeMode("light"), ThemeMode.LIGHT)
        self.assertIs(ThemeMode("ida"), ThemeMode.IDA_NATIVE)

    def test_from_string_invalid_raises(self):
        with self.assertRaises(ValueError):
            ThemeMode("neon_pink")


class TestThemeTokens(unittest.TestCase):
    REQUIRED_KEYS = {
        "window", "window_text", "base", "alt_base", "text",
        "button", "button_text", "highlight", "highlight_text",
        "mid", "light", "dark", "success", "warning", "error",
        "code_text", "code_bg",
    }

    def _make_tokens(self) -> ThemeTokens:
        return ThemeTokens(
            window="#000000", window_text="#ffffff",
            base="#111111", alt_base="#1a1a1a", text="#e0e0e0",
            button="#222222", button_text="#e0e0e0",
            highlight="#007acc", highlight_text="#ffffff",
            mid="#666666", light="#888888", dark="#333333",
            success="#4ec9b0", warning="#dcdcaa", error="#f48771",
            code_text="#e0e0e0", code_bg="#1a1a1a",
        )

    def test_required_keys_present(self):
        tokens = self._make_tokens()
        keys = set(asdict(tokens).keys())
        self.assertEqual(keys, self.REQUIRED_KEYS)

    def test_keys_count_is_17(self):
        tokens = self._make_tokens()
        self.assertEqual(len(asdict(tokens)), 17)

    def test_all_values_are_hex_colors(self):
        tokens = self._make_tokens()
        pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for key, val in asdict(tokens).items():
            self.assertRegex(val, pattern, f"{key}={val} is not #rrggbb")

    def test_frozen_dataclass(self):
        tokens = self._make_tokens()
        with self.assertRaises(Exception):
            tokens.window = "#ffffff"  # type: ignore[misc]

    def test_is_dark_helper_true_for_dark_window(self):
        from rikugan.ui.theme.tokens import is_dark_tokens
        tokens = self._make_tokens()  # window=#000000
        self.assertTrue(is_dark_tokens(tokens))

    def test_is_dark_helper_false_for_light_window(self):
        from rikugan.ui.theme.tokens import is_dark_tokens
        tokens = ThemeTokens(
            window="#ffffff", window_text="#000000",
            base="#fafafa", alt_base="#f0f0f0", text="#1a1a1a",
            button="#ffffff", button_text="#1a1a1a",
            highlight="#0066cc", highlight_text="#ffffff",
            mid="#cccccc", light="#ffffff", dark="#999999",
            success="#2c8a4a", warning="#a67900", error="#c42b1c",
            code_text="#1a1a1a", code_bg="#f0f0f0",
        )
        self.assertFalse(is_dark_tokens(tokens))


if __name__ == "__main__":
    unittest.main()
