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
        # Task 6: themeChanged payload is now ThemeTokens (was ThemeMode).
        m = ThemeManager.instance()
        received: list = []
        m.themeChanged.connect(lambda tokens: received.append(tokens))
        m.set_mode(ThemeMode.LIGHT)
        self.assertEqual(len(received), 1)
        self.assertIsInstance(received[0], ThemeTokens)
        self.assertEqual(received[0].window.lower(), "#ffffff")

    def test_tokens_returns_dataclass(self):
        m = ThemeManager.instance()
        m.set_mode(ThemeMode.DARK)
        # Without app context, mode DARK should still return DARK_TOKENS
        tokens = m.tokens()
        self.assertIsInstance(tokens, ThemeTokens)
        # In DARK mode with no app override, window should be #1e1e1e
        self.assertEqual(tokens.window.lower(), "#1e1e1e")

    def test_apply_now_does_not_set_app_stylesheet(self):
        """Bug A regression: manager._apply_now must NOT call
        QApplication.setStyleSheet() — in a plugin host (IDA, Ghidra) the
        QApplication is shared, so a global QWidget rule would bleed
        into every host widget (disassembly, output window, etc.).
        Widgets subscribe to themeChanged and re-style themselves.
        """
        m = ThemeManager.instance()
        # Track any setStyleSheet calls routed through the seam. The
        # manager uses ThemeManager._app_source() to read palette; in
        # production that returns QApplication.instance(). For this
        # test we inject a fake source with a flag.
        class _TrackingApp:
            def __init__(self) -> None:
                self.setStyleSheet_called_with: list[str] = []

            def setStyleSheet(self, qss: str) -> None:
                self.setStyleSheet_called_with.append(qss)

            def palette(self):
                # Return a minimal palette (qt_stubs may not have one).
                import rikugan.ui.theme.manager as mgr_mod
                return mgr_mod.QPalette()

        app = _TrackingApp()
        m._app_source = lambda: app  # type: ignore[assignment]
        try:
            m.set_mode(ThemeMode.LIGHT)
        finally:
            m._app_source = None  # type: ignore[assignment]
        self.assertEqual(
            app.setStyleSheet_called_with,
            [],
            "manager must not call setStyleSheet on the host QApplication",
        )


class _FakeQApp:
    """Stand-in for QApplication that returns a fixed palette.

    Lives at module scope so TestThemeManagerModeResolution can use it
    without rebuilding for each test.
    """

    def __init__(self, pal) -> None:
        self._pal = pal

    def palette(self):
        return self._pal


