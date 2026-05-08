"""Binary Ninja tool registry.

Wires Binary Ninja-specific tool modules into the shared ToolRegistry.
"""

from __future__ import annotations

from ...core.thread_safety import idasync
from ...tools import web
from ...tools.registry import ToolRegistry
from . import (  # type: ignore[assignment]
    annotations,
    database,
    decompiler,
    disassembly,
    functions,
    il,
    il_analysis,
    il_transform,
    navigation,
    scripting,
    strings,
    types_tools,
    xrefs,
)

_TOOL_MODULES = (
    navigation,
    functions,
    strings,
    database,
    disassembly,
    decompiler,
    xrefs,
    annotations,
    types_tools,
    scripting,
    il,
    il_analysis,
    il_transform,
    web,
)


def create_default_registry() -> ToolRegistry:
    """Create a Binary Ninja registry with all built-in BN tools."""
    registry = ToolRegistry(dispatch_wrapper=idasync)
    for mod in _TOOL_MODULES:
        registry.register_module(mod)
    return registry
