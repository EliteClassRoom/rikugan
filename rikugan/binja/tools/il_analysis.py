"""IL analysis tools — read-only IL inspection primitives for Binary Ninja."""

from __future__ import annotations

from typing import Annotated, Any

from ...core.logging import log_debug
from ...tools.base import tool
from .compat import parse_addr_like, require_bv
from .fn_utils import get_function_at, get_function_name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_il(func: Any, level: str = "mlil") -> Any:
    """Get IL at the requested level."""
    for attr in (level, "mlil", "hlil", "llil"):
        il = getattr(func, attr, None)
        if il is not None:
            return il
    return None


def _edge_type_name(edge: Any) -> str:
    """Get human-readable edge type."""
    etype = getattr(edge, "type", None)
    if etype is None:
        return "unknown"
    name = getattr(etype, "name", None)
    return str(name) if name else str(etype)


def _is_const_expr(expr: Any) -> tuple[bool, int | None]:
    """Check if an IL expression is a constant. Returns (is_const, value)."""
    if expr is None:
        return False, None
    op = getattr(expr, "operation", None)
    op_name = getattr(op, "name", "") if op else ""
    if "CONST" in op_name:
        val = getattr(expr, "constant", None)
        if val is None:
            val = getattr(expr, "value", None)
        if isinstance(val, int):
            return True, val
    return False, None


def _get_var_name(var: Any) -> str:
    """Get a variable's name."""
    name = getattr(var, "name", None)
    if name:
        return str(name)
    return str(var)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(category="il", requires_decompiler=True)
