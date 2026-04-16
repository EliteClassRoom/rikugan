"""Binary Ninja version-compatibility layer and core view helpers."""

from __future__ import annotations

import inspect
from typing import Any

from ...core.errors import ToolError
from ...core.host import (
    get_binary_ninja_view,
    get_current_address,
    navigate_to,
    set_current_address,
)
from ...core.logging import log_debug


def get_bn_module() -> Any:
    try:
        import binaryninja as bn  # type: ignore[import-not-found]
    except Exception as e:  # pragma: no cover - runtime guarded by host detection
        raise ToolError(f"Binary Ninja API unavailable: {e}") from e
    return bn


def require_bv() -> Any:
    bv = get_binary_ninja_view()
    if bv is None:
        raise ToolError(
            "No active BinaryView. Open a binary in Binary Ninja and invoke Rikugan from that view.",
        )
    return bv


def current_ea_or_default(default: int = 0) -> int:
    ea = get_current_address()
    return int(ea) if ea is not None else int(default)


def parse_addr_like(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def call_compat(obj: Any, *method_names: str, default: Any = None, **kwargs: Any) -> Any:
    """Call first existing method name on *obj*, returning default on failure."""
    for name in method_names:
        meth = getattr(obj, name, None)
        if not callable(meth):
            continue
        try:
            return meth(**kwargs)
        except TypeError:
            # Some BN APIs are positional-only across versions.
            if kwargs:
                try:
                    return meth(*kwargs.values())
                except Exception as _e:
                    log_debug(f"call_compat positional fallback failed for {name}: {_e}")
                    continue
        except Exception as _e:
            log_debug(f"call_compat failed for {name}: {_e}")
            continue
    return default


def navigate(ea: int) -> bool:
    ok = navigate_to(int(ea))
    if ok:
        set_current_address(int(ea))
    return ok


def update_analysis_and_wait(bv: Any, func: Any = None) -> None:
    # Force reanalysis of a specific function first (triggers redecompilation)
    if func is not None:
        reanalyze = getattr(func, "reanalyze", None)
        if callable(reanalyze):
            try:
                reanalyze()
            except Exception as e:
                log_debug(f"func.reanalyze() failed: {e}")
    for name in ("update_analysis_and_wait", "updateAnalysisAndWait"):
        meth = getattr(bv, name, None)
        if callable(meth):
            try:
                meth()
                return
            except Exception as e:
                log_debug(f"update_analysis_and_wait {name} failed: {e}")
                continue


def read_bytes_safe(bv: Any, ea: int, size: int) -> bytes:
    """Read `size` bytes from `bv` at `ea`, zero-padding on short reads."""
    data = b""
    read = getattr(bv, "read", None)
    if callable(read):
        try:
            data = bytes(read(ea, size) or b"")
        except Exception:
            data = b""
    if len(data) < size:
        data += b"\x00" * (size - len(data))
    return data


def py_signature_accepts(func: Any, argc: int) -> bool:
    try:
        sig = inspect.signature(func)
    except Exception:
        return False
    params = list(sig.parameters.values())
    required = [
        p for p in params if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    return len(required) <= argc <= len(params)
