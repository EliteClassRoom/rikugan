"""Disassembly and instruction-level helpers for Binary Ninja."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ...core.logging import log_debug


def get_instruction_len(bv: Any, ea: int) -> int:
    ea = int(ea)
    for name in ("get_instruction_length", "getInstructionLength"):
        meth = getattr(bv, name, None)
        if callable(meth):
            try:
                l = int(meth(ea))
                if l > 0:
                    return l
            except Exception as e:
                log_debug(f"get_instruction_len {name} failed at 0x{ea:x}: {e}")
                continue

    text = get_disassembly_line(bv, ea)
    if text:
        return 1
    return 0


def get_instruction_text_tokens(bv: Any, ea: int) -> tuple[list[Any], int]:
    ea = int(ea)
    meth = getattr(bv, "get_instruction_text", None)
    if callable(meth):
        try:
            res = meth(ea)
            if isinstance(res, tuple) and len(res) == 2:
                toks, l = res
                return list(toks or []), int(l or 0)
        except Exception as e:
            log_debug(f"get_instruction_text failed at 0x{ea:x}: {e}")
    return [], 0


def render_tokens(tokens: Sequence[Any]) -> str:
    out = []
    for t in tokens:
        txt = getattr(t, "text", None)
        if txt is None:
            txt = str(t)
        out.append(str(txt))
    return "".join(out).strip()


def get_disassembly_line(bv: Any, ea: int) -> str:
    ea = int(ea)
    for name in ("get_disassembly", "getDisassembly"):
        meth = getattr(bv, name, None)
        if callable(meth):
            try:
                text = meth(ea)
                if text:
                    return str(text)
            except Exception as e:
                log_debug(f"get_disassembly_line {name} failed at 0x{ea:x}: {e}")
                continue
    toks, _ = get_instruction_text_tokens(bv, ea)
    return render_tokens(toks)
