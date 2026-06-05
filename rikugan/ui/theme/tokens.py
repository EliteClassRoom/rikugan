"""ThemeMode enum and ThemeTokens dataclass — 17 semantic color keys.

The 12 QPalette-aligned keys (window, window_text, base, alt_base, text,
button, button_text, highlight, highlight_text, mid, light, dark) are
derived from QPalette in IDA_NATIVE mode and hardcoded in DARK/LIGHT
modes. The 5 semantic keys (success, warning, error, code_text, code_bg)
are derived per-theme (no QPalette equivalent).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ThemeMode(str, Enum):
    """User-selectable theme mode.

    AUTO: follow host — IDA→native palette, standalone→Dark.
    DARK: Rikugan hardcoded dark theme.
    LIGHT: Rikugan VS Code Light+ theme.
    IDA_NATIVE: always transparent, follow IDA palette (non-IDA falls
        back to DARK with a warning).
    """

    AUTO = "auto"
    DARK = "dark"
    LIGHT = "light"
    IDA_NATIVE = "ida"


@dataclass(frozen=True)
class ThemeTokens:
    """17 semantic color tokens, immutable."""

    # QPalette-aligned (12)
    window: str
    window_text: str
    base: str
    alt_base: str
    text: str
    button: str
    button_text: str
    highlight: str
    highlight_text: str
    mid: str
    light: str
    dark: str
    # Semantic (5) — derived per-theme
    success: str
    warning: str
    error: str
    code_text: str
    code_bg: str


def is_dark_tokens(tokens: ThemeTokens) -> bool:
    """Return True when the token's window color is dark (luminance < 0.5).

    Uses sRGB linearization formula:
    L = 0.2126*R + 0.7152*G + 0.0722*B (linearized).
    """
    # Inline luminance calculation to avoid the import cycle with manager.py
    # (manager.py is not created yet in this task, and is_dark_tokens is
    # called by manager's blend_tokens in later tasks).
    hex_color = tokens.window
    if not (len(hex_color) == 7 and hex_color.startswith("#")):
        return False
    raw = hex_color[1:]
    r = int(raw[0:2], 16) / 255.0
    g = int(raw[2:4], 16) / 255.0
    b = int(raw[4:6], 16) / 255.0

    def _linearize(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r_lin, g_lin, b_lin = _linearize(r), _linearize(g), _linearize(b)
    return (0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin) < 0.5
