"""Inline delegation approval widget for Orchestra sub-agent delegation.

The modal ``QDialog`` variant that used to live here was dead code —
the chat renders delegation approvals inline (embedded in the message
stream) via :class:`DelegationApprovalWidget`, never as a modal dialog.
Only the inline widget is wired up by ``chat_view``.
"""

from __future__ import annotations

from typing import Any

from ..ui.qt_compat import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    Signal,
)
from .styles import (
    get_delegation_approval_widget_style,
    get_delegation_header_style,
    get_delegation_info_style,
    get_delegation_preview_style,
)


class DelegationApprovalWidget(QFrame):
    """Inline widget version of delegation approval for embedding in chat view.

    Use this when the approval should be shown inline rather than as a modal dialog.
    """

    approved = Signal(str, str)  # (task_name, decision)
    denied = Signal(str, str)  # (task_name, decision)

    def __init__(
        self,
        task_name: str,
        instruction: str,
        context: str,
        tools: list[str],
        model: str,
        max_steps: int = 20,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("delegation_approval")
        self.setStyleSheet(get_delegation_approval_widget_style())
        self._task_name = task_name
        self._instruction = instruction
        self._context = context
        self._tools = tools
        self._model = model
        self._max_steps = max_steps

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        header = QLabel(f"Sub-Agent Delegation: {task_name}")
        header.setStyleSheet(get_delegation_header_style())
        layout.addWidget(header)

        info = QLabel(f"Model: {model} | Tools: {len(tools)} | Max Steps: {max_steps}")
        info.setStyleSheet(get_delegation_info_style())
        layout.addWidget(info)

        instruction_preview = QLabel(f"Task: {instruction[:200]}{'...' if len(instruction) > 200 else ''}")
        instruction_preview.setStyleSheet(get_delegation_preview_style())
        instruction_preview.setWordWrap(True)
        layout.addWidget(instruction_preview)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        approve_btn = QPushButton("Approve")
        approve_btn.setObjectName("approve_btn")
        approve_btn.clicked.connect(self._on_approve)
        deny_btn = QPushButton("Deny")
        deny_btn.setObjectName("deny_btn")
        deny_btn.clicked.connect(self._on_deny)
        btn_layout.addWidget(approve_btn)
        btn_layout.addWidget(deny_btn)
        layout.addLayout(btn_layout)

    def _on_approve(self) -> None:
        self.approved.emit(self._task_name, "approve")

    def _on_deny(self) -> None:
        self.denied.emit(self._task_name, "deny")

    def get_spec(self) -> dict[str, Any]:
        return {
            "task": self._task_name,
            "instruction": self._instruction,
            "context": self._context,
            "tools": self._tools,
            "model": self._model,
            "max_steps": self._max_steps,
        }
