"""IL-level tooling for Binary Ninja."""

from __future__ import annotations

from typing import Annotated, Any

from ...core.logging import log_debug
from ...tools.base import tool
from .compat import parse_addr_like, require_bv, update_analysis_and_wait
from .decompiler import get_pseudocode
from .disasm_utils import get_instruction_len
from .fn_utils import get_function_at, get_function_name

_IL_LEVELS = {
    # Primary IL level names
    "llil": "llil",
    "mlil": "mlil",
    "hlil": "hlil",
    # Backward-compat MMAT_* aliases
    "MMAT_GENERATED": "llil",
    "MMAT_PREOPTIMIZED": "llil",
    "MMAT_LOCOPT": "mlil",
    "MMAT_CALLS": "mlil",
    "MMAT_GLBOPT1": "mlil",
    "MMAT_GLBOPT2": "mlil",
    "MMAT_GLBOPT3": "mlil",
    "MMAT_LVARS": "hlil",
}


def _parse_level(value: str) -> str:
    raw = str(value).strip()
    upper = raw.upper()
    if upper in _IL_LEVELS:
        return upper
    lower = raw.lower()
    if lower in _IL_LEVELS:
        return lower
    return "hlil"


def _il_for(func: Any, level_name: str):
    level = _IL_LEVELS.get(level_name, "hlil")
    for attr in (level, "hlil", "mlil", "llil"):
        try:
            il = getattr(func, attr)
            if il is not None:
                return il
        except Exception as e:
            log_debug(f"_il_for: attribute {attr!r} failed: {e}")
            continue
    return None


def _render_il(il: Any) -> str:
    insns = getattr(il, "instructions", None)
    if insns is None:
        text = str(il)
        return text if text else "(no IL output)"
    lines = []
    for i, ins in enumerate(list(insns)):
        addr = getattr(ins, "address", None)
        pfx = f"[{i:4d}] "
        if isinstance(addr, int):
            pfx += f"0x{addr:08x}  "
        lines.append(pfx + str(ins))
    return "\n".join(lines) if lines else "(no IL output)"


