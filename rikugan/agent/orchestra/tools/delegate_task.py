"""delegate_task orchestration tool — requires user approval before spawning sub-agent."""

from __future__ import annotations

import queue
from typing import Any

DELEGATE_TASK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate_task",
        "description": (
            "Delegate a subtask to a specialized sub-agent. "
            "The sub-agent will be created with the four-tuple φ = <I, C, T, M>: "
            "- I: Your instruction describing the task "
            "- C: Context you provide with relevant binary information "
            "- T: Tools you specify from the available tool list "
            "- M: Model you select for the sub-agent "
            "Optionally set 'mode' to run the sub-agent in a specific mode "
            "(exploration, plan, research) for structured workflows. "
            "This tool requires user approval before the sub-agent can be spawned."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Brief name for this subtask (displayed in UI).",
                },
                "instruction": {
                    "type": "string",
                    "description": "Detailed instruction for the sub-agent explaining what to do.",
                },
                "context": {
                    "type": "string",
                    "description": "Relevant context from the main task (binary info, position, etc.).",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tool names to make available to the sub-agent.",
                },
                "model": {
                    "type": "string",
                    "description": "Model to use for this sub-agent.",
                    "enum": [
                        "claude-sonnet-4-20250514",
                        "claude-haiku-4-20250514",
                        "gpt-4o-mini",
                    ],
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Maximum turns for the sub-agent (default: 20).",
                    "default": 20,
                },
                "mode": {
                    "type": "string",
                    "description": (
                        "Mode to run the sub-agent in. "
                        "Valid values: 'exploration' or 'explore' (autonomous read-only investigation), "
                        "'plan' (generate plan, get approval, execute steps), "
                        "'research' (exploration + write markdown notes), "
                        "'normal' or '' (standard agent loop). "
                        "Defaults to 'normal' if not specified."
                    ),
                    "enum": ["exploration", "explore", "plan", "research", "normal", ""],
                    "default": "",
                },
            },
            "required": ["task", "instruction", "tools", "model"],
        },
    },
}


def handle_delegate_task(
    tc_id: str,
    arguments: dict[str, Any],
    approval_queue: queue.Queue[str],
) -> tuple[str, bool]:
    """Handle delegate_task tool invocation.

    This tool requires user approval before the sub-agent can be spawned.
    The approval is done by passing the spec to the UI via the approval_queue.

    Returns:
        (content, is_error) tuple
    """
    task = arguments.get("task", "")
    instruction = arguments.get("instruction", "")
    context = arguments.get("context", "")
    tools = arguments.get("tools", [])
    model = arguments.get("model", "")
    max_steps = arguments.get("max_steps", 20)

    if not instruction:
        return ("Error: 'instruction' is required for delegate_task.", True)
    if not task:
        return ("Error: 'task' is required for delegate_task.", True)
    if not model:
        return ("Error: 'model' is required for delegate_task.", True)

    spec_json = {
        "task": task,
        "instruction": instruction,
        "context": context,
        "tools": tools,
        "model": model,
        "max_steps": max_steps,
    }

    approval_queue.put(f"DELEGATE_TASK:{tc_id}:{spec_json}")

    return (f"Delegation request sent for approval: {task}", False)