class TestThemeManagerModeResolution(unittest.TestCase):
    """Tests for set_mode + _compute_tokens across all 4 modes.

    The qt_stubs module-level injection replaces PySide6.QtGui.QPalette
    with a no-op class that does not preserve state set via setColor().
    These tests need the real PySide6 to exercise a live QPalette, so
    setUpClass drops the stub modules and reloads the theme modules so
    they pick up the real PySide6 (and so QApplication.instance()
    refers to the real class with a real classmethod).
    """

    @classmethod
    def setUpClass(cls) -> None:
        import importlib
        import sys

        # Save a snapshot of the current PySide6 module map so we can
        # restore it in tearDownClass. The qt_stubs module injected
        # these at the top of this test file; other test files in
        # this run (e.g. test_markdown.py) depend on those stubs
        # remaining installed. Without restoration, the dropped stubs
        # would cascade into import errors in unrelated tests.
        cls._saved_pyside6_modules = {
            name: mod
            for name, mod in sys.modules.items()
            if name.startswith("PySide6")
        }

        # Drop all stub PySide6 modules so the real ones get re-imported.
        for name in list(sys.modules):
            if name.startswith("PySide6"):
                del sys.modules[name]

        # Reload the theme modules so their PySide6 references resolve
        # to the real classes. Manager pulls in palette_ida at module
        # load; reload palette_ida first so the name it binds in
        # manager is the freshly-loaded module.
        from rikugan.ui.theme import manager, palette_ida

        importlib.reload(palette_ida)
        importlib.reload(manager)

        # Collapse the 50ms debounce to 0ms for these tests so the
        # synchronous signal payload can be inspected without spinning
        # an event loop. The debounce itself is exercised by
        # TestThemeManagerDebounce below.
        manager._DEBOUNCE_MS = 0

        cls.ThemeManager = manager.ThemeManager
        cls.DARK_TOKENS = palette_ida.DARK_TOKENS if hasattr(palette_ida, "DARK_TOKENS") else None

        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QApplication

        cls.QApplication = QApplication
        cls.QColor = QColor
        cls.QPalette = QPalette

        # QApplication is required so that processEvents() can dispatch
        # 0ms QTimer events. The singleton is reused if it already
        # exists (e.g. when TestThemeManagerDebounce ran first).
        cls._app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        # Restore the original PySide6 stub modules so subsequent test
        # files that depend on stubs (e.g. test_markdown.py) keep
        # working. Without this, the dropped stubs would cascade into
        # import errors in unrelated tests.
        import sys

        for name in list(sys.modules):
            if name.startswith("PySide6"):
                del sys.modules[name]
        for name, mod in cls._saved_pyside6_modules.items():
            sys.modules[name] = mod

    def setUp(self) -> None:
        self.ThemeManager.reset()

    def tearDown(self) -> None:
        self.ThemeManager.reset()

    def test_set_mode_emits_tokens_not_mode(self):
        """After Task 6, set_mode should emit ThemeTokens, not ThemeMode."""
        from PySide6.QtCore import QCoreApplication

        mgr = self.ThemeManager.instance()
        captured: list = []
        mgr.themeChanged.connect(lambda payload: captured.append(payload))
        mgr.set_mode(ThemeMode.DARK)
        # Pump the 0ms debounce timer (set in setUpClass).
        QCoreApplication.processEvents()
        # Token emission — payload is a ThemeTokens instance
        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], ThemeTokens)
        self.assertEqual(captured[0].window.lower(), "#1e1e1e")

    def test_dark_mode_returns_dark_tokens(self):
        mgr = self.ThemeManager.instance()
        mgr.set_mode(ThemeMode.DARK)
        self.assertEqual(mgr.tokens().window.lower(), "#1e1e1e")

    def test_light_mode_returns_light_tokens(self):
        mgr = self.ThemeManager.instance()
        mgr.set_mode(ThemeMode.LIGHT)
        self.assertEqual(mgr.tokens().window.lower(), "#ffffff")

    def test_auto_mode_falls_back_to_dark_on_non_ida(self):
        """AUTO + non-IDA host → DARK_TOKENS (no QApplication lookup)."""
        from unittest.mock import patch

        mgr = self.ThemeManager.instance()
        with patch("rikugan.core.host.is_ida", return_value=False):
            mgr.set_mode(ThemeMode.AUTO)
            self.assertEqual(mgr.tokens().window.lower(), "#1e1e1e")

    def test_auto_mode_uses_ida_palette_when_in_ida(self):
        """AUTO + IDA host with QApplication → derive_ida_tokens(app)."""
        from unittest.mock import patch

        QPalette = self.QPalette
        QColor = self.QColor
        QApplication = self.QApplication

        mgr = self.ThemeManager.instance()
        # Set a different mode first so the subsequent set_mode(AUTO) is
        # not a no-op (idempotency check). This invalidates the cache so
        # _compute_tokens re-runs with the patches active.
        mgr.set_mode(ThemeMode.DARK)
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#abcdef"))
        fake_app = _FakeQApp(pal)

        with patch("rikugan.core.host.is_ida", return_value=True), patch.object(
            QApplication, "instance", return_value=fake_app
        ):
            mgr.set_mode(ThemeMode.AUTO)
            self.assertEqual(mgr.tokens().window.lower(), "#abcdef")

    def test_auto_mode_handles_no_qapplication(self):
        """AUTO + IDA host but no QApplication → fall back to DARK_TOKENS."""
        from unittest.mock import patch

        QApplication = self.QApplication

        mgr = self.ThemeManager.instance()
        with patch("rikugan.core.host.is_ida", return_value=True), patch.object(
            QApplication, "instance", return_value=None
        ):
            mgr.set_mode(ThemeMode.AUTO)
            self.assertEqual(mgr.tokens().window.lower(), "#1e1e1e")

    def test_ida_native_mode_falls_back_on_non_ida(self):
        """IDA_NATIVE on non-IDA host → log warning + DARK_TOKENS."""
        from unittest.mock import patch

        mgr = self.ThemeManager.instance()
        with patch("rikugan.core.host.is_ida", return_value=False):
            mgr.set_mode(ThemeMode.IDA_NATIVE)
            self.assertEqual(mgr.tokens().window.lower(), "#1e1e1e")

    def test_ida_native_mode_uses_ida_palette_when_in_ida(self):
        """IDA_NATIVE + IDA host → derive_ida_tokens(app)."""
        from unittest.mock import patch

        QPalette = self.QPalette
        QColor = self.QColor
        QApplication = self.QApplication

        mgr = self.ThemeManager.instance()
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#123456"))
        fake_app = _FakeQApp(pal)

        with patch("rikugan.core.host.is_ida", return_value=True), patch.object(
            QApplication, "instance", return_value=fake_app
        ):
            mgr.set_mode(ThemeMode.IDA_NATIVE)
            self.assertEqual(mgr.tokens().window.lower(), "#123456")

    def test_set_mode_idempotent(self):
        """Setting the same mode twice should emit only one signal."""
        from PySide6.QtCore import QCoreApplication

        mgr = self.ThemeManager.instance()
        captured: list = []
        mgr.themeChanged.connect(lambda payload: captured.append(payload))
        mgr.set_mode(ThemeMode.DARK)
        mgr.set_mode(ThemeMode.DARK)  # no-op
        # Pump the 0ms debounce timer (set in setUpClass).
        QCoreApplication.processEvents()
        self.assertEqual(len(captured), 1)


