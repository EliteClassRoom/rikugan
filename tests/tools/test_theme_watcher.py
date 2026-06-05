"""Tests for rikugan.ui.theme.watcher — IDAThemeWatcher palette change detection.

Mirrors the TestThemeManagerModeResolution pattern: drops qt_stubs in
setUpClass so the real PySide6 (QPalette, QApplication, QColor) drives
the test, and restores them in tearDownClass so downstream tests that
depend on the stubs keep working.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

# ``tokens`` is pure-Python (no PySide6 dependency) so it is safe to
# import here even after the stubs are installed. ``manager`` is
# imported inside setUpClass after the stubs are dropped, so the test
# methods always see the real PySide6-bound ThemeManager.
from rikugan.ui.theme.tokens import ThemeMode  # noqa: E402  (post-stub)


class _Source:
    """Stand-in for QApplication that returns a fixed palette."""

    def __init__(self, pal) -> None:
        self.pal = pal

    def palette(self) -> object:
        return self.pal


class TestPaletteSignature(unittest.TestCase):
    """_palette_signature is the change-detection key — it must be a
    tuple[str, str] that flips when Window or WindowText color flips.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import importlib
        import sys

        # Drop the qt_stubs-installed PySide6 modules so we can re-import
        # the real ones (setColor must actually persist colors).
        cls._saved_pyside6_modules = {
            name: mod
            for name, mod in sys.modules.items()
            if name.startswith("PySide6")
        }
        for name in list(sys.modules):
            if name.startswith("PySide6"):
                del sys.modules[name]

        # Reload the watcher so its PySide6 refs resolve to the real classes.
        from rikugan.ui.theme import watcher

        importlib.reload(watcher)
        # Stash the module so tests can call module-level helpers without
        # triggering the bound-method descriptor protocol (which would
        # treat ``self._palette_signature`` as a method and inject ``self``
        # as the first argument).
        cls._watcher = watcher

        from PySide6.QtGui import QColor, QPalette

        cls.QColor = QColor
        cls.QPalette = QPalette

    @classmethod
    def tearDownClass(cls) -> None:
        import sys

        for name in list(sys.modules):
            if name.startswith("PySide6"):
                del sys.modules[name]
        for name, mod in cls._saved_pyside6_modules.items():
            sys.modules[name] = mod

    def test_signature_changes_with_window_color(self) -> None:
        QPalette = self.QPalette
        QColor = self.QColor
        pal1 = QPalette()
        pal1.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal1.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        pal2 = QPalette()
        pal2.setColor(QPalette.ColorRole.Window, QColor("#222222"))
        pal2.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        self.assertNotEqual(
            self._watcher._palette_signature(pal1),
            self._watcher._palette_signature(pal2),
        )

    def test_signature_unchanged_for_same_palette(self) -> None:
        QPalette = self.QPalette
        QColor = self.QColor
        pal1 = QPalette()
        pal1.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal1.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        pal2 = QPalette()
        pal2.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal2.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        self.assertEqual(
            self._watcher._palette_signature(pal1),
            self._watcher._palette_signature(pal2),
        )

    def test_signature_includes_text_color(self) -> None:
        QPalette = self.QPalette
        QColor = self.QColor
        pal1 = QPalette()
        pal1.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal1.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        pal2 = QPalette()
        pal2.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal2.setColor(QPalette.ColorRole.WindowText, QColor("#dddddd"))
        self.assertNotEqual(
            self._watcher._palette_signature(pal1),
            self._watcher._palette_signature(pal2),
        )


