"""Tests for the isolated, passive ``HistoryPanel`` widget.

Spec sections exercised:
- §6.3 (panel content + state copy)
- §6.4 (passive widget — no SessionHistory/config/thread/executor/I/O imports)
- §8.4 (search is case-insensitive title-only, no worker hit)
- §11.3 (titles are plain-text, never interpolated into QSS)
- §13 (Retry only on error; empty / search-empty / error copy exact)

The widget is intentionally passive: tests use the Qt stub injection
from ``tests.qt_stubs`` so no real PySide6 runtime is required. Signal
emission is asserted via direct call to ``clicked.emit()`` /
``mouseReleaseEvent(None)`` so the suite stays deterministic — no event
loop, no flaky pixel measurement.
"""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass

from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()

# Ensure the real module is loaded even if a sibling test stubbed it.
sys.modules.pop("rikugan.ui.history_panel", None)

from rikugan.ui.history_panel import (  # noqa: E402
    HISTORY_PANEL_CONTENT_MAX_WIDTH,
    HistoryPanel,
)
from rikugan.ui.qt_compat import Qt  # noqa: E402


@dataclass(frozen=True)
class _EntryFactory:
    """Build a SessionHistoryEntry-compatible object without importing the
    full DTO module. The widget's signature only requires the named
    attributes the History row reads (``title``, ``session_id``,
    ``provider``, ``model``, ``message_count``, ``updated_at``); other
    fields are ignored.
    """

    session_id: str = "session-a"
    title: str = "Untitled chat"
    created_at: float = 0.0
    updated_at: float = 0.0
    provider: str = ""
    model: str = ""
    message_count: int = 0


def _entry(
    session_id: str = "session-a",
    title: str = "Untitled chat",
    *,
    provider: str = "",
    model: str = "",
    message_count: int = 0,
    updated_at: float = 0.0,
) -> _EntryFactory:
    """Construct a minimal history entry with sensible defaults.

    Tests can override any named field via keyword args; positional
    arguments cover the common ``session_id`` + ``title`` case the
    spec uses as its primary example.
    """
    return _EntryFactory(
        session_id=session_id,
        title=title,
        created_at=0.0,
        updated_at=updated_at,
        provider=provider,
        model=model,
        message_count=message_count,
    )


class TestEmptyStateCopy(unittest.TestCase):
    def test_no_entries_shows_idb_empty_message(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([])
        self.assertEqual(
            panel._status_label.text(),
            "No saved chats for this IDB yet.",
        )
        # Retry must not appear when no entries have been delivered.
        self.assertFalse(panel._retry_btn.isVisible())

    def test_search_miss_shows_search_empty_message(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry("a", "Analyze Parser")])
        panel._search.setText("missing")
        self.assertEqual(
            panel._status_label.text(),
            "No chats match your search.",
        )
        self.assertFalse(panel._retry_btn.isVisible())

    def test_header_titles_are_exact_copy(self) -> None:
        panel = HistoryPanel()
        self.assertEqual(panel._title.text(), "Chat History")
        self.assertEqual(panel._scope_label.text(), "Current IDB")
        self.assertEqual(panel._search.placeholderText(), "Search conversations…")


class TestSearchFiltering(unittest.TestCase):
    def test_search_is_case_insensitive_title_only(self) -> None:
        panel = HistoryPanel()
        panel.set_entries(
            [
                _entry("a", "Analyze Parser"),
                _entry("b", "Map imports"),
            ]
        )
        panel._search.setText(" parser ")
        # Whitespace is stripped; ``casefold`` matches title substring.
        self.assertEqual(panel.visible_session_ids(), ["a"])

    def test_empty_query_returns_full_list(self) -> None:
        panel = HistoryPanel()
        panel.set_entries(
            [
                _entry("a", "Foo"),
                _entry("b", "Bar"),
            ]
        )
        panel._search.setText("foo")  # matches "Foo" only
        self.assertEqual(panel.visible_session_ids(), ["a"])
        panel._search.setText("")
        # Empty query restores the full set (cache-only, no worker hit).
        self.assertEqual(panel.visible_session_ids(), ["a", "b"])

    def test_search_never_inspects_other_fields(self) -> None:
        panel = HistoryPanel()
        panel.set_entries(
            [
                _entry("a", "Foo", provider="claude", model="sonnet"),
            ]
        )
        # Query that matches only a provider/model field must NOT match —
        # search is title-only per spec §8.4.
        panel._search.setText("claude")
        self.assertEqual(panel.visible_session_ids(), [])


