"""complete orchestration tool — mark task complete with answer (GAIA-style)."""

from __future__ import annotations

from typing import Any

COMPLETE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "complete",
        "description": (
            "Mark the task as complete with the given answer. "
            "Use this for GAIA-style tasks where a definitive answer is expected. "
            "This signals that orchestration is done and provides the final answer directly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "The final answer to the user's question.",
                },
            },
            "required": ["answer"],
        },
    },
}


def handle_complete(tc_id: str, arguments: dict[str, Any]) -> tuple[str, bool]:
    """Handle complete tool invocation."""
    answer = arguments.get("answer", "")

    if not answer:
        return ("Error: 'answer' is required for complete.", True)

    return (f"## Answer\n\n{answer}", False)
