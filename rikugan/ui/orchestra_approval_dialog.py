"""Delegation approval dialog for Orchestra sub-agent delegation requests."""

from __future__ import annotations

from typing import Any

from ..ui.qt_compat import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    Signal,
)
from .styles import (
    get_delegation_approval_widget_style,
    get_delegation_dialog_style,
    get_delegation_header_style,
    get_delegation_info_style,
    get_delegation_preview_style,
)


class DelegationApprovalDialog(QDialog):
    """Dialog shown when a delegate_task request requires user approval.

    Displays the delegation details (task, instruction, context, tools, model)
    and provides Approve/Deny buttons.
    """

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
        self.setStyleSheet(get_delegation_dialog_style())
        self.setWindowTitle("Sub-Agent Delegation Request")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._result: str = "deny"

        layout = QVBoxLayout(self)

        header = QLabel(f"Delegation Request: {task_name}")
        header.setObjectName("header")
        layout.addWidget(header)

        self._build_section(layout, "Instruction", instruction)

        if context:
            self._build_section(layout, "Context", context, scrollable=True)

        tools_text = ", ".join(tools) if tools else "all available tools"
        self._build_section(layout, "Tools", tools_text)

        model_text = QLabel(f"Model: {model}")
        layout.addWidget(model_text)

        max_steps_text = QLabel(f"Max Steps: {max_steps}")
        layout.addWidget(max_steps_text)

        button_box = QDialogButtonBox()
        button_box.setStyleSheet("QDialogButtonBox { spacing: 8px; }")

        approve_btn = button_box.addButton("Approve", QDialogButtonBox.AcceptRole)
        approve_btn.setObjectName("approve_btn")
        deny_btn = button_box.addButton("Deny", QDialogButtonBox.RejectRole)
        deny_btn.setObjectName("deny_btn")

        approve_btn.clicked.connect(self._on_approve)
        deny_btn.clicked.connect(self._on_deny)

        layout.addSpacing(10)
        layout.addWidget(button_box)

    def _build_section(self, parent: QVBoxLayout, title: str, content: str, scrollable: bool = False) -> None:
        label = QLabel(title)
        label.setObjectName("section")
        parent.addWidget(label)

        if scrollable:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setMinimumHeight(80)
            scroll.setMaximumHeight(150)

            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(content)
            scroll.setWidget(text)
            parent.addWidget(scroll)
        else:
            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(content)
            text.setMaximumHeight(80 if content.count("\n") <= 3 else 120)
            parent.addWidget(text)

    def _on_approve(self) -> None:
        self._result = "approve"
        self.accept()

    def _on_deny(self) -> None:
        self._result = "deny"
        self.reject()

    def result(self) -> str:
        return self._result


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
        from ..ui.qt_compat import QPushButton

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
