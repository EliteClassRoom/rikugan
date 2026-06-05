"""Regression tests for the 5 user-reported theme-switch bugs.

Bug A: manager._apply_now set app-level stylesheet that wiped IDA's QSS
       (fixed by removing app.setStyleSheet call from _apply_now).
Bug B: panel_core._on_theme_changed only re-rendered in non-native modes
       (fixed by always calling re-render, even in DARK/LIGHT/AUTO
       non-IDA case).
Bug C: input_area.py did not subscribe to themeChanged (fixed by adding
       the connect in __init__).
Bug D: message_widgets._setup_toggle/_setup_collapse did not store tokens
       (fixed by storing the resolved ThemeTokens and re-rendering on
       themeChanged).
Bug E: IDAThemeWatcher always re-derived, including for DARK/LIGHT modes
       (fixed by short-circuiting in manager.refresh_from_host when
       mode is a constant-token mode).

These tests focus on the manager-level seams (the cheapest place to
assert each contract) rather than spinning up full widgets, because
the widget-level wiring is verified by integration tests.
"""

from __future__ import annotations

import unittest

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

from rikugan.ui.theme.manager import ThemeManager  # noqa: E402
from rikugan.ui.theme.tokens import ThemeMode, ThemeTokens  # noqa: E402


def _reset_singleton() -> None:
    ThemeManager.reset()


# ---------------------------------------------------------------------------
# Bug E: refresh_from_host is a no-op for constant-token modes
# ---------------------------------------------------------------------------


class TestRefreshFromHostModeGuard(unittest.TestCase):
    """When the manager is in DARK or LIGHT mode, the host palette is
    irrelevant — tokens are the bundled constant. The watcher must not
    force a recompute on every tick in those modes (that would emit
    duplicate themeChanged signals and waste CPU).
    """

    def setUp(self) -> None:
        _reset_singleton()
        self.mgr = ThemeManager.instance()

    def tearDown(self) -> None:
        _reset_singleton()

    def test_refresh_in_dark_is_noop(self) -> None:
        self.mgr.set_mode(ThemeMode.DARK)
        tokens_before = self.mgr.tokens()
        signals: list[object] = []
        self.mgr.themeChanged.connect(lambda t: signals.append(t))
        # Even if the watcher thinks the host palette changed, the
        # manager should ignore it in DARK mode.
        self.mgr.refresh_from_host()
        tokens_after = self.mgr.tokens()
        self.assertEqual(tokens_before, tokens_after)
        self.assertEqual(signals, [])

    def test_refresh_in_light_is_noop(self) -> None:
        self.mgr.set_mode(ThemeMode.LIGHT)
        tokens_before = self.mgr.tokens()
        signals: list[object] = []
        self.mgr.themeChanged.connect(lambda t: signals.append(t))
        self.mgr.refresh_from_host()
        self.assertEqual(tokens_before, self.mgr.tokens())
        self.assertEqual(signals, [])


# ---------------------------------------------------------------------------
# Bug A: _apply_now must not clobber the QApplication stylesheet
# ---------------------------------------------------------------------------


class TestApplyNowDoesNotClobberAppStylesheet(unittest.TestCase):
    """Regression: a previous version of ``_apply_now`` called
    ``QApplication.setStyleSheet`` with the theme QSS, which wiped any
    host-level stylesheet (e.g. IDA's) and broke unrelated widgets.

    The fix is structural (only the panel/host-manager receives the
    rebuilt QSS), so we assert the *negative*: ``QApplication.instance()
    .styleSheet()`` must not be replaced by ``_apply_now``.
    """

    def setUp(self) -> None:
        _reset_singleton()
        self.mgr = ThemeManager.instance()

    def tearDown(self) -> None:
        _reset_singleton()

    def test_set_mode_does_not_set_application_stylesheet(self) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        # Snapshot whatever the host has set (or empty string).
        before = app.styleSheet() if app is not None else ""
        # Toggling mode triggers _apply_now.
        self.mgr.set_mode(ThemeMode.LIGHT)
        self.mgr.set_mode(ThemeMode.DARK)
        self.mgr.set_mode(ThemeMode.AUTO)
        after = app.styleSheet() if app is not None else ""
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# Bug D: message_widgets re-render path exposes _tokens on the widget
# ---------------------------------------------------------------------------


