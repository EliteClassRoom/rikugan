"""Multi-line input area with Enter/Shift+Enter handling and /skill autocomplete."""

from __future__ import annotations

from .qt_compat import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    Qt,
    QVBoxLayout,
    QWidget,
)


class _SkillPopup(QFrame):
    """Lightweight autocomplete popup for /skill slugs.

    Uses QLabel items inside a QFrame — avoids QListWidget Shiboken surface.
    NO Signal definitions here — this class is defined during the Shiboken
    bypass window and adding Signal descriptors corrupts Shiboken's internal
    signal registry on Python 3.14 + Shiboken 6.8.2, causing SIGSEGV in
    checkQtSignal() on any later signal operation (e.g. QTimer.singleShot).
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("skill_popup")
        self.setWindowFlags(Qt.WindowType.ToolTip)
        self.setStyleSheet(
            "QFrame#skill_popup { border: 1px solid; border-radius: 4px; padding: 2px; }"
            "QLabel { padding: 3px 8px; }"
            "QLabel#skill_popup_label[selected=\"true\"] {"
            "    background-color: palette(highlight);"
            "    color: palette(highlightedText);"
            "}"
            "QLabel#skill_popup_label[selected=\"false\"] {"
            "    background-color: transparent;"
            "}"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(0)
        self._labels: list[QLabel] = []
        self._slugs: list[str] = []
        self._selected_idx = 0

    def set_items(self, slugs: list[str]) -> None:
        """Replace popup contents with filtered slugs."""
        # Clear old labels
        for lbl in self._labels:
            self._layout.removeWidget(lbl)
            lbl.setParent(None)
        self._labels.clear()
        self._slugs = list(slugs)
        self._selected_idx = 0

        for slug in slugs:
            lbl = QLabel(f"/{slug}")
            lbl.setObjectName("skill_popup_label")
            self._labels.append(lbl)
            self._layout.addWidget(lbl)

        self._update_highlight()
        self.adjustSize()

    def _update_highlight(self) -> None:
        for i, lbl in enumerate(self._labels):
            is_selected = (i == self._selected_idx)
            was_selected = lbl.property("selected") == "true"
            if was_selected != is_selected:
                lbl.setProperty("selected", "true" if is_selected else "false")
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)

    def move_selection(self, delta: int) -> None:
        if not self._slugs:
            return
        self._selected_idx = (self._selected_idx + delta) % len(self._slugs)
        self._update_highlight()

    def current_slug(self) -> str | None:
        if 0 <= self._selected_idx < len(self._slugs):
            return self._slugs[self._selected_idx]
        return None

    def is_empty(self) -> bool:
        return len(self._slugs) == 0


class InputArea(QPlainTextEdit):
    """Chat input area with keyboard shortcuts.

    - Enter: submit message
    - Shift+Enter: newline
    - Escape: cancel running agent
    - /: skill autocomplete popup

    Uses plain Python callbacks instead of PySide6 Signals to avoid
    Shiboken C++ dispatch crashes (UAF in checkQtSignal on Python 3.14).
    """

    # Do NOT define Signal() here — Shiboken signal dispatch causes
    # random SIGSEGV during emit() on Python 3.14 + PySide6 6.8.2.

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("input_area")
        self.setPlaceholderText("Ask about this binary... (/ for skills, /modify to patch)")
        self.setMaximumHeight(100)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._enabled = True
        self._skill_slugs: list[str] = []
        self._popup: _SkillPopup | None = None
        self._submit_callback = None  # Callable[[str], None]
        self._cancel_callback = None  # Callable[[], None]

    def set_submit_callback(self, callback) -> None:
        """Set the callback for submit (Enter key). Callback signature: (str) -> None."""
        self._submit_callback = callback

    def set_cancel_callback(self, callback) -> None:
        """Set the callback for cancel (Escape key). Callback signature: () -> None."""
        self._cancel_callback = callback

    def set_skill_slugs(self, slugs: list[str]) -> None:
        """Set the list of available skill slugs for autocomplete.

        Automatically includes /plan, /modify, /explore, and /research as built-in commands.
        """
        combined = set(slugs)
        combined.update(("plan", "modify", "explore", "research"))
        self._skill_slugs = sorted(combined)

    def keyPressEvent(self, event) -> None:
        # Handle popup navigation when popup is visible
        if self._popup and self._popup.isVisible():
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                slug = self._popup.current_slug()
                if slug:
                    self._accept_completion(slug)
                return
            elif event.key() == Qt.Key.Key_Escape:
                self._dismiss_popup()
                return
            elif event.key() == Qt.Key.Key_Down:
                self._popup.move_selection(1)
                return
            elif event.key() == Qt.Key.Key_Up:
                self._popup.move_selection(-1)
                return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                text = self.toPlainText().strip()
                if text and self._enabled:
                    # Plain Python callback — no Shiboken signal dispatch
                    if self._submit_callback:
                        self._submit_callback(text)
                    self.clear()
        elif event.key() == Qt.Key.Key_Escape:
            if self._cancel_callback:
                self._cancel_callback()
        else:
            # Let the base class process the key first (inserts character),
            # then check if we need to show/update/dismiss the autocomplete.
            super().keyPressEvent(event)
            self._check_autocomplete()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.setReadOnly(not enabled)
        if enabled:
            self.setPlaceholderText("Ask about this binary... (/ for skills, /modify to patch)")
        else:
            self.setPlaceholderText("Rikugan is thinking...")

    # ------------------------------------------------------------------
    # Autocomplete
    # ------------------------------------------------------------------

    def _check_autocomplete(self) -> None:
        """Check current text and show/hide the skill autocomplete popup."""
        text = self.toPlainText()
        if not text.startswith("/") or not self._skill_slugs:
            self._dismiss_popup()
            return

        # Extract partial slug (everything after / up to first space)
        parts = text[1:].split(None, 1)
        # If there's already a space, the slug is complete — dismiss
        if len(parts) > 1:
            self._dismiss_popup()
            return

        partial = parts[0] if parts else ""
        matches = [s for s in self._skill_slugs if s.startswith(partial)]

        if not matches:
            self._dismiss_popup()
            return

        self._show_popup(matches)

    def _show_popup(self, slugs: list[str]) -> None:
        if self._popup is None:
            self._popup = _SkillPopup()
        self._popup.set_items(slugs)

        # Position above the input area
        pos = self.mapToGlobal(self.rect().topLeft())
        popup_height = self._popup.sizeHint().height()
        self._popup.move(pos.x(), pos.y() - popup_height - 4)
        self._popup.show()

    def _dismiss_popup(self) -> None:
        if self._popup and self._popup.isVisible():
            self._popup.hide()

    def _accept_completion(self, slug: str) -> None:
        """Replace current text with /slug and a trailing space."""
        self._dismiss_popup()
        self.setPlainText(f"/{slug} ")
        # Move cursor to end
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)
