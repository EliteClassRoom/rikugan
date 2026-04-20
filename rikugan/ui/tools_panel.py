"""Tools panel: container for bulk renamer and agent tree.

Can be shown as an independent window (QDialog) or embedded in a layout.
"""

from __future__ import annotations

from .qt_compat import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from .styles import (
    get_placeholder_style,
    get_tools_panel_header_style,
    get_tools_panel_style,
)


class ToolsPanel(QWidget):
    """Standalone tools window containing tabs: Renamer, Agents."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("tools_panel")
        self.setWindowTitle("Rikugan Tools")
        self.setStyleSheet(get_tools_panel_style())
        # No minimum size — this widget is embedded in IDA dockable forms
        # and Binary Ninja sidebars, which can be any size.

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar with title (hidden when docked in IDA)
        self._header = QFrame()
        self._header.setObjectName("tools_panel_header")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("Tools")
        title.setStyleSheet(get_tools_panel_header_style())
        header_layout.addWidget(title)
        header_layout.addStretch()

        main_layout.addWidget(self._header)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setObjectName("tools_tabs")

        # Placeholder tabs
        self._renamer_placeholder = QLabel("Not loaded")
        self._renamer_placeholder.setStyleSheet(get_placeholder_style())
        self._renamer_placeholder.setWordWrap(True)
        self._tabs.addTab(self._renamer_placeholder, "Renamer")

        self._agents_placeholder = QLabel("Not loaded")
        self._agents_placeholder.setStyleSheet(get_placeholder_style())
        self._agents_placeholder.setWordWrap(True)
        self._tabs.addTab(self._agents_placeholder, "Agents")

        self._orchestra_placeholder = QLabel("Not loaded")
        self._orchestra_placeholder.setStyleSheet(get_placeholder_style())
        self._orchestra_placeholder.setWordWrap(True)
        self._tabs.addTab(self._orchestra_placeholder, "Orchestra")

        main_layout.addWidget(self._tabs)

    def _replace_tab(self, index: int, widget: QWidget, label: str) -> None:
        """Replace the widget at the given tab index."""
        old = self._tabs.widget(index)
        self._tabs.removeTab(index)
        self._tabs.insertTab(index, widget, label)
        if old is not None:
            old.deleteLater()

    def set_renamer_widget(self, widget: QWidget) -> None:
        """Replace the Renamer tab content."""
        self._replace_tab(0, widget, "Renamer")

    def set_agents_widget(self, widget: QWidget) -> None:
        """Replace the Agents tab content."""
        self._replace_tab(1, widget, "Agents")

    def set_orchestra_widget(self, widget: QWidget) -> None:
        """Replace the Orchestra tab content."""
        self._replace_tab(2, widget, "Orchestra")

    def hide_header(self) -> None:
        """Hide the title bar (used when embedded in a dockable form)."""
        self._header.setVisible(False)
