"""IL transformation tools — write operations for Binary Ninja IL modification."""

from __future__ import annotations

from typing import Annotated, Any

from ...core.logging import log_debug, log_error
from ...tools.base import tool
from ...tools.script_guard import safe_builtins
from .compat import get_bn_module, parse_addr_like, require_bv, update_analysis_and_wait
from .fn_utils import get_function_at, get_function_name

# ---------------------------------------------------------------------------
# Internal state for workflow management
# ---------------------------------------------------------------------------

_installed_workflows: dict[str, dict[str, Any]] = {}
"""name -> {"workflow": ..., "activity": ..., "description": ...}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_il_func(func: Any, level: str = "mlil") -> Any:
    """Get IL function at the requested level."""
    for attr in (level, "mlil", "hlil", "llil"):
        il = getattr(func, attr, None)
        if il is not None:
            return il
    return None


def _finalize_il(il_func: Any) -> None:
    """Call finalize() and generate_ssa_form() on an IL function."""
    finalize = getattr(il_func, "finalize", None)
    if callable(finalize):
        try:
            finalize()
        except Exception as e:
            log_debug(f"finalize() failed: {e}")

    gen_ssa = getattr(il_func, "generate_ssa_form", None)
    if callable(gen_ssa):
        try:
            gen_ssa()
        except Exception as e:
            log_debug(f"generate_ssa_form() failed: {e}")


def _get_instr_at_index(il_func: Any, index: int) -> Any:
    """Get an IL instruction by its expression index."""
    try:
        return il_func[index]
    except (IndexError, KeyError, TypeError):
        return None


def _replace_expr(il_func: Any, old_expr: Any, new_expr: Any) -> bool:
    """Replace an IL expression using replace_expr."""
    replace = getattr(il_func, "replace_expr", None)
    if not callable(replace):
        return False
    try:
        replace(old_expr, new_expr)
        return True
    except Exception as e:
        log_debug(f"replace_expr failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(category="il", requires_decompiler=True, mutating=True)
def il_replace_expr(
    address: Annotated[str, "Function address (hex string)"],
    expr_index: Annotated[int, "IL expression index to replace"],
    replacement_type: Annotated[
        str,
        "Replacement type: 'const' (constant value), 'nop', or 'copy_from' (copy from another index)",
    ],
    value: Annotated[int, "Value for 'const' type, or source index for 'copy_from'"] = 0,
    size: Annotated[int, "Size in bytes for the replacement expression"] = 0,
    level: Annotated[str, "IL level: 'llil' or 'mlil'"] = "mlil",
) -> str:
    """Replace an IL expression at a given index with a new expression."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    il_func = _get_il_func(func, level)
    if il_func is None:
        return f"IL not available for {get_function_name(func)} at {level}"

    old_expr = _get_instr_at_index(il_func, expr_index)
    if old_expr is None:
        return f"No expression at index {expr_index}"

    expr_size = size if size > 0 else getattr(old_expr, "size", 4)

    if replacement_type == "const":
        const_fn = getattr(il_func, "const", None)
        if not callable(const_fn):
            return "IL function does not support const() expression creation"
        new_expr = const_fn(expr_size, value)
    elif replacement_type == "nop":
        nop_fn = getattr(il_func, "nop", None)
        if not callable(nop_fn):
            return "IL function does not support nop() expression creation"
        new_expr = nop_fn()
    elif replacement_type == "copy_from":
        src_expr = _get_instr_at_index(il_func, value)
        if src_expr is None:
            return f"No expression at source index {value}"
        copy_fn = getattr(src_expr, "copy_to", None)
        if callable(copy_fn):
            new_expr = copy_fn(il_func)
        else:
            return "Expression does not support copy_to()"
    else:
        return f"Unknown replacement type: {replacement_type}. Use 'const', 'nop', or 'copy_from'."

    old_str = str(old_expr)[:80]
    if not _replace_expr(il_func, old_expr, new_expr):
        return f"Failed to replace expression at index {expr_index}: {old_str}"

    _finalize_il(il_func)
    update_analysis_and_wait(bv, func)

    return f"Replaced expression at index {expr_index}: {old_str} -> {replacement_type}({value})"


