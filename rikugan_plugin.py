"""Rikugan - Intelligent Reverse-engineering Integrated System.

IDA Pro plugin entry point.
All rikugan.* imports are deferred to avoid crashes during plugin enumeration.
"""

import builtins
import importlib
import threading

import idaapi

# ---------------------------------------------------------------------------
# Shiboken __import__ hook re-entrancy guard
# ---------------------------------------------------------------------------
# PySide6/Shiboken6 patches builtins.__import__ with a hook.  When this
# hook is invoked during Qt signal dispatch (e.g. submit_requested.emit()),
# and the connected slot's code triggers an import, the hook re-enters
# itself.  After 3-4 levels of nesting the hook accesses freed memory
# (UAF → SIGSEGV in ___lldb_unnamed_symbol945, address looks like ASCII
# string fragment — type-name pointer corruption).
#
# Fix: wrap the hook so that first-level calls go through Shiboken
# normally (preserving PySide6 module wrapping), but nested calls
# (re-entrant) are redirected to CPython's standard import, avoiding
# the corruption.  Installed once and never removed.

_import_guard = threading.local()
_shiboken_import = builtins.__import__


def _guarded_import(*args, **kwargs):
    if getattr(_import_guard, "active", False):
        # Re-entrant call — bypass Shiboken's hook
        return importlib.__import__(*args, **kwargs)
    _import_guard.active = True
    try:
        return _shiboken_import(*args, **kwargs)
    finally:
        _import_guard.active = False


_guarded_import._rikugan_guarded = True  # marker to avoid double-wrapping
if not getattr(builtins.__import__, "_rikugan_guarded", False):
    builtins.__import__ = _guarded_import


