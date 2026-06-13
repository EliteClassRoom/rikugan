"""Static JSON schemas for Rikugan's pseudo-tools.

These schemas are passed to LLM providers to describe pseudo-tool calls
(``exploration_report``, ``phase_transition``, ``save_memory``,
``spawn_subagent``, ``research_note``, ``ask_user``) that the agent
loop handles internally rather than forwarding to the user-supplied
tool registry.

All schemas are module-level constants because they do not depend on
runtime state — they are pure data describing the contract between the
LLM and the agent loop.  Putting them in their own module keeps
``loop.py`` focused on control flow and makes it trivial for new agent
modes to reuse the exact same tool surface.
"""

# Pseudo-tool: structured finding during binary exploration.
EXPLORATION_REPORT_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "exploration_report",
        "description": (
            "Log a structured finding during binary exploration. "
            "Call this whenever you discover something relevant to "
            "the user's goal: a function's purpose, a key constant, "
            "a data structure, or a hypothesis about what to change."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Type of finding.",
                    "enum": [
                        "function_purpose",
                        "data_structure",
                        "constant",
                        "hypothesis",
                        "string_ref",
                        "import_usage",
                        "patch_result",
                        "general",
                    ],
                },
                "address": {
                    "type": "integer",
                    "description": "Address related to this finding (hex or decimal).",
                },
                "function_name": {
                    "type": "string",
                    "description": "Name of the function (for function_purpose findings).",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of the finding.",
                },
                "evidence": {
                    "type": "string",
                    "description": "Supporting evidence (e.g. decompiled code snippet).",
                },
                "relevance": {
                    "type": "string",
                    "description": "Why this finding is relevant to the user's goal.",
                },
            },
            "required": ["category", "summary"],
        },
    },
}

# Pseudo-tool: declare an explicit phase transition during exploration.
PHASE_TRANSITION_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "phase_transition",
        "description": (
            "Declare a phase transition during exploration. "
            "Use this to signal movement from one exploration phase to "
            "another (e.g. initial → analysis, analysis → synthesis)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to_phase": {
                    "type": "string",
                    "description": "The phase you are moving to.",
                    "enum": [
                        "initial",
                        "analysis",
                        "synthesis",
                        "review",
                        "complete",
                    ],
                },
                "reason": {
                    "type": "string",
                    "description": "Why this transition makes sense now.",
                },
            },
            "required": ["to_phase", "reason"],
        },
    },
}

# Pseudo-tool: persist a fact to long-term memory.
SAVE_MEMORY_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": (
            "Persist a fact to long-term memory. Use this for any "
            "discovery worth remembering across sessions — function "
            "purposes, key constants, project conventions, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact to remember.",
                },
                "category": {
                    "type": "string",
                    "description": "Category for organising memories.",
                    "default": "general",
                },
            },
            "required": ["fact"],
        },
    },
}

# Pseudo-tool: spawn a subagent to handle a sub-task in parallel.
SPAWN_SUBAGENT_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "spawn_subagent",
        "description": (
            "Spawn a subagent to handle a sub-task in parallel. "
            "Returns the subagent's final answer when it completes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Clear description of the sub-task.",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Type of subagent to spawn.",
                    "default": "general",
                },
            },
            "required": ["task"],
        },
    },
}

# Pseudo-tool: save a research-mode note into the session notebook.
RESEARCH_NOTE_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "research_note",
        "description": (
            "Save a structured research note. Use this to capture "
            "findings, hypotheses, and observations as you investigate "
            "the target binary."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the note.",
                },
                "content": {
                    "type": "string",
                    "description": "Note content (markdown supported).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for filtering notes.",
                },
            },
            "required": ["title", "content"],
        },
    },
}

# Pseudo-tool: ask the user a clarifying question.
ASK_USER_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Ask the user a clarifying question. The user's response "
            "is returned as the tool result so you can continue with "
            "the requested information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional multiple-choice options. Omit for a "
                        "free-form question."
                    ),
                },
            },
            "required": ["question"],
        },
    },
}


#: Aggregate list of all pseudo-tool schemas in the order they should be
#: presented to the LLM.
ALL_PSEUDO_TOOL_SCHEMAS: tuple[dict, ...] = (
    EXPLORATION_REPORT_SCHEMA,
    PHASE_TRANSITION_SCHEMA,
    SAVE_MEMORY_SCHEMA,
    SPAWN_SUBAGENT_SCHEMA,
    RESEARCH_NOTE_SCHEMA,
    ASK_USER_SCHEMA,
)


#: Pseudo-tool: delegate a task to an external agent (Claude Code,
#: Codex CLI, or an A2A-compatible HTTP endpoint).
#:
#: The agent_name must match an entry from
#: ``A2ADispatcher.discover()``. The ``context`` field is optional;
#: the dispatcher prepends it to the task so the external agent has
#: binary context if ``include_context`` is set.
DELEGATE_EXTERNAL_TASK_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "delegate_external_task",
        "description": (
            "Delegate a sub-task to an external agent (Claude Code "
            "CLI, Codex CLI, or an A2A-compatible HTTP endpoint). "
            "Use this when the user's request is better suited to a "
            "separate agent session — e.g. a long code-generation "
            "task that benefits from a fresh context window, or a "
            "research task that another agent can run in parallel. "
            "The external agent's response is returned as the tool "
            "result and forwarded back to the user. "
            "Set ``include_context`` to true to send the current "
            "binary's metadata along with the task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": (
                        "Name of the external agent to delegate to. "
                        "Must be in the discovered agent list "
                        "(use the A2A panel or /a2a slash command to "
                        "list available agents). Common values: "
                        "'claude', 'codex'."
                    ),
                },
                "task": {
                    "type": "string",
                    "description": (
                        "The task description to send to the external "
                        "agent. Be specific — the external agent has "
                        "no Rikugan tool access, so include any "
                        "binary details (addresses, decompiled "
                        "snippets, function names) inline."
                    ),
                },
                "include_context": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, prepend the current binary's "
                        "metadata (name, arch, entry point) and the "
                        "current cursor's function context to the "
                        "task before sending."
                    ),
                },
            },
            "required": ["agent", "task"],
        },
    },
}


__all__ = [
    "ALL_PSEUDO_TOOL_SCHEMAS",
    "ASK_USER_SCHEMA",
    "DELEGATE_EXTERNAL_TASK_SCHEMA",
    "EXPLORATION_REPORT_SCHEMA",
    "PHASE_TRANSITION_SCHEMA",
    "RESEARCH_NOTE_SCHEMA",
    "SAVE_MEMORY_SCHEMA",
    "SPAWN_SUBAGENT_SCHEMA",
]