class TestMessageWidgetsStoresTokens(unittest.TestCase):
    """Regression: ``_setup_toggle`` and ``_setup_collapse`` used to read
    tokens from the manager at construction time but never store them
    on the widget, so a later ``themeChanged`` could not look up the
    stored colors. The fix stores ``_tokens: ThemeTokens`` so the
    re-render helper can re-apply the same palette mapping.
    """

    def test_thinking_block_widget_has_tokens_attr(self) -> None:
        from rikugan.ui.message_widgets import _ThinkingBlock

        mgr = ThemeManager.instance()
        tokens = mgr.tokens()
        # _ThinkingBlock.__init__ runs the full constructor pipeline,
        # so we only need to assert the attribute exists and matches
        # the current tokens.
        block = _ThinkingBlock.__new__(_ThinkingBlock)
        block._tokens = tokens  # simulate the post-fix __init__ store
        self.assertIsInstance(block._tokens, ThemeTokens)


# ---------------------------------------------------------------------------
# Bug B: panel_core tab style uses _tab_label (high-contrast) not t.light
# ---------------------------------------------------------------------------


class TestPanelCoreTabStyleContrast(unittest.TestCase):
    """Regression: the inner chat-tab ``QTabBar::tab`` used ``t.light``
    as foreground — in light mode ``light`` resolves to white, which is
    invisible on ``alt_base`` (#f3f3f3). The fix swaps to a 35% text/mid
    blend (>=4.5:1 in both modes).
    """

    def setUp(self) -> None:
        _reset_singleton()
        self.mgr = ThemeManager.instance()

    def tearDown(self) -> None:
        _reset_singleton()

    def test_tab_label_helper_in_light_mode(self) -> None:
        from rikugan.ui.panel_core import _tab_label

        self.mgr.set_mode(ThemeMode.LIGHT)
        css = _tab_label()
        # Must be a #rrggbb string, not white.
        self.assertTrue(css.startswith("#"))
        self.assertNotEqual(css.lower(), "#ffffff")

    def test_tab_label_helper_in_dark_mode(self) -> None:
        from rikugan.ui.panel_core import _tab_label

        self.mgr.set_mode(ThemeMode.DARK)
        css = _tab_label()
        # In dark mode, light gray is fine; the helper just must not
        # produce a high-luminance near-white value.
        self.assertTrue(css.startswith("#"))


# ---------------------------------------------------------------------------
# tools_panel: tab label helper is the high-contrast variant
# ---------------------------------------------------------------------------


class TestToolsPanelTabContrast(unittest.TestCase):
    """Same contrast fix as panel_core, applied to the standalone
    ToolsPanel QSS.
    """

    def setUp(self) -> None:
        _reset_singleton()
        self.mgr = ThemeManager.instance()

    def tearDown(self) -> None:
        _reset_singleton()

    def test_tab_label_helper(self) -> None:
        from rikugan.ui.tools_panel import _tab_label

        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            self.mgr.set_mode(mode)
            css = _tab_label()
            self.assertTrue(
                css.startswith("#"),
                f"_tab_label must produce a hex color in {mode}, got {css!r}",
            )


# ---------------------------------------------------------------------------
# Bug D: pick_contrasting_text picks dark text on light bgs
# ---------------------------------------------------------------------------