def _patch_nop(bv: Any, ea: int) -> bool:
    # Prefer host-native NOP conversion when available.
    for meth_name in ("convert_to_nop", "convertToNop"):
        meth = getattr(bv, meth_name, None)
        if callable(meth):
            try:
                rc = meth(ea)
                if rc is None or bool(rc):
                    return True
            except Exception as e:
                log_debug(f"_patch_nop {meth_name} failed at 0x{ea:x}: {e}")
                continue

    size = max(1, get_instruction_len(bv, ea))
    nop_bytes = None
    arch = getattr(bv, "arch", None)
    if arch is not None:
        asm = getattr(arch, "assemble", None)
        if callable(asm):
            try:
                b = asm("nop", ea)
                if b:
                    nop_bytes = bytes(b)
            except Exception as e:
                log_debug(f"_patch_nop arch.assemble failed at 0x{ea:x}: {e}")
                nop_bytes = None
    if not nop_bytes:
        nop_bytes = b"\x90"
    data = (nop_bytes * ((size + len(nop_bytes) - 1) // len(nop_bytes)))[:size]

    write = getattr(bv, "write", None)
    if callable(write):
        try:
            write(ea, data)
            return True
        except Exception as e:
            log_debug(f"_patch_nop bv.write failed at 0x{ea:x}: {e}")
            return False
    return False


@tool(category="il", requires_decompiler=True)
def get_il(
    address: Annotated[str, "Function address (hex string, e.g. '0x401000')"],
    level: Annotated[str, "IL level: 'llil', 'mlil', or 'hlil'"] = "hlil",
) -> str:
    """Get function IL at a given level (LLIL/MLIL/HLIL)."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    lvl = _parse_level(level)
    il = _il_for(func, lvl)
    if il is None:
        return f"IL not available for {get_function_name(func)} at {lvl}"

    start = int(getattr(func, "start", ea))
    end = int(getattr(func, "highest_address", start))
    resolved = _IL_LEVELS.get(lvl, lvl)
    header = f"=== IL for {get_function_name(func)} at {resolved} ===\nFunction: 0x{start:x} - 0x{end:x}\n"
    return header + _render_il(il)


@tool(category="il", requires_decompiler=True)
def get_il_block(
    address: Annotated[str, "Function address (hex string)"],
    block_index: Annotated[int, "Block index (0-based)"],
    level: Annotated[str, "IL level: 'llil', 'mlil', or 'hlil'"] = "hlil",
) -> str:
    """Get detailed IL for a single basic block."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    lvl = _parse_level(level)
    il = _il_for(func, lvl)
    if il is None:
        return "IL not available for this function"

    blocks = list(getattr(il, "basic_blocks", []) or [])
    if block_index < 0 or block_index >= len(blocks):
        return f"Block index {block_index} out of range [0, {max(0, len(blocks) - 1)}]"

    blk = blocks[block_index]
    resolved = _IL_LEVELS.get(lvl, lvl)
    lines = [
        f"=== Block {block_index} of {get_function_name(func)} at {resolved} ===",
        "",
    ]
    start = getattr(blk, "start", None)
    end = getattr(blk, "end", None)
    if isinstance(start, int) and isinstance(end, int):
        lines.append(f"Range: 0x{start:x} .. 0x{end:x}")

    # Try to iterate IL instructions in this block using index spans.
    insns = list(getattr(il, "instructions", []) or [])
    if isinstance(start, int) and isinstance(end, int) and insns:
        block_ins = insns[start:end] if 0 <= start < len(insns) else []
    else:
        block_ins = insns

    lines.append("")
    lines.append("Instructions:")
    for i, ins in enumerate(block_ins):
        addr = getattr(ins, "address", None)
        ea_str = f"0x{addr:08x}" if isinstance(addr, int) else "--------"
        lines.append(f"  [{i:3d}] {ea_str}  {ins}")
    lines.append(f"\nTotal: {len(block_ins)} instructions")
    return "\n".join(lines)


@tool(category="il", requires_decompiler=True, mutating=True)
def nop_instructions(
    func_address: Annotated[str, "Address of the function to patch"],
    instruction_addresses: Annotated[
        str,
        "Comma-separated hex addresses of instructions to NOP (e.g. '0x401004,0x401008,0x40100c')",
    ],
) -> str:
    """Patch selected instructions to NOP bytes and update analysis."""
    bv = require_bv()
    ea = parse_addr_like(func_address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    raw_addrs = [s.strip() for s in instruction_addresses.split(",") if s.strip()]
    if not raw_addrs:
        return "No instruction addresses provided."

    patched = 0
    failed = []
    for raw in raw_addrs:
        try:
            target = parse_addr_like(raw)
        except Exception:
            failed.append(raw)
            continue
        if _patch_nop(bv, target):
            patched += 1
        else:
            failed.append(raw)

    update_analysis_and_wait(bv, func)

    summary = f"Patched {patched}/{len(raw_addrs)} instruction(s) with NOP."
    if failed:
        summary += f" Failed: {', '.join(failed)}."
    return summary


@tool(category="il", requires_decompiler=True)
def redecompile_function(
    address: Annotated[str, "Function address to redecompile (hex string)"],
) -> str:
    """Refresh analysis and return current pseudocode for a function."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    update_analysis_and_wait(bv, func)
    start = int(getattr(func, "start", ea))
    pseudocode = get_pseudocode(f"0x{start:x}", with_line_numbers=False)
    return f"=== Redecompiled {get_function_name(func)} ===\n\n{pseudocode}"


# Backward-compat aliases
get_microcode = get_il
get_microcode_block = get_il_block
nop_microcode = nop_instructions
