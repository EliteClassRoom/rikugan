"""Cross-reference tools."""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from typing import Annotated

from ...tools.base import parse_addr, tool


def format_callers_callees(fname: str, start: int, callers: Iterable[str], callees: Iterable[str]) -> str:
    """Format a function callers/callees summary (shared between IDA and BN xref tools)."""
    callers = sorted(callers)
    callees = sorted(callees)
    parts = [f"Function: {fname} (0x{start:x})"]
    parts.append(f"\nCallers ({len(callers)}):")
    for c in callers:
        parts.append(f"  {c}")
    parts.append(f"\nCallees ({len(callees)}):")
    for c in callees:
        parts.append(f"  {c}")
    return "\n".join(parts)


ida_funcs = ida_name = ida_xref = idautils = None  # populated below when IDA is available
try:
    ida_funcs = importlib.import_module("ida_funcs")
    ida_name = importlib.import_module("ida_name")
    ida_xref = importlib.import_module("ida_xref")
    idautils = importlib.import_module("idautils")
except ImportError:
    ida_funcs = ida_name = ida_xref = idautils = None  # IDA not present — tools unavailable in non-IDA context


# Xref type constants → human-readable names.
# Covers code-ref (fl_*) and data-ref (dr_*) types from ida_xref.
_XREF_TYPE_MAP = {
    0: "Data_Unknown",
    1: "dr_O",  # offset
    2: "dr_W",  # write
    3: "dr_R",  # read
    4: "dr_T",  # text/informational
    5: "dr_I",  # informational
    16: "fl_CF",  # call far
    17: "fl_CN",  # call near
    18: "fl_JF",  # jump far
    19: "fl_JN",  # jump near
    20: "fl_US",  # user-specified
    21: "fl_F",  # ordinary flow
}


def _xref_type_name(xtype: int) -> str:
    """Get a readable name for an xref type, with fallback."""
    return _XREF_TYPE_MAP.get(xtype, f"type_{xtype}")


@tool(category="xrefs")
def xrefs_to(
    address: Annotated[str, "Target address (hex string)"],
    limit: Annotated[int, "Max results"] = 30,
) -> str:
    """Get all cross-references to the given address."""

    ea = parse_addr(address)
    target_name = ida_name.get_name(ea)
    lines = [f"Cross-references to 0x{ea:x}" + (f" ({target_name})" if target_name else "") + ":"]

    count = 0
    for xref in idautils.XrefsTo(ea, 0):
        if count >= limit:
            lines.append(f"  ... (truncated at {limit})")
            break

        xtype = _xref_type_name(xref.type)
        func = ida_funcs.get_func(xref.frm)
        fname = ida_name.get_name(func.start_ea) if func else "?"
        lines.append(f"  0x{xref.frm:x}  [{xtype:12s}]  in {fname}")
        count += 1

    if count == 0:
        lines.append("  (none)")
    return "\n".join(lines)


@tool(category="xrefs")
def xrefs_from(
    address: Annotated[str, "Source address (hex string)"],
    limit: Annotated[int, "Max results"] = 30,
) -> str:
    """Get all cross-references from the given address."""

    ea = parse_addr(address)
    lines = [f"Cross-references from 0x{ea:x}:"]

    count = 0
    for xref in idautils.XrefsFrom(ea, 0):
        if count >= limit:
            lines.append(f"  ... (truncated at {limit})")
            break
        xtype = _xref_type_name(xref.type)
        target_name = ida_name.get_name(xref.to) or ""
        lines.append(f"  0x{xref.to:x}  [{xtype:12s}]  {target_name}")
        count += 1

    if count == 0:
        lines.append("  (none)")
    return "\n".join(lines)


@tool(category="xrefs")
def function_xrefs(
    address: Annotated[str, "Function address (hex string)"],
) -> str:
    """Get cross-references to and from a function (callers + callees)."""

    ea = parse_addr(address)
    func = ida_funcs.get_func(ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    fname = ida_name.get_name(func.start_ea)

    # Callers
    callers = set()
    for ref in idautils.CodeRefsTo(func.start_ea, 0):
        cf = ida_funcs.get_func(ref)
        if cf and cf.start_ea != func.start_ea:
            callers.add(ida_name.get_name(cf.start_ea))

    # Callees
    callees = set()
    for item in idautils.FuncItems(func.start_ea):
        for ref in idautils.CodeRefsFrom(item, 0):
            cf = ida_funcs.get_func(ref)
            if cf and cf.start_ea != func.start_ea:
                callees.add(ida_name.get_name(cf.start_ea))

    return format_callers_callees(fname, func.start_ea, callers, callees)
