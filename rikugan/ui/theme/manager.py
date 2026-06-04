"""ThemeManager singleton and color math helpers.

The manager owns the current ThemeMode and exposes:
- mode: the user-selected mode (read/write)
- tokens(): the resolved ThemeTokens for the current mode
- themeChanged: signal emitted on mode change
- set_mode(mode): change mode (triggers debounced QSS rebuild in Task 7)

Helpers (private/public):
- _hex_luminance(hex): sRGB-linearized luminance (IEC 61966-2-1)
- blend_tokens(a, b, t): linear interpolation between two token sets
- format_template(s, mapping): str.format with {placeholders}
- is_dark_tokens(tokens): True when tokens.window is dark (lum < 0.5)
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from PySide6.QtCore import QObject, Signal

from .tokens import ThemeMode, ThemeTokens

# Match only well-formed placeholders: {identifier} where identifier is
# a Python identifier (letters, digits, underscores; not starting with digit).
# This deliberately leaves QSS-style braces like "{ color: red; }" untouched.
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


# === Helpers (public) ===

def is_dark_tokens(tokens: ThemeTokens) -> bool:
    """Return True if tokens.window is a dark color (luminance < 0.5)."""
    return _hex_luminance(tokens.window) < 0.5


def _hex_luminance(hex_color: str) -> float:
    """sRGB-linearized luminance for a #rrggbb color.

    Uses IEC 61966-2-1 EOTF inverse + BT.709 luminance coefficients.
    Returns 0.0-1.0; 0.0 = black, 1.0 = white.

    Tolerates uppercase, but expects a valid 7-char #rrggbb.
    """
    h = hex_color.strip().lower()
    if not (len(h) == 7 and h.startswith("#")):
        return 0.0
    r = int(h[1:3], 16) / 255.0
    g = int(h[3:5], 16) / 255.0
    b = int(h[5:7], 16) / 255.0

    def _srgb_to_linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r_lin, g_lin, b_lin = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def blend_tokens(a: ThemeTokens, b: ThemeTokens, t: float) -> ThemeTokens:
    """Linearly interpolate between two ThemeTokens.

    t=0.0 returns a, t=1.0 returns b, t=0.5 is the midpoint.
    Each field is blended independently; uses sRGB-linear space for accuracy.
    """
    def _blend_hex(h1: str, h2: str, t: float) -> str:
        # Convert to linear, interpolate, convert back to sRGB hex
        c1 = _hex_to_linear_rgb(h1)
        c2 = _hex_to_linear_rgb(h2)
        out = tuple(c1[i] * (1 - t) + c2[i] * t for i in range(3))
        return _linear_rgb_to_hex(out)

    return ThemeTokens(**{
        field: _blend_hex(getattr(a, field), getattr(b, field), t)
        for field in asdict_fields()
    })


def format_template(template: str, mapping: Mapping[str, str]) -> str:
    """Substitute ``{name}`` placeholders with values from ``mapping``.

    Only well-formed identifiers (``{identifier}``) are replaced; any
    other brace sequences (e.g. QSS rules like ``{ color: red; }``) are
    preserved verbatim. Missing keys raise ``KeyError``.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in mapping:
            raise KeyError(key)
        return str(mapping[key])

    return _PLACEHOLDER_RE.sub(_replace, template)


# === Internal helpers (module-private) ===

def _hex_to_linear_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert #rrggbb to linear-light (R, G, B) in 0-1 range."""
    h = hex_color.strip().lower()
    r = int(h[1:3], 16) / 255.0
    g = int(h[3:5], 16) / 255.0
    b = int(h[5:7], 16) / 255.0

    def _srgb_to_linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return (_srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b))


def _linear_rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    """Convert linear-light (R, G, B) in 0-1 range to #rrggbb."""
    def _linear_to_srgb(c: float) -> int:
        c = max(0.0, min(1.0, c))  # clamp
        s = c * 12.92 if c <= 0.00304 else 1.055 * (c ** (1 / 2.4)) - 0.055
        return round(s * 255)

    r, g, b = rgb
    return f"#{_linear_to_srgb(r):02x}{_linear_to_srgb(g):02x}{_linear_to_srgb(b):02x}"


def asdict_fields() -> list[str]:
    """Return the 17 ThemeTokens field names in declaration order."""
    return [
        "window", "window_text", "base", "alt_base", "text",
        "button", "button_text", "highlight", "highlight_text",
        "mid", "light", "dark", "success", "warning", "error",
        "code_text", "code_bg",
    ]


# === ThemeManager (singleton) ===

class ThemeManager(QObject):
    """Singleton holding the active ThemeMode and resolved ThemeTokens.

    Lifecycle:
    - Use ThemeManager.instance() to get the singleton
    - set_mode(mode) updates the mode and emits themeChanged
    - tokens() returns the resolved ThemeTokens for the current mode
    - reset() (class method) clears the singleton (testability)
    """

    themeChanged = Signal(object)  # emits ThemeMode

    _instance: ThemeManager | None = None

    def __init__(self) -> None:
        super().__init__()
        self._mode: ThemeMode = ThemeMode.AUTO
        # _compute_tokens and QSS rebuild are wired in Tasks 6-7.
        # For now, the skeleton just stores mode and emits a signal.

    @classmethod
    def instance(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Clear the singleton. Test-only helper."""
        cls._instance = None

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    def set_mode(self, mode: ThemeMode) -> None:
        """Update the active mode. Emits themeChanged on change."""
        if self._mode == mode:
            return
        self._mode = mode
        self.themeChanged.emit(mode)

    def tokens(self) -> ThemeTokens:
        """Return ThemeTokens for the current mode.

        Note: For Task 4, this returns the palette for the current mode
        with no overrides. Tasks 5-6 add IDA_NATIVE derivation and
        AUTO mode resolution.
        """
        from .palette_dark import DARK_TOKENS
        from .palette_light import LIGHT_TOKENS

        # Simple mapping for now; full resolution lands in Task 6
        if self._mode == ThemeMode.LIGHT:
            return LIGHT_TOKENS
        if self._mode == ThemeMode.DARK:
            return DARK_TOKENS
        # AUTO and IDA_NATIVE: in Task 4, both fall back to DARK
        return DARK_TOKENS
