"""ThemeManager singleton and color math helpers.

The manager owns the current ThemeMode and exposes:
- mode: the user-selected mode (read/write)
- tokens(): the resolved ThemeTokens for the current mode
- themeChanged: signal emitted on mode change (carries the new ThemeTokens)
- set_mode(mode): change mode (triggers debounced QSS rebuild in Task 7)

Helpers (private/public):
- _hex_luminance(hex): sRGB-linearized luminance (IEC 61966-2-1)
- blend_tokens(a, b, t): linear interpolation between two token sets
- format_template(s, mapping): str.format with {placeholders}
- is_dark_tokens(tokens): True when tokens.window is dark (lum < 0.5)
    (re-exported from .tokens; lives there to keep the type module's
    predicates self-contained)
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal  # type: ignore[import-not-found]
from PySide6.QtWidgets import QApplication  # type: ignore[import-not-found]

from .palette_dark import DARK_TOKENS
from .palette_light import LIGHT_TOKENS
from .tokens import ThemeMode, ThemeTokens, is_dark_tokens  # noqa: F401 — re-exported for tests

# Logging is best-effort: when other tests in the suite replace
# rikugan.core.logging with a stub module that lacks get_logger, we
# fall back to a no-op logger so manager.py can still be imported.
try:
    from ...core.logging import get_logger
except ImportError:  # pragma: no cover — defensive guard
    import logging as _logging

    def get_logger() -> _logging.Logger:  # type: ignore[no-redef]
        return _logging.getLogger("Rikugan")

# Note: palette_ida is imported lazily inside _compute_tokens to break the
# manager <-> palette_ida cycle (palette_ida imports _blend_hex / _hex_luminance
# from manager at module load).

# Match only well-formed placeholders: {identifier} where identifier is
# a Python identifier (letters, digits, underscores; not starting with digit).
# This deliberately leaves QSS-style braces like "{ color: red; }" untouched.
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


# === Helpers (public) ===

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


def _blend_hex(h1: str, h2: str, t: float) -> str:
    """Linearly interpolate two #rrggbb colors in sRGB-linear space.

    t=0.0 returns h1, t=1.0 returns h2, t=0.5 is the midpoint. Used by
    both blend_tokens (per-field blending) and palette_ida (semantic
    hue blending). Module-level so palette_ida can import the primitive
    directly without rebuilding full ThemeTokens.
    """
    c1 = _hex_to_linear_rgb(h1)
    c2 = _hex_to_linear_rgb(h2)
    out = tuple(c1[i] * (1 - t) + c2[i] * t for i in range(3))
    return _linear_rgb_to_hex(out)


def blend_tokens(a: ThemeTokens, b: ThemeTokens, t: float) -> ThemeTokens:
    """Linearly interpolate between two ThemeTokens.

    t=0.0 returns a, t=1.0 returns b, t=0.5 is the midpoint.
    Each field is blended independently; uses sRGB-linear space for accuracy.
    """
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

_DEBOUNCE_MS = 50

# Minimal QSS template — covers the most-common widget backgrounds. The
# full template is built incrementally as more widgets subscribe; for
# now this is enough to verify the rebuild path works.
_QSS_TEMPLATE = """
QWidget {{
    background-color: {window};
    color: {text};
}}
QFrame {{
    background-color: {base};
    border: 1px solid {mid};
}}
QPushButton {{
    background-color: {button};
    color: {button_text};
    border: 1px solid {mid};
    padding: 4px;
    border-radius: 4px;
}}
QPushButton:hover {{
    background-color: {alt_base};
}}
QToolButton {{
    background-color: {button};
    color: {button_text};
    border: 1px solid {mid};
    padding: 2px;
}}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {base};
    color: {text};
    border: 1px solid {mid};
    selection-background-color: {highlight};
    selection-color: {highlight_text};
}}
QTabWidget::pane {{
    border: 1px solid {mid};
    background-color: {window};
}}
QTabBar::tab {{
    background-color: {alt_base};
    color: {text};
    padding: 6px 12px;
    border: 1px solid {mid};
}}
QTabBar::tab:selected {{
    background-color: {window};
    color: {text};
}}
QMenu {{
    background-color: {window};
    color: {text};
    border: 1px solid {mid};
}}
QMenu::item:selected {{
    background-color: {highlight};
    color: {highlight_text};
}}
QScrollBar:vertical {{
    background-color: {alt_base};
    width: 12px;
}}
QScrollBar::handle:vertical {{
    background-color: {mid};
    border-radius: 4px;
}}
QScrollBar:horizontal {{
    background-color: {alt_base};
    height: 12px;
}}
QScrollBar::handle:horizontal {{
    background-color: {mid};
    border-radius: 4px;
}}
"""


class ThemeManager(QObject):
    """Singleton holding the active ThemeMode and resolved ThemeTokens.

    Lifecycle:
    - Use ThemeManager.instance() to get the singleton
    - set_mode(mode) updates the mode and emits themeChanged (with tokens)
    - tokens() returns the resolved ThemeTokens for the current mode
    - reset() (class method) clears the singleton (testability)
    """

    themeChanged = Signal(object)  # emits ThemeTokens (was ThemeMode before Task 6)

    _instance: ThemeManager | None = None

    def __init__(self) -> None:
        super().__init__()
        self._mode: ThemeMode = ThemeMode.AUTO
        self._tokens_cache: ThemeTokens | None = None
        self._pending_apply: QTimer | None = None
        # Compute initial tokens immediately so the first themeChanged
        # listener can render correctly (Task 14 tests this).
        self._tokens_cache = self._compute_tokens()
        # AUTO-mode derivation hint log is shown exactly once so users
        # can confirm in the IDA Output window that the manager is
        # actually pulling from the host palette (and not just falling
        # through to DARK_TOKENS). Reset by ``reset()`` for tests.
        self._log_auto_derive_once_flag: bool = False

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
        """Set the theme mode. No-op if same value. Debounces rapid switches.

        Rapid calls within 50ms coalesce into a single QSS rebuild + signal emit.
        """
        if mode == self._mode:
            return
        self._mode = mode
        self._tokens_cache = None  # force recompute on apply
        # Debounce: if a previous apply is pending, cancel it.
        if self._pending_apply is not None:
            self._pending_apply.stop()
        # Parent the timer to self so it is destroyed with the manager
        # and its queued timeout events cannot fire on a freed object.
        self._pending_apply = QTimer(self)
        self._pending_apply.setSingleShot(True)
        self._pending_apply.timeout.connect(self._apply_now)
        self._pending_apply.start(_DEBOUNCE_MS)

    def tokens(self) -> ThemeTokens:
        """Return ThemeTokens for the current mode (cached)."""
        if self._tokens_cache is None:
            self._tokens_cache = self._compute_tokens()
        return self._tokens_cache

    def refresh_from_host(self) -> None:
        """Re-derive tokens from the current QApplication palette.

        Called by ``IDAThemeWatcher`` when ``QPalette`` changes. Invalidates
        the token cache and re-applies (QSS + signal emit), bypassing the
        debounce — the watcher tick is already rate-limited at 500ms
        intervals, so additional coalescing is unnecessary and would
        only delay the user's switch by 50ms.

        For DARK and LIGHT modes, the bundled constant tokens are the
        source of truth (the user explicitly picked that look). The
        host palette is irrelevant, so the call is a no-op — this both
        saves work and avoids spuriously emitting ``themeChanged``
        whenever IDA repaints its own widgets.
        """
        if self._mode in (ThemeMode.DARK, ThemeMode.LIGHT):
            return
        self._tokens_cache = None
        # Bypass debounce — watcher tick is already rate-limited.
        if self._pending_apply is not None:
            self._pending_apply.stop()
            self._pending_apply = None
        self._apply_now()

    def _log_auto_derive_once(self, tokens: ThemeTokens) -> None:
        """One-shot INFO log confirming AUTO-mode derivation.

        Helps users diagnose the common "AUTO looks identical to DARK"
        complaint: IDA's default palette is dark, so the manager is
        doing the right thing — it just looks like DARK until the user
        picks a non-default theme via View → Change theme or
        ``idaalt``. Without this log, users assume the manager is
        silently falling through to DARK_TOKENS.
        """
        if self._log_auto_derive_once_flag:
            return
        self._log_auto_derive_once_flag = True
        try:
            from ...core.logging import log_info

            log_info(
                f"ThemeManager: AUTO mode deriving from host palette — "
                f"window={tokens.window}, text={tokens.text}, "
                f"base={tokens.base}. If AUTO looks identical to DARK, "
                f"your IDA theme is also dark; try View → Change theme."
            )
        except Exception:
            # Logging is best-effort; never let a log call break the
            # theme apply path.
            pass

    def _app_source(self) -> Any:
        """Return the object to read QPalette from. Patchable for tests.

        Production: returns ``QApplication.instance()`` (the QApplication
        singleton). Tests: can be overridden (e.g.
        ``mgr._app_source = lambda: fake_source``) to inject a fake
        QApplication without monkey-patching PySide6.

        The method is deliberately annotated as ``Any`` — the seam is
        duck-typed: any object with a ``.palette()`` method works.
        """
        return QApplication.instance()

    def _apply_now(self) -> None:
        """Compute current tokens and emit ``themeChanged``.

        Per-widget stylesheets are the responsibility of individual
        widgets (panel_core, message_widgets, etc.) which subscribe to
        ``themeChanged``. The manager deliberately does NOT call
        ``QApplication.setStyleSheet()`` because:

        * In a plugin host (IDA) the QApplication is shared, so a
          global ``QWidget { ... }`` selector bleeds into every host
          widget (disassembly view, output window, function list...).
        * ``setStyleSheet()`` re-styles every widget in the process, so
          it is also a major startup / runtime cost.

        The previous incarnation of this method did call
        ``app.setStyleSheet()`` and caused both regressions: IDA's own
        windows picked up Rikugan's colors, and plugin load became
        noticeably slower on hosts with many widgets.
        """
        tokens = self.tokens()
        self.themeChanged.emit(tokens)
        self._pending_apply = None

    def _compute_tokens(self) -> ThemeTokens:
        """Compute tokens for the current mode.

        AUTO: IDA → derive_ida_tokens; standalone → DARK_TOKENS.
        DARK: DARK_TOKENS.
        LIGHT: LIGHT_TOKENS.
        IDA_NATIVE: derive_ida_tokens (non-IDA → DARK_TOKENS + warning log).

        Palette reads go through ``_app_source()`` so tests can inject a
        fake QApplication (or an offline stub) without monkey-patching
        ``QApplication.instance``. Production behavior is unchanged
        because the seam's default implementation delegates to
        ``QApplication.instance()``.
        """
        from ...core.host import is_ida
        from ...core.logging import log_warning

        if self._mode == ThemeMode.DARK:
            return DARK_TOKENS
        if self._mode == ThemeMode.LIGHT:
            return LIGHT_TOKENS
        if self._mode == ThemeMode.AUTO:
            if is_ida():
                try:
                    # Lazy import: palette_ida imports _blend_hex from
                    # this module at load time, so a module-level import
                    # would create a cycle. Falling through to DARK_TOKENS
                    # if the import or palette lookup fails keeps the
                    # manager usable when Qt is unavailable (e.g. in
                    # tests that don't load the real PySide6).
                    from .palette_ida import derive_ida_tokens

                    app = self._app_source()
                    if app is not None:
                        tokens = derive_ida_tokens(app)
                        # One-time hint log so users can confirm in the
                        # IDA Output window that AUTO is actually
                        # deriving from the host palette and not just
                        # returning DARK_TOKENS. Common confusion:
                        # IDA's default palette is dark, so AUTO will
                        # look identical to DARK until the user picks a
                        # non-default theme via View → Change theme.
                        self._log_auto_derive_once(tokens)
                        return tokens
                except Exception:
                    pass
            return DARK_TOKENS
        if self._mode == ThemeMode.IDA_NATIVE:
            if not is_ida():
                log_warning(
                    "IDA Native theme requested on non-IDA host; "
                    "falling back to Dark"
                )
                return DARK_TOKENS
            try:
                from .palette_ida import derive_ida_tokens

                app = self._app_source()
                if app is not None:
                    return derive_ida_tokens(app)
            except Exception:
                pass
            return DARK_TOKENS
        return DARK_TOKENS  # unreachable; defensive
