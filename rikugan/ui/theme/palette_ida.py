"""Derive ThemeTokens from the current QApplication palette.

Used when ThemeMode is AUTO (in IDA) or IDA_NATIVE. Reads 12 QPalette
roles and derives 5 semantic tokens (success/warning/error/code_text/code_bg)
by blending fixed base hues toward the active text luminance.
"""

from __future__ import annotations

from typing import Any

try:
    from PySide6.QtGui import QPalette  # type: ignore[import-not-found]

    _HAS_QT = True
except ImportError:  # pragma: no cover
    QPalette = None  # type: ignore[assignment]
    _HAS_QT = False

from .manager import _blend_hex, _hex_luminance
from .tokens import ThemeTokens

# Fixed reference hues for semantic tokens.
_SUCCESS_BASE = "#4ec9b0"
_WARNING_BASE = "#dcdcaa"
_ERROR_BASE = "#f48771"

_ROLE_KEYS: list[tuple[Any, str]] = []
if _HAS_QT and QPalette is not None:
    _ROLE_KEYS = [
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
    """Read 12 QPalette role colors as a dict of hex strings."""
    pal = source.palette()
    out: dict[str, str] = {}
    for role, key in _ROLE_KEYS:
        try:
            out[key] = pal.color(role).name()
        except Exception:
            out[key] = "#000000"
    return out


def _derive_semantic_tokens(qp_colors: dict[str, str]) -> dict[str, str]:
    text = qp_colors.get("text", "#000000")
    alt_base = qp_colors.get("alt_base", "#000000")
    is_dark = _hex_luminance(qp_colors.get("window", "#000000")) < 0.5
    amount = 0.15 if is_dark else 0.35

    return {
        "success": _blend_hex(_SUCCESS_BASE, text, amount),
        "warning": _blend_hex(_WARNING_BASE, text, amount),
        "error": _blend_hex(_ERROR_BASE, text, amount),
        "code_text": text,
        "code_bg": alt_base,
    }


def derive_ida_tokens(source: Any) -> ThemeTokens:
    """Build a full ThemeTokens from a QApplication-like `source`."""
    qp = _read_qpalette_colors(source)
    semantic = _derive_semantic_tokens(qp)
    return ThemeTokens(**qp, **semantic)