def get_cfg(
    address: Annotated[str, "Function address (hex string, e.g. '0x401000')"],
    level: Annotated[str, "IL level: 'llil', 'mlil', or 'hlil'"] = "mlil",
) -> str:
    """Get CFG structure: blocks, edges, dominators, back edges, loop detection."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    il = _get_il(func, level)
    if il is None:
        return f"IL not available for {get_function_name(func)} at {level}"

    blocks = list(getattr(il, "basic_blocks", []) or [])
    if not blocks:
        return "No basic blocks found"

    lines = [
        f"=== CFG for {get_function_name(func)} at {level} ===",
        f"Blocks: {len(blocks)}",
        "",
    ]

    back_edges: list[tuple[int, int]] = []
    loop_headers: set[int] = set()

    for i, block in enumerate(blocks):
        start = int(getattr(block, "start", 0))
        end = int(getattr(block, "end", start))
        insn_count = int(getattr(block, "instruction_count", end - start))

        lines.append(f"Block {i}: 0x{start:x}-0x{end:x} ({insn_count} instructions)")

        # Incoming edges
        incoming = list(getattr(block, "incoming_edges", []) or [])
        if incoming:
            for edge in incoming:
                src = getattr(edge, "source", None)
                src_start = int(getattr(src, "start", 0)) if src else 0
                etype = _edge_type_name(edge)
                is_back = getattr(edge, "back_edge", False)
                suffix = " [BACK EDGE]" if is_back else ""
                lines.append(f"  <- 0x{src_start:x} ({etype}){suffix}")
                if is_back:
                    back_edges.append((src_start, start))
                    loop_headers.add(start)

        # Outgoing edges
        outgoing = list(getattr(block, "outgoing_edges", []) or [])
        if outgoing:
            for edge in outgoing:
                tgt = getattr(edge, "target", None)
                tgt_start = int(getattr(tgt, "start", 0)) if tgt else 0
                etype = _edge_type_name(edge)
                is_back = getattr(edge, "back_edge", False)
                suffix = " [BACK EDGE]" if is_back else ""
                lines.append(f"  -> 0x{tgt_start:x} ({etype}){suffix}")
                if is_back:
                    back_edges.append((start, tgt_start))
                    loop_headers.add(tgt_start)

        # Dominators
        dominators = getattr(block, "dominators", None)
        if dominators:
            dom_addrs = sorted(int(getattr(d, "start", 0)) for d in dominators if d is not block)
            if dom_addrs:
                lines.append(f"  dominators: {', '.join(f'0x{a:x}' for a in dom_addrs)}")

        idom = getattr(block, "immediate_dominator", None)
        if idom is not None and idom is not block:
            idom_start = int(getattr(idom, "start", 0))
            lines.append(f"  idom: 0x{idom_start:x}")

        lines.append("")

    # Summary
    lines.append("--- Summary ---")
    if back_edges:
        lines.append(f"Back edges: {len(back_edges)}")
        for src, tgt in back_edges:
            lines.append(f"  0x{src:x} -> 0x{tgt:x}")
    if loop_headers:
        lines.append(f"Loop headers: {', '.join(f'0x{h:x}' for h in sorted(loop_headers))}")
    if not back_edges and not loop_headers:
        lines.append("No loops detected")

    return "\n".join(lines)


@tool(category="il", requires_decompiler=True)
def track_variable_ssa(
    address: Annotated[str, "Function address (hex string)"],
    variable_name: Annotated[str, "Variable name to track"],
    level: Annotated[str, "IL level for SSA: 'mlil' or 'hlil'"] = "mlil",
) -> str:
    """Track SSA def-use chains: all versions of a variable, constant values, where used."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    il = _get_il(func, level)
    if il is None:
        return f"IL not available for {get_function_name(func)}"

    ssa = getattr(il, "ssa_form", None)
    if ssa is None:
        return f"SSA form not available at {level} level"

    # Find the variable
    target_var = None
    all_vars = getattr(ssa, "vars", None) or getattr(il, "vars", None) or []
    for v in all_vars:
        if _get_var_name(v) == variable_name:
            target_var = v
            break

    if target_var is None:
        var_names = sorted(set(_get_var_name(v) for v in all_vars))
        msg = f"Variable '{variable_name}' not found.\n"
        msg += f"Available variables: {', '.join(var_names[:30])}"
        # Fall back to instruction scan — the variable may appear only
        # as a memory reference (e.g. -O0 stack slots)
        scan_lines: list[str] = []
        _scan_variable_uses(il, variable_name, scan_lines)
        if scan_lines:
            msg += f"\n\nInstruction scan for '{variable_name}':\n"
            msg += "\n".join(scan_lines[:30])
        return msg

    lines = [f"=== SSA tracking for '{variable_name}' in {get_function_name(func)} ==="]

    # Track each SSA version
    ssa_vars = getattr(ssa, "ssa_vars", None)
    if ssa_vars is None:
        lines.append("(SSA var enumeration not available — scanning instructions)")
        _scan_variable_uses(ssa, variable_name, lines)
        return "\n".join(lines)

    version_count = 0
    for ssa_var in ssa_vars:
        var = getattr(ssa_var, "var", ssa_var)
        if _get_var_name(var) != variable_name:
            continue

        version = getattr(ssa_var, "version", "?")
        version_count += 1
        lines.append(f"\n--- {variable_name}#{version} ---")

        # Definition
        get_def = getattr(ssa, "get_ssa_var_definition", None)
        if callable(get_def):
            try:
                defn = get_def(ssa_var)
                if defn is not None:
                    addr = getattr(defn, "address", 0)
                    lines.append(f"  Defined at 0x{addr:x}: {defn}")

                    src = getattr(defn, "src", None)
                    if src is not None:
                        is_const, val = _is_const_expr(src)
                        if is_const:
                            lines.append(f"  Constant value: {val} (0x{val:x})")
            except Exception as e:
                log_debug(f"get_ssa_var_definition failed for {ssa_var}: {e}")

        # Uses
        get_uses = getattr(ssa, "get_ssa_var_uses", None)
        if callable(get_uses):
            try:
                uses = list(get_uses(ssa_var))
                lines.append(f"  Uses ({len(uses)}):")
                for use in uses[:20]:
                    addr = getattr(use, "address", 0)
                    lines.append(f"    0x{addr:x}: {str(use)[:100]}")
                if len(uses) > 20:
                    lines.append(f"    ... and {len(uses) - 20} more")
            except Exception as e:
                log_debug(f"get_ssa_var_uses failed for {ssa_var}: {e}")

    if version_count == 0:
        lines.append("No SSA versions found — falling back to instruction scan")
        _scan_variable_uses(ssa, variable_name, lines)

    lines.append(f"\nTotal SSA versions: {version_count}")
    return "\n".join(lines)


def _scan_variable_uses(il: Any, var_name: str, lines: list[str]) -> None:
    """Scan all instructions for references to a variable name."""
    instructions = list(getattr(il, "instructions", []) or [])
    for inst in instructions:
        inst_str = str(inst)
        if var_name in inst_str:
            addr = getattr(inst, "address", 0)
            lines.append(f"  0x{addr:x}: {inst_str[:120]}")
