"""System prompt builder with binary context awareness."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..core.logging import log_debug
from ..core.profile import IOC_FILTER_CATEGORIES
from ..core.sanitize import quote_untrusted, sanitize_binary_context, sanitize_memory
from ..tools.catalog import format_tools_catalog as _format_tools_catalog  # re-export
from .prompts.ida import IDA_BASE_PROMPT

_BASE_PROMPT = IDA_BASE_PROMPT  # backward compat alias

if TYPE_CHECKING:
    from ..core.profile import AnalysisProfile


# Maximum number of lines to load from RIKUGAN.md
_MAX_MEMORY_LINES = 200

# Phase 4.1: persistent-memory cache.
#
# The agent loop re-builds the system prompt on every turn, so
# ``_load_persistent_memory`` runs once per LLM call. For a long session
# with no memory edits that's pure I/O waste — ``os.path.isfile``,
# ``os.stat``, and ``open(...)`` on every prompt build.
#
# Cache key: absolute path. Value: ``(mtime_ns, content_or_marker)``
# where *content_or_marker* is either the loaded text or a sentinel
# ``"<missing>"`` so we can cache the "file does not exist" answer
# without re-running ``isfile`` every turn.
#
# Invalidation is purely mtime-based: any save_memory tool write (which
# appends to ``RIKUGAN.md`` via ``loop.append_to_memory_file``) bumps
# the file's mtime, so the next prompt build sees a new mtime and
# rebuilds.  Manual edits by the user also bump mtime, so they are
# picked up automatically.
_MEMORY_CACHE: dict[str, tuple[int, str]] = {}
_MEMORY_MISSING_SENTINEL = "<missing>"


def _load_persistent_memory(idb_dir: str = "") -> str | None:
    """Load RIKUGAN.md from the IDB directory (first 200 lines).

    The file acts as persistent cross-session memory for the agent.

    Phase 4.1: results are cached by ``(path, mtime_ns)`` so back-to-back
    calls within the same session (one per LLM turn) do not re-stat /
    re-open the file when nothing has changed.
    """
    if not idb_dir:
        return None

    md_path = os.path.join(idb_dir, "RIKUGAN.md")

    try:
        st = os.stat(md_path)
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
    except OSError:
        # File missing (or unreadable) — cache the miss so we do not
        # re-stat on every prompt build.
        cached = _MEMORY_CACHE.get(md_path)
        if cached is not None and cached[0] == -1:
            return None
        _MEMORY_CACHE[md_path] = (-1, _MEMORY_MISSING_SENTINEL)
        return None

    cached = _MEMORY_CACHE.get(md_path)
    if cached is not None and cached[0] == mtime_ns:
        cached_content = cached[1]
        if cached_content == _MEMORY_MISSING_SENTINEL:
            return None
        return cached_content

    # mtime differs (or no cache) — reload from disk.
    try:
        with open(md_path, encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= _MAX_MEMORY_LINES:
                    lines.append(f"\n... (truncated at {_MAX_MEMORY_LINES} lines)")
                    break
                lines.append(line)
        content = "".join(lines).strip()
        if content:
            _MEMORY_CACHE[md_path] = (mtime_ns, content)
            log_debug(f"Loaded persistent memory from {md_path} ({len(lines)} lines)")
            return content
    except OSError as e:
        log_debug(f"Failed to load RIKUGAN.md: {e}")

    # Empty file — still cache so we don't re-read a zero-byte file.
    _MEMORY_CACHE[md_path] = (mtime_ns, "")
    return None


# Re-export so callers that still import ``format_tools_catalog`` from
# ``agent.system_prompt`` keep working. ``ToolRegistry`` now reads it
# directly from ``rikugan.tools.catalog`` to avoid the
# agent <-> tools round-trip during tool registration.
format_tools_catalog = _format_tools_catalog


def build_system_prompt(
    host_name: str = "IDA Pro",
    binary_info: str | None = None,
    current_function: str | None = None,
    current_address: str | None = None,
    extra_context: str | None = None,
    active_goal: str | None = None,
    tool_names: list[str] | None = None,
    skill_summary: str | None = None,
    idb_dir: str | None = None,
    profile: AnalysisProfile | None = None,
    tools_table: str | None = None,
) -> str:
    """Build the full system prompt with optional binary context."""
    base_prompt = IDA_BASE_PROMPT
    parts = [base_prompt]

    # Persistent memory — loaded early so it's part of the cached prefix.
    # Sanitized to prevent poisoned memory files from injecting instructions.
    memory = _load_persistent_memory(idb_dir or "")
    if memory:
        parts.append(f"\n## Persistent Memory (RIKUGAN.md)\n{sanitize_memory(memory)}")

    if active_goal:
        parts.append(
            "\n## Active Goal\n"
            "Use this as the standing analysis objective for the current session.\n"
            + quote_untrusted(active_goal, "active_goal", max_length=1000)
        )

    # Binary context is untrusted — function names, strings, and metadata
    # originate from the analyzed binary and could contain adversarial content.
    # When profile.hide_binary_metadata is set, skip binary context entirely.
    if profile and profile.hide_binary_metadata:
        log_debug("Profile: hiding binary metadata from system prompt")
    else:
        if binary_info:
            parts.append(f"\n## Current Binary\n{sanitize_binary_context(binary_info, 'binary_info')}")

        if current_address:
            parts.append(
                f"\n## Current Position\nAddress: {sanitize_binary_context(current_address, 'cursor_address')}"
            )
            if current_function:
                parts.append(f"Function: {sanitize_binary_context(current_function, 'cursor_function')}")

    if tools_table:
        # Prefer the categorized catalog — it gives the LLM category
        # grouping + one-line description hints so it can pick the right
        # tool without scanning the full provider schema.
        parts.append(f"\n{tools_table}")
    elif tool_names:
        # Fallback: comma-separated names only. Less useful but still
        # better than nothing for hosts that do not pre-compute a table.
        parts.append(f"\n## Available Tools\n{', '.join(tool_names)}")

    if skill_summary:
        parts.append(f"\n## Skills\n{skill_summary}")

    if extra_context:
        parts.append(f"\n## Additional Context\n{extra_context}")

    # Profile-driven prompt additions
    if profile:
        if profile.singular_analysis:
            parts.append(
                "\n## Analysis Constraint\n"
                "You are operating in singular analysis mode. "
                "Focus only on the specific question asked. "
                "Do not reference or cross-correlate with other binaries, "
                "samples, or external threat intelligence."
            )
        if profile.custom_filters:
            parts.append("\n## Profile Instructions\n" + "\n".join(profile.custom_filters))
        if profile.denied_functions:
            parts.append(
                "\n## Restricted Functions\n"
                "Do NOT call or reference the following functions in your analysis:\n"
                + "\n".join(f"- {fn}" for fn in profile.denied_functions)
            )

        # Profile awareness — tell the agent about the active profile
        if profile.name != "default":
            section = f"\n## Active Profile: {profile.name}\n"
            if profile.description:
                section += f"{profile.description}\n\n"
            section += (
                "You are operating under this analysis profile. "
                "The user has configured specific constraints and data filters. "
                "Respect these constraints in your analysis and output.\n"
            )
            if profile.has_any_ioc_filter:
                active = [
                    IOC_FILTER_CATEGORIES[k] for k, v in profile.ioc_filters.items() if v and k in IOC_FILTER_CATEGORIES
                ]
                if active:
                    section += (
                        "\nIOC filtering is active — the following are automatically redacted:\n"
                        + "\n".join(f"- {f}" for f in active)
                        + "\n\nIMPORTANT CONSTRAINTS:\n"
                        "- Do NOT attempt to reconstruct or reference original values "
                        "behind redaction markers.\n"
                        "- Hex-encoded data (hexdumps, raw bytes) is also sanitized — "
                        "do NOT decode hex bytes to recover filtered IOC data.\n"
                        "- Do NOT use read_bytes or memory dumps to circumvent IOC filters.\n"
                        "- If a value has been redacted, treat it as permanently unavailable.\n"
                    )
            parts.append(section)

    return "\n".join(parts)
