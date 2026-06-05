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
from .styles import maybe_host_stylesheet


def _muted():
    from .theme.manager import ThemeManager, _blend_hex
    t = ThemeManager.instance().tokens()
    return _blend_hex(t.text, t.mid, 0.5)


def _tab_label():
    """High-contrast unselected tab label color (~4.5:1 against ``alt_base``).

    A 50/50 blend of ``text`` and ``mid`` (the global ``_muted``) yields
    ~3.5:1 in light mode and falls under WCAG AA. We shift the blend
    toward ``text`` (0.35) so unselected tabs stay readable in both
    light and dark modes.
    """
    from .theme.manager import ThemeManager, _blend_hex
    t = ThemeManager.instance().tokens()
    return _blend_hex(t.text, t.mid, 0.35)


def _hover_bg():
    from .theme.manager import ThemeManager, _blend_hex
    t = ThemeManager.instance().tokens()
    return _blend_hex(t.alt_base, t.mid, 0.5)


def _header_style() -> str:
    from .theme.manager import ThemeManager
    t = ThemeManager.instance().tokens()
    return f"color: {t.text}; font-weight: bold; font-size: 12px;"


def _panel_style() -> str:
    from .theme.manager import ThemeManager
    t = ThemeManager.instance().tokens()
    return (
        f"""
    QWidget#tools_panel {{
        background: {t.base};
    }}
    QTabWidget::pane {{
        border: none;
        background: {t.base};
    }}
    QTabBar::tab {{
        background: {t.alt_base};
        color: {_tab_label()};
        border: 1px solid {t.mid};
        border-bottom: none;
        padding: 5px 14px;
        font-size: 11px;
        min-width: 60px;
    }}
    QTabBar::tab:selected {{
        background: {t.base};
        color: {t.text};
        border-bottom: 2px solid {t.success};
    }}
    QTabBar::tab:hover:!selected {{
        background: {_hover_bg()};
        color: {t.text};
    }}
"""
    )


def _placeholder_style() -> str:
    from .theme.manager import ThemeManager
    t = ThemeManager.instance().tokens()
    return f"color: {_muted()}; padding: 20px;"


class ToolsPanel(QWidget):
    """Standalone tools window containing tabs: Renamer, Agents."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("tools_panel")
        self.setWindowTitle("Rikugan Tools")
        from .theme.manager import ThemeManager
        ThemeManager.instance().themeChanged.connect(self._apply_styles)
        # No minimum size — this widget is embedded in IDA dockable forms
        # which can be any size.

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar with title (hidden when docked in IDA)
        self._header = QFrame()
        self._header.setObjectName("tools_panel_header")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        self._title = QLabel("Tools")
        header_layout.addWidget(self._title)
        header_layout.addStretch()

        main_layout.addWidget(self._header)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setObjectName("tools_tabs")

        # Placeholder tabs
        self._renamer_placeholder = QLabel("Not loaded")
        self._renamer_placeholder.setWordWrap(True)
        self._tabs.addTab(self._renamer_placeholder, "Renamer")

        self._agents_placeholder = QLabel("Not loaded")
        self._agents_placeholder.setWordWrap(True)
        self._tabs.addTab(self._agents_placeholder, "Agents")

        main_layout.addWidget(self._tabs)

        # Apply themed styles now that all children exist.
        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(maybe_host_stylesheet(_panel_style()))
        self._title.setStyleSheet(maybe_host_stylesheet(_header_style()))
        # The placeholder QLabels are owned by QTabWidget and removed
        # (via deleteLater) when the real Renamer/Agents widget replaces
        # them. The PySide6 wrapper for a deleted C++ object raises
        # ``RuntimeError: Internal C++ object already deleted`` on the
        # next method call, so guard both reads.
        if self._renamer_placeholder is not None:
            self._renamer_placeholder.setStyleSheet(
                maybe_host_stylesheet(_placeholder_style())
            )
        if self._agents_placeholder is not None:
            self._agents_placeholder.setStyleSheet(
                maybe_host_stylesheet(_placeholder_style())
            )

    def _replace_tab(self, index: int, widget: QWidget, label: str) -> None:
        """Replace the widget at the given tab index."""
        old = self._tabs.widget(index)
        self._tabs.removeTab(index)
        self._tabs.insertTab(index, widget, label)
        if old is not None:
            # Drop our reference to the placeholder (if this is the
            # first replace) so ``_apply_styles`` doesn't try to
            # setStyleSheet on a deleted C++ object the next time the
            # theme fires. deleteLater schedules the C++ delete; the
            # Python wrapper will be GC'd once we drop the ref.
            if index == 0:
                self._renamer_placeholder = None
            elif index == 1:
                self._agents_placeholder = None
            old.deleteLater()

    def set_renamer_widget(self, widget: QWidget) -> None:
        """Replace the Renamer tab content."""
        self._replace_tab(0, widget, "Renamer")

    def set_agents_widget(self, widget: QWidget) -> None:
        """Replace the Agents tab content."""
        self._replace_tab(1, widget, "Agents")

    def hide_header(self) -> None:
        """Hide the title bar (used when embedded in a dockable form)."""
        self._header.setVisible(False)
