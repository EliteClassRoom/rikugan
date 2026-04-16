"""String listing and searching tools for Binary Ninja."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from ...core.logging import log_debug
from ...tools.base import tool
from .compat import parse_addr_like, require_bv


def _iter_strings(bv) -> Iterable[tuple[int, int, str]]:
    strings = getattr(bv, "strings", None)
    if strings is None:
        get_strings = getattr(bv, "get_strings", None)
        if callable(get_strings):
            try:
                strings = list(get_strings())
            except Exception:
                strings = []
        else:
            strings = []

    for s in list(strings or []):
        ea = int(getattr(s, "start", getattr(s, "address", 0)))
        length = int(getattr(s, "length", 0))
        value = getattr(s, "value", None)
        if value is None:
            value = getattr(s, "string", None)
        if value is None:
            value = str(s)
        yield ea, length, str(value)


@tool(category="strings")
def list_strings(
    offset: Annotated[int, "Start index"] = 0,
    limit: Annotated[int, "Max results"] = 50,
) -> str:
    """List defined strings in the binary with pagination."""
    bv = require_bv()
    strings = list(_iter_strings(bv))
    total = len(strings)
    page = strings[offset : offset + limit]
    lines = [f"Strings {offset}\u2013{offset + len(page)} of {total}:"]
    for ea, length, text in page:
        lines.append(f"  0x{ea:x}  [{length}] {text}")
    return "\n".join(lines)


@tool(category="strings")
def search_strings(
    query: Annotated[str, "Search substring (case-insensitive)"],
    limit: Annotated[int, "Max results"] = 20,
) -> str:
    """Search for strings containing the given substring."""
    bv = require_bv()
    q = query.lower()
    results = []
    for ea, length, text in _iter_strings(bv):
        if q in text.lower():
            results.append(f"  0x{ea:x}  [{length}] {text}")
            if len(results) >= limit:
                break
    if not results:
        return f"No strings matching '{query}'"
    return f"Found {len(results)} string(s):\n" + "\n".join(results)


@tool(category="strings")
def get_string_at(address: Annotated[str, "Address (hex string)"]) -> str:
    """Read the string at a specific address."""
    bv = require_bv()
    ea = parse_addr_like(address)

    get_string_at_fn = getattr(bv, "get_string_at", None)
    if callable(get_string_at_fn):
        try:
            s = get_string_at_fn(ea)
            if s is not None:
                value = getattr(s, "value", None) or getattr(s, "string", None)
                if value is not None:
                    return str(value)
        except Exception as e:
            log_debug(f"get_string_at failed at 0x{ea:x}: {e}")

    for start, _length, text in _iter_strings(bv):
        if start == ea:
            return text
    return f"No string at 0x{ea:x}"
