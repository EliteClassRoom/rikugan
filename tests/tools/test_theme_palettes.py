"""Tests for rikugan.ui.theme palettes (DARK, LIGHT, IDA_NATIVE)."""

from __future__ import annotations

import re
import unittest
from dataclasses import asdict

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()


class TestDarkPalette(unittest.TestCase):
    def test_dark_tokens_is_dark(self):
        """DARK_TOKENS.window must be a dark color (we use #1e1e1e)."""
        from rikugan.ui.theme.palette_dark import DARK_TOKENS
        self.assertEqual(DARK_TOKENS.window.lower(), "#1e1e1e")

    def test_dark_tokens_has_all_keys(self):
        """DARK_TOKENS must have all 17 required keys."""
        from rikugan.ui.theme.palette_dark import DARK_TOKENS
        self.assertEqual(len(asdict(DARK_TOKENS)), 17)

    def test_dark_tokens_hex_format(self):
        """All 17 values must be valid 6-char hex colors."""
        from rikugan.ui.theme.palette_dark import DARK_TOKENS
        pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for k, v in asdict(DARK_TOKENS).items():
            self.assertRegex(v, pattern, f"{k}={v}")

    def test_dark_text_contrast(self):
        """text color must have high luminance contrast against window."""
        from dataclasses import replace

        from rikugan.ui.theme.palette_dark import DARK_TOKENS
        from rikugan.ui.theme.tokens import is_dark_tokens
        self.assertTrue(is_dark_tokens(DARK_TOKENS))
        # text must NOT be dark (it should be the light foreground) —
        # verify by swapping window for the text color and checking
        # the swapped tokens are not dark.
        text_as_window = replace(DARK_TOKENS, window=DARK_TOKENS.text)
        self.assertFalse(is_dark_tokens(text_as_window))


class TestLightPalette(unittest.TestCase):
    def test_light_tokens_window_is_light(self):
        """LIGHT_TOKENS.window should have luminance > 0.5 (a light background)."""
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        from rikugan.ui.theme.tokens import is_dark_tokens
        self.assertFalse(is_dark_tokens(LIGHT_TOKENS))

    def test_light_tokens_highlight_value(self):
        """Design lock: VS Code Light+ uses #0066cc for highlight."""
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        self.assertEqual(LIGHT_TOKENS.highlight.lower(), "#0066cc")

    def test_light_tokens_has_all_keys(self):
        """LIGHT_TOKENS must have all 17 required keys."""
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        self.assertEqual(len(asdict(LIGHT_TOKENS)), 17)

    def test_light_tokens_hex_format(self):
        """All 17 values must be valid 6-char hex colors."""
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for k, v in asdict(LIGHT_TOKENS).items():
            self.assertRegex(v, pattern, f"{k}={v}")

    def test_light_foreground_is_dark(self):
        """text must be a dark foreground color (high contrast against light window).

        Uses dataclasses.replace to swap window for text, then verifies
        the swapped value is dark. This is more readable than a 14-line
        inline ThemeTokens constructor and is 18-field-safe.
        """
        from dataclasses import replace

        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        from rikugan.ui.theme.tokens import is_dark_tokens
        text_as_window = replace(LIGHT_TOKENS, window=LIGHT_TOKENS.text)
        self.assertTrue(is_dark_tokens(text_as_window))


if __name__ == "__main__":
    unittest.main()