@tool(category="il", requires_decompiler=True, mutating=True)
def il_set_condition(
    address: Annotated[str, "Function address (hex string)"],
    condition_address: Annotated[str, "Address of the conditional branch (hex string)"],
    force: Annotated[str, "'true' or 'false' — force the condition to this value"],
    level: Annotated[str, "IL level: 'llil' or 'mlil'"] = "mlil",
) -> str:
    """Force a conditional branch true/false by replacing the condition expr with a const."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    cond_ea = parse_addr_like(condition_address)
    il_func = _get_il_func(func, level)
    if il_func is None:
        return f"IL not available for {get_function_name(func)} at {level}"

    # Find the IF instruction at the given address
    instructions = list(getattr(il_func, "instructions", []) or [])
    target_inst = None
    for inst in instructions:
        inst_addr = getattr(inst, "address", None)
        if inst_addr is not None and int(inst_addr) == cond_ea:
            op = getattr(inst, "operation", None)
            op_name = getattr(op, "name", "") if op else ""
            if "IF" in op_name:
                target_inst = inst
                break

    if target_inst is None:
        return f"No conditional branch found at 0x{cond_ea:x}"

    condition = getattr(target_inst, "condition", None)
    if condition is None:
        return f"Instruction at 0x{cond_ea:x} has no condition expression"

    force_val = force.strip().lower()
    if force_val not in ("true", "false"):
        return "force must be 'true' or 'false'"

    const_val = 1 if force_val == "true" else 0
    cond_size = getattr(condition, "size", 1)

    const_fn = getattr(il_func, "const", None)
    if not callable(const_fn):
        return "IL function does not support const() expression creation"

    new_expr = const_fn(cond_size, const_val)
    old_str = str(condition)[:80]

    if not _replace_expr(il_func, condition, new_expr):
        return f"Failed to replace condition at 0x{cond_ea:x}: {old_str}"

    _finalize_il(il_func)
    update_analysis_and_wait(bv, func)

    return f"Forced condition at 0x{cond_ea:x} to {force_val}: {old_str} -> const({const_val})"


@tool(category="il", requires_decompiler=True, mutating=True)
def il_nop_expr(
    address: Annotated[str, "Function address (hex string)"],
    expr_index: Annotated[int, "IL expression index to NOP"],
    level: Annotated[str, "IL level: 'llil' or 'mlil'"] = "mlil",
) -> str:
    """Replace an IL expression with a NOP at IL level."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    il_func = _get_il_func(func, level)
    if il_func is None:
        return f"IL not available for {get_function_name(func)} at {level}"

    old_expr = _get_instr_at_index(il_func, expr_index)
    if old_expr is None:
        return f"No expression at index {expr_index}"

    nop_fn = getattr(il_func, "nop", None)
    if not callable(nop_fn):
        return "IL function does not support nop() expression creation"

    old_str = str(old_expr)[:80]
    new_expr = nop_fn()

    if not _replace_expr(il_func, old_expr, new_expr):
        return f"Failed to NOP expression at index {expr_index}: {old_str}"

    _finalize_il(il_func)
    update_analysis_and_wait(bv, func)

    return f"NOPed expression at index {expr_index}: {old_str}"


@tool(category="il", requires_decompiler=True, mutating=True)
def il_remove_block(
    address: Annotated[str, "Function address (hex string)"],
    block_index: Annotated[int, "Block index to remove (0-based)"],
    level: Annotated[str, "IL level: 'llil' or 'mlil'"] = "mlil",
) -> str:
    """Remove a basic block by NOPing all its instructions."""
    bv = require_bv()
    ea = parse_addr_like(address)
    func = get_function_at(bv, ea)
    if func is None:
        return f"No function at 0x{ea:x}"

    il_func = _get_il_func(func, level)
    if il_func is None:
        return f"IL not available for {get_function_name(func)} at {level}"

    blocks = list(getattr(il_func, "basic_blocks", []) or [])
    if block_index < 0 or block_index >= len(blocks):
        return f"Block index {block_index} out of range [0, {len(blocks) - 1}]"

    block = blocks[block_index]
    block_start = int(getattr(block, "start", 0))
    block_end = int(getattr(block, "end", block_start))

    nop_fn = getattr(il_func, "nop", None)
    if not callable(nop_fn):
        return "IL function does not support nop() expression creation"

    # NOP all instructions in the block
    instructions = list(getattr(il_func, "instructions", []) or [])
    nopped = 0
    for inst in instructions:
        idx = getattr(inst, "instr_index", None) or getattr(inst, "expr_index", None)
        addr = getattr(inst, "address", 0)

        # Check if instruction belongs to this block by index range
        if isinstance(idx, int) and block_start <= idx < block_end:
            new_expr = nop_fn()
            if _replace_expr(il_func, inst, new_expr):
                nopped += 1
        elif isinstance(addr, int) and block_start <= addr < block_end:
            # Fallback: match by address
            new_expr = nop_fn()
            if _replace_expr(il_func, inst, new_expr):
                nopped += 1

    _finalize_il(il_func)
    update_analysis_and_wait(bv, func)

    return f"Removed block {block_index} (0x{block_start:x}-0x{block_end:x}): NOPed {nopped} instructions"


