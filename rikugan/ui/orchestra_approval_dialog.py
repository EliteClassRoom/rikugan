"""Delegation approval dialog for Orchestra sub-agent delegation requests."""

from __future__ import annotations

from typing import Any

from ..ui.qt_compat import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_DELEGATION_DIALOG_STYLE = """
    QDialog {
        background: #1e1e1e;
        color: #d4d4d4;
    }
    QLabel {
        color: #d4d4d4;
    }
    QLabel.header {
        font-size: 14px;
        font-weight: bold;
        color: #4ec9b0;
    }
    QLabel.section {
        font-size: 11px;
        font-weight: bold;
        color: #808080;
        margin-top: 8px;
    }
    QTextEdit, QScrollArea {
        background: #1e1e2e;
        color: #d4d4d4;
        border: 1px solid #3c3c3c;
        border-radius: 4px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 11px;
    }
    QScrollArea {
        border: none;
    }
    QTextEdit:read-only {
        background: #252536;
    }
    QDialogButtonBox {
        button-layout: 0;
    }
    QPushButton {
        background: #2d2d2d;
        color: #d4d4d4;
        border: 1px solid #3c3c3c;
        border-radius: 4px;
        padding: 6px 16px;
        font-size: 12px;
    }
    QPushButton:hover {
        background: #3c3c3c;
    }
    QPushButton#approve_btn {
        background: #2ea043;
        color: white;
        border-color: #2ea043;
    }
    QPushButton#approve_btn:hover {
        background: #3fb950;
    }
    QPushButton#deny_btn {
        background: #c42b1c;
        color: white;
        border-color: #c42b1c;
    }
    QPushButton#deny_btn:hover {
        background: #e83a2a;
    }
"""


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
        self.setStyleSheet(_DELEGATION_DIALOG_STYLE)
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

    approved = None
    denied = None

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
        self.setStyleSheet(
            "QFrame#delegation_approval { border: 1px solid #4ec9b0; border-radius: 6px; background: #1e2e2e; }"
        )
        self._task_name = task_name
        self._instruction = instruction
        self._context = context
        self._tools = tools
        self._model = model
        self._max_steps = max_steps

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        header = QLabel(f"Sub-Agent Delegation: {task_name}")
        header.setStyleSheet("color: #4ec9b0; font-weight: bold; font-size: 11px;")
        layout.addWidget(header)

        info = QLabel(f"Model: {model} | Tools: {len(tools)} | Max Steps: {max_steps}")
        info.setStyleSheet("color: #808080; font-size: 10px;")
        layout.addWidget(info)

        instruction_preview = QLabel(f"Task: {instruction[:200]}{'...' if len(instruction) > 200 else ''}")
        instruction_preview.setStyleSheet("color: #d4d4d4; font-size: 10px;")
        instruction_preview.setWordWrap(True)
        layout.addWidget(instruction_preview)

    def get_spec(self) -> dict[str, Any]:
        return {
            "task": self._task_name,
            "instruction": self._instruction,
            "context": self._context,
            "tools": self._tools,
            "model": self._model,
            "max_steps": self._max_steps,
        }