class TestPlainTextTitles(unittest.TestCase):
    def test_row_title_is_plain_text(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry(title="<b>not rich</b>")])
        row = panel._row_widgets[0]
        self.assertEqual(row._title.textFormat(), Qt.TextFormat.PlainText)

    def test_row_meta_is_plain_text(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry(title="x")])
        row = panel._row_widgets[0]
        self.assertEqual(row._meta.textFormat(), Qt.TextFormat.PlainText)

    def test_status_label_is_plain_text(self) -> None:
        """The status label carries internal copy (empty / loading / error)
        and must never auto-promote to rich text — Qt's heuristic
        would otherwise allow a malformed copy to escape into HTML."""
        panel = HistoryPanel()
        self.assertEqual(panel._status_label.textFormat(), Qt.TextFormat.PlainText)

    def test_status_label_is_plain_text_after_error(self) -> None:
        """``set_error`` updates the label text; the format guard
        survives the swap."""
        panel = HistoryPanel()
        panel.set_error("Recent chats are still being saved.")
        self.assertEqual(panel._status_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(panel._status_label.text(), "Recent chats are still being saved.")


class TestNoHorizontalOverflow(unittest.TestCase):
    """320 px no-overflow is asserted via deterministic widget properties.

    The panel caps its content width via ``setMaximumWidth`` and forces
    every title / meta label to wrap and respect the same cap. These are
    observable widget state, not pixel measurements, so the test is
    deterministic.
    """

    def test_panel_maximum_width_is_capped_at_320(self) -> None:
        panel = HistoryPanel()
        self.assertLessEqual(panel.maximumWidth(), HISTORY_PANEL_CONTENT_MAX_WIDTH)
        self.assertEqual(HISTORY_PANEL_CONTENT_MAX_WIDTH, 320)

    def test_long_title_label_word_wraps_and_caps_width(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry(title="A" * 240)])
        row = panel._row_widgets[0]
        # Title is forced to wrap so a long string never overflows.
        self.assertTrue(row._title.wordWrap())
        # And it is capped to the content width.
        self.assertLessEqual(row._title.maximumWidth(), HISTORY_PANEL_CONTENT_MAX_WIDTH)

    def test_long_meta_label_word_wraps_and_caps_width(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry(title="x", provider="claude", model="opus-x" * 30, message_count=999)])
        row = panel._row_widgets[0]
        self.assertTrue(row._meta.wordWrap())
        self.assertLessEqual(row._meta.maximumWidth(), HISTORY_PANEL_CONTENT_MAX_WIDTH)

    def test_scroll_area_horizontal_policy_is_always_off(self) -> None:
        """The list scroll area must never show a horizontal scrollbar —
        the canonical ``setHorizontalScrollBarPolicy`` API is used so
        a row title cannot widen the panel past its 320 px cap."""
        panel = HistoryPanel()
        scroll = panel._list_scroll
        self.assertEqual(
            scroll.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )

    def test_scroll_area_keeps_border_and_background_qss(self) -> None:
        """The horizontal-scrollbar QSS rule was removed when the
        scrollbar API took over, but the border / background QSS for
        the scroll area is still applied via ``setStyleSheet`` so the
        host theme paints the area consistently."""
        panel = HistoryPanel()
        scroll = panel._list_scroll
        qss = scroll.styleSheet()
        self.assertIn("QScrollArea", qss)
        self.assertIn("border: none", qss)
        # The scrollbar height hack from the previous implementation is
        # gone — verifying the API-based fix took effect.
        self.assertNotIn("QScrollBar:horizontal", qss)


