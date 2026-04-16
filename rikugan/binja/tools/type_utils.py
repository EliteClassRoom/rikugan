"""Type parsing and definition helpers for Binary Ninja."""

from __future__ import annotations

from typing import Any

from ...core.errors import ToolError
from ...core.logging import log_debug
from .compat import get_bn_module


def parse_type_string(bv: Any, type_src: str) -> tuple[Any, str]:
    """Parse C type text and return (type_obj, parsed_name)."""
    parse_fn = getattr(bv, "parse_type_string", None)
    if callable(parse_fn):
        try:
            res = parse_fn(type_src)
            if isinstance(res, tuple) and len(res) >= 2:
                return res[0], str(res[1] or "")
            # Some versions return object with type/name attributes.
            t = getattr(res, "type", None)
            n = getattr(res, "name", "")
            if t is not None:
                return t, str(n or "")
        except Exception as e:
            log_debug(f"bv.parse_type_string failed for {type_src!r}: {e}")

    bn = get_bn_module()
    parse_global = getattr(bn, "parse_type_string", None)
    if callable(parse_global):
        try:
            res = parse_global(type_src, getattr(bv, "platform", None))
            if isinstance(res, tuple) and len(res) >= 2:
                return res[0], str(res[1] or "")
        except Exception as e:
            log_debug(f"bn.parse_type_string failed for {type_src!r}: {e}")

    raise ToolError(f"Failed to parse type string: {type_src}")


def define_user_type(bv: Any, name: str, t: Any) -> bool:
    for meth_name in ("define_user_type", "defineUserType"):
        meth = getattr(bv, meth_name, None)
        if callable(meth):
            try:
                meth(name, t)
                return True
            except Exception as e:
                log_debug(f"define_user_type {meth_name}({name!r}) failed: {e}")
                continue
    return False