@tool(category="il", requires_decompiler=True, mutating=True)
def patch_branch(
    address: Annotated[str, "Address of the conditional branch instruction (hex string)"],
    action: Annotated[str, "Action: 'force_true', 'force_false', 'invert', or 'unconditional'"],
) -> str:
    """Force conditional branch at byte level (force_true/false/invert/unconditional)."""
    bv = require_bv()
    ea = parse_addr_like(address)

    # Read the instruction bytes
    arch = getattr(bv, "arch", None)
    if arch is None:
        return "Architecture not available"

    arch_name = str(getattr(arch, "name", "")).lower()

    # Get instruction length
    get_len = getattr(bv, "get_instruction_length", None)
    if callable(get_len):
        try:
            insn_len = int(get_len(ea))
        except Exception:
            insn_len = 0
    else:
        insn_len = 0

    if insn_len == 0:
        return f"Cannot determine instruction length at 0x{ea:x}"

    orig_bytes = bv.read(ea, insn_len)
    if not orig_bytes:
        return f"Cannot read bytes at 0x{ea:x}"

    action = action.strip().lower()
    new_bytes = None

    if "x86" in arch_name or "x86_64" in arch_name:
        new_bytes = _patch_x86_branch(orig_bytes, action, insn_len)
    else:
        return f"Branch patching not implemented for architecture: {arch_name}. Use il_set_condition for IL-level modification instead."

    if new_bytes is None:
        return f"Cannot patch instruction at 0x{ea:x} with action '{action}': unsupported opcode 0x{orig_bytes[0]:02x}"

    # Write the patched bytes
    write = getattr(bv, "write", None)
    if not callable(write):
        return "BinaryView.write() not available"

    try:
        write(ea, new_bytes)
    except Exception as e:
        return f"Failed to write patched bytes at 0x{ea:x}: {e}"

    func = get_function_at(bv, ea)
    update_analysis_and_wait(bv, func)

    orig_hex = " ".join(f"{b:02x}" for b in orig_bytes)
    new_hex = " ".join(f"{b:02x}" for b in new_bytes)
    return f"Patched branch at 0x{ea:x}: {orig_hex} -> {new_hex} ({action})"


def _patch_x86_branch(orig: bytes, action: str, length: int) -> bytes | None:
    """Patch x86/x64 conditional branch bytes."""
    opcode = orig[0]

    # Short conditional jumps: 0x70-0x7F (Jcc rel8)
    if 0x70 <= opcode <= 0x7F:
        if action == "force_true":
            # Replace with JMP rel8 (0xEB)
            return bytes([0xEB]) + orig[1:]
        elif action == "force_false":
            # Replace with NOP sled
            return b"\x90" * length
        elif action == "invert":
            # Flip the condition bit (bit 0)
            return bytes([opcode ^ 0x01]) + orig[1:]
        elif action == "unconditional":
            return bytes([0xEB]) + orig[1:]

    # Near conditional jumps: 0x0F 0x80-0x8F (Jcc rel32)
    if opcode == 0x0F and length >= 2 and 0x80 <= orig[1] <= 0x8F:
        if action == "force_true":
            # Replace with JMP rel32 (0xE9) + adjust offset
            # 0x0F 0x8x rel32 -> 0xE9 rel32 + NOP
            return bytes([0xE9]) + orig[2:6] + b"\x90"
        elif action == "force_false":
            return b"\x90" * length
        elif action == "invert":
            return bytes([0x0F, orig[1] ^ 0x01]) + orig[2:]
        elif action == "unconditional":
            return bytes([0xE9]) + orig[2:6] + b"\x90"

    return None


