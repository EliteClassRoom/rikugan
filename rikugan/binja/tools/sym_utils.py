"""Symbol lookup and manipulation helpers for Binary Ninja."""

from __future__ import annotations

from typing import Any

from ...core.logging import log_debug
from .compat import get_bn_module
from .fn_utils import get_function_at, get_function_name


def get_symbol_at(bv: Any, ea: int) -> Any:
    ea = int(ea)
    for name in ("get_symbol_at", "getSymbolAt"):
        meth = getattr(bv, name, None)
        if callable(meth):
            try:
                sym = meth(ea)
                if sym is not None:
                    return sym
            except Exception as e:
                log_debug(f"get_symbol_at {name} failed at 0x{ea:x}: {e}")
                continue
    return None


def symbol_name(sym: Any) -> str:
    if sym is None:
        return ""
    return str(getattr(sym, "full_name", None) or getattr(sym, "short_name", None) or getattr(sym, "name", None) or "")


def resolve_name_at(bv: Any, ea: int) -> str:
    sym = get_symbol_at(bv, ea)
    if sym is not None:
        name = symbol_name(sym)
        if name:
            return name

    func = get_function_at(bv, ea)
    if func is not None:
        return get_function_name(func)
    return ""


def iter_symbols(bv: Any) -> list[Any]:
    symbols: list[Any] = []
    get_symbols = getattr(bv, "get_symbols", None)
    if callable(get_symbols):
        try:
            symbols = list(get_symbols())
        except Exception as e:
            log_debug(f"get_symbols() failed: {e}")
            symbols = []

    if not symbols:
        raw = getattr(bv, "symbols", None)
        if isinstance(raw, dict):
            for _, val in raw.items():
                if isinstance(val, list):
                    symbols.extend(val)
                else:
                    symbols.append(val)
        elif raw is not None:
            try:
                symbols = list(raw)
            except Exception as e:
                log_debug(f"iter bv.symbols failed: {e}")
                symbols = []

    return symbols


def iter_symbols_by_name(bv: Any, name: str) -> list[Any]:
    get_by_name = getattr(bv, "get_symbols_by_name", None)
    if callable(get_by_name):
        try:
            return list(get_by_name(name))
        except Exception as e:
            log_debug(f"get_symbols_by_name({name!r}) failed: {e}")
    return [s for s in iter_symbols(bv) if symbol_name(s) == name]


def symbol_type_name(sym: Any) -> str:
    t = getattr(sym, "type", None)
    if t is None:
        return ""
    n = getattr(t, "name", None)
    if n:
        return str(n)
    return str(t)


def is_import_symbol(sym: Any) -> bool:
    tname = symbol_type_name(sym).lower()
    return "import" in tname or "external" in tname


def is_export_symbol(sym: Any) -> bool:
    tname = symbol_type_name(sym).lower()
    return "export" in tname


def symbol_address(sym: Any) -> int | None:
    for attr in ("address", "addr", "raw_name_addr"):
        v = getattr(sym, attr, None)
        if isinstance(v, int):
            return int(v)
    return None


def _build_user_symbol(bn: Any, sym_type: Any, ea: int, new_name: str) -> Any:
    symbol_cls = getattr(bn, "Symbol", None)
    if symbol_cls is None:
        return None
    try:
        return symbol_cls(sym_type, int(ea), new_name)
    except TypeError:
        # Some versions accept optional short/full names.
        try:
            return symbol_cls(sym_type, int(ea), new_name, new_name)
        except Exception as e:
            log_debug(f"Symbol constructor failed at 0x{ea:x}: {e}")
            return None


def rename_symbol_at(bv: Any, ea: int, new_name: str) -> bool:
    bn = get_bn_module()
    ea = int(ea)
    sym = get_symbol_at(bv, ea)
    sym_type = None
    if sym is not None:
        sym_type = getattr(sym, "type", None)
    if sym_type is None:
        st = getattr(bn, "SymbolType", None)
        sym_type = getattr(st, "FunctionSymbol", None) if st is not None else None

    new_sym = _build_user_symbol(bn, sym_type, ea, new_name)
    if new_sym is None:
        return False

    for name in ("define_user_symbol", "defineUserSymbol"):
        meth = getattr(bv, name, None)
        if callable(meth):
            try:
                meth(new_sym)
                return True
            except Exception as e:
                log_debug(f"rename_symbol_at {name} failed at 0x{ea:x}: {e}")
                continue
    return False
