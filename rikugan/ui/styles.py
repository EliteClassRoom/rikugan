"""Backward-compat wrapper around rikugan.ui.theme.

This module preserves the public API that widget code has depended on
since pre-theme-system refactors. The 8 public functions delegate to
:mod:`rikugan.ui.theme` (ThemeManager, palette_ida) and the legacy
``DARK_THEME`` / ``IDA_NATIVE_THEME`` constants are now dict-shaped
aliases for ``DARK_TOKENS`` and the fallback palette.

New code should use ``rikugan.ui.theme.ThemeManager.instance()`` directly.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .theme.manager import (
    _QSS_TEMPLATE,
    DARK_TOKENS,
    ThemeManager,
    _hex_luminance,  # re-exported under the same name below
    format_template,
)

# ``_read_qpalette_colors`` is imported lazily inside ``get_host_palette_colors``
# because ``palette_ida`` references ``QPalette.ColorRole`` at module load,
# which the qt_stubs used by the test suite don't provide.
from .theme.tokens import ThemeMode, ThemeTokens  # noqa: F401 — re-exported

# Re-export for backward compat. Order is significant: ``__all__`` documents
# the public surface that older modules (and tests) can still rely on.
__all__ = [  # noqa: RUF022 — grouped by category, not alphabetical
    # color math
    "blend_theme_color",
    "_hex_luminance",
    # palette
    "get_host_palette_colors",
    "use_native_host_theme",
    # stylesheet helpers
    "maybe_host_stylesheet",
    "host_stylesheet",
    "build_theme_stylesheet",
    "build_small_button_stylesheet",
    "build_input_area_stylesheet",
    # legacy constants
    "DARK_THEME",
    "IDA_NATIVE_THEME",
    "_FALLBACK_COLORS",
]


# === Color math =========================================================

def _blend_channel(a: int, b: int, amount: float) -> int:
    """Linearly interpolate one sRGB channel (clamped to [0, 255])."""
    amount = max(0.0, min(1.0, amount))
    return round(a + (b - a) * amount)


def blend_theme_color(color_a: str, color_b: str, amount: float) -> str:
    """Blend two ``#rrggbb`` colors in sRGB space.

    Kept as a free function (not a method on ThemeManager) for backward
    compat with the pre-theme-system import shape:

        from rikugan.ui.styles import blend_theme_color
    """
    a = color_a.lstrip("#")
    b = color_b.lstrip("#")
    if len(a) != 6 or len(b) != 6:
        return color_a

    ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    br, bg, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    return (
        f"#{_blend_channel(ar, br, amount):02x}"
        f"{_blend_channel(ag, bg, amount):02x}"
        f"{_blend_channel(ab, bb, amount):02x}"
    )


# Manager's _hex_luminance is already bound at module import time via the
# import above. The __all__ entry re-exports it under the same name so
# existing callers (``from .styles import _hex_luminance``) keep working.


# === Legacy constants ===================================================
#
# These were originally full QSS strings. The new theme system stores
# colors as a ``ThemeTokens`` dataclass. We expose the constants as
# dicts of QPalette roles so any caller doing ``styles.DARK_THEME['window']``
# keeps working.

_FALLBACK_COLORS = {
    "window": "#1e1e1e",
    "window_text": "#d4d4d4",
    "base": "#1e1e1e",
    "alt_base": "#252526",
    "text": "#d4d4d4",
    "button": "#2d2d30",
    "button_text": "#d4d4d4",
    "highlight": "#0e639c",
    "highlight_text": "#ffffff",
    "mid": "#3c3c3c",
    "dark": "#1a1a1a",
    "light": "#5a5a5a",
}

DARK_THEME = {
    "window": DARK_TOKENS.window,
    "window_text": DARK_TOKENS.window_text,
    "base": DARK_TOKENS.base,
    "alt_base": DARK_TOKENS.alt_base,
    "text": DARK_TOKENS.text,
    "button": DARK_TOKENS.button,
    "button_text": DARK_TOKENS.button_text,
    "highlight": DARK_TOKENS.highlight,
    "highlight_text": DARK_TOKENS.highlight_text,
    "mid": DARK_TOKENS.mid,
    "dark": DARK_TOKENS.dark,
    "light": DARK_TOKENS.light,
}

# IDA_NATIVE_THEME is now derived at runtime from QPalette; this dict
# is just a fallback for callers that need a static reference. The
# manager's ``tokens()`` is the real source of truth.
IDA_NATIVE_THEME = dict(_FALLBACK_COLORS)


# === Palette access =====================================================

def get_host_palette_colors(source: Any = None) -> dict[str, str]:
    """Return the 12 QPalette-role colors as a dict of hex strings.

    Delegates to the manager + ``_read_qpalette_colors`` for the live
    QApplication palette. Falls back to ``_FALLBACK_COLORS`` if no
    QApplication is available or palette access raises.
    """
    try:
        if source is None:
            source = ThemeManager.instance()._app_source()
        if source is None:
            return dict(_FALLBACK_COLORS)
        # Lazy import — ``palette_ida`` references ``QPalette.ColorRole`` at
        # module load, which the qt_stubs used in tests don't provide.
        from .theme.palette_ida import _read_qpalette_colors
        return _read_qpalette_colors(source)
    except Exception:
        return dict(_FALLBACK_COLORS)


# === Native-mode predicates =============================================

def use_native_host_theme() -> bool:
    """Return True when the active theme follows the host's native palette.

    Maps :class:`ThemeMode` to a yes/no answer:

    * ``AUTO`` — True on IDA (use the live QPalette), False elsewhere
      (Binja falls back to DARK via the manager).
    * ``IDA_NATIVE`` — True on IDA, False elsewhere (manager emits a
      warning and falls back to DARK on non-IDA hosts).
    * ``DARK`` / ``LIGHT`` — always False (Rikugan owns the styling).
    """
    from ..core.host import is_ida
    mode = ThemeManager.instance().mode
    if mode in (ThemeMode.AUTO, ThemeMode.IDA_NATIVE):
        return is_ida()
    return False


def maybe_host_stylesheet(css: str) -> str:
    """Return ``css`` unless the host should keep its native theme."""
    return "" if use_native_host_theme() else css


def host_stylesheet(custom_css: str, native_css: str = "") -> str:
    """Pick the right stylesheet for the active host theme mode."""
    return native_css if use_native_host_theme() else custom_css


# === Stylesheet builders ================================================

def build_theme_stylesheet(source: Any = None) -> str:
    """Build the full panel QSS for the current theme.

    Returns ``""`` in native mode (host handles styling) and a full
    QSS built from the current :class:`ThemeTokens` otherwise. The
    ``source`` parameter is kept for backward compat but unused —
    tokens now come from the manager, not from a widget instance.
    """
    if use_native_host_theme():
        return ""
    tokens = ThemeManager.instance().tokens()
    return format_template(_QSS_TEMPLATE, asdict(tokens))


def build_small_button_stylesheet(source: Any = None, danger: bool = False) -> str:
    """Build a palette-aware small button QSS for host UIs.

    * Native mode + ``danger=False`` → empty string (host button styles).
    * Native mode + ``danger=True`` → danger colors only (so Stop /
      Cancel stays red even in IDA native mode). Kept as a string
      constant because in native mode we have no tokens to interpolate.
    * Non-native mode → QSS built from the current ``ThemeTokens``.

    The ``source`` parameter is kept for backward compat but unused.
    """
    if use_native_host_theme() and not danger:
        return ""
    if use_native_host_theme() and danger:
        # Only override the danger colors; let the host keep its own
        # sizing/borders so the button doesn't change shape.
        return (
            "QPushButton { color: #f87171; border: 1px solid #c42b1c; }"
            "QPushButton:hover { background: #3a1a1a; }"
        )
    tokens = ThemeManager.instance().tokens()
    bg = tokens.button
    fg = tokens.button_text
    border = blend_theme_color(tokens.mid, tokens.window, 0.35)
    hover = blend_theme_color(bg, tokens.light, 0.12)
    pressed = blend_theme_color(bg, tokens.dark, 0.15)
    if danger:
        danger_fg = "#f87171"
        danger_border = blend_theme_color("#f44747", tokens.window, 0.2)
        return (
            f"QPushButton {{ background-color: {bg}; color: {danger_fg}; "
            f"border: 1px solid {danger_border}; border-radius: 6px; "
            f"padding: 4px; font-size: 11px; }}"
            f"QPushButton:hover {{ background-color: {blend_theme_color('#3a1a1a', tokens.light, 0.12)}; }}"
            f"QPushButton:pressed {{ background-color: {blend_theme_color('#3a1a1a', tokens.dark, 0.15)}; }}"
        )
    return (
        f"QPushButton {{ background-color: {bg}; color: {fg}; "
        f"border: 1px solid {border}; border-radius: 6px; "
        f"padding: 4px; font-size: 11px; }}"
        f"QPushButton:hover {{ background-color: {hover}; }}"
        f"QPushButton:pressed {{ background-color: {pressed}; }}"
        f"QPushButton:disabled {{ color: {blend_theme_color(fg, tokens.window, 0.45)}; "
        f"border-color: {blend_theme_color(border, tokens.window, 0.35)}; }}"
    )


def build_input_area_stylesheet(source: Any = None) -> str:
    """Build a palette-aware input editor QSS.

    Returns ``""`` in native mode (host editor styles) and a Rikugan
    QSS built from the current ``ThemeTokens`` otherwise.

    The ``source`` parameter is kept for backward compat but unused.
    """
    if use_native_host_theme():
        return ""
    tokens = ThemeManager.instance().tokens()
    bg = blend_theme_color(tokens.window, tokens.button, 0.22)
    border = blend_theme_color(tokens.mid, tokens.window, 0.35)
    return (
        f"QPlainTextEdit, QTextEdit {{ "
        f"background-color: {bg}; color: {tokens.window_text}; "
        f"border: 1px solid {border}; border-radius: 8px; "
        f"padding: 8px; font-size: 13px; "
        f"selection-background-color: {tokens.highlight}; "
        f"selection-color: {tokens.highlight_text}; }}"
        f"QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {tokens.highlight}; }}"
    )