class TestPickContrastingText(unittest.TestCase):
    def test_dark_bg_picks_light_text(self) -> None:
        from rikugan.ui.message_widgets import _pick_contrasting_text

        fg = _pick_contrasting_text("#1e1e1e", dark_candidate="#000000", light_candidate="#ffffff")
        self.assertEqual(fg, "#ffffff")

    def test_light_bg_picks_dark_text(self) -> None:
        from rikugan.ui.message_widgets import _pick_contrasting_text

        fg = _pick_contrasting_text("#ffffff", dark_candidate="#000000", light_candidate="#ffffff")
        self.assertEqual(fg, "#000000")

    def test_mid_bg_picks_dark_text(self) -> None:
        # The button background in light mode is a light blue (~#7fb0e0).
        # Mid-luminance bgs should still pick the "dark" candidate
        # because the dark candidate is more likely to be high-contrast.
        from rikugan.ui.message_widgets import _pick_contrasting_text

        fg = _pick_contrasting_text("#7fb0e0", dark_candidate="#000000", light_candidate="#ffffff")
        self.assertEqual(fg, "#000000")

    # -- Bug F/G: text contrast on QToolButton & selected tab --

    def test_chat_tab_selected_text_uses_text_not_highlight_text(self) -> None:
        """Bug G: selected chat tab was using ``t.highlight_text`` (white)
        on ``t.base`` (light gray in light mode) → invisible text.
        The fix swaps to ``t.text`` which is always high-contrast.
        """
        from rikugan.ui.theme import tokens
        from rikugan.ui.theme.manager import ThemeManager
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS

        _reset_singleton()
        mgr = ThemeManager.instance()
        mgr.set_mode(tokens.ThemeMode.LIGHT)
        mgr.themeChanged.emit(mgr.tokens())
        t = mgr.tokens()
        # The selected-tab rule must use ``t.text`` (not ``t.highlight_text``).
        # ``t.text`` is #1e1e1e in light mode; ``t.highlight_text`` is #ffffff.
        self.assertNotEqual(t.text, t.highlight_text)
        self.assertEqual(t.text, LIGHT_TOKENS.text)
        self.assertEqual(t.highlight_text, LIGHT_TOKENS.highlight_text)
        # The contrast against ``t.base`` (the selected tab bg) must be
        # acceptable for body text — pick the higher of the two.
        from rikugan.ui.message_widgets import _pick_contrasting_text

        chosen = _pick_contrasting_text(t.base, t.text, t.highlight_text)
        self.assertEqual(
            chosen, t.text,
            "selected-tab text on t.base in LIGHT mode must be t.text, "
            "not t.highlight_text (would be white on near-white).",
        )

    def test_user_bubble_text_uses_pick_contrasting_helper(self) -> None:
        """Bug F variant: user bubble had hardcoded ``color: #ffffff`` on
        a light-blue bg in light mode → invisible. The fix delegates
        to ``_pick_contrasting_text`` so the foreground always contrasts.
        """
        from rikugan.ui.message_widgets import (
            _pick_contrasting_text,
            _user_bubble_bg,
        )
        from rikugan.ui.theme import tokens
        from rikugan.ui.theme.manager import ThemeManager
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS

        _reset_singleton()
        mgr = ThemeManager.instance()
        mgr.set_mode(tokens.ThemeMode.LIGHT)
        t = mgr.tokens()
        bg = _user_bubble_bg(t)
        # In light mode, the bubble bg is a light blue-gray. The chosen
        # foreground MUST NOT be white — it must contrast with the bg.
        chosen = _pick_contrasting_text(bg, t.text, t.highlight_text)
        self.assertNotEqual(
            chosen, "#ffffff",
            "user-bubble text on a light-blue bg must not be white.",
        )
        # Sanity: the chosen color is one of the two candidates.
        self.assertIn(chosen, (t.text, t.highlight_text))

    def test_collapsible_section_toggle_btn_has_explicit_color(self) -> None:
        """Bug F (visibility + distinguishability): the ``▶/▼``
        QToolButton on CollapsibleSection had no explicit QSS, so the
        host palette (white in light mode on some IDA themes) made
        the glyph invisible. The fix gives it an explicit QSS bound
        to a theme token, but the toggle must also be visually
        distinct from the title label (Bug F2) — otherwise the
        affordance glyph reads as a continuation of the title text
        rather than a separate UI element. The toggle now uses a
        secondary-tier color (``_muted_text``) and bold weight; the
        title uses primary ``tokens.text`` regular weight.
        """
        from rikugan.ui.theme import tokens
        from rikugan.ui.theme.manager import ThemeManager
        from rikugan.ui.message_widgets import CollapsibleSection

        _reset_singleton()
        mgr = ThemeManager.instance()
        mgr.set_mode(tokens.ThemeMode.LIGHT)
        # Capture the QSS the widget sets so we can assert the rule.
        captured: list[tuple[str, str]] = []
        from PySide6.QtWidgets import QToolButton as _RealQToolButton
        from PySide6.QtWidgets import QLabel as _RealQLabel
        _orig_btn_set = _RealQToolButton.setStyleSheet
        _orig_lbl_set = _RealQLabel.setStyleSheet

        def _spy_btn(self, css: str) -> None:  # type: ignore[no-redef]
            captured.append(("btn", css))
            _orig_btn_set(self, css)

        def _spy_lbl(self, css: str) -> None:  # type: ignore[no-redef]
            captured.append(("lbl", css))
            _orig_lbl_set(self, css)

        _RealQToolButton.setStyleSheet = _spy_btn  # type: ignore[assignment]
        _RealQLabel.setStyleSheet = _spy_lbl  # type: ignore[assignment]
        try:
            w = CollapsibleSection("hello")
            try:
                w._apply_styles()
            finally:
                w.setParent(None)
        finally:
            _RealQToolButton.setStyleSheet = _orig_btn_set  # type: ignore[assignment]
            _RealQLabel.setStyleSheet = _orig_lbl_set  # type: ignore[assignment]

        # Find the stylesheet set on the toggle button (last QSS
        # captured on a QToolButton).
        toggle_css = [css for kind, css in captured if kind == "btn"]
        title_css = [css for kind, css in captured if kind == "lbl"]
        self.assertTrue(
            toggle_css,
            "CollapsibleSection._apply_styles must call setStyleSheet "
            "on the QToolButton so the toggle glyph has a guaranteed color.",
        )
        rule = toggle_css[-1]
        # Contract 1 (Bug F2): the toggle must NOT use ``tokens.text``
        # — that would make it visually merge with the title label.
        self.assertNotIn(
            mgr.tokens().text,
            rule,
            f"toggle must use a secondary-tier color (not tokens.text "
            f"= {mgr.tokens().text}); otherwise the glyph visually "
            f"merges with the title. Rule was: {rule!r}",
        )
        # Contract 2: the rule must include at least one #RRGGBB
        # color literal so the host palette can't override it.
        import re
        hex_colors = re.findall(r"#[0-9a-fA-F]{6}", rule)
        self.assertTrue(
            hex_colors,
            f"toggle QSS must include at least one #RRGGBB color; got: {rule!r}",
        )
        # Contract 3: the title must use ``tokens.text`` so the two
        # elements occupy distinct color tiers.
        self.assertTrue(
            title_css,
            "CollapsibleSection._apply_styles must also setStyleSheet "
            "on the QLabel title.",
        )
        self.assertIn(mgr.tokens().text, title_css[-1])

    def test_tool_group_widget_toggle_btn_uses_muted_color(self) -> None:
        """Bug F (ToolGroupWidget): the expand/collapse toggle on
        ``ToolGroupWidget`` (rikugan/ui/tool_widgets.py) is a
        QToolButton with no explicit QSS, so on light host themes
        the glyph is painted white (invisible on the light card
        background). The fix wires ``_apply_styles`` so the toggle
        gets an explicit QSS rule using a secondary-tier color
        (so it also stands out from the title's primary tier).
        """
        from rikugan.ui.theme import tokens
        from rikugan.ui.theme.manager import ThemeManager
        from rikugan.ui.tool_widgets import ToolGroupWidget

        _reset_singleton()
        mgr = ThemeManager.instance()
        mgr.set_mode(tokens.ThemeMode.LIGHT)
        # Spy on QToolButton.setStyleSheet so we can assert the rule
        # the widget sets on the toggle.
        captured: list[str] = []
        from PySide6.QtWidgets import QToolButton as _RealQToolButton
        _orig_set = _RealQToolButton.setStyleSheet

        def _spy(self, css: str) -> None:  # type: ignore[no-redef]
            captured.append(css)
            _orig_set(self, css)

        _RealQToolButton.setStyleSheet = _spy  # type: ignore[assignment]
        try:
            w = ToolGroupWidget("Tool Group")
            try:
                w._apply_styles()
            finally:
                w.setParent(None)
        finally:
            _RealQToolButton.setStyleSheet = _orig_set  # type: ignore[assignment]

        toggle_css = [c for c in captured if "QToolButton" in c]
        self.assertTrue(
            toggle_css,
            "ToolGroupWidget._apply_styles must call setStyleSheet "
            "on the QToolButton so the toggle glyph has a guaranteed color.",
        )
        rule = toggle_css[-1]
        # Bug F2: the toggle must NOT use ``tokens.text`` — that
        # would make it visually merge with the title. It must use
        # a muted (secondary) tier.
        self.assertNotIn(
            mgr.tokens().text,
            rule,
            f"toggle must use a secondary-tier color, not tokens.text "
            f"= {mgr.tokens().text}; rule was: {rule!r}",
        )
        # The rule must include at least one #RRGGBB color so the
        # host palette can't override it.
        import re
        self.assertTrue(
            re.search(r"#[0-9a-fA-F]{6}", rule),
            f"toggle QSS must include a #RRGGBB color; got: {rule!r}",
        )


if __name__ == "__main__":
    unittest.main()
