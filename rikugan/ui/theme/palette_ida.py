"""Derive ThemeTokens from the current QApplication palette.

Used when ThemeMode is AUTO (in IDA) or IDA_NATIVE. Reads 12 QPalette
roles and derives 5 semantic tokens (success/warning/error/code_text/code_bg)
by blending fixed base hues toward the active text luminance.

This module is IDA-specific — non-IDA hosts fall back to DARK_TOKENS in
the manager before calling here.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QPalette

from .manager import _blend_hex, _hex_luminance
from .tokens import ThemeTokens

# Fixed reference hues for semantic tokens.
# VS Code-inspired: teal-green, pale yellow, soft red. These are blended
# toward the active text color at derive time so they stay legible on
# both dark and light backgrounds.
_SUCCESS_BASE = "#4ec9b0"
_WARNING_BASE = "#dcdcaa"
_ERROR_BASE = "#f48771"

_ROLE_KEYS: list[tuple[QPalette.ColorRole, str]] = [
    (QPalette.ColorRole.Window, "window"),
    (QPalette.ColorRole.WindowText, "window_text"),
    (QPalette.ColorRole.Base, "base"),
    (QPalette.ColorRole.AlternateBase, "alt_base"),
    (QPalette.ColorRole.Text, "text"),
    (QPalette.ColorRole.Button, "button"),
    (QPalette.ColorRole.ButtonText, "button_text"),
    (QPalette.ColorRole.Highlight, "highlight"),
    (QPalette.ColorRole.HighlightedText, "highlight_text"),
    (QPalette.ColorRole.Mid, "mid"),
    (QPalette.ColorRole.Dark, "dark"),
    (QPalette.ColorRole.Light, "light"),
]


def _read_qpalette_colors(source: Any) -> dict[str, str]:
    """Read 12 QPalette role colors as a dict of hex strings.

    `source` must have a `palette()` method (QApplication or a test fake).
    """
    pal = source.palette()
    out: dict[str, str] = {}
    for role, key in _ROLE_KEYS:
        out[key] = pal.color(role).name()
    return out


def _derive_semantic_tokens(qp_colors: dict[str, str]) -> dict[str, str]:
    """Derive success/warning/error/code_text/code_bg from QPalette values.

    Strategy:
    - Blend base hues toward text luminance for legibility (15% blend
      in dark, 35% in light — light needs more desaturation).
    - code_text = text (same as body text)
    - code_bg = alt_base (slightly recessed surface)
    """
    text = qp_colors["text"]
    alt_base = qp_colors["alt_base"]
    is_dark = _hex_luminance(qp_colors["window"]) < 0.5
    amount = 0.15 if is_dark else 0.35

    return {
        "success": _blend_hex(_SUCCESS_BASE, text, amount),
        "warning": _blend_hex(_WARNING_BASE, text, amount),
        "error": _blend_hex(_ERROR_BASE, text, amount),
        "code_text": text,
        "code_bg": alt_base,
    }


def derive_ida_tokens(source: Any) -> ThemeTokens:
    """Build a full ThemeTokens from a QApplication-like `source`.

    `source` must have a `palette()` method. Returns ThemeTokens with
    all 17 fields populated.
    """
    qp = _read_qpalette_colors(source)
    semantic = _derive_semantic_tokens(qp)
    return ThemeTokens(**qp, **semantic)