class RikuganPlugmod(idaapi.plugmod_t):
    """Per-database plugin module."""

    def __init__(self):
        super().__init__()
        self._panel = None

    def run(self, arg: int) -> bool:
        # Initialize theme system (best-effort). Lazy imports keep
        # rikugan.* off the module-load path to avoid import-time
        # crashes during plugin enumeration.
        try:
            from rikugan.core.config import RikuganConfig
            from rikugan.core.host import is_ida
            from rikugan.ui.theme.manager import ThemeManager
            from rikugan.ui.theme.tokens import ThemeMode

            config = RikuganConfig.load_or_create()
            theme_mgr = ThemeManager.instance()
            try:
                theme_mgr.set_mode(ThemeMode(config.theme_mode))
            except Exception:
                # Fall back to AUTO if config has an unknown mode
                theme_mgr.set_mode(ThemeMode.AUTO)

            # Start IDA palette watcher (IDA host only — standalone is
            # not theme-aware via QPalette). The watcher is also skipped in
            # DARK/LIGHT modes: the manager returns the bundled constant
            # tokens without consulting QPalette, so polling the host
            # palette every 500 ms is pure overhead (and risks spurious
            # refresh_from_host calls that re-emit the same tokens).
            # The getattr guard prevents a second start when run() is
            # invoked more than once.
            needs_palette_watch = theme_mgr.mode in (
                ThemeMode.AUTO,
                ThemeMode.IDA_NATIVE,
            )
            if (
                is_ida()
                and needs_palette_watch
                and not getattr(self, "_theme_watcher", None)
            ):
                from rikugan.ui.theme.watcher import IDAThemeWatcher

                self._theme_watcher = IDAThemeWatcher(interval_ms=500)
                self._theme_watcher.start()
        except Exception as e:
            # Theme init is best-effort — the plugin must still work
            # even if the theme system is unavailable (e.g. headless
            # IDA, missing PySide6, or a Qt stub without QTimer.singleShot).
            _log(f"Theme init failed: {e}")

        self._toggle_panel()
        return True

    def term(self) -> None:
        # Stop theme watcher first so it cannot fire while we tear down
        # the panel (the watcher polls QApplication.palette() and the
        # panel close may flush Qt events).
        watcher = getattr(self, "_theme_watcher", None)
        if watcher is not None:
            try:
                watcher.stop()
            except Exception as e:
                _log(f"Theme watcher stop failed: {e}")
            self._theme_watcher = None

        _log("RikuganPlugmod.term() called")
        panel = self._panel
        self._panel = None
        if panel is not None:
            try:
                panel.close()
            except Exception as e:
                idaapi.msg(f"[Rikugan] Panel close error: {e}\n")
        # Flush deferred widget deletions while Python is still alive.
        # Without this, orphaned PySide6-wrapped QFrames survive until
        # QApplication::~QApplication() where their C++ destructors call
        # disconnectNotify -> PyErr_Occurred on a dead interpreter -> crash.
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
        except Exception:
            pass

    def _toggle_panel(self) -> None:
        try:
            _log("_toggle_panel: entry")
            if self._panel is not None:
                _log("_toggle_panel: panel exists, calling show()")
                self._panel.show()
                return

            # Import only the panel entry module here.  Its dependency chain
            # loads the rest lazily as needed, avoiding a full recursive
            # package walk on first panel open.
            _log("_toggle_panel: importing panel module")

            # Temporarily bypass Shiboken's __import__ hook while the panel
            # module and its direct imports execute. importlib.import_module()
            # itself avoids __import__, but module code can still emit
            # IMPORT_NAME bytecode that reaches builtins.__import__.
            saved_import = builtins.__import__
            builtins.__import__ = importlib.__import__
            try:
                RikuganPanel = importlib.import_module("rikugan.ida.ui.panel").RikuganPanel
            finally:
                builtins.__import__ = saved_import

            _log("_toggle_panel: panel module loaded")

            _log("_toggle_panel: creating RikuganPanel()")
            self._panel = RikuganPanel()
            _log("_toggle_panel: calling show()")
            self._panel.show()
            _log("_toggle_panel: done")
        except Exception as e:
            import sys
            import traceback
            tb_str = traceback.format_exc()
            idaapi.msg(f"[Rikugan] Failed to open panel: {e}\n{tb_str}\n")
            try:
                importlib.import_module("rikugan.core.logging").log_error(
                    f"Failed to open panel: {e}\n{tb_str}"
                )
            except Exception:
                try:
                    import os
                    log_path = os.path.join(os.path.expanduser("~"), ".idapro", "rikugan", "rikugan_debug.log")
                    with open(log_path, "a") as f:
                        f.write(f"[Rikugan CRASH] {e}\n{tb_str}\n")
                        f.flush()
                        os.fsync(f.fileno())
                except Exception:
                    print(f"[Rikugan CRASH] {e}\n{tb_str}", file=sys.stderr)


class RikuganPlugin(idaapi.plugin_t):
    flags = idaapi.PLUGIN_MULTI | idaapi.PLUGIN_FIX
    comment = "Intelligent Reverse-engineering Integrated System"
    help = ""
    wanted_name = "Rikugan"
    wanted_hotkey = "Ctrl+Shift+I"

    def init(self) -> idaapi.plugmod_t:
        _ver = importlib.import_module("rikugan.constants").PLUGIN_VERSION
        idaapi.msg(f"[Rikugan] Plugin loaded (v{_ver})\n")
        return RikuganPlugmod()


def _log(msg: str) -> None:
    """Best-effort log to IDA output and debug file."""
    idaapi.msg(f"[Rikugan] {msg}\n")
    try:
        logging_mod = importlib.import_module("rikugan.core.logging")
        trace = getattr(logging_mod, "log_trace", None)
        if callable(trace):
            trace(msg)
            return
        debug = getattr(logging_mod, "log_debug", None)
        if callable(debug):
            debug(msg)
    except Exception:
        # Early bootstrap can observe partially initialized modules; ignore.
        pass


def PLUGIN_ENTRY():  # noqa: N802
    return RikuganPlugin()
