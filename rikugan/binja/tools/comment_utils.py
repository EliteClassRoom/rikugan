"""Comment read/write helpers for Binary Ninja."""

from __future__ import annotations

from typing import Any

from ...core.logging import log_debug


def get_comment_at(bv: Any, ea: int) -> str:
    ea = int(ea)
    for name in ("get_comment_at", "getCommentAt"):
        meth = getattr(bv, name, None)
        if callable(meth):
            try:
                c = meth(ea)
                if c:
                    return str(c)
            except Exception as e:
                log_debug(f"get_comment_at {name} failed at 0x{ea:x}: {e}")
                continue
    return ""


def set_comment_at(bv: Any, ea: int, comment: str) -> bool:
    ea = int(ea)
    for name in ("set_comment_at", "setCommentAt"):
        meth = getattr(bv, name, None)
        if callable(meth):
            try:
                meth(ea, comment)
                return True
            except Exception as e:
                log_debug(f"set_comment_at {name} failed at 0x{ea:x}: {e}")
                continue
    return False
