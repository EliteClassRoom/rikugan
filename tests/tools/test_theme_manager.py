"""Tests for rikugan.ui.theme.manager — ThemeManager helpers and singleton."""

from __future__ import annotations

import unittest
from dataclasses import asdict

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

from rikugan.ui.theme.manager import (
    ThemeManager,
    _hex_luminance,
    blend_tokens,
    format_template,
    is_dark_tokens,
)
from rikugan.ui.theme.palette_dark import DARK_TOKENS
from rikugan.ui.theme.palette_light import LIGHT_TOKENS
from rikugan.ui.theme.tokens import ThemeMode, ThemeTokens


class TestHexLuminance(unittest.TestCase):
    def test_black_is_zero(self):
        self.assertAlmostEqual(_hex_luminance("#000000"), 0.0, places=4)

    def test_white_is_one(self):
        self.assertAlmostEqual(_hex_luminance("#ffffff"), 1.0, places=4)

    def test_gray_mid(self):
        # #808080 is the sRGB midpoint; after linearization, its luminance
        # is ~0.2159 (sRGB is gamma-encoded, not linear). The value 0.5 in
        # linear space corresponds to roughly #c5c5c5 in sRGB.
        lum = _hex_luminance("#808080")
        self.assertAlmostEqual(lum, 0.2159, places=3)

    def test_uppercase_hex(self):
        # luminance is case-insensitive
        self.assertAlmostEqual(_hex_luminance("#FFFFFF"), 1.0, places=4)


class TestIsDarkTokens(unittest.TestCase):
    def test_dark_tokens_returns_true(self):
        self.assertTrue(is_dark_tokens(DARK_TOKENS))

    def test_light_tokens_returns_false(self):
        self.assertFalse(is_dark_tokens(LIGHT_TOKENS))

    def test_inverse_helper_consistency(self):
        # If luminance < 0.5, is_dark_tokens should be True
        self.assertEqual(is_dark_tokens(DARK_TOKENS), _hex_luminance(DARK_TOKENS.window) < 0.5)


class TestBlendTokens(unittest.TestCase):
    def test_blend_toward_self_returns_same(self):
        """blend(DARK, DARK, 1.0) should equal DARK."""
        result = blend_tokens(DARK_TOKENS, DARK_TOKENS, 0.5)
        for k, v in asdict(DARK_TOKENS).items():
            self.assertEqual(getattr(result, k), v)

    def test_blend_alpha_zero_returns_first(self):
        """blend(A, B, 0.0) should equal A."""
        result = blend_tokens(DARK_TOKENS, LIGHT_TOKENS, 0.0)
        for k, v in asdict(DARK_TOKENS).items():
            self.assertEqual(getattr(result, k), v)

    def test_blend_alpha_one_returns_second(self):
        """blend(A, B, 1.0) should equal B."""
        result = blend_tokens(DARK_TOKENS, LIGHT_TOKENS, 1.0)
        for k, v in asdict(LIGHT_TOKENS).items():
            self.assertEqual(getattr(result, k), v)

    def test_blend_midpoint_in_range(self):
        """blend(DARK, LIGHT, 0.5) midpoint should have intermediate values."""
        result = blend_tokens(DARK_TOKENS, LIGHT_TOKENS, 0.5)
        # Mid-point color should be a valid hex (rounding)
        for v in asdict(result).values():
            self.assertRegex(v, r"^#[0-9a-fA-F]{6}$")

    def test_blend_returns_theme_tokens(self):
        """Result should be a ThemeTokens instance."""
        result = blend_tokens(DARK_TOKENS, LIGHT_TOKENS, 0.5)
        self.assertIsInstance(result, ThemeTokens)


class TestFormatTemplate(unittest.TestCase):
    def test_no_placeholders_returns_unchanged(self):
        self.assertEqual(format_template("QPushButton { color: red; }", {}), "QPushButton { color: red; }")

    def test_single_placeholder_replaced(self):
        result = format_template("color: {text};", {"text": "#ffffff"})
        self.assertEqual(result, "color: #ffffff;")

    def test_multiple_placeholders_replaced(self):
        result = format_template("bg:{window} text:{text};", {"window": "#000000", "text": "#fff"})
        self.assertEqual(result, "bg:#000000 text:#fff;")

    def test_missing_key_raises(self):
        with self.assertRaises(KeyError):
            format_template("color: {missing};", {})


class TestThemeManagerSingleton(unittest.TestCase):
    def setUp(self):
        ThemeManager.reset()

    def tearDown(self):
        ThemeManager.reset()

    def test_singleton_returns_same_instance(self):
        a = ThemeManager.instance()
        b = ThemeManager.instance()
        self.assertIs(a, b)

    def test_initial_mode_is_auto(self):
        m = ThemeManager.instance()
        self.assertEqual(m.mode, ThemeMode.AUTO)

    def test_reset_clears_singleton(self):
        a = ThemeManager.instance()
        ThemeManager.reset()
        b = ThemeManager.instance()
        self.assertIsNot(a, b)

    def test_set_mode_updates_mode(self):
        m = ThemeManager.instance()
        m.set_mode(ThemeMode.DARK)
        self.assertEqual(m.mode, ThemeMode.DARK)

    def test_set_mode_emits_signal(self):
        m = ThemeManager.instance()
        received: list = []
        m.themeChanged.connect(lambda mode: received.append(mode))
        m.set_mode(ThemeMode.LIGHT)
        self.assertEqual(received, [ThemeMode.LIGHT])

    def test_tokens_returns_dataclass(self):
        m = ThemeManager.instance()
        m.set_mode(ThemeMode.DARK)
        # Without app context, mode DARK should still return DARK_TOKENS
        tokens = m.tokens()
        self.assertIsInstance(tokens, ThemeTokens)
        # In DARK mode with no app override, window should be #1e1e1e
        self.assertEqual(tokens.window.lower(), "#1e1e1e")


if __name__ == "__main__":
    unittest.main()