class TestRetryVisibility(unittest.TestCase):
    def test_retry_hidden_after_set_entries(self) -> None:
        panel = HistoryPanel()
        panel.set_error("boom", retry_visible=True)
        self.assertTrue(panel._retry_btn.isVisible())
        panel.set_entries([_entry("a", "Foo")])
        self.assertFalse(panel._retry_btn.isVisible())

    def test_retry_hidden_when_error_says_so(self) -> None:
        panel = HistoryPanel()
        panel.set_error("Recent chats are still being saved.", retry_visible=False)
        self.assertFalse(panel._retry_btn.isVisible())

    def test_retry_shown_only_after_set_error_with_retry(self) -> None:
        panel = HistoryPanel()
        # Default state: no retry.
        self.assertFalse(panel._retry_btn.isVisible())
        panel.set_loading()
        self.assertFalse(panel._retry_btn.isVisible())
        panel.set_error("Boom", retry_visible=True)
        self.assertTrue(panel._retry_btn.isVisible())


class TestSignals(unittest.TestCase):
    def test_close_button_emits_close_requested(self) -> None:
        panel = HistoryPanel()
        captured: list[str] = []
        panel.close_requested.connect(lambda: captured.append("close"))
        panel._close_btn.clicked.emit()
        self.assertEqual(captured, ["close"])

    def test_retry_button_emits_retry_requested(self) -> None:
        panel = HistoryPanel()
        panel.set_error("Boom", retry_visible=True)
        captured: list[str] = []
        panel.retry_requested.connect(lambda: captured.append("retry"))
        panel._retry_btn.clicked.emit()
        self.assertEqual(captured, ["retry"])

    def test_row_click_emits_session_open_requested_with_session_id(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry("session-42", "Analyze parser")])
        captured: list[str] = []
        panel.session_open_requested.connect(captured.append)
        # ``mouseReleaseEvent`` is a class method, so a synthetic
        # release on the row dispatches the open request.
        row = panel._row_widgets[0]
        row.mouseReleaseEvent(None)
        self.assertEqual(captured, ["session-42"])

    def test_mouse_release_event_is_a_class_method(self) -> None:
        """``mouseReleaseEvent`` must be a class method, not an instance
        attribute set in ``__init__``. Instance-assigned callables
        bypass PySide6's Shiboken dispatch path and can be silently
        masked by a class-level override in a future refactor."""
        from rikugan.ui.history_panel import HistoryRowWidget

        self.assertIn("mouseReleaseEvent", vars(HistoryRowWidget))
        # The descriptor is a function, not a per-instance bound method.
        self.assertTrue(callable(HistoryRowWidget.mouseReleaseEvent))

    def test_mouse_release_event_emits_with_correct_session_id(self) -> None:
        """Class-method form preserves the same behaviour as the
        previous instance-assignment: a click emits the bound entry's
        session_id through the row's signal."""
        panel = HistoryPanel()
        panel.set_entries(
            [
                _entry("session-a", "Foo"),
                _entry("session-b", "Bar"),
            ]
        )
        captured: list[str] = []
        panel.session_open_requested.connect(captured.append)
        # Click each row separately.
        for row in panel._row_widgets:
            row.mouseReleaseEvent(None)
        self.assertEqual(captured, ["session-a", "session-b"])


