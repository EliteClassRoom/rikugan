"""Rikugan - Intelligent Reverse-engineering Integrated System.

IDA Pro plugin entry point.
All rikugan.* imports are deferred to avoid crashes during plugin enumeration.

Startup path:
  IDA load → RikuganPlugin.init() [imports constants only]
  → user activates → RikuganPlugmod._toggle_panel()
    → minimal import of rikugan.ida.ui.panel
    → RikuganPanel() → show()
  Old behaviour (disabled): recursive full-package preload.
  Restore old path: set RIKUGAN_PRELOAD_ALL=1.
"""

import builtins
import importlib
import os
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
        self._toggle_panel()
        return True

    def term(self) -> None:
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
        except Exception as exc:
            import sys

            sys.stderr.write(f"[Rikugan] QApplication.processEvents failed: {exc}\n")

    def _toggle_panel(self) -> None:
        # Lazily import startup_timing within toggle_panel so that the
        # plugin module itself does NOT import rikugan.* at load time.
        from rikugan.core.startup_timing import (
            complete as _complete_timing,
        )
        from rikugan.core.startup_timing import (
            end as _end_phase,
        )
        from rikugan.core.startup_timing import (
            flush as _flush_timing,
        )
        from rikugan.core.startup_timing import (
            start as _start_phase,
        )

        t_toggle = _start_phase("toggle.total")
        try:
            _log("_toggle_panel: entry")
            if self._panel is not None:
                _log("_toggle_panel: panel exists, calling show()")
                self._panel.show()
                return

            # Minimal import path: load only the rikugan.ida.ui.panel module.
            # The old behaviour (recursive full-package preload via
            # pkgutil.iter_modules) is available via RIKUGAN_PRELOAD_ALL=1.
            _PRELOAD_ALL = os.environ.get("RIKUGAN_PRELOAD_ALL", "") in ("1", "yes", "true")

            if _PRELOAD_ALL:
                _log("_toggle_panel: RIKUGAN_PRELOAD_ALL=1 — performing full recursive import")

                t_bulk = _start_phase("toggle.bulk_import_all")
                import pkgutil

                import rikugan

                _imported = 0
                _skipped = 0

                def _load_submodules(pkg):
                    nonlocal _imported, _skipped
                    for _finder, modname, ispkg in pkgutil.iter_modules(pkg.__path__, prefix=pkg.__name__ + "."):
                        try:
                            mod = importlib.import_module(modname)
                            _imported += 1
                            if ispkg:
                                _load_submodules(mod)
                        except Exception as e:
                            _skipped += 1
                            import sys

                            sys.stderr.write(f"[Rikugan] Skipping {modname}: {e}\n")

                saved_import = builtins.__import__
                builtins.__import__ = importlib.__import__
                try:
                    _load_submodules(rikugan)
                finally:
                    builtins.__import__ = saved_import
                _end_phase("toggle.bulk_import_all", t_bulk, meta={"imported": _imported, "skipped": _skipped})
                _log("_toggle_panel: all rikugan modules loaded")
            else:
                _log("_toggle_panel: using minimal import (set RIKUGAN_PRELOAD_ALL=1 for legacy full preload)")

            _log("_toggle_panel: importing rikugan.ida.ui.panel")
            t_import_panel = _start_phase("toggle.import_panel_module")
            RikuganPanel = importlib.import_module("rikugan.ida.ui.panel").RikuganPanel
            _end_phase("toggle.import_panel_module", t_import_panel)

            _log("_toggle_panel: creating RikuganPanel()")
            t_construct = _start_phase("toggle.panel_construct")
            self._panel = RikuganPanel()
            _end_phase("toggle.panel_construct", t_construct)

            _log("_toggle_panel: calling show()")
            t_show = _start_phase("toggle.panel_show")
            self._panel.show()
            _end_phase("toggle.panel_show", t_show)

            _log("_toggle_panel: done")
            _end_phase("toggle.total", t_toggle)

            # Mark startup session complete, then flush timing records
            # to the debug log now that the logging subsystem is available.
            try:
                _complete_timing()
                _flush_timing()
            except Exception as exc:
                import sys

                sys.stderr.write(f"[Rikugan] timing flush failed: {exc}\n")
        except Exception as e:
            import sys
            import traceback

            tb_str = traceback.format_exc()
            idaapi.msg(f"[Rikugan] Failed to open panel: {e}\n{tb_str}\n")
            try:
                importlib.import_module("rikugan.core.logging").log_error(f"Failed to open panel: {e}\n{tb_str}")
            except Exception:
                try:
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
    """Best-effort log to IDA output and debug file.

    Caches the ``log_trace`` callable after the first successful import so
    that repeated ``importlib`` calls are avoided during the tight bootstrap
    path.  A single transient import failure does **not** permanently
    suppress further attempts — the import is retried on every call until it
    succeeds.  Only a successful import is cached.
    """
    idaapi.msg(f"[Rikugan] {msg}\n")
    cached = getattr(_log, "_cached_log_trace", None)
    if cached is not None:
        try:
            cached(msg)
        except Exception as e:
            import sys

            sys.stderr.write(f"[Rikugan] cached log_trace failed during bootstrap: {e}\n")
        return
    try:
        log_func = importlib.import_module("rikugan.core.logging").log_trace
        _log._cached_log_trace = log_func
        log_func(msg)
    except Exception as e:
        import sys

        sys.stderr.write(f"[Rikugan] log_trace unavailable during bootstrap: {e}\n")


def PLUGIN_ENTRY():
    return RikuganPlugin()