@tool(category="il", requires_decompiler=True, mutating=True)
def write_bytes(
    address: Annotated[str, "Target address (hex string)"],
    hex_bytes: Annotated[str, "Hex byte string to write (e.g. '90 90 90' or '909090')"],
) -> str:
    """Write arbitrary hex bytes + re-analysis. Low-level escape hatch."""
    bv = require_bv()
    ea = parse_addr_like(address)

    # Parse hex bytes
    cleaned = hex_bytes.replace(" ", "").replace(",", "")
    if len(cleaned) % 2 != 0:
        return f"Invalid hex string: odd length ({len(cleaned)})"

    try:
        data = bytes.fromhex(cleaned)
    except ValueError as e:
        return f"Invalid hex string: {e}"

    if not data:
        return "No bytes to write"

    # Read original bytes for reporting
    orig = bv.read(ea, len(data))
    orig_hex = " ".join(f"{b:02x}" for b in orig) if orig else "(unreadable)"

    write = getattr(bv, "write", None)
    if not callable(write):
        return "BinaryView.write() not available"

    try:
        write(ea, data)
    except Exception as e:
        return f"Failed to write {len(data)} bytes at 0x{ea:x}: {e}"

    func = get_function_at(bv, ea)
    update_analysis_and_wait(bv, func)

    new_hex = " ".join(f"{b:02x}" for b in data)
    return f"Wrote {len(data)} bytes at 0x{ea:x}: {orig_hex} -> {new_hex}"


@tool(category="il", requires_decompiler=True, mutating=True)
def install_il_workflow(
    name: Annotated[str, "Unique name for this workflow activity"],
    description: Annotated[str, "What this transform does"],
    il_level: Annotated[str, "'llil' or 'mlil' — the IL level to modify"],
    python_code: Annotated[
        str,
        "Python code defining a transform(analysis_context, il_func) function. "
        "The function receives an AnalysisContext and the IL function to modify. "
        "Use il_func.replace_expr() for modifications, then call "
        "il_func.finalize() and il_func.generate_ssa_form().",
    ],
) -> str:
    """Register a Python function as a workflow activity at a pipeline stage.

    This hooks into BN's analysis pipeline. The transform runs automatically
    whenever a function is analyzed.
    """
    if name in _installed_workflows:
        return f"Workflow '{name}' already exists. Remove it first."

    bn = get_bn_module()

    # Validate IL level
    il_level = il_level.strip().lower()
    if il_level not in ("llil", "mlil"):
        return "il_level must be 'llil' or 'mlil'"

    # Compile the user code — exec is expected to define transform() in ns
    ns: dict = {"__builtins__": safe_builtins(), "transform": None}
    try:
        exec(python_code, ns)
    except Exception as e:
        return f"Failed to compile transform code: {e}"

    transform_fn = ns["transform"]
    if not callable(transform_fn):
        return "python_code must define a transform(analysis_context, il_func) function"

    # Get BN workflow classes
    Workflow = getattr(bn, "Workflow", None)
    Activity = getattr(bn, "Activity", None)
    if Workflow is None or Activity is None:
        return "Binary Ninja Workflow/Activity API not available (requires BN 3.x+)"

    try:
        # Clone the default workflow
        base_workflow = Workflow("core.function.metaAnalysis")
        workflow_name = f"rikugan.{name}"
        cloned = base_workflow.clone(workflow_name)

        # Determine pipeline insertion point
        if il_level == "llil":
            insert_point = "core.function.generateMediumLevelIL"
            insert_method = "insert_before"
        else:  # mlil
            insert_point = "core.function.generateMediumLevelIL"
            insert_method = "insert_after"

        # Create wrapper that extracts IL and calls user transform
        def _activity_wrapper(analysis_context):
            try:
                if il_level == "llil":
                    il_func = analysis_context.llil
                else:
                    il_func = analysis_context.mlil
                if il_func is not None:
                    transform_fn(analysis_context, il_func)
            except Exception as e:
                log_error(f"Workflow activity '{name}' failed: {e}")

        # Create and register the activity
        activity_name = f"rikugan.activity.{name}"
        activity = Activity(activity_name, action=_activity_wrapper)
        cloned.register_activity(activity)

        inserter = getattr(cloned, insert_method, None)
        if callable(inserter):
            inserter(insert_point, activity_name)
        else:
            return f"Workflow does not support {insert_method}()"

        cloned.register()

        _installed_workflows[name] = {
            "workflow": cloned,
            "workflow_name": workflow_name,
            "activity": activity,
            "activity_name": activity_name,
            "description": description,
            "il_level": il_level,
        }

        return (
            f"Workflow activity '{name}' installed successfully.\n"
            f"  IL level: {il_level}\n"
            f"  Pipeline: {insert_method.replace('_', ' ')} {insert_point}\n"
            f"  Description: {description}\n"
            f"Note: New and re-analyzed functions will use this transform. "
            f"Existing functions need re-analysis to apply."
        )

    except Exception as e:
        return f"Failed to install workflow: {e}"