class TestThemeManagerDebounce(unittest.TestCase):
    """Tests for the 50ms debounce + QSS rebuild on set_mode (Task 7).

    Mirrors TestThemeManagerModeResolution: drops qt_stubs in setUpClass
    so real PySide6 (QTimer, QCoreApplication, QApplication) drives the
    test. The setUpClass also instantiates a QApplication — Qt timer
    events only fire when an event loop is alive, and we rely on
    processEvents() to drive them after a brief wait (sleep + process
    is the simplest pattern that works without a QEventLoop.exec()).
    """

    @classmethod
    def setUpClass(cls) -> None:
        import importlib
        import sys

        # Save the stub snapshot so tearDownClass can restore it for
        # downstream tests that depend on the stubs.
        cls._saved_pyside6_modules = {
            name: mod
            for name, mod in sys.modules.items()
            if name.startswith("PySide6")
        }
        for name in list(sys.modules):
            if name.startswith("PySide6"):
                del sys.modules[name]

        # Reload the theme module so it binds to real PySide6.
        from rikugan.ui.theme import manager

        importlib.reload(manager)
        cls.ThemeManager = manager.ThemeManager

        # QApplication is required for QTimer events to fire under
        # processEvents(). It is a singleton; the existing instance is
        # reused if one was already created (e.g. by a prior test class).
        from PySide6.QtWidgets import QApplication

        cls.QApplication = QApplication
        cls._app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        import sys

        for name in list(sys.modules):
            if name.startswith("PySide6"):
                del sys.modules[name]
        for name, mod in cls._saved_pyside6_modules.items():
            sys.modules[name] = mod

    def setUp(self) -> None:
        self.ThemeManager.reset()

    def tearDown(self) -> None:
        self.ThemeManager.reset()

    @staticmethod
    def _wait_for_debounce(ms: int = 80) -> None:
        """Wait for a 50ms debounce timer to expire, then pump the event
        loop so the queued timeout event is dispatched.

        processEvents() alone does not wait for unexpired timer events;
        a small sleep + processEvents() is the simplest reliable flush.
        """
        import time

        from PySide6.QtCore import QCoreApplication

        time.sleep(ms / 1000.0)
        QCoreApplication.processEvents()

    def test_rapid_set_mode_emits_only_once(self):
        """3 rapid set_mode calls within 50ms should emit 1 signal total."""
        from PySide6.QtCore import QCoreApplication

        mgr = self.ThemeManager.instance()
        captured: list = []
        mgr.themeChanged.connect(lambda t: captured.append(t))

        mgr.set_mode(ThemeMode.DARK)
        mgr.set_mode(ThemeMode.LIGHT)
        mgr.set_mode(ThemeMode.DARK)

        # Flush the pending debounce apply.
        self._wait_for_debounce()
        # Re-entrant processEvents in case the timer fires during the
        # first dispatch.
        QCoreApplication.processEvents()

        # Only the LAST mode should result in a single emission
        self.assertEqual(len(captured), 1)
        # tokens should be DARK (last mode set)
        self.assertEqual(captured[0].window.lower(), "#1e1e1e")

    def test_qss_not_applied_to_application(self):
        """ThemeManager must NOT call ``QApplication.setStyleSheet()``.

        Rikugan is a plugin loaded into a shared QApplication host (IDA,
        Ghidra). Calling ``app.setStyleSheet()`` would cascade a global
        ``QWidget { ... }`` selector to every host widget (disassembly
        view, function list, output window, ...) and also re-style all
        of them on every theme change — visible as "IDA windows turn
        Rikugan color" and "plugin loads slowly". Per-widget
        stylesheets are the responsibility of subscribers to
        ``themeChanged`` (panel_core, message_widgets, ...).
        """
        from PySide6.QtCore import QCoreApplication  # noqa: I001
        from unittest.mock import MagicMock, patch

        mgr = self.ThemeManager.instance()
        # Warm-up: set to DARK first so the next set_mode is non-idempotent
        mgr.set_mode(ThemeMode.DARK)
        self._wait_for_debounce()  # flush the warm-up's pending apply
        QCoreApplication.processEvents()

        captured_qss: list = []
        mock_app = MagicMock()
        mock_app.setStyleSheet.side_effect = lambda qss: captured_qss.append(qss)

        with patch.object(self.QApplication, "instance", return_value=mock_app):
            mgr.set_mode(ThemeMode.LIGHT)
            self._wait_for_debounce()
            QCoreApplication.processEvents()
            # The manager must not touch the global QApplication
            # stylesheet — that would bleed into the host UI.
            self.assertEqual(
                captured_qss,
                [],
                "ThemeManager must not call QApplication.setStyleSheet() — "
                "it would cascade to every host widget in a shared QApplication.",
            )

    def test_theme_changed_signal_still_emits(self):
        """After the global-QSS removal, ``themeChanged`` must still fire.

        Per-widget subscribers (panel_core, message_widgets, ...) rely
        on this signal to re-apply their own stylesheets, so it must
        keep working even though we no longer touch the application
        stylesheet.
        """
        from PySide6.QtCore import QCoreApplication

        mgr = self.ThemeManager.instance()
        mgr.set_mode(ThemeMode.DARK)
        self._wait_for_debounce()
        QCoreApplication.processEvents()

        captured: list = []
        mgr.themeChanged.connect(lambda tokens: captured.append(tokens))

        mgr.set_mode(ThemeMode.LIGHT)
        self._wait_for_debounce()
        QCoreApplication.processEvents()
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].window.lower(), "#ffffff")


if __name__ == "__main__":
    unittest.main()
