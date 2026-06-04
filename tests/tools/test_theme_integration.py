"""End-to-end tests for the theme system — widget subscription round-trip,
mode switching, QSS rebuild path, and full token coverage.

Uses the qt_stubs QTimer (which fires synchronously on start() with a
0ms debounce) so the test does not need a real QApplication or event
loop. This keeps the test fast, deterministic, and free of test
ordering side effects (no drop/restore of PySide6 modules).
"""

from __future__ import annotations

import unittest
from typing import Any

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

from rikugan.ui.theme.manager import ThemeManager
from rikugan.ui.theme.tokens import ThemeMode, ThemeTokens


# The 17 ThemeTokens field names. Order is irrelevant for these tests
# (we use getattr) but listing them explicitly documents the contract.
_ALL_TOKEN_FIELDS: tuple[str, ...] = (
    "window", "window_text", "base", "alt_base", "text",
    "button", "button_text", "highlight", "highlight_text",
    "mid", "dark", "light",
    "success", "warning", "error", "code_bg", "code_text",
)


class TestThemeIntegration(unittest.TestCase):
    """End-to-end tests exercising the ThemeManager singleton as a whole.

    Covers:
    1. widget subscription round-trip (themeChanged signal)
    2. QSS rebuild path on set_mode (smoke test — no exceptions)
    3. multi-mode switching (DARK → LIGHT → AUTO → DARK)
    4. all 4 modes produce valid ThemeTokens with 17 hex fields
    """

    def setUp(self) -> None:
        ThemeManager.reset()

    def tearDown(self) -> None:
        ThemeManager.reset()

    # ------------------------------------------------------------------
    # 1. Subscription round-trip
    # ------------------------------------------------------------------
    def test_widget_receives_tokens_on_subscription(self) -> None:
        """A widget that subscribes to themeChanged should receive tokens
        when the mode is switched AFTER the subscription.

        Qt signals do not replay the initial state — connect() only
        delivers future emissions. The widget must therefore receive
        tokens on the next set_mode call, not on subscription.

        The qt_stub QTimer fires synchronously on start() (0ms debounce),
        so the themeChanged emit happens inside set_mode() without
        needing processEvents.
        """

        class _FakeWidget:
            def __init__(self) -> None:
                self.last_tokens: ThemeTokens | None = None
                ThemeManager.instance().themeChanged.connect(self._on_change)

            def _on_change(self, t: ThemeTokens) -> None:
                self.last_tokens = t

        mgr = ThemeManager.instance()
        # Set initial mode to DARK before the widget subscribes. The
        # qt_stub QTimer fires synchronously, so the DARK emit happens
        # inside set_mode() and is delivered to whatever listeners
        # exist at that time (none yet).
        mgr.set_mode(ThemeMode.DARK)

        # Widget subscribes — it should NOT receive the current DARK
        # state. themeChanged is a "change" signal, not a "current
        # state" signal. Qt only delivers emissions that happen AFTER
        # connect().
        widget = _FakeWidget()
        self.assertIsNone(widget.last_tokens)

        # Switch theme — widget should receive the new (LIGHT) tokens
        # synchronously.
        mgr.set_mode(ThemeMode.LIGHT)

        self.assertIsNotNone(widget.last_tokens)
        # LIGHT theme window is "#ffffff" (different from DARK's #1e1e1e)
        self.assertNotEqual(widget.last_tokens.window.lower(), "#1e1e1e")
        self.assertEqual(widget.last_tokens.window.lower(), "#ffffff")

    # ------------------------------------------------------------------
    # 2. QSS rebuild path (smoke test)
    # ------------------------------------------------------------------
    def test_qss_rebuild_called_on_set_mode(self) -> None:
        """ThemeManager.set_mode() should trigger QSS rebuild without errors.

        The qt_stub QApplication.setStyleSheet is a no-op, so we cannot
        capture the QSS string. This test instead exercises the full
        set_mode → _apply_now → setStyleSheet path and verifies the
        post-switch tokens are valid. The "no exception" assertion is
        implicit: the test would fail with a stack trace otherwise. The
        actual QSS application contract is covered by
        TestThemeManagerDebounce.test_qss_applied_to_application in
        test_theme_manager.py (which patches the real QApplication).
        """
        mgr = ThemeManager.instance()
        # Switch through two modes — each call exercises the full
        # _apply_now path (compute tokens → build stylesheet →
        # qApp.setStyleSheet → emit themeChanged).
        mgr.set_mode(ThemeMode.DARK)
        mgr.set_mode(ThemeMode.LIGHT)

        # Final mode is LIGHT — window should resolve to the LIGHT
        # palette's window color.
        self.assertEqual(mgr.tokens().window.lower(), "#ffffff")

    # ------------------------------------------------------------------
    # 3. Full switch round-trip
    # ------------------------------------------------------------------
    def test_full_switch_round_trip(self) -> None:
        """Dark → Light → Auto → Dark should produce one themeChanged
        emission per distinct mode.

        The qt_stub QTimer fires synchronously on start() (0ms
        debounce), so each set_mode delivers its emit immediately
        before the next set_mode is called. The set_mode idempotency
        check (``if mode == self._mode: return``) ensures that
        re-setting the same mode does not produce a duplicate emit,
        but four distinct modes in sequence produce four distinct
        emissions.
        """
        mgr = ThemeManager.instance()
        captured: list[Any] = []
        mgr.themeChanged.connect(lambda t: captured.append(t))

        # Initial mode is AUTO. Each distinct set_mode below is
        # non-idempotent and emits synchronously.
        mgr.set_mode(ThemeMode.DARK)   # AUTO → DARK
        mgr.set_mode(ThemeMode.LIGHT)  # DARK → LIGHT
        mgr.set_mode(ThemeMode.AUTO)   # LIGHT → AUTO
        mgr.set_mode(ThemeMode.DARK)   # AUTO → DARK

        # All 4 distinct mode switches should produce exactly 4
        # emissions.
        self.assertEqual(len(captured), 4)
        # Each payload must be a ThemeTokens instance with a valid
        # 7-char hex window color.
        for payload in captured:
            self.assertIsInstance(payload, ThemeTokens)
            self.assertTrue(payload.window.startswith("#"))
            self.assertEqual(len(payload.window), 7)

    # ------------------------------------------------------------------
    # 4. All 4 modes produce valid 17-field tokens
    # ------------------------------------------------------------------
    def test_tokens_for_all_modes_resolve(self) -> None:
        """All 4 modes (AUTO, DARK, LIGHT, IDA_NATIVE) should produce
        valid ThemeTokens with all 17 fields populated as #rrggbb.
        """
        for mode in (ThemeMode.AUTO, ThemeMode.DARK, ThemeMode.LIGHT,
                     ThemeMode.IDA_NATIVE):
            mgr = ThemeManager.instance()
            mgr.set_mode(mode)
            tokens = mgr.tokens()

            # Verify all 17 fields are populated
            for field in _ALL_TOKEN_FIELDS:
                value = getattr(tokens, field)
                self.assertTrue(
                    value.startswith("#"),
                    f"{mode.value}.{field} = {value!r} is not a hex color",
                )
                self.assertEqual(
                    len(value), 7,
                    f"{mode.value}.{field} = {value!r} is not a 7-char hex",
                )


if __name__ == "__main__":
    unittest.main()
