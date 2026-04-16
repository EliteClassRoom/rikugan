"""Prompt-generating command handlers for Binary Ninja UI actions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...ui.action_handlers import (
    handle_annotate,
    handle_clean,
    handle_deobfuscate,
    handle_explain,
    handle_rename,
    handle_send_to,
    handle_suggest_types,
    handle_vuln_audit,
    handle_xref_analysis,
)


def build_context(
    bv: Any,
    ea: int,
    get_function_at: Callable[[Any, int], Any],
    get_function_name: Callable[[Any], str],
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "ea": int(ea),
        "func_ea": None,
        "func_name": None,
        "selected_text": "",
    }
    func = get_function_at(bv, ea)
    if func is not None:
        ctx["func_ea"] = int(getattr(func, "start", ea))
        ctx["func_name"] = get_function_name(func)
    return ctx


# Binary Ninja uses "IL" terminology
def handle_deobfuscate_bn(ctx: dict[str, Any]) -> str:
    return handle_deobfuscate(ctx, optimizer_term="IL")


def handle_clean_il(ctx: dict[str, Any]) -> str:
    return handle_clean(ctx, ir_term="IL")


def handle_smart_patch(ctx: dict[str, Any]) -> str:
    name = ctx["func_name"] or f"sub_{ctx['ea']:x}"
    ea = ctx["func_ea"] or ctx["ea"]
    return f"/smart-patch-binja Patch function {name} at 0x{ea:x}.\nDesired behavior: "


ACTION_DEFS: tuple[tuple[str, str, Callable[[dict[str, Any]], str], bool], ...] = (
    (
        "Send to Rikugan",
        "Send selection or address to Rikugan input",
        handle_send_to,
        False,
    ),
    ("Explain this", "Explain the current function with Rikugan", handle_explain, True),
    (
        "Rename with Rikugan",
        "Analyze and rename the current function",
        handle_rename,
        True,
    ),
    (
        "Deobfuscate with Rikugan",
        "Deobfuscate the current function",
        handle_deobfuscate_bn,
        True,
    ),
    (
        "Find vulnerabilities",
        "Audit the current function for security bugs",
        handle_vuln_audit,
        True,
    ),
    (
        "Suggest types",
        "Infer and apply types for the current function",
        handle_suggest_types,
        True,
    ),
    (
        "Annotate function",
        "Add comments to the current function",
        handle_annotate,
        True,
    ),
    ("Clean IL", "Clean IR IL for the current function", handle_clean_il, True),
    (
        "Xref analysis",
        "Deep cross-reference analysis on the current function",
        handle_xref_analysis,
        True,
    ),
    (
        "Smart Patch",
        "Modify function behavior with natural language and apply binary patches",
        handle_smart_patch,
        False,
    ),
)