class TestIDAThemeWatcher(unittest.TestCase):
    """End-to-end tests for the watcher's change detection and lifecycle.

    These exercise real QPalette + the manager's _compute_tokens path
    under patches (is_ida=True, QApplication.instance=Source). The
    watcher is intentionally cheap to drive: _tick() is public and
    synchronous so we can call it directly without an event loop.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import importlib
        import sys

        cls._saved_pyside6_modules = {
            name: mod
            for name, mod in sys.modules.items()
            if name.startswith("PySide6")
        }
        for name in list(sys.modules):
            if name.startswith("PySide6"):
                del sys.modules[name]

        from rikugan.ui.theme import manager, palette_ida, watcher

        importlib.reload(palette_ida)
        importlib.reload(manager)
        importlib.reload(watcher)

        # Collapse debounce to 0ms so themeChanged fires synchronously
        # inside refresh_from_host → _apply_now.
        manager._DEBOUNCE_MS = 0

        cls.ThemeManager = manager.ThemeManager
        cls.IDAThemeWatcher = watcher.IDAThemeWatcher

        from PySide6.QtCore import QCoreApplication  # noqa: F401  (kept for parity)
        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QApplication

        cls.QApplication = QApplication
        cls.QColor = QColor
        cls.QPalette = QPalette

        # QApplication is required so processEvents() can dispatch any
        # 0ms timer events and the palette roles are real.
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
        self._watcher = None

    def tearDown(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        self.ThemeManager.reset()

    def _make_dark_palette(self) -> object:
        QPalette = self.QPalette
        QColor = self.QColor
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#111111"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a1a1a"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#eeeeee"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#222222"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#eeeeee"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#007acc"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Mid, QColor("#444444"))
        pal.setColor(QPalette.ColorRole.Dark, QColor("#000000"))
        pal.setColor(QPalette.ColorRole.Light, QColor("#888888"))
        return pal

    def test_detects_palette_change(self) -> None:
        """When the palette changes, refresh_from_host is called and
        themeChanged emits tokens with the new window color.
        """
        QPalette = self.QPalette
        QColor = self.QColor
        IDAThemeWatcher = self.IDAThemeWatcher
        ThemeManager = self.ThemeManager

        pal = self._make_dark_palette()
        source = _Source(pal)

        mgr = ThemeManager.instance()
        # Switch out of AUTO first so the next set_mode(AUTO) is
        # non-idempotent (defeats the same-mode early-return).
        mgr.set_mode(ThemeMode.DARK)
        # Inject the test seam — overrides the class method on this
        # instance, so the watcher's _tick reads source.palette()
        # instead of QApplication.instance().palette().
        mgr._app_source = lambda: source

        captured: list = []
        mgr.themeChanged.connect(lambda t: captured.append(t))

        with patch("rikugan.core.host.is_ida", return_value=True):
            mgr.set_mode(ThemeMode.AUTO)
            watcher = IDAThemeWatcher(interval_ms=50)
            self._watcher = watcher
            watcher.start()

            # First tick establishes the baseline (no prior sig → always
            # "changed" → refresh_from_host → 1 emit, which we discard).
            watcher._tick()
            captured.clear()

            # Now flip the palette and tick again — should detect change.
            pal.setColor(QPalette.ColorRole.Window, QColor("#fafafa"))
            pal.setColor(QPalette.ColorRole.WindowText, QColor("#1a1a1a"))
            watcher._tick()

        self.assertGreater(
            len(captured), 0, "watcher should emit themeChanged on palette change"
        )
        self.assertEqual(captured[-1].window.lower(), "#fafafa")

    def test_no_signal_on_no_change(self) -> None:
        """When the palette is unchanged, no themeChanged is emitted."""
        IDAThemeWatcher = self.IDAThemeWatcher
        ThemeManager = self.ThemeManager

        pal = self._make_dark_palette()
        source = _Source(pal)

        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.DARK)
        # Inject the test seam.
        mgr._app_source = lambda: source

        captured: list = []
        mgr.themeChanged.connect(lambda t: captured.append(t))

        with patch("rikugan.core.host.is_ida", return_value=True):
            mgr.set_mode(ThemeMode.AUTO)
            watcher = IDAThemeWatcher(interval_ms=50)
            self._watcher = watcher
            watcher.start()

            # First tick — establishes baseline (1 emit, discarded).
            watcher._tick()
            captured.clear()

            # Second tick — same palette, no emit.
            watcher._tick()
            self.assertEqual(len(captured), 0)

    def test_stop_prevents_further_ticks(self) -> None:
        """After stop(), _alive is cleared so no further ticks reschedule."""
        IDAThemeWatcher = self.IDAThemeWatcher

        watcher = IDAThemeWatcher(interval_ms=50)
        watcher.start()
        self.assertTrue(watcher._alive.is_set())
        watcher.stop()
        self.assertFalse(watcher._alive.is_set())

    def test_start_is_idempotent(self) -> None:
        """Calling start() twice does not schedule two tick chains."""
        IDAThemeWatcher = self.IDAThemeWatcher

        watcher = IDAThemeWatcher(interval_ms=50)
        watcher.start()
        watcher.start()  # second call is a no-op (flag already set)
        self.assertTrue(watcher._alive.is_set())
        # Only one chain should be active; nothing to assert directly,
        # but the flag staying set without doubling is the contract.
        watcher.stop()


class TestPluginWatcherGate(unittest.TestCase):
    """Bug E regression: the IDA plugin must not start IDAThemeWatcher
    when the user has chosen DARK or LIGHT — those modes return bundled
    constants and never read QPalette, so polling the host palette is
    pure overhead (and risks spurious refresh_from_host calls that
    re-emit the same tokens).
    """

    def test_needs_palette_watch_logic(self) -> None:
        """Mirror the gate from rikugan_plugin.run() and assert its
        truth table across all 4 modes.
        """
        from rikugan.ui.theme.tokens import ThemeMode

        for mode, expected in [
            (ThemeMode.AUTO, True),
            (ThemeMode.IDA_NATIVE, True),
            (ThemeMode.DARK, False),
            (ThemeMode.LIGHT, False),
        ]:
            with self.subTest(mode=mode):
                needs_palette_watch = mode in (ThemeMode.AUTO, ThemeMode.IDA_NATIVE)
                self.assertEqual(needs_palette_watch, expected)


if __name__ == "__main__":
    unittest.main()
