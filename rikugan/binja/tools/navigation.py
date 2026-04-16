"""Navigation tools for Binary Ninja."""

from __future__ import annotations

from typing import Annotated

from ...tools.base import tool
from .compat import current_ea_or_default, navigate, parse_addr_like, require_bv
from .fn_utils import get_function_at, get_function_name
from .sym_utils import (
    iter_symbols_by_name,
    symbol_address,
)
from .sym_utils import (
    resolve_name_at as _get_name_at,
)


@tool(category="navigation")
def get_cursor_position() -> str:
    """Get the current cursor address in the Binary Ninja view."""
    ea = current_ea_or_default(0)
    return f"0x{ea:x}"


@tool(category="navigation")
def get_current_function() -> str:
    """Get information about the function at the current cursor position."""
    bv = require_bv()
    ea = current_ea_or_default(0)
    func = get_function_at(bv, ea)
    if func is None:
        return "No function at current address"

    start = int(getattr(func, "start", ea))
    end = int(getattr(func, "highest_address", start))
    size = max(0, end - start)
    name = get_function_name(func)
    return f"Name: {name}\nStart: 0x{start:x}\nEnd: 0x{end:x}\nSize: {size} bytes"


@tool(category="navigation")
def jump_to(
    address: Annotated[str, "Address to jump to (hex string, e.g. '0x401000')"],
) -> str:
    """Jump the Binary Ninja view to the specified address."""
    ea = parse_addr_like(address)
    if navigate(ea):
        return f"Jumped to 0x{ea:x}"
    return f"Could not navigate to 0x{ea:x}. Ensure the Rikugan panel was opened from the active Binary Ninja UI."


@tool(category="navigation")
def get_name_at(address: Annotated[str, "Address to query (hex string)"]) -> str:
    """Get the name/label at the specified address."""
    bv = require_bv()
    ea = parse_addr_like(address)
    name = _get_name_at(bv, ea)
    return name if name else f"No name at 0x{ea:x}"


@tool(category="navigation")
def get_address_of(name: Annotated[str, "Symbol name to look up"]) -> str:
    """Get the address of a named symbol."""
    bv = require_bv()
    syms = iter_symbols_by_name(bv, name)
    for sym in syms:
        ea = symbol_address(sym)
        if ea is not None:
            return f"0x{ea:x}"
    return f"Symbol not found: {name}"
