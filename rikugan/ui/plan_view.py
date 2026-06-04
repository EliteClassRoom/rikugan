"""Plan mode view: step-by-step plan display with approve/reject."""

from __future__ import annotations

from .qt_compat import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from .styles import maybe_host_stylesheet

# Status → token key for the per-step indicator colour.
_PLAN_STATUS_TOKEN: dict[str, str] = {
    "pending": "light",
    "active": "highlight",
    "done": "success",
    "error": "error",
    "skipped": "light",
}


def _status_color(status: str) -> str:
    from .theme.manager import ThemeManager
    t = ThemeManager.instance().tokens()
    key = _PLAN_STATUS_TOKEN.get(status, "text")
    return getattr(t, key)


def _text_color() -> str:
    from .theme.manager import ThemeManager
    return ThemeManager.instance().tokens().text


class PlanStepWidget(QFrame):
    """Single plan step with status indicator."""

    def __init__(self, index: int, text: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("plan_step")
        self._index = index
        self._status = "pending"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._status_label = QLabel("○")
        self._status_label.setFixedWidth(20)
        self._status_label.setStyleSheet(maybe_host_stylesheet(f"color: {_status_color('pending')}; font-size: 14px;"))
        layout.addWidget(self._status_label)

        self._step_label = QLabel(f"{index + 1}. {text}")
        self._step_label.setWordWrap(True)
        self._step_label.setStyleSheet(maybe_host_stylesheet(f"color: {_text_color()}; font-size: 12px;"))
        layout.addWidget(self._step_label, 1)

    def set_status(self, status: str) -> None:
        self._status = status
        color = _status_color(status)
        if status == "active":
            self.setObjectName("plan_step_active")
            self._status_label.setText("▶")
        elif status == "done":
            self.setObjectName("plan_step_done")
            self._status_label.setText("✓")
        elif status == "error":
            self._status_label.setText("✗")
        elif status == "skipped":
            self.setObjectName("plan_step")
            self._status_label.setText("−")
        else:
            self.setObjectName("plan_step")
            self._status_label.setText("○")
        self._status_label.setStyleSheet(maybe_host_stylesheet(f"color: {color}; font-size: 14px;"))
        self.style().unpolish(self)
        self.style().polish(self)


class PlanView(QFrame):
    """Plan mode view with approve/reject controls.

    Uses plain Python callbacks instead of Signal() to avoid corrupting
    Shiboken's global signal registry on Python 3.14.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("plan_view")
        self._steps: list[PlanStepWidget] = []
        self._on_approved = None
        self._on_rejected = None
        from .theme.manager import ThemeManager
        ThemeManager.instance().themeChanged.connect(self._on_theme_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Header
        self._header = QLabel("Plan")
        layout.addWidget(self._header)

        # Steps container
        self._steps_container = QVBoxLayout()
        layout.addLayout(self._steps_container)

        # Approve/reject buttons
        btn_layout = QHBoxLayout()

        self._approve_btn = QPushButton("Approve & Execute")
        self._approve_btn.clicked.connect(self._fire_approved)
        btn_layout.addWidget(self._approve_btn)

        self._reject_btn = QPushButton("Reject")
        self._reject_btn.clicked.connect(self._fire_rejected)
        btn_layout.addWidget(self._reject_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()

        self._apply_styles()

    # ----- Theme wiring -------------------------------------------------
    def _on_theme_changed(self, _tokens) -> None:
        self._apply_styles()
        # Re-render every step so its indicator colour follows the new theme.
        for step in self._steps:
            step.set_status(step._status)

    def _apply_styles(self) -> None:
        from .theme.manager import ThemeManager, _blend_hex

        t = ThemeManager.instance().tokens()
        self._header.setStyleSheet(
            maybe_host_stylesheet(f"color: {t.highlight}; font-weight: bold; font-size: 13px;")
        )
        # Approve: green-tinted from success token; brighten for hover.
        approve_hover = _blend_hex(t.success, t.highlight_text, 0.2)
        self._approve_btn.setStyleSheet(
            maybe_host_stylesheet(
                f"QPushButton {{ background: {t.success}; color: {t.highlight_text}; border: none; "
                f"border-radius: 6px; padding: 6px 16px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: {approve_hover}; }}"
            )
        )
        # Reject: red-tinted from error token; brighten for hover.
        reject_hover = _blend_hex(t.error, t.highlight_text, 0.2)
        self._reject_btn.setStyleSheet(
            maybe_host_stylesheet(
                f"QPushButton {{ background: {t.error}; color: {t.highlight_text}; border: none; "
                f"border-radius: 6px; padding: 6px 16px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: {reject_hover}; }}"
            )
        )

    def set_plan(self, steps: list[str]) -> None:
        """Set plan steps and display them."""
        self.clear()
        for i, text in enumerate(steps):
            step_widget = PlanStepWidget(i, text)
            self._steps.append(step_widget)
            self._steps_container.addWidget(step_widget)

    def set_step_status(self, index: int, status: str) -> None:
        if 0 <= index < len(self._steps):
            self._steps[index].set_status(status)

    def set_buttons_visible(self, visible: bool) -> None:
        self._approve_btn.setVisible(visible)
        self._reject_btn.setVisible(visible)

    def set_approved_callback(self, callback) -> None:
        self._on_approved = callback

    def set_rejected_callback(self, callback) -> None:
        self._on_rejected = callback

    def _fire_approved(self) -> None:
        if self._on_approved is not None:
            self._on_approved()

    def _fire_rejected(self) -> None:
        if self._on_rejected is not None:
            self._on_rejected()

    def clear(self) -> None:
        for step in self._steps:
            step.deleteLater()
        self._steps.clear()
