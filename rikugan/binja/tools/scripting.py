"""Python scripting execution tool for Binary Ninja."""

from __future__ import annotations

import importlib
from typing import Annotated

from ...core.logging import log_debug
from ...tools.base import tool
from ...tools.script_guard import run_guarded_script, safe_builtins
from .compat import current_ea_or_default, require_bv

_BN_MODULE_NAMES = (
    "binaryninja",
    "binaryninjaui",
)
_cached_namespace: dict | None = None


def _get_base_namespace() -> dict:
    """Return a cached namespace with common Binary Ninja modules pre-imported."""
    global _cached_namespace
    if _cached_namespace is None:
        ns: dict = {}
        for mod_name in _BN_MODULE_NAMES:
            try:
                ns[mod_name] = importlib.import_module(mod_name)
            except ImportError as e:
                log_debug(f"Optional BN module {mod_name!r} not available: {e}")
        _cached_namespace = ns

    bv = require_bv()
    result: dict = {"__builtins__": safe_builtins()}
    result.update(_cached_namespace)
    result["bv"] = bv
    result["current_address"] = current_ea_or_default(0)
    return result


@tool(category="scripting", mutating=True)
def execute_python(
    code: Annotated[str, "Python code to execute in Binary Ninja's scripting environment"],
) -> str:
    """Execute arbitrary Python code in Binary Ninja context and return stdout/stderr.

    The code runs with access to `binaryninja`, `binaryninjaui`, `bv`, and
    `current_address`.
    """
    return run_guarded_script(code, _get_base_namespace)
