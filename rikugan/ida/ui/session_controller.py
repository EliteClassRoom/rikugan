"""IDA session controller."""

from __future__ import annotations

import importlib
from typing import Any

from ...core.config import RikuganConfig
from ...core.host import get_database_path
from ...ui.session_controller_base import SessionControllerBase
from ..tools.registry import create_default_registry, register_advanced_tools, reset_failed_advanced_modules


class IdaSessionController(SessionControllerBase):
    """IDA-oriented controller."""

    def __init__(self, config: RikuganConfig):
        super().__init__(
            config=config,
            tool_registry_factory=create_default_registry,
            database_path_getter=get_database_path,
            host_name="IDA Pro",
            ensure_tools_ready=register_advanced_tools,
            reset_deferred_tools=reset_failed_advanced_modules,
        )

    def list_functions_raw(self, offset: int = 0, limit: int = 0) -> list[dict]:
        """Enumerate all functions in the IDB for the bulk renamer.

        Delegates to the IDA-specific private helper in functions.py.
        Called from the UI thread.  Supports chunked loading via
        *offset* and *limit*.
        """
        from ..tools.functions import _enumerate_all_functions

        return _enumerate_all_functions(offset=offset, limit=limit)

    def get_function_count(self) -> int:
        """Return the total number of functions in the IDB."""
        from ..tools.functions import _get_function_count

        return _get_function_count()

    def begin_function_enumeration(self) -> None:
        """Start a cursor-based function enumeration session.

        Called from the UI thread before QTimer-driven chunk loading.  The
        iterator is consumed incrementally by ``next_function_chunk()`` so IDA
        functions are not repeatedly materialized into full Python lists.
        """
        try:
            idautils = importlib.import_module("idautils")
        except ImportError:
            self._function_enum_iter = None
            raise
        self._function_enum_iter = iter(idautils.Functions())

    def next_function_chunk(self, limit: int) -> tuple[list[dict], bool]:
        """Return up to *limit* function entries and whether more may remain."""
        iterator = getattr(self, "_function_enum_iter", None)
        if iterator is None:
            return [], False
        try:
            ida_funcs = importlib.import_module("ida_funcs")
            ida_name = importlib.import_module("ida_name")
        except ImportError:
            self._function_enum_iter = None
            raise
        try:
            ida_segment: Any = importlib.import_module("ida_segment")
        except ImportError:
            ida_segment = None

        chunk: list[dict] = []
        more = True
        for _ in range(max(1, limit)):
            try:
                ea = next(iterator)
            except StopIteration:
                more = False
                self._function_enum_iter = None
                break
            name = ida_name.get_name(ea)
            is_import = False
            if ida_segment is not None:
                try:
                    seg = ida_segment.getseg(ea)
                    if seg is not None:
                        seg_type_name = getattr(ida_segment, "get_segm_name", lambda s: "")(seg)
                        if seg_type_name in (".idata", ".extern", "extern"):
                            is_import = True
                except Exception as exc:
                    from ...core.logging import log_debug

                    log_debug(f"Import segment detection failed for 0x{ea:x}: {exc}")
            size_bytes = 0
            func = ida_funcs.get_func(ea)
            if func is not None:
                size_bytes = func.end_ea - func.start_ea
            chunk.append({"address": ea, "name": name, "is_import": is_import, "size_bytes": size_bytes})
        return chunk, more

    def cancel_function_enumeration(self) -> None:
        """Cancel any active cursor-based function enumeration session."""
        self._function_enum_iter = None


# Backwards-compatible alias
SessionController = IdaSessionController
