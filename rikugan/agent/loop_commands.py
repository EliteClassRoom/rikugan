"""Slash-command handlers for the agent loop.

These generators were extracted verbatim from ``rikugan.agent.loop`` so
that ``AgentLoop`` only contains the turn orchestration logic, while
standalone commands (/goal, /memory, /undo, /mcp, /doctor) live here.

Each function receives the :class:`AgentLoop` instance as ``loop`` and
yields :class:`TurnEvent` objects exactly like the original methods did.
No command logic was changed.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import TYPE_CHECKING

from ..core.errors import ToolError
from ..core.logging import log_error, log_info
from ..core.sanitize import strip_injection_markers
from .turn import TurnEvent

if TYPE_CHECKING:
    from .loop import AgentLoop


_MAX_GOAL_CHARS = 1000


def _handle_memory_command(loop: AgentLoop) -> Generator[TurnEvent, None, None]:
    """Show current RIKUGAN.md contents in chat."""
    idb_dir = ""
    if loop.session.idb_path:
        idb_dir = os.path.dirname(loop.session.idb_path)
    if not idb_dir:
        yield TurnEvent.text_done("No IDB path set — persistent memory is not available.")
        return

    md_path = os.path.join(idb_dir, "RIKUGAN.md")
    if not os.path.isfile(md_path):
        yield TurnEvent.text_done(
            f"No persistent memory file found.\n\n"
            f"A `RIKUGAN.md` file will be created in `{idb_dir}` "
            f"when the agent first uses `save_memory`."
        )
        return

    try:
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            yield TurnEvent.text_done("RIKUGAN.md exists but is empty.")
        else:
            yield TurnEvent.text_done(f"**Persistent Memory** (`{md_path}`):\n\n{content}")
    except OSError as e:
        yield TurnEvent.error_event(f"Failed to read RIKUGAN.md: {e}")


def _handle_goal_command(loop: AgentLoop, raw_goal: str) -> Generator[TurnEvent, None, None]:
    goal = strip_injection_markers(raw_goal.strip())
    if not goal:
        current = loop.session.metadata.get("active_goal", "").strip()
        if current:
            yield TurnEvent.text_done(f"**Active Goal**\n\n{current}")
        else:
            yield TurnEvent.text_done("No active goal set. Use `/goal <objective>` to set one.")
        return

    if goal.lower() in {"clear", "reset", "unset"}:
        loop.session.metadata.pop("active_goal", None)
        yield TurnEvent.text_done("Active goal cleared.")
        return

    if len(goal) > _MAX_GOAL_CHARS:
        goal = goal[:_MAX_GOAL_CHARS].rstrip() + "..."

    loop.session.metadata["active_goal"] = goal
    yield TurnEvent.text_done(f"Active goal set:\n\n{goal}")


def _handle_undo_command(loop: AgentLoop, raw_cmd: str) -> Generator[TurnEvent, None, None]:
    """Undo the last N mutations."""
    # Parse count from "/undo" or "/undo N"
    parts = raw_cmd.strip().split()
    count = 1
    if len(parts) > 1:
        try:
            count = int(parts[1])
        except ValueError:
            yield TurnEvent.error_event(f"Invalid undo count: {parts[1]}. Usage: /undo [N]")
            return

    if not loop._mutation_log:
        yield TurnEvent.text_done("Nothing to undo — mutation log is empty.")
        return

    count = min(count, len(loop._mutation_log))
    undone = 0
    errors = []
    for _ in range(count):
        record = loop._mutation_log.pop()
        if not record.reversible:
            errors.append(f"Cannot undo: {record.description} (not reversible)")
            continue
        try:
            loop.tools.execute(record.reverse_tool, record.reverse_arguments)
            undone += 1
            log_info(f"Undo: {record.description}")
        except ToolError as e:
            errors.append(f"Failed to undo {record.description}: {e}")
            log_error(f"Undo failed: {record.description}: {e}")

    parts_out = []
    if undone:
        parts_out.append(f"Undid {undone} mutation(s).")
    if errors:
        parts_out.append("\n".join(errors))
    yield TurnEvent.text_done("\n".join(parts_out) if parts_out else "Nothing undone.")


def _handle_mcp_command(loop: AgentLoop) -> Generator[TurnEvent, None, None]:
    """Show MCP server health and status."""
    # Access the MCP manager via the tool registry's registered tools
    # We check for MCP-prefixed tools and try to reach the manager
    mcp_tools = [n for n in loop.tools.list_names() if n.startswith("mcp_")]
    if not mcp_tools:
        yield TurnEvent.text_done("No MCP servers configured or connected.")
        return

    lines = ["**MCP Server Status**\n"]
    # Group tools by server prefix
    servers: dict[str, list[str]] = {}
    for name in mcp_tools:
        # MCP tools are named mcp_<server>_<tool>
        parts = name.split("_", 2)
        server = parts[1] if len(parts) >= 3 else "unknown"
        servers.setdefault(server, []).append(name)

    for server, tools in sorted(servers.items()):
        lines.append(f"- **{server}**: {len(tools)} tools registered")

    lines.append(f"\n**Total**: {len(mcp_tools)} MCP tools available")
    yield TurnEvent.text_done("\n".join(lines))


def _handle_doctor_command(loop: AgentLoop) -> Generator[TurnEvent, None, None]:
    """Diagnose common setup issues."""
    issues: list[str] = []
    ok: list[str] = []

    # Check provider
    if loop.provider:
        ok.append(f"Provider: {loop.config.provider.name} ({loop.config.provider.model})")
    else:
        issues.append("No LLM provider configured")

    # Check API key
    if loop.config.provider.api_key:
        ok.append("API key: configured")
    else:
        env_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if env_key:
            ok.append("API key: from environment variable")
        else:
            issues.append("No API key configured (set in config or environment)")

    # Check tools
    tool_count = len(loop.tools.list_names())
    if tool_count > 0:
        ok.append(f"Tools: {tool_count} registered")
    else:
        issues.append("No tools registered — check plugin initialization")

    # Check skills
    if loop.skills:
        slugs = loop.skills.list_slugs()
        ok.append(f"Skills: {len(slugs)} loaded")
    else:
        issues.append("No skill registry — skills won't be available")

    # Check context window
    from .loop import _MIN_CONTEXT_WINDOW_TOKENS

    ctx = loop.config.provider.context_window
    if ctx >= _MIN_CONTEXT_WINDOW_TOKENS:
        ok.append(f"Context window: {ctx:,} tokens")
    else:
        issues.append(f"Context window very small: {ctx} tokens")

    # Check config validation
    config_errors = loop.config.validate()
    if config_errors:
        issues.extend(f"Config: {e}" for e in config_errors)
    else:
        ok.append("Config: valid")

    # Check IDB path for persistent memory
    if loop.session.idb_path:
        ok.append(f"IDB: {loop.session.idb_path}")
    else:
        issues.append("No IDB path — persistent memory disabled")

    # Surface missing optional Python deps so users know which
    # provider features are unavailable. We don't treat these as
    # "issues" because the plugin can still run; they're warnings.
    try:
        from ...core.dependencies import get_missing_dependency_warnings

        for warning in get_missing_dependency_warnings():
            issues.append(warning)
    except Exception:
        pass

    # Format output
    lines = ["**Rikugan Doctor**\n"]
    if ok:
        lines.append("**OK:**")
        for item in ok:
            lines.append(f"  - {item}")
    if issues:
        lines.append("\n**Issues:**")
        for item in issues:
            lines.append(f"  - {item}")
    else:
        lines.append("\nNo issues found.")
    yield TurnEvent.text_done("\n".join(lines))
