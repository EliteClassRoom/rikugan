"""Tools panel: container for bulk renamer, agent tree, and A2A bridge.

Can be shown as an independent window (QDialog) or embedded in a layout.
"""

from __future__ import annotations

import time

from ..core.early_log import _early_log
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
    """Standalone tools window containing tabs: Renamer, Agents, A2A."""

    def __init__(self, parent: QWidget | None = None):
        _early_log("tools_panel:init:entry")
        _t0 = time.monotonic()
        super().__init__(parent)
        self.setObjectName("tools_panel")
        self.setWindowTitle("Rikugan Tools")
        self.setStyleSheet(get_tools_panel_style())
        # No minimum size — this widget is embedded in IDA dockable forms
        # and IDA sidebars, which can be any size.

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
        # Lazy tab population: route ``currentChanged`` so we can
        # tell ``panel_core`` which tab became visible.
        self._tabs.currentChanged.connect(self._on_tab_changed)
        _early_log("tools_panel:tabs_created")

        # Per-tab initialization flags. Set True once a tab's heavy
        # widget has been created/replaced by panel_core. Keeps the
        # placeholder until the user actually selects the tab (or
        # panel_core explicitly requests it via ``show_tools_panel``).
        self._renamer_initialized = False
        self._agents_initialized = False
        self._a2a_initialized = False
        self._knowledge_initialized = False

        # Placeholder tabs. Real widgets are injected by
        # ``set_*_widget`` methods called from panel_core.
        self._renamer_placeholder = QLabel("Not loaded")
        self._renamer_placeholder.setStyleSheet(get_placeholder_style())
        self._renamer_placeholder.setWordWrap(True)
        self._tabs.addTab(self._renamer_placeholder, "Renamer")

        self._agents_placeholder = QLabel("Not loaded")
        self._agents_placeholder.setStyleSheet(get_placeholder_style())
        self._agents_placeholder.setWordWrap(True)
        self._tabs.addTab(self._agents_placeholder, "Agents")

        # A2A bridge placeholder — the real widget is created on
        # first A2A-tab selection so A2A discovery (PATH, config,
        # optional HTTP agent-card fetch) doesn't block startup.
        self._a2a_widget = QLabel("Click Refresh to discover external agents")
        self._a2a_widget.setStyleSheet(get_placeholder_style())
        self._a2a_widget.setWordWrap(True)
        self._tabs.addTab(self._a2a_widget, "A2A")

        # Knowledge tab: lazily filled by panel_core from
        # ``_ensure_knowledge_tab_initialized()``. A placeholder
        # keeps the tab order stable (0=Renamer, 1=Agents, 2=A2A,
        # 3=Knowledge) so existing ``tab_index=0/1/2`` callers
        # keep working.
        self._knowledge_widget = QLabel("Not loaded")
        self._knowledge_widget.setStyleSheet(get_placeholder_style())
        self._knowledge_widget.setWordWrap(True)
        self._tabs.addTab(self._knowledge_widget, "Knowledge")

        main_layout.addWidget(self._tabs)
        _early_log(f"tools_panel:init:done:elapsed_ms={int((time.monotonic() - _t0) * 1000)}")

    def _on_tab_changed(self, index: int) -> None:
        """Forward tab selection to panel_core so it can lazy-init that tab.

        The hook is wired via ``_tabs.currentChanged``. The panel
        core installs an ``on_tab_activated`` callback via
        :meth:`set_tab_activation_callback` after the panel is
        embedded or docked; until then the signal is a no-op.
        """
        callback = getattr(self, "_on_tab_activated_cb", None)
        if callback is None:
            return
        try:
            callback(index)
        except Exception as e:  # defensive — never crash Qt
            from ..core.logging import log_debug

            log_debug(f"tools_panel tab activation callback failed: {e}")

    def set_tab_activation_callback(self, callback) -> None:
        """Register a callback invoked whenever a tab becomes active.

        ``panel_core`` uses this to drive per-tab lazy initialization.
        Storing the callback as a plain attribute avoids a Qt signal
        round-trip and lets the callback know whether the panel is
        embedded or docked.
        """
        self._on_tab_activated_cb = callback

    def _replace_tab(self, index: int, widget: QWidget, label: str) -> QWidget | None:
        """Replace the widget at the given tab index.

        Returns the widget that was previously shown at ``index``
        (after detaching it from the tab widget) so callers can keep
        a strong reference if needed. The returned widget has already
        been removed from the tab and had ``shutdown()`` called on it
        when applicable, but has NOT been deleted — the caller owns
        its lifetime after this call.
        """
        old = self._tabs.widget(index)
        self._tabs.removeTab(index)
        self._tabs.insertTab(index, widget, label)
        if old is not None and old is not widget:
            # Shut down the old widget first so any background threads
            # / timers tied to it stop while the replacement is still
            # alive. ``hasattr`` keeps the helper robust against plain
            # placeholder QLabels that do not implement shutdown().
            if hasattr(old, "shutdown"):
                try:
                    old.shutdown()
                except Exception:  # defensive — teardown must not raise
                    pass
            old.deleteLater()
        return old

    def set_renamer_widget(self, widget: QWidget) -> None:
        """Replace the Renamer tab content."""
        self._replace_tab(0, widget, "Renamer")
        self._renamer_initialized = True

    def set_agents_widget(self, widget: QWidget) -> None:
        """Replace the Agents tab content."""
        self._replace_tab(1, widget, "Agents")
        self._agents_initialized = True

    def set_a2a_widget(self, widget: QWidget) -> None:
        """Replace the A2A tab content (replaces our default bridge).

        Also updates ``self._a2a_widget`` so the panel always knows
        which widget is active in the A2A slot. ``shutdown()`` only
        needs this when the caller later destroys the panel.
        """
        self._replace_tab(2, widget, "A2A")
        self._a2a_widget = widget
        self._a2a_initialized = True

    def set_knowledge_widget(self, widget: QWidget) -> None:
        """Replace the Knowledge tab content (4th tab).

        Index 3 must remain stable so :meth:`show_tools_with_renamer`
        and other ``tab_index=0/1/2`` callers don't shift the Renamer
        and Agents tabs when Knowledge is added.
        """
        self._replace_tab(3, widget, "Knowledge")
        self._knowledge_widget = widget
        self._knowledge_initialized = True

    def hide_header(self) -> None:
        """Hide the title bar (used when embedded in a dockable form)."""
        self._header.setVisible(False)

    def shutdown(self) -> None:
        """Propagate shutdown to lazy tab widgets.

        Walks every tab and shuts down any widget that exposes a
        ``shutdown()`` method (the heavy Real widgets — not the
        lightweight ``QLabel`` placeholders). Failures are swallowed
        so a misbehaving tab cannot block panel teardown.
        """
        for index in range(self._tabs.count()):
            widget = self._tabs.widget(index)
            if widget is None:
                continue
            if hasattr(widget, "shutdown"):
                try:
                    widget.shutdown()
                except Exception:  # defensive — teardown must not raise
                    pass
