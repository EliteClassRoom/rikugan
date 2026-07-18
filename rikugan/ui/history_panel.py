"""Chat History side panel — isolated, passive metadata-only widget.

This widget is intentionally passive (spec §6.3):

* It never imports the chat-history persistence layer, the
  composition seam, threading primitives, executors, file I/O, or any
  other heavyweight seam.
* It exposes a Qt-only main-thread surface — three signals and five
  methods. PanelCore owns the worker, request queue, generation
  counter, and polling timer.
* It accepts a frozen :class:`SessionHistoryEntry` DTO per row and
  never exposes storage internals (paths, manifest keys, memory IDs).
* It must never start threads or perform I/O.

The widget is responsible for:

* Rendering the title + metadata row in plain text (spec §11.3 — never
  interpolate untrusted titles into stylesheets or LLM prompts).
* Case-insensitive title-only search over the cached list (spec §8.4).
  Search runs on the Qt main thread against the last ``set_entries``
  payload only — it never re-queries the persistence layer.
* Visual state transitions: empty / search-empty / loading / error /
  list. Retry is visible only after an explicit ``set_error`` call
  with ``retry_visible=True``.
* Re-rendering on theme changes via the
  :func:`bind_theme`/ :func:`disconnect_theme` helper.

The panel's content is capped at 320 px wide so a long title cannot
overflow horizontally on narrow IDA layouts (the cap is enforced via
``setMaximumWidth`` on every title/meta label and verified by a
deterministic widget-property assertion — see
``tests/ui/test_history_panel.py``).

Reopening behaviour (cached rows survive, query persists across close
+ refresh) is **PanelCore's** concern — this widget only renders what
it was given. ``set_loading`` does NOT clear cached rows because the
spec says "Closing and reopening History preserves the last successful
rows and search query, but reopening always starts a background refresh
so newly saved turns can reorder the list."
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from .qt_compat import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)
from .styles import (
    get_history_close_btn_style,
    get_history_meta_style,
    get_history_panel_style,
    get_history_retry_btn_style,
    get_history_row_style,
    get_history_scope_style,
    get_history_search_style,
    get_history_status_style,
    get_history_title_style,
    maybe_host_stylesheet,
)
from .theme.applicator import bind_theme, disconnect_theme

if TYPE_CHECKING:
    from ..state.history_types import SessionHistoryEntry


# Maximum panel content width. The panel caps itself + every title/meta
# label at this width so a long title cannot overflow horizontally on
# narrow IDA layouts (the spec lists 320 px as the reference width).
HISTORY_PANEL_CONTENT_MAX_WIDTH = 320
# Panel-level padding (left + right) consumed by the root QVBoxLayout.
_HISTORY_PANEL_PADDING = 16
# Row-level horizontal inset (left + right padding inside each row).
_HISTORY_ROW_HORIZONTAL_INSET = 12
# Computed cap for the row's title and meta labels. The cap is the
# panel width minus the panel padding minus the row inset.
_HISTORY_LABEL_MAX_WIDTH = HISTORY_PANEL_CONTENT_MAX_WIDTH - _HISTORY_PANEL_PADDING - _HISTORY_ROW_HORIZONTAL_INSET
# Separator used in the meta line.
_HISTORY_META_SEPARATOR = "  ·  "

# Empty / search-empty / loading / error copy strings (spec §13). These
# are the exact strings the test suite asserts, and they are referenced
# only by the public methods so a typo here is caught at test time.
_EMPTY_COPY = "No saved chats for this IDB yet."
_SEARCH_EMPTY_COPY = "No chats match your search."
_LOADING_COPY = "Loading chats…"


# Stacked-state identifiers (used internally for state tracking — not
# part of the public surface).
_STATE_STATUS = "status"  # empty / search-empty / error
_STATE_LOADING = "loading"
_STATE_LIST = "list"


def _format_updated_at(updated_at: float) -> str:
    """Format the file mtime as a short, locale-independent timestamp."""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(updated_at))


def _format_message_count(message_count: int) -> str:
    """Format the message-count suffix."""
    if message_count == 1:
        return "1 message"
    return f"{message_count} messages"


def _format_provider_model(provider: str, model: str) -> str:
    """Format the provider/model footer for the meta line."""
    parts = [p for p in (provider, model) if p]
    return _HISTORY_META_SEPARATOR.join(parts)


class HistoryRowWidget(QFrame):
    """Single metadata row: title + meta line. Plain-text only.

    The title is forced to ``Qt.TextFormat.PlainText`` so the untrusted
    storage-derived string can never render as rich HTML (spec §11.3).
    The label is word-wrapped and capped at
    :data:`_HISTORY_LABEL_MAX_WIDTH` so the row never produces a
    horizontal scrollbar at the reference 320 px panel width.
    """

    session_open_requested = Signal(str)  # emits the row's session_id

    def __init__(
        self,
        entry: SessionHistoryEntry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("history_row")
        self.setStyleSheet(get_history_row_style())
        self._entry = entry

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        # Title: plain text only, word-wrap, capped width. Storage
        # boundary already sanitizes the title through
        # ``derive_history_title`` (spec §9.1), so it is safe to
        # display directly without further escaping.
        self._title = QLabel(entry.title)
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setWordWrap(True)
        self._title.setMaximumWidth(_HISTORY_LABEL_MAX_WIDTH)
        self._title.setStyleSheet(get_history_title_style())
        text_col.addWidget(self._title)

        # Meta line: timestamp · provider/model · message count. We
        # build the segments deterministically — empty fields are
        # dropped so a legacy row without provider info still renders
        # the timestamp.
        meta_bits = [
            _format_updated_at(entry.updated_at),
            _format_provider_model(entry.provider, entry.model),
            _format_message_count(entry.message_count),
        ]
        meta_text = _HISTORY_META_SEPARATOR.join(part for part in meta_bits if part)
        self._meta = QLabel(meta_text)
        self._meta.setTextFormat(Qt.TextFormat.PlainText)
        self._meta.setWordWrap(True)
        self._meta.setMaximumWidth(_HISTORY_LABEL_MAX_WIDTH)
        self._meta.setStyleSheet(get_history_meta_style())
        text_col.addWidget(self._meta)

        layout.addLayout(text_col, 1)

    @property
    def entry(self) -> SessionHistoryEntry:
        return self._entry

    def mouseReleaseEvent(self, event: object) -> None:
        """Forward a row click to ``session_open_requested``.

        Implemented as a class method (not via instance attribute
        assignment) so the dispatcher is part of the widget's stable
        API surface and survives ``PySide6``'s Shiboken dispatch path.
        A click anywhere in the row fires the open request; the
        forwarded ``session_id`` comes from the row's bound entry
        so the panel's ``session_open_requested(str)`` carries the
        right value.
        """
        self.session_open_requested.emit(self._entry.session_id)

    def shutdown(self) -> None:
        """Detach the theme subscription (idempotent)."""
        disconnect_theme(self)

    def _apply_styles(self, _tokens: object = None) -> None:
        """Re-apply per-row styles from the live tokens."""
        if getattr(self, "_title", None) is not None:
            self._title.setStyleSheet(get_history_title_style())
        if getattr(self, "_meta", None) is not None:
            self._meta.setStyleSheet(get_history_meta_style())
        self.setStyleSheet(get_history_row_style())


class HistoryPanel(QFrame):
    """Side panel listing past chat sessions for the current IDB.

    The panel is intentionally passive: it never imports the persistence
    layer, config, threading, executors, or I/O. PanelCore owns the
    worker, request queue, generation counter, and polling timer.

    Public surface (consumed by Tasks 8-10):

    Signals:
      * ``session_open_requested(session_id: str)`` — fired on row click.
      * ``close_requested()`` — fired on the header close button.
      * ``retry_requested()`` — fired on the Retry button.

    Methods:
      * ``set_entries(entries)`` — replace cached list + re-render.
      * ``set_loading()`` — show loading state, preserve cache.
      * ``set_error(message, retry_visible=True)`` — show error state.
      * ``clear()`` — reset cached entries AND the search query.
      * ``shutdown()`` — disconnect theme subscriptions (idempotent).
      * ``visible_session_ids()`` — ids of rows currently rendered.
    """

    session_open_requested = Signal(str)
    close_requested = Signal()
    retry_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("history_panel")
        # Cap the panel's own width so the splitter cannot grant it
        # more than 320 px even if the parent layout grows. The row
        # labels carry their own matching caps below.
        self.setMaximumWidth(HISTORY_PANEL_CONTENT_MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(get_history_panel_style())

        # Cached state.
        self._entries: tuple[SessionHistoryEntry, ...] = ()
        self._row_widgets: list[HistoryRowWidget] = []
        self._state: str = _STATE_STATUS

        # === Root layout ============================================
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === Header ==================================================
        self._header = QFrame()
        self._header.setObjectName("history_header")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(8, 8, 8, 4)
        header_layout.setSpacing(8)

        self._title = QLabel()
        self._title.setText("Chat History")
        self._title.setStyleSheet(get_history_title_style())
        header_layout.addWidget(self._title)

        self._scope_label = QLabel()
        self._scope_label.setText("Current IDB")
        self._scope_label.setStyleSheet(get_history_scope_style())
        header_layout.addWidget(self._scope_label)
        header_layout.addStretch(1)

        self._close_btn = QPushButton()
        self._close_btn.setText("Close")
        self._close_btn.setObjectName("history_close_btn")
        self._close_btn.setStyleSheet(get_history_close_btn_style())
        self._close_btn.clicked.connect(lambda: self.close_requested.emit())
        header_layout.addWidget(self._close_btn)
        main_layout.addWidget(self._header)

        # === Search ==================================================
        self._search = QLineEdit()
        self._search.setObjectName("history_search")
        self._search.setPlaceholderText("Search conversations…")
        self._search.setStyleSheet(get_history_search_style())
        self._search.textChanged.connect(self._on_search_changed)
        main_layout.addWidget(self._search)

        # === Stacked states ==========================================
        self._stack = QStackedWidget()
        self._stack.setObjectName("history_stack")

        # Status states (empty / search-empty / error / loading) share
        # one frame so the visual structure stays stable across states.
        self._status_frame = QFrame()
        self._status_frame.setObjectName("history_status")
        status_layout = QVBoxLayout(self._status_frame)
        status_layout.setContentsMargins(12, 24, 12, 12)
        status_layout.setSpacing(8)
        status_layout.addStretch(1)

        self._status_label = QLabel()
        # Plain-text only — the status message is derived from internal
        # state ("No saved chats…", "Loading chats…", the error string
        # from ``set_error``) so it never carries user-supplied HTML.
        # Forcing PlainText here matches the row-title guard (spec
        # §11.3) and ensures the label is never auto-promoted to rich
        # text by Qt's heuristic.
        self._status_label.setTextFormat(Qt.TextFormat.PlainText)
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(get_history_status_style())
        status_layout.addWidget(self._status_label)

        # Retry row — centered, hidden by default. Visible only after
        # ``set_error(message, retry_visible=True)``.
        retry_row = QHBoxLayout()
        retry_row.setContentsMargins(0, 0, 0, 0)
        retry_row.setSpacing(0)
        retry_row.addStretch(1)
        self._retry_btn = QPushButton()
        self._retry_btn.setText("Retry")
        self._retry_btn.setObjectName("history_retry_btn")
        self._retry_btn.setStyleSheet(get_history_retry_btn_style())
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(lambda: self.retry_requested.emit())
        retry_row.addWidget(self._retry_btn)
        retry_row.addStretch(1)
        status_layout.addLayout(retry_row)

        status_layout.addStretch(1)
        self._stack.addWidget(self._status_frame)  # index 0

        # List state — scroll area filled with rows.
        self._list_scroll = QScrollArea()
        self._list_scroll.setObjectName("history_list_scroll")
        self._list_scroll.setWidgetResizable(True)
        # Disable the horizontal scrollbar via the canonical Qt API so
        # narrow panels never widen past HISTORY_PANEL_CONTENT_MAX_WIDTH
        # even if a row's title overflows. The border / background QSS
        # stays separate so the host theme still paints the scroll area.
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._list_widget = QFrame()
        self._list_widget.setObjectName("history_list")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch(1)
        self._list_scroll.setWidget(self._list_widget)

        list_container = QFrame()
        list_container.setObjectName("history_list_container")
        list_container_layout = QVBoxLayout(list_container)
        list_container_layout.setContentsMargins(8, 4, 8, 4)
        list_container_layout.setSpacing(0)
        list_container_layout.addWidget(self._list_scroll)
        self._stack.addWidget(list_container)  # index 1

        main_layout.addWidget(self._stack, 1)

        # === Initial state ===========================================
        self._set_status_message(_EMPTY_COPY)
        self._stack.setCurrentWidget(self._status_frame)

        # Theme binding: re-apply styles on every ``themeChanged`` emit.
        # ``bind_theme`` runs the callback synchronously so the initial
        # paint reflects the active palette.
        bind_theme(self, self._apply_styles)

    # === Public API ====================================================

    def set_entries(self, entries: list[SessionHistoryEntry]) -> None:
        """Replace the cached entry list and re-render rows.

        ``PanelCore`` is responsible for sorting the entries newest-first
        and applying the current-IDB filter; this widget trusts what it
        was given. Any pending error state is cleared because a fresh
        delivery implies the previous failure has been resolved.
        """
        self._entries = tuple(entries)
        self._retry_btn.setVisible(False)
        self._apply_search()

    def set_loading(self) -> None:
        """Show the loading state. Cached rows + query are preserved.

        Reopening the panel starts a background refresh; the spec says
        "Closing and reopening History preserves the last successful
        rows and search query, but reopening always starts a background
        refresh so newly saved turns can reorder the list." We do not
        drop the cached rows here — ``PanelCore`` swaps them in via
        ``set_entries`` once the new list arrives.
        """
        self._state = _STATE_LOADING
        self._set_status_message(_LOADING_COPY)
        self._retry_btn.setVisible(False)
        self._stack.setCurrentWidget(self._status_frame)

    def set_error(self, message: str, retry_visible: bool = True) -> None:
        """Show the error state with an optional Retry button.

        The Retry button is rendered only when ``retry_visible=True``;
        passing ``False`` shows the message alone (e.g. while a flush
        is still pending).
        """
        self._state = _STATE_STATUS
        self._set_status_message(message)
        self._retry_btn.setVisible(bool(retry_visible))
        # Hide existing rows so the user does not see stale data behind
        # the error message. They are re-shown when ``set_entries``
        # delivers a new list.
        for row in self._row_widgets:
            row.setVisible(False)
        self._stack.setCurrentWidget(self._status_frame)

    def clear(self) -> None:
        """Reset cached entries AND the search query.

        Used by ``PanelCore`` for explicit resets (IDB switch, initial
        empty state). Unlike ``set_loading``, this empties the rows so
        the next ``set_entries`` paints a clean slate.
        """
        self._entries = ()
        # Reset the search box so a fresh reopen starts empty. We set
        # the text directly; ``textChanged`` fires ``_apply_search``
        # which short-circuits on the empty entries list.
        self._search.setText("")
        self._render_rows([])
        self._state = _STATE_STATUS
        self._set_status_message(_EMPTY_COPY)
        self._retry_btn.setVisible(False)
        self._stack.setCurrentWidget(self._status_frame)

    def shutdown(self) -> None:
        """Detach theme subscriptions on this panel and every row.

        Idempotent — safe to call from ``PanelCore.shutdown`` and from
        ``deleteLater`` paths.
        """
        disconnect_theme(self)
        for row in list(self._row_widgets):
            row.shutdown()

    def visible_session_ids(self) -> list[str]:
        """Return the IDs currently rendered as rows, in display order."""
        return [row.entry.session_id for row in self._row_widgets if row.isVisible()]

    # === Internals ====================================================

    def _on_search_changed(self, _text: str) -> None:
        """Re-render rows from the cached list with the new query."""
        # Loading trumps everything; do not touch rows until the
        # background refresh returns.
        if self._state == _STATE_LOADING:
            return
        self._apply_search()

    def _apply_search(self) -> None:
        """Render rows from ``self._entries`` + current search query."""
        query = self._search.text().strip().casefold()
        visible = [entry for entry in self._entries if query in entry.title.casefold()]
        if not self._entries:
            self._state = _STATE_STATUS
            self._set_status_message(_EMPTY_COPY)
            self._retry_btn.setVisible(False)
            self._stack.setCurrentWidget(self._status_frame)
            self._render_rows([])
            return
        if not visible:
            self._state = _STATE_STATUS
            self._set_status_message(_SEARCH_EMPTY_COPY)
            self._retry_btn.setVisible(False)
            self._stack.setCurrentWidget(self._status_frame)
            self._render_rows([])
            return
        self._state = _STATE_LIST
        # Index 1 is the list container — switching here is cheaper
        # than calling ``setCurrentWidget`` with a tracked reference.
        self._stack.setCurrentIndex(1)
        self._render_rows(visible)

    def _set_status_message(self, text: str) -> None:
        self._status_label.setText(text)

    def _render_rows(self, entries: list[SessionHistoryEntry]) -> None:
        """Replace current rows with the given entries (in given order)."""
        # Drop existing rows — including hidden ones from a previous
        # error state. ``shutdown`` is idempotent so the row's theme
        # subscription is released before we lose the reference.
        for row in list(self._row_widgets):
            self._list_layout.removeWidget(row)
            row.shutdown()
            row.deleteLater()
        self._row_widgets = []

        # Insert new rows before the trailing stretch.
        for entry in entries:
            row = HistoryRowWidget(entry, self._list_widget)
            row.session_open_requested.connect(self.session_open_requested.emit)
            row._apply_styles()
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._row_widgets.append(row)

    def _apply_styles(self, _tokens: object = None) -> None:
        """Refresh chrome + row styles from the live tokens.

        In host-theme (IDA-native) mode the panel-level stylesheet is
        cleared via ``maybe_host_stylesheet`` so the host palette takes
        over without an explicit per-widget override.
        """
        if getattr(self, "_title", None) is not None:
            self._title.setStyleSheet(maybe_host_stylesheet(get_history_title_style()))
        if getattr(self, "_scope_label", None) is not None:
            self._scope_label.setStyleSheet(maybe_host_stylesheet(get_history_scope_style()))
        if getattr(self, "_status_label", None) is not None:
            self._status_label.setStyleSheet(maybe_host_stylesheet(get_history_status_style()))
        if getattr(self, "_retry_btn", None) is not None:
            self._retry_btn.setStyleSheet(maybe_host_stylesheet(get_history_retry_btn_style()))
        if getattr(self, "_close_btn", None) is not None:
            self._close_btn.setStyleSheet(maybe_host_stylesheet(get_history_close_btn_style()))
        if getattr(self, "_search", None) is not None:
            self._search.setStyleSheet(maybe_host_stylesheet(get_history_search_style()))
        self.setStyleSheet(maybe_host_stylesheet(get_history_panel_style()))
        for row in self._row_widgets:
            row._apply_styles()


__all__ = [
    "HISTORY_PANEL_CONTENT_MAX_WIDTH",
    "HistoryPanel",
    "HistoryRowWidget",
]
