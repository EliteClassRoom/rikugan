"""Function lookup and iteration helpers for Binary Ninja."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ...core.logging import log_debug
from .compat import call_compat
from .disasm_utils import get_instruction_len


def get_function_at(bv: Any, ea: int) -> Any:
    ea = int(ea)
    f = call_compat(bv, "get_function_at", default=None, addr=ea)
    if f is not None:
        return f
    f = call_compat(bv, "get_function_at", default=None, address=ea)
    if f is not None:
        return f

    get_containing = getattr(bv, "get_functions_containing", None)
    if callable(get_containing):
        try:
            funcs = list(get_containing(ea))
            if funcs:
                return funcs[0]
        except Exception as e:
            log_debug(f"get_functions_containing failed at 0x{ea:x}: {e}")
    return None


def get_function_name(func: Any) -> str:
    name = getattr(func, "name", None)
    if name:
        return str(name)
    sym = getattr(func, "symbol", None)
    if sym is not None:
        sname = getattr(sym, "full_name", None) or getattr(sym, "name", None)
        if sname:
            return str(sname)
    start = getattr(func, "start", 0)
    return f"sub_{int(start):x}"


def get_function_end(func: Any) -> int:
    for attr in ("highest_address", "end", "highestAddress"):
        v = getattr(func, attr, None)
        if isinstance(v, int) and v >= int(getattr(func, "start", 0)):
            return int(v)

    try:
        addrs = list(iter_function_instruction_addresses(func))
        if addrs:
            return max(addrs) + 1
    except Exception as e:
        log_debug(f"iter_function_instruction_addresses failed: {e}")
    return int(getattr(func, "start", 0))


def iter_functions(bv: Any) -> list[Any]:
    funcs = list(getattr(bv, "functions", []) or [])
    try:
        funcs.sort(key=lambda f: int(getattr(f, "start", 0)))
    except Exception as e:
        log_debug(f"Function sort failed: {e}")
    return funcs


def iter_function_instruction_addresses(func: Any, max_instructions: int = 100000) -> Iterable[int]:
    count = 0
    for bb in list(getattr(func, "basic_blocks", []) or []):
        start = int(getattr(bb, "start", 0))
        end = int(getattr(bb, "end", start))
        ea = start
        while ea < end and count < max_instructions:
            yield ea
            count += 1
            # Fall back to 1-byte stepping when instruction length is unknown.
            ilen = 1
            view = getattr(func, "view", None)
            if view is not None:
                l = get_instruction_len(view, ea)
                if l > 0:
                    ilen = l
            ea += max(1, ilen)
