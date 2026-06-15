"""Function listing, searching, and info tools."""

from __future__ import annotations

import importlib
from typing import Annotated, Any

from ...core.logging import log_debug
from ...tools.base import parse_addr, tool
from ...tools.formatting import format_function_summary
from ...tools.pagination import format_page

try:
    ida_funcs = importlib.import_module("ida_funcs")
    ida_gdl = importlib.import_module("ida_gdl")
    ida_name = importlib.import_module("ida_name")
    idc = importlib.import_module("idc")
    idautils = importlib.import_module("idautils")
except ImportError as e:
    log_debug(f"IDA modules not available: {e}")


@tool(category="functions")
def list_functions(
    offset: Annotated[int, "Start index for pagination"] = 0,
    limit: Annotated[int, "Max number of functions to return"] = 50,
) -> str:
    """List functions in the binary with pagination."""

    funcs = list(idautils.Functions())
    rows = [f"  0x{ea:x}  {ida_name.get_name(ea)}" for ea in funcs]
    return format_page(rows, offset=offset, limit=limit, title="Functions")


def _enumerate_all_functions(
    offset: int = 0,
    limit: int = 0,
) -> list[dict]:
    """Return function metadata as raw dicts for UI components.

    This is a non-tool helper for UI components (bulk renamer) that need
    the full function list without the overhead of text formatting or
    repeated enumeration.  Returns a list of dicts with keys:
    "address", "name", "is_import", "size_bytes" (end_ea - start_ea,
    0 when not computed).

    When *offset* and *limit* are provided, returns only a slice of the
    full list — used by chunked QTimer-driven loading so the UI thread
    stays responsive during enumeration of large binaries.

    Follows the project import discipline: all IDA API modules are
    imported via ``importlib.import_module()`` inside try/except blocks.
    """
    ida_segment = _noisy_ida_import("ida_segment")

    funcs: list[dict] = []
    # Build a stable list of function addresses up-front
    addrs = list(idautils.Functions())
    if limit > 0:
        addrs = addrs[offset : offset + limit]
    elif offset > 0:
        addrs = addrs[offset:]

    for ea in addrs:
        name = ida_name.get_name(ea)
        # Detect imports via segment type — more reliable than flag checks.
        is_import = False
        if ida_segment is not None:
            try:
                seg = ida_segment.getseg(ea)
                if seg is not None:
                    seg_type_name = getattr(ida_segment, "get_segm_name", lambda s: "")(seg)
                    if seg_type_name in (".idata", ".extern", "extern"):
                        is_import = True
            except Exception as seg_err:
                log_debug(f"Segment detection failed for 0x{ea:x}: {seg_err}")
        # Compute size_bytes from function bounds (zero if unavailable).
        size_bytes = 0
        func = ida_funcs.get_func(ea)
        if func is not None:
            size_bytes = func.end_ea - func.start_ea
        funcs.append({
            "address": ea,
            "name": name,
            "is_import": is_import,
            "size_bytes": size_bytes,
        })
    return funcs


def _get_function_count() -> int:
    """Return the total number of functions in the IDB."""
    return len(list(idautils.Functions()))


def _noisy_ida_import(module_name: str) -> Any:
    """Import an IDA API module via importlib, returning None on failure."""
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        log_debug(f"IDA API module {module_name!r} not available: {e}")
        return None


@tool(category="functions")
def get_function_info(address: Annotated[str, "Function address (hex string)"]) -> str:
    """Get detailed information about a specific function."""

    ea = parse_addr(address)
    func = ida_funcs.get_func(ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    name = ida_name.get_name(func.start_ea)
    size = func.end_ea - func.start_ea
    # Count basic blocks and instructions
    blocks = 0
    instrs = 0
    try:
        fc = ida_gdl.FlowChart(func)
        for block in fc:
            blocks += 1
            head = block.start_ea
            while head < block.end_ea:
                instrs += 1
                head = idc.next_head(head, block.end_ea)
    except Exception as e:
        log_debug(f"FlowChart analysis failed for 0x{ea:x}: {e}")

    # Get callers and callees
    callers = []
    for ref in idautils.CodeRefsTo(func.start_ea, 0):
        caller_func = ida_funcs.get_func(ref)
        if caller_func:
            cname = ida_name.get_name(caller_func.start_ea)
            callers.append(cname)
    callers = list(set(callers))[:10]

    callees = []
    for item in idautils.FuncItems(func.start_ea):
        for ref in idautils.CodeRefsFrom(item, 0):
            callee_func = ida_funcs.get_func(ref)
            if callee_func and callee_func.start_ea != func.start_ea:
                cname = ida_name.get_name(callee_func.start_ea)
                callees.append(cname)
    callees = list(set(callees))[:10]

    return format_function_summary(name, func.start_ea, func.end_ea, size, blocks, instrs, callers, callees)


@tool(category="functions")
def search_functions(
    query: Annotated[str, "Search string (substring match on function name)"],
    limit: Annotated[int, "Max results"] = 20,
) -> str:
    """Search for functions by name substring."""

    results = []
    q = query.lower()
    for ea in idautils.Functions():
        name = ida_name.get_name(ea)
        if q in name.lower():
            results.append(f"  0x{ea:x}  {name}")
            if len(results) >= limit:
                break

    if not results:
        return f"No functions matching '{query}'"
    return f"Found {len(results)} function(s):\n" + "\n".join(results)


@tool(category="functions")
def get_function_name(
    address: Annotated[str, "Function address (hex string)"],
) -> str:
    """Get the current name of a function at an address.

    Returns a raw name string suitable for mutation pre-state capture.
    """
    ea = parse_addr(address)
    func = ida_funcs.get_func(ea)
    if func is None:
        return ""
    return ida_name.get_name(func.start_ea) or ""
