"""Binary Ninja QWidget wrapper around the shared Rikugan panel core."""

from __future__ import annotations

from ...ui.panel_core import RikuganPanelCore
from ...ui.qt_compat import QVBoxLayout, QWidget
from .session_controller import BinaryNinjaSessionController


class RikuganPanel(QWidget):
    """Binary Ninja panel widget."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._core: RikuganPanelCore | None = RikuganPanelCore(
            controller_factory=BinaryNinjaSessionController,
            ui_hooks_factory=None,
            parent=self,
        )
        layout.addWidget(self._core)
        self._apply_binja_theme()

    def _apply_binja_theme(self) -> None:
        """Apply Binary Ninja's theme to the Rikugan panel.

        Respects the config's theme setting. If theme is "dark" or "light",
        use those instead. If "binja" (default), inherit BN's Qt theme.
        """
        if self._core is None:
            return
        try:
            config_theme = getattr(self._core, "_config", None)
            if config_theme is not None:
                config_theme = config_theme.theme
            if config_theme in ("dark", "light"):
                self._core.set_theme(config_theme)
            else:
                # config_theme == "binja" or invalid — inherit BN's Qt theme.
                # Binary Ninja embeds Rikugan in its own UI which has its own
                # Qt stylesheet. We just need to disable dark markdown colors.
                self._core.set_theme("binja")
        except Exception:
            self._core.set_theme("binja")

    def mount(self, parent: QWidget) -> None:
        if self.parent() is not parent:
            self.setParent(parent)
        layout = parent.layout()
        if layout is None:
            layout = QVBoxLayout(parent)
            layout.setContentsMargins(0, 0, 0, 0)
        if layout.indexOf(self) < 0:
            layout.addWidget(self)

    def prefill_input(self, text: str, auto_submit: bool = False) -> None:
        if self._core is not None:
            self._core.prefill_input(text, auto_submit=auto_submit)

    def shutdown(self) -> None:
        if self._core is not None:
            self._core.shutdown()
            self._core = None

    def on_database_changed(self, new_path: str) -> None:
        if self._core is not None:
            self._core.on_database_changed(new_path)
