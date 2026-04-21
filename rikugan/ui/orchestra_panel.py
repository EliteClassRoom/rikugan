"""Orchestra panel: displays delegation tree and active sub-agents."""

from __future__ import annotations

from typing import Any

from ..ui.qt_compat import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from .styles import get_orchestra_panel_style, get_orchestra_stats_style

_STATUS_ICONS = {
    "pending": "⏳",
    "running": "🔄",
    "completed": "✅",
    "failed": "❌",
    "cancelled": "⏹",
}


class DelegationTreeWidget(QTreeWidget):
    """Tree widget showing the delegation hierarchy of sub-agents."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setHeaderLabels(["Status", "Task", "Model", "Tools", "Progress"])
        self.header().setSectionResizeMode(QHeaderView.Interactive)
        self.setColumnWidth(0, 60)
        self.setColumnWidth(1, 200)
        self.setColumnWidth(2, 100)
        self.setColumnWidth(3, 100)
        self.setAlternatingRowColors(False)
        self.setRootIsDecorated(True)

    def add_delegation(
        self,
        agent_id: str,
        task_name: str,
        model: str,
        tools: list[str],
        status: str = "pending",
        parent_agent_id: str | None = None,
    ) -> None:
        """Add a delegation row to the tree."""
        status_icon = _STATUS_ICONS.get(status.lower(), "❓")
        tools_preview = ", ".join(tools[:3]) if len(tools) <= 3 else ", ".join(tools[:3]) + "..."

        item_data = [status_icon, task_name, model, tools_preview, "0 turns"]
        item = QTreeWidgetItem(item_data)
        item.setData(0, 0, {"agent_id": agent_id, "status": status})
        item.setTextAlignment(0, 1)
        item.setTextAlignment(2, 1)
        item.setTextAlignment(3, 1)
        item.setTextAlignment(4, 1)

        self.addTopLevelItem(item)

    def update_delegation(self, agent_id: str, status: str, progress: str = "") -> None:
        """Update a delegation's status and progress."""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, 0).get("agent_id") == agent_id:
                status_icon = _STATUS_ICONS.get(status.lower(), "❓")
                item.setText(0, status_icon)
                item.setData(0, 0, {"agent_id": agent_id, "status": status})
                if progress:
                    item.setText(4, progress)
                break


class OrchestraPanel(QWidget):
    """Panel showing active Orchestra orchestrator and delegation tree.

    Can be embedded in ToolsPanel as a tab.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("orchestra_panel")
        self.setStyleSheet(get_orchestra_panel_style())
        self._delegations: dict[str, dict[str, Any]] = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        header = QLabel("Orchestra Orchestrator")
        header.setObjectName("header")
        main_layout.addWidget(header)

        self._stats_label = QLabel("0 active / 0 completed")
        self._stats_label.setStyleSheet(get_orchestra_stats_style())
        main_layout.addWidget(self._stats_label)

        self._tree = DelegationTreeWidget()
        main_layout.addWidget(self._tree, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self._kill_btn = QPushButton("Kill Selected")
        self._kill_btn.setEnabled(False)
        self._kill_btn.clicked.connect(self._on_kill)
        btn_layout.addWidget(self._kill_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._on_refresh)
        btn_layout.addWidget(self._refresh_btn)

        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)

    def add_delegation(
        self,
        agent_id: str,
        task_name: str,
        instruction: str,
        model: str,
        tools: list[str],
        context: str = "",
        max_steps: int = 20,
    ) -> None:
        """Register a new delegation."""
        self._delegations[agent_id] = {
            "task_name": task_name,
            "instruction": instruction,
            "model": model,
            "tools": tools,
            "context": context,
            "max_steps": max_steps,
            "status": "pending",
            "turn_count": 0,
        }
        self._tree.add_delegation(agent_id, task_name, model, tools, "pending")
        self._update_stats()

    def update_delegation(self, agent_id: str, status: str, turn_count: int = 0) -> None:
        """Update a delegation's status."""
        if agent_id in self._delegations:
            self._delegations[agent_id]["status"] = status
            self._delegations[agent_id]["turn_count"] = turn_count

        progress = f"{turn_count} turns"
        self._tree.update_delegation(agent_id, status, progress)
        self._update_stats()

    def complete_delegation(self, agent_id: str, summary: str = "") -> None:
        """Mark a delegation as completed."""
        if agent_id in self._delegations:
            self._delegations[agent_id]["status"] = "completed"
            self._delegations[agent_id]["summary"] = summary
        self._tree.update_delegation(agent_id, "completed", "")
        self._update_stats()

    def fail_delegation(self, agent_id: str, error: str = "") -> None:
        """Mark a delegation as failed."""
        if agent_id in self._delegations:
            self._delegations[agent_id]["status"] = "failed"
            self._delegations[agent_id]["error"] = error
        self._tree.update_delegation(agent_id, "failed", "")
        self._update_stats()

    def _update_stats(self) -> None:
        active = sum(1 for d in self._delegations.values() if d["status"] == "running")
        completed = sum(1 for d in self._delegations.values() if d["status"] == "completed")
        self._stats_label.setText(f"{active} active / {completed} completed")

    def _on_kill(self) -> None:
        current = self._tree.currentItem()
        if current:
            agent_id = current.data(0, 0).get("agent_id")
            if agent_id and self._on_kill_callback:
                self._on_kill_callback(agent_id)

    def _on_refresh(self) -> None:
        """Refresh the delegation tree from the subagent manager."""
        # Delegate to the kill callback if set — it handles tree refresh
        if hasattr(self, "_on_kill_callback") and self._on_kill_callback:
            self._on_kill_callback("refresh")

    def set_kill_callback(self, callback) -> None:
        self._on_kill_callback = callback

    def get_delegation(self, agent_id: str) -> dict[str, Any] | None:
        return self._delegations.get(agent_id)
