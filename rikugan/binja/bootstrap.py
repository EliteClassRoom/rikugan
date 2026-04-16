"""Binary Ninja plugin bootstrap: sidebar, commands, and panel orchestration.

Extracted from the root ``rikugan_binaryninja.py`` entry point so the entry
point remains a thin host-loader shim. All runtime orchestration lives here.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import binaryninja as bn  # type: ignore[import-not-found]

try:
    import binaryninjaui as bnui  # type: ignore[import-not-found]
except Exception:
    bnui = None

from ..core.host import get_database_path, set_binary_ninja_context
from ..core.logging import log_debug
from .tools.fn_utils import get_function_at, get_function_name
from .ui.actions import ACTION_DEFS, build_context
from .ui.panel import RikuganPanel

RIKUGAN_SIDEBAR_NAME = "Rikugan"

_PANEL: RikuganPanel | None = None
_LAST_BV: Any = None
_REGISTERED = False
_SIDEBAR_REGISTERED = False


# ------------------------------------------------------------------
# Navigation & context
# ------------------------------------------------------------------


def _navigate_cb(ea: int) -> bool:
    """Best-effort Binary Ninja UI navigation callback."""
    global _LAST_BV
    bv = _LAST_BV
    if bv is None:
        return False

    # Try BinaryView.navigate(view, addr)
    nav = getattr(bv, "navigate", None)
    if callable(nav):
        for view in ("Graph:IL", "Graph:Disassembly", "Linear:Disassembly", "Linear"):
            try:
                if bool(nav(view, int(ea))):
                    return True
            except Exception as e:
                log_debug(f"_navigate_cb nav({view!r}) failed at 0x{ea:x}: {e}")
                continue
        try:
            if bool(nav(int(ea))):
                return True
        except Exception as e:
            log_debug(f"_navigate_cb nav(ea) failed at 0x{ea:x}: {e}")

    # Try UIContext navigation APIs if available
    if bnui is not None:
        try:
            ui_ctx_cls = getattr(bnui, "UIContext", None)
            if ui_ctx_cls is not None:
                active = ui_ctx_cls.activeContext()
                if active is not None:
                    vf = active.getCurrentViewFrame()
                    if vf is not None:
                        for meth_name in ("navigate", "setCurrentOffset"):
                            meth = getattr(vf, meth_name, None)
                            if callable(meth):
                                try:
                                    rc = meth(int(ea))
                                    if rc is None or bool(rc):
                                        return True
                                except Exception as e:
                                    log_debug(f"_navigate_cb UIContext.{meth_name} failed at 0x{ea:x}: {e}")
        except Exception as e:
            log_debug(f"_navigate_cb UIContext navigation failed at 0x{ea:x}: {e}")

    return False


def _update_context(bv: Any, address: int | None = None) -> None:
    global _LAST_BV
    changed_view = (bv is not _LAST_BV) and (_LAST_BV is not None)
    _LAST_BV = bv
    set_binary_ninja_context(bv=bv, address=address, navigate_cb=_navigate_cb)
    if changed_view:
        # BinaryView changed — notify panel with normalized path from host context.
        panel = _get_sidebar_panel(create_if_missing=False)
        if panel is not None:
            try:
                panel.on_database_changed(get_database_path())
            except Exception as e:
                log_debug(f"_update_context on_database_changed failed: {e}")


# ------------------------------------------------------------------
# Sidebar & panel helpers
# ------------------------------------------------------------------


def _active_sidebar() -> Any:
    if bnui is None:
        return None
    try:
        ui_ctx_cls = getattr(bnui, "UIContext", None)
        if ui_ctx_cls is None:
            return None
        ui_ctx = ui_ctx_cls.activeContext()
        if ui_ctx is None:
            return None
        sidebar_get = getattr(ui_ctx, "sidebar", None)
        if not callable(sidebar_get):
            return None
        return sidebar_get()
    except Exception:
        return None


def _get_sidebar_panel(create_if_missing: bool = True) -> RikuganPanel | None:
    sidebar = _active_sidebar()
    if sidebar is None:
        return None
    try:
        widget = sidebar.widget(RIKUGAN_SIDEBAR_NAME)
        if widget is None and create_if_missing:
            sidebar.activate(RIKUGAN_SIDEBAR_NAME)
            widget = sidebar.widget(RIKUGAN_SIDEBAR_NAME)
        if widget is not None and hasattr(widget, "panel"):
            panel = widget.panel
            if isinstance(panel, RikuganPanel):
                return panel
    except Exception:
        return None
    return None


def _ensure_panel(bv: Any, address: int | None = None) -> RikuganPanel:
    global _PANEL
    _update_context(bv, address)

    # Preferred mode: sidebar panel (like Sidekick)
    sidebar_panel = _get_sidebar_panel(create_if_missing=True)
    if sidebar_panel is not None:
        return sidebar_panel

    # Fallback: floating widget
    if _PANEL is None:
        _PANEL = RikuganPanel()

    _PANEL.show()
    try:
        _PANEL.raise_()
        _PANEL.activateWindow()
    except Exception as e:
        log_debug(f"_ensure_panel raise_/activateWindow failed: {e}")
    return _PANEL


# ------------------------------------------------------------------
# Action callbacks
# ------------------------------------------------------------------


def _action_callback(handler: Callable[[dict[str, Any]], str], auto_submit: bool):
    def _cb(bv, addr):
        _update_context(bv, int(addr))
        panel = _ensure_panel(bv, int(addr))
        ctx = build_context(bv, int(addr), get_function_at, get_function_name)
        text = handler(ctx)
        if text:
            panel.prefill_input(text, auto_submit=auto_submit)

    return _cb


def _open_panel_command(bv):
    _ensure_panel(bv, None)


# ------------------------------------------------------------------
# Sidebar widget registration
# ------------------------------------------------------------------


def _register_sidebar() -> None:
    global _SIDEBAR_REGISTERED
    if _SIDEBAR_REGISTERED or bnui is None:
        return

    Sidebar = getattr(bnui, "Sidebar", None)
    SidebarWidget = getattr(bnui, "SidebarWidget", None)
    SidebarWidgetType = getattr(bnui, "SidebarWidgetType", None)
    SidebarWidgetLocation = getattr(bnui, "SidebarWidgetLocation", None)
    SidebarContextSensitivity = getattr(bnui, "SidebarContextSensitivity", None)
    if Sidebar is None or SidebarWidget is None or SidebarWidgetType is None:
        return

    from PySide6.QtGui import QImage

    class RikuganSidebarWidget(SidebarWidget):  # type: ignore[misc, valid-type]
        def __init__(self, view_frame, binary_view):
            super().__init__(RIKUGAN_SIDEBAR_NAME)
            self.view_frame = view_frame
            self.binary_view = binary_view
            # Ensure host DB context exists before panel/controller construction.
            _update_context(binary_view, None)
            self.panel = RikuganPanel()
            self.panel.mount(self)

        def notifyViewLocationChanged(self, view, location):  # type: ignore[override]
            try:
                ea = int(location.getOffset())
            except Exception:
                ea = None
            _update_context(self.binary_view, ea)

        def closing(self):
            """Sidebar lifecycle callback."""
            try:
                self.panel.shutdown()
            except Exception as e:
                log_debug(f"RikuganSidebarWidget.closing panel.shutdown failed: {e}")

    # Resolve assets directory relative to the project root (two levels up from rikugan/binja/)
    _assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets")

    class RikuganSidebarWidgetType(SidebarWidgetType):  # type: ignore[misc, valid-type]
        def __init__(self):
            icon = QImage(os.path.join(_assets_dir, "rikugan_icon_light.png"))
            if icon.isNull():
                icon = QImage(":/icons/sidekick-assistant.png")
            if icon.isNull():
                icon = QImage(os.path.join(_assets_dir, "chat.png"))
            SidebarWidgetType.__init__(self, icon, RIKUGAN_SIDEBAR_NAME)

        def createWidget(self, frame, data):
            if data is None:
                return None
            return RikuganSidebarWidget(frame, data)

        def defaultLocation(self):
            if SidebarWidgetLocation is not None:
                return SidebarWidgetLocation.LeftContent
            return super().defaultLocation()

        def contextSensitivity(self):
            if SidebarContextSensitivity is not None:
                return SidebarContextSensitivity.PerViewTypeSidebarContext
            return super().contextSensitivity()

        def isInReferenceArea(self):
            return False

    try:
        Sidebar.addSidebarWidgetType(RikuganSidebarWidgetType())
        _SIDEBAR_REGISTERED = True
    except Exception:
        _SIDEBAR_REGISTERED = False


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------


def register_plugin() -> None:
    """Register Rikugan sidebar and commands with Binary Ninja."""
    global _REGISTERED
    if _REGISTERED:
        return

    _register_sidebar()

    plugin_cmd = getattr(bn, "PluginCommand", None)
    if plugin_cmd is None:
        return

    plugin_cmd.register(
        "Rikugan\\Open Panel",
        "Open Rikugan chat panel",
        _open_panel_command,
    )

    register_for_address = getattr(plugin_cmd, "register_for_address", None)
    if callable(register_for_address):
        for label, desc, handler, auto_submit in ACTION_DEFS:
            register_for_address(
                f"Rikugan\\{label}",
                desc,
                _action_callback(handler, auto_submit),
            )

    _REGISTERED = True