class TestClearResetsCachedEntriesAndQuery(unittest.TestCase):
    def test_clear_resets_cached_entries(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry("a", "Foo"), _entry("b", "Bar")])
        self.assertEqual(len(panel._row_widgets), 2)
        panel.clear()
        # No rows remain.
        self.assertEqual(panel._row_widgets, [])
        # Status copy reverts to the IDB-empty message.
        self.assertEqual(
            panel._status_label.text(),
            "No saved chats for this IDB yet.",
        )

    def test_clear_resets_query(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry("a", "Foo")])
        panel._search.setText("foo")
        panel.clear()
        # Search box resets so the user starts a fresh query on reopen.
        self.assertEqual(panel._search.text(), "")
        # A subsequent ``set_entries`` shows the full list, not the
        # cached query-filtered subset.
        panel.set_entries([_entry("a", "Foo"), _entry("b", "Bar")])
        self.assertEqual(panel.visible_session_ids(), ["a", "b"])


class TestLoadingState(unittest.TestCase):
    def test_set_loading_does_not_drop_cached_rows(self) -> None:
        """Reopening history starts a refresh; cached rows survive until
        PanelCore delivers a new list. The widget must not clear rows
        when entering the loading state — that is PanelCore's job via
        ``set_entries`` / ``clear``."""
        panel = HistoryPanel()
        panel.set_entries([_entry("a", "Foo")])
        self.assertEqual(len(panel._row_widgets), 1)
        panel.set_loading()
        # Loading status copy is shown, but cached rows are preserved.
        self.assertEqual(len(panel._row_widgets), 1)
        self.assertEqual(panel._status_label.text(), "Loading chats…")
        self.assertFalse(panel._retry_btn.isVisible())

    def test_set_loading_preserves_search_query(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry("a", "Foo")])
        panel._search.setText("foo")
        panel.set_loading()
        self.assertEqual(panel._search.text(), "foo")


class TestShutdownIsIdempotent(unittest.TestCase):
    def test_shutdown_can_be_called_twice(self) -> None:
        panel = HistoryPanel()
        panel.set_entries([_entry("a", "Foo")])
        panel.shutdown()
        # No exception; rows still accessible for inspection.
        panel.shutdown()
        self.assertEqual(len(panel._row_widgets), 1)


class TestNoForbiddenImports(unittest.TestCase):
    """Passive widget invariant: it never imports SessionHistory, the
    config layer, threading primitives, executors, or I/O modules.

    Tasks 8-10 own PanelCore composition. If this test ever fails,
    the widget has grown a forbidden seam that must be removed before
    shipping.

    Substring matches like ``"SessionHistory"`` in ``"SessionHistoryEntry"``
    are allowed because the entry DTO is a frozen data contract the
    widget explicitly consumes — only SessionHistory (the persistence
    layer) and its public methods are forbidden.
    """

    def test_history_panel_does_not_import_io_or_threading(self) -> None:
        import pathlib
        import re

        source = (pathlib.Path(__file__).parents[2] / "rikugan/ui/history_panel.py").read_text(encoding="utf-8")
        # Word-boundary match so "SessionHistory" inside
        # "SessionHistoryEntry" or comments referring to the DTO class
        # does not trip the assertion. ``SessionHistory`` is the
        # persistence layer (forbidden); ``SessionHistoryEntry`` is
        # the immutable DTO the widget consumes (allowed).
        forbidden_patterns = (
            (r"\bSessionHistory\b", "SessionHistory (persistence layer)"),
            (r"\bsave_session\b", "save_session (storage seam)"),
            (r"\bload_session\b", "load_session (storage seam)"),
            (r"\blist_sessions\b", "list_sessions (storage seam)"),
            (r"\bThreadPoolExecutor\b", "ThreadPoolExecutor (threading)"),
            (r"^import threading\b", "threading module"),
            (r"^from threading\b", "threading module"),
            (r"\bsubprocess\b", "subprocess module"),
            (r"\bos\.system\b", "os.system (process spawning)"),
            (r"\bpanel_core\b", "panel_core (composition seam)"),
        )
        for pattern, label in forbidden_patterns:
            self.assertIsNone(
                re.search(pattern, source, re.MULTILINE),
                f"history_panel.py must not reference {label!r} (pattern: {pattern!r})",
            )


if __name__ == "__main__":
    unittest.main()
