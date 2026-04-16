"""String listing and searching tools."""

from __future__ import annotations

import importlib
from typing import Annotated

from ...core.logging import log_debug
from ...tools.base import parse_addr, tool

try:
    idautils = importlib.import_module("idautils")
    idc = importlib.import_module("idc")
except ImportError as e:
    log_debug(f"IDA modules not available: {e}")


@tool(category="strings")
def list_strings(
    offset: Annotated[int, "Start index"] = 0,
    limit: Annotated[int, "Max results"] = 50,
) -> str:
    """List defined strings in the binary with pagination."""

    strings = list(idautils.Strings())
    total = len(strings)
    page = strings[offset : offset + limit]

    lines = [f"Strings {offset}\u2013{offset + len(page)} of {total}:"]
    for s in page:
        lines.append(f"  0x{s.ea:x}  [{s.length}] {s!s}")
    return "\n".join(lines)


@tool(category="strings")
def search_strings(
    query: Annotated[str, "Search substring (case-insensitive)"],
    limit: Annotated[int, "Max results"] = 20,
) -> str:
    """Search for strings containing the given substring."""

    results = []
    q = query.lower()
    for s in idautils.Strings():
        text = str(s)
        if q in text.lower():
            results.append(f"  0x{s.ea:x}  [{s.length}] {text}")
            if len(results) >= limit:
                break

    if not results:
        return f"No strings matching '{query}'"
    return f"Found {len(results)} string(s):\n" + "\n".join(results)


@tool(category="strings")
def get_string_at(address: Annotated[str, "Address (hex string)"]) -> str:
    """Read the string at a specific address."""

    ea = parse_addr(address)
    s = idc.get_strlit_contents(ea)
    if s is None:
        return f"No string at 0x{ea:x}"
    try:
        return s.decode("utf-8", errors="replace")
    except Exception:
        return repr(s)
