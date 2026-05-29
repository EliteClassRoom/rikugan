# ARCHITECTURE.md — Rikugan Agent Internals

This document describes the internal architecture of the Rikugan agent in full technical detail. It is intended for engineers who need to understand, modify, or extend the system.

---

## Table of Contents

1. [High-Level Overview](#high-level-overview)
2. [The Agentic Loop](#the-agentic-loop)
3. [TurnEvent System](#turnevent-system)
4. [Tool Framework](#tool-framework)
5. [Pseudo-Tools](#pseudo-tools)
6. [Skill System](#skill-system)
7. [Exploration Mode](#exploration-mode)
8. [Plan Mode](#plan-mode)
9. [Subagents](#subagents)
10. [Mutation Tracking and Undo](#mutation-tracking-and-undo)
11. [Context Window Management](#context-window-management)
12. [Persistent Memory](#persistent-memory)
13. [Session Management](#session-management)
14. [MCP Integration](#mcp-integration)
15. [Provider Layer](#provider-layer)
16. [System Prompt Architecture](#system-prompt-architecture)
17. [UI Layer](#ui-layer)
18. [Thread Safety Model](#thread-safety-model)
19. [Error Handling and Retry](#error-handling-and-retry)
20. [Logging](#logging)
21. [Commands Reference](#commands-reference)
22. [Data Flow Diagrams](#data-flow-diagrams)

---

## High-Level Overview

Rikugan is a **generator-based agentic loop** embedded inside IDA Pro. The agent runs in a background thread and communicates with the Qt UI via a stream of `TurnEvent` objects. All IDA API calls are marshalled to the main thread via `@idasync`.

```
User Input
    │
    ▼
┌──────────────────────────────────────────┐
│            SessionControllerBase          │
│  (creates AgentLoop, manages tabs/state) │
└───────────────┬──────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────┐
│  BackgroundAgentRunner (threading.Thread) │
│  ┌────────────────────────────────────┐  │
│  │          AgentLoop.run()           │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │ while has_tool_calls:        │  │  │
│  │  │   stream LLM response       │  │  │
│  │  │   parse tool calls          │  │  │
│  │  │   execute tools             │  │  │
│  │  │   feed results back         │  │  │
│  │  │   yield TurnEvents ─────────┼──┼──┼──→ Queue → UI poll
│  │  └──────────────────────────────┘  │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

Key files:
- `rikugan/agent/loop.py` — `AgentLoop` + `BackgroundAgentRunner`
- `rikugan/agent/turn.py` — `TurnEvent` / `TurnEventType`
- `rikugan/tools/base.py` — `@tool` decorator, `ToolDefinition`
- `rikugan/tools/registry.py` — `ToolRegistry`
- `rikugan/ui/panel_core.py` — `RikuganPanelCore` (Qt UI)
- `rikugan/ui/session_controller_base.py` — `SessionControllerBase`

---

## The Agentic Loop

**File**: `rikugan/agent/loop.py`

### `AgentLoop.run(user_message) -> Generator[TurnEvent]`

The entry point is `AgentLoop.run()`, a Python generator. It yields `TurnEvent` objects that the UI consumes. The loop proceeds as follows:

1. **Command Detection** — The message is checked for command prefixes:
   - `/plan <msg>` → plan mode
   - `/modify <msg>` → exploration mode (4-phase, with patching)
   - `/explore <msg>` → exploration mode (explore-only, read-only)
   - `/memory` → show RIKUGAN.md contents
   - `/undo [N]` → undo last N mutations
   - `/mcp` → show MCP server health
   - `/doctor` → diagnose setup issues

2. **Skill Resolution** — `_resolve_skill()` checks if the message starts with a skill slug (e.g., `/malware-analysis`). If matched, the skill's body is prepended to the system prompt and `allowed_tools` is enforced.

3. **System Prompt Build** — `build_system_prompt()` assembles the prompt from host-specific base + binary context + cursor position + tool list + skill + persistent memory (RIKUGAN.md).

4. **Turn Loop** — The core loop:
   ```
   while True:
       yield TURN_START
       stream = provider.chat_stream(messages, tools, system)
       text, tool_calls = _stream_llm_turn(stream)  # yields TEXT_DELTA events
       yield TEXT_DONE
       if no tool_calls:
           break  # LLM is done
       results = _execute_tool_calls(tool_calls)  # yields TOOL_RESULT events
       append results to messages
       yield TURN_END
   ```

5. **Context Compaction** — At the start of each turn, `ContextWindowManager.should_compact()` is checked. If the context is above 80% of the window, messages are compacted (old middle messages summarized, head + tail preserved).

6. **Cancellation** — `_check_cancelled()` is called at multiple points. It raises `CancellationError` which is caught at the top level and yields a `CANCELLED` event.

### `_stream_llm_turn()`

Consumes the provider's `chat_stream()` generator. Each `StreamChunk` is processed:

- `chunk.text` → yields `TEXT_DELTA` events, accumulates full text
- `chunk.is_tool_call_start` → yields `TOOL_CALL_START`, starts accumulating tool call
- `chunk.tool_args_delta` → yields `TOOL_CALL_ARGS_DELTA`, accumulates JSON args
- `chunk.is_tool_call_end` → yields `TOOL_CALL_DONE`, finalizes the `ToolCall`
- `chunk.usage` → yields `USAGE_UPDATE`, updates context manager

Returns `(full_text, List[ToolCall])`.

### `_execute_tool_calls()`

Takes a list of `ToolCall` objects and executes each one. For each call:

1. **Pseudo-tool check** — Handled inline with `continue` (see [Pseudo-Tools](#pseudo-tools))
2. **Approval gate** — `execute_python` requires user approval unless previously allowed
3. **Pre-state capture** — For mutating tools, `capture_pre_state()` calls getter tools to record the current state before mutation
4. **Execution** — `ToolRegistry.execute(name, args)` dispatches to the handler
5. **Mutation recording** — If `defn.mutating`, `build_reverse_record()` creates a `MutationRecord` and appends to `_mutation_log`. Yields a `MUTATION_RECORDED` event
6. **Error handling** — `ToolError` and general `Exception` are caught and returned as error results
7. **Result** — Each result becomes a `ToolResult` and yields a `TOOL_RESULT` event

### `BackgroundAgentRunner`

Wraps the generator in a `threading.Thread`. Events are forwarded to a `queue.Queue` that the UI polls at 50ms intervals via `QTimer`.

```python
class BackgroundAgentRunner:
    def start(self, user_message):
        self._thread = Thread(target=self._run, args=(user_message,))
        self._thread.start()

    def _run(self, message):
        for event in self.agent_loop.run(message):
            self._event_queue.put(event)

    def get_event(self, timeout=0):
        return self._event_queue.get(timeout=timeout)
```

---

## TurnEvent System

**File**: `rikugan/agent/turn.py`

All communication from the agent loop to the UI goes through `TurnEvent` objects. Each event has a `type` (enum) and optional payload fields.

### Event Types

| Type | Description | Key Fields |
|------|-------------|------------|
| `TEXT_DELTA` | Streaming text token | `text` |
| `TEXT_DONE` | Full assistant text complete | `text` |
| `TOOL_CALL_START` | LLM requested a tool call | `tool_call_id`, `tool_name` |
| `TOOL_CALL_ARGS_DELTA` | Streaming tool arguments | `tool_call_id`, `tool_args` |
| `TOOL_CALL_DONE` | Tool call arguments finalized | `tool_call_id`, `tool_name`, `tool_args` |
| `TOOL_RESULT` | Tool execution result | `tool_call_id`, `tool_name`, `tool_result`, `tool_is_error` |
| `TURN_START` | New turn begins | `turn_number` |
| `TURN_END` | Turn complete | `turn_number` |
| `ERROR` | Error occurred | `error` |
| `CANCELLED` | User cancelled | — |
| `USAGE_UPDATE` | Token usage update | `usage` (TokenUsage) |
| `USER_QUESTION` | Agent asks user a question | `text`, `metadata.options` |
| `PLAN_GENERATED` | Plan mode: plan ready | `plan_steps` |
| `PLAN_STEP_START` | Plan mode: executing step | `plan_step_index`, `text` |
| `PLAN_STEP_DONE` | Plan mode: step complete | `plan_step_index`, `text` |
| `TOOL_APPROVAL_REQUEST` | Script approval needed | `tool_call_id`, `tool_name`, `tool_args`, `text` |
| `EXPLORATION_PHASE_CHANGE` | Phase transition | `metadata.from_phase`, `metadata.to_phase` |
| `EXPLORATION_FINDING` | Discovery logged | `text`, `metadata.category`, `metadata.address`, `metadata.relevance` |
| `PATCH_APPLIED` | Binary patch applied | `text`, `metadata.address`, `metadata.original`, `metadata.new` |
| `PATCH_VERIFIED` | Patch verified | `text`, `metadata.address`, `metadata.success` |
| `SAVE_APPROVAL_REQUEST` | Save gate reached | `text`, `metadata.patch_count`, `metadata.total_bytes` |
| `SAVE_COMPLETED` | Patches saved to file | `text`, `metadata.patch_count` |
| `SAVE_DISCARDED` | Patches discarded | `text`, `metadata.rolled_back` |
| `MUTATION_RECORDED` | Mutation logged for undo | `tool_name`, `text`, `metadata.reversible`, `metadata.reverse_tool` |

Each event type has a static factory method on `TurnEvent` for clean construction (e.g., `TurnEvent.text_delta("hello")`).

---

## Tool Framework

**Files**: `rikugan/tools/base.py`, `rikugan/tools/registry.py`

### `@tool` Decorator

Tools are defined with the `@tool` decorator on plain functions:

```python
@tool(category="annotations", mutating=True)
def rename_function(
    old_name: Annotated[str, "Current function name"],
    new_name: Annotated[str, "New name to assign"],
) -> str:
    """Rename a function in the database."""
    # ... implementation
```

The decorator:
1. Inspects the function signature using `typing.get_type_hints()`
2. Extracts parameter descriptions from `Annotated` metadata
3. Generates a `ToolDefinition` with JSON schema
4. Wraps the handler with `@idasync` for IDA thread-safety
5. Attaches the definition as `func._tool_definition`

### `ToolDefinition`

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: List[ParameterSchema]
    category: str = "general"
    requires_decompiler: bool = False
    mutating: bool = False              # marks tool as modifying the database
    timeout: Optional[float] = None     # per-tool timeout in seconds
    handler: Optional[Callable] = None
```

Key flags:
- `mutating=True` — Triggers pre-state capture and mutation recording for undo
- `requires_decompiler=True` — Tool is excluded if decompiler is unavailable
- `timeout` — Per-tool timeout; wrapped in `ThreadPoolExecutor` during execution

### `ToolRegistry`

Central registry for all tool definitions. Core methods:
- `register(defn)` / `register_module(module)` — Registration
- `execute(name, args)` — Dispatches to handler with argument coercion and timeout
- `get(name)` → `ToolDefinition` — Lookup
- `to_provider_format()` → list of JSON schemas for LLM

Argument coercion in `execute()`:
- Hex strings (`"0x401000"`) → `int` for integer parameters
- `"true"`/`"false"` strings → `bool`
- `0`/`1` integers → `bool`

Timeout wrapping:
```python
future = _executor.submit(defn.handler, **arguments)
result = future.result(timeout=timeout)  # default 30s
```

### Tool Categories

Each host provides ~56 tools organized by category:

| Category | Examples |
|----------|----------|
| Navigation | `get_cursor_position`, `jump_to`, `get_name_at` |
| Functions | `list_functions`, `search_functions`, `get_function_info` |
| Strings | `list_strings`, `search_strings` |
| Database | `list_segments`, `list_imports`, `list_exports`, `read_bytes` |
| Disassembly | `read_disassembly`, `read_function_disassembly` |
| Decompiler | `decompile_function`, `get_pseudocode` |
| Xrefs | `xrefs_to`, `xrefs_from`, `function_xrefs` |
| Annotations | `rename_function`, `set_comment`, `set_type` |
| Types | `create_struct`, `modify_struct`, `set_function_prototype` |
| Scripting | `execute_python` (requires approval) |
| Microcode (IDA) | `get_microcode`, `nop_microcode` |

---

## Pseudo-Tools

Pseudo-tools are tool schemas injected into the LLM's tool list but handled directly in `_execute_tool_calls()` rather than dispatched through the registry. They use a `continue` statement to skip normal execution.

### `exploration_report`

Used during exploration mode to log structured findings:

```json
{
  "category": "function_purpose|hypothesis|data_structure|constant|string_ref|import_usage|patch_result",
  "summary": "Description of the finding",
  "address": 4198400,
  "function_name": "main",
  "relevance": "high|medium|low",
  "original_hex": "74 05",   // for patch_result only
  "new_hex": "75 05"         // for patch_result only
}
```

When `category="patch_result"`, the handler also creates a `PatchRecord` and appends it to `state.patches_applied` for the save gate.

### `phase_transition`

Requests a phase change in exploration mode. Validates via `ExplorationState.can_transition_to()`.

### `save_memory`

Persists a fact to `RIKUGAN.md` in the IDB directory:
```json
{"fact": "sub_401230 is the snake initializer", "category": "function_purpose"}
```

### `spawn_subagent`

Creates an isolated `SubagentRunner` with its own `SessionState`:
```json
{"task": "Analyze the main function", "max_turns": 5}
```

---

## Skill System

**Files**: `rikugan/skills/loader.py`, `rikugan/skills/registry.py`

### Skill Format

Skills are Markdown files with YAML frontmatter:

```markdown
---
name: Malware Analysis
description: Windows PE malware analysis workflow
tags: [malware, windows]
allowed_tools: [decompile_function, list_imports, search_strings]
mode: exploration   # optional: exploration, plan
---
Task: Analyze this binary as potential malware.

## Approach
1. Check imports for suspicious APIs...
```

### Frontmatter Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Display name |
| `description` | str | One-line description |
| `tags` | list | Categorization tags |
| `allowed_tools` | list | Tool whitelist (empty = all tools) |
| `mode` | str | `"exploration"` activates exploration mode, `"plan"` activates plan mode |

### Discovery

`SkillRegistry.discover()` scans:
1. Built-in skills: `rikugan/skills/builtins/*/SKILL.md`
2. User skills: `~/.idapro/rikugan/skills/*/SKILL.md`

Reference files in `references/*.md` subdirectories are automatically appended to the skill body.

### Skill Activation

When a user types `/<slug>`, `_resolve_skill()` in `loop.py`:
1. Finds the matching `SkillDefinition`
2. Prepends the skill body to the system prompt
3. If `allowed_tools` is set, filters the tool list
4. If `mode: exploration`, activates exploration mode

### Built-in Skills (10)

| Slug | Purpose |
|------|---------|
| `/malware-analysis` | Windows PE malware triage |
| `/linux-malware` | ELF malware analysis |
| `/deobfuscation` | String decryption, CFF, opaque predicates |
| `/vuln-audit` | Buffer overflow, format string, integer bugs |
| `/driver-analysis` | Windows kernel driver analysis |
| `/ctf` | CTF challenge solving |
| `/generic-re` | General reverse engineering |
| `/ida-scripting` | IDAPython API reference |
| `/modify` | Exploration mode: autonomous binary modification |
| `/smart-patch-ida` | IDA-specific binary patching |

---

## Exploration Mode

**Files**: `rikugan/agent/exploration_mode.py`, `rikugan/agent/loop.py` (`_run_exploration_mode()`)

Exploration mode is a **4-phase autonomous agent flow** for binary modification:

```
EXPLORE ──→ PLAN ──→ EXECUTE ──→ SAVE
```

### Phase 1: EXPLORE

The agent autonomously investigates the binary to understand the user's goal.

- Triggered by `/modify <goal>` or `/explore <goal>` or skills with `mode: exploration`
- Uses all analysis tools + `exploration_report` pseudo-tool + `phase_transition` pseudo-tool
- Findings are accumulated in a `KnowledgeBase`:
  - `relevant_functions` — discovered functions with addresses and summaries
  - `findings` — structured findings (function_purpose, hypothesis, data_structure, etc.)
  - `hypotheses` — extracted from findings with `category="hypothesis"`
- Turn limit: 30 turns (`max_explore_turns`)
- For `/modify`: Phase 1 runs as a **subagent** (isolated context window)
- For `/explore`: Phase 1 runs inline (explore-only, no patching phases follow)
- System addendum: `EXPLORATION_SYSTEM_ADDENDUM` guides the agent's strategy

### Phase Transition Gate

To move from EXPLORE → PLAN, `KnowledgeBase.has_minimum_for_planning` must be true:
- At least 1 relevant function
- At least 1 hypothesis
- At least 1 hypothesis with `relevance="high"`

If the gate fails, the agent receives a gap description and continues exploring.

### Phase 2: PLAN

The agent synthesizes findings into a concrete modification plan.

- Receives `PLAN_SYNTHESIS_PROMPT` with `KnowledgeBase.to_summary()`
- Outputs a numbered list of changes, each with target address, current/proposed behavior, patch strategy
- Parsed into `ModificationPlan` with `PlannedChange` objects
- Addresses extracted from step text via regex
- User must approve the plan before execution proceeds
- Approved plans are persisted to `RIKUGAN.md` for cross-session reference

### Phase 3: EXECUTE

The agent applies patches in-memory for each planned change.

- Iterates over `ModificationPlan.changes`
- Each step uses `EXECUTE_STEP_PROMPT` with the change description
- Activates the IDA patching skill: `smart-patch-ida`
- After each patch, the agent calls `exploration_report(category="patch_result")` with `original_hex`/`new_hex`
- This creates a `PatchRecord` in `state.patches_applied`
- Turn limit: 20 turns (`max_execute_turns`)

### Phase 4: SAVE

User approval gate before persisting changes.

- Emits `SAVE_APPROVAL_REQUEST` with patch count, total bytes, verification status, per-patch details
- User responds "Save All" or "Discard All"
- **Save**: emits `SAVE_COMPLETED`
- **Discard**: rolls back patches by writing `PatchRecord.original_bytes` back via `execute_python`, emits `SAVE_DISCARDED`

### ExplorationState

```python
@dataclass
class ExplorationState:
    phase: ExplorationPhase
    knowledge_base: KnowledgeBase
    modification_plan: Optional[ModificationPlan]
    patches_applied: List[PatchRecord]
    explore_turns: int
    execute_turns: int
    total_turns: int        # monotonic counter for UI
    max_explore_turns: int  # default 30
    max_execute_turns: int  # default 20
    explore_only: bool      # True for /explore (no patching)
```

### `/explore` vs `/modify`

| Aspect | `/explore` | `/modify` |
|--------|-----------|-----------|
| Phases | EXPLORE only | EXPLORE → PLAN → EXECUTE → SAVE |
| Subagent | No (inline) | Yes (Phase 1 in subagent) |
| Patching | No | Yes |
| Knowledge base | Accumulated, returned to caller | Accumulated, passed to Phase 2 |

---

## Plan Mode

**Files**: `rikugan/agent/plan_mode.py`, `rikugan/agent/loop.py`

Plan mode is a simpler two-step workflow: **plan first, then execute**.

Triggered by `/plan <message>`.

### Flow

1. **Plan Generation** — LLM receives `_PLAN_GENERATION_PROMPT` and outputs a numbered list
2. **Plan Parsing** — `parse_plan()` extracts numbered steps from the text
3. **User Approval** — `PLAN_GENERATED` event; user approves or rejects
4. **Step Execution** — For each step:
   - Emit `PLAN_STEP_START`
   - Run a full turn cycle with `_STEP_EXECUTION_PROMPT`
   - Emit `PLAN_STEP_DONE`

Plan mode is orthogonal to exploration mode. `/plan` does not enter exploration phases.

---

## Subagents

**File**: `rikugan/agent/subagent.py`

Subagents are isolated `AgentLoop` instances with their own `SessionState`. They keep the parent's context window clean from verbose tool output.

### `SubagentRunner`

```python
class SubagentRunner:
    def run_task(self, task, max_turns=20) -> Generator[TurnEvent, None, str]:
        # General-purpose: returns final text
        loop = AgentLoop(provider, tools, config, fresh_session)
        for event in loop.run(augmented_task):
            yield event
        return final_text

    def run_exploration(self, user_goal, max_turns=30) -> Generator[TurnEvent, None, KnowledgeBase]:
        # Phase 1 specific: returns KnowledgeBase
        loop = AgentLoop(provider, tools, config, fresh_session)
        for event in loop.run(f"/explore {user_goal}"):
            yield event
        return loop.last_knowledge_base
```

### `spawn_subagent` Pseudo-Tool

The LLM can also spawn subagents via the `spawn_subagent` pseudo-tool:

```json
{"task": "Analyze the main function", "max_turns": 5}
```

The parent loop creates a `SubagentRunner`, delegates all events to the UI, and receives only the compact text summary.

### Knowledge Base Transfer

When a subagent running in explore mode finishes:
1. `_clear_exploration_state()` saves the `KnowledgeBase` to `_last_knowledge_base`
2. The parent accesses it via the `last_knowledge_base` property
3. The parent populates its own `ExplorationState.knowledge_base` from the subagent's results
4. Phases 2-4 proceed in the parent with a clean context window

---

## Mutation Tracking and Undo

**File**: `rikugan/agent/mutation.py`

Every mutating tool call (`defn.mutating=True`) is recorded in `AgentLoop._mutation_log` for undo support.

### `MutationRecord`

```python
@dataclass
class MutationRecord:
    tool_name: str              # e.g., "rename_function"
    arguments: Dict[str, Any]   # original arguments
    reverse_tool: str           # tool to call for undo
    reverse_arguments: Dict      # arguments for undo
    timestamp: float
    description: str            # human-readable
    reversible: bool            # False for execute_python, etc.
```

### `build_reverse_record()`

Generates reverse operations for known tools:

| Tool | Reverse Strategy |
|------|-----------------|
| `rename_function` | Swap `old_name` ↔ `new_name` |
| `rename_variable` / `rename_single_variable` | Swap `variable_name` ↔ `new_name` |
| `set_comment` | Restore `old_comment` (from pre-state) or `delete_comment` |
| `set_function_comment` | Restore `old_comment` or `delete_function_comment` |
| `rename_data` | Restore `old_name` (from pre-state) |
| `set_function_prototype` | Restore `old_prototype` (from pre-state) |
| `retype_variable` | Restore `old_type` (from pre-state) |
| `execute_python` | **Not reversible** (`reversible=False`) |

### `capture_pre_state()`

For tools that need pre-mutation state (comments, prototypes, types), calls getter tools before the mutation:

```python
# Before set_comment:
old_comment = tool_executor("get_comment", {"address": address})
# After: build_reverse_record uses old_comment for undo
```

### `/undo [N]`

The `/undo` command:
1. Parses the count (default 1)
2. Iterates `_mutation_log` in reverse
3. For each reversible record: calls `ToolRegistry.execute(reverse_tool, reverse_args)`
4. Pops the record from the log
5. Yields results as text events

### UI Integration

- `MUTATION_RECORDED` events flow to `RikuganPanelCore._on_mutation_recorded()`
- A `MutationLogPanel` (in a horizontal `QSplitter` alongside the chat) shows the mutation history
- "Mutations" toggle button appears after the first mutation
- "Undo Last" button submits `/undo 1` through the agent loop

---

## Context Window Management

**File**: `rikugan/agent/context_window.py`

### `ContextWindowManager`

Tracks token usage and compacts the conversation when approaching limits.

```python
class ContextWindowManager:
    max_tokens: int           # from config (default 128000)
    compaction_threshold: 0.8 # compact when usage > 80%

    def should_compact() -> bool
    def compact_messages(messages) -> List[Message]
    def estimate_tokens(text) -> int  # ~3.5 chars/token heuristic
```

### Compaction Strategy

When `should_compact()` returns True:
1. Keep the first message (system/initial)
2. Keep the last 4 messages (recent context)
3. Summarize all middle messages into one `[Context summary]` message

### Per-Message Truncation

`SessionState._truncate_results()` caps tool results to prevent individual messages from consuming too much context. Truncated results include `[...N chars omitted]` markers.

### Integration with AgentLoop

At the top of each turn in `run()`:
```python
if self._context_manager.should_compact():
    messages = self._context_manager.compact_messages(messages)
```

---

## Persistent Memory

**Files**: `rikugan/agent/system_prompt.py`, `rikugan/agent/loop.py`

### RIKUGAN.md

A per-binary Markdown file stored alongside the IDB. It acts as cross-session memory.

- **Location**: `<idb_directory>/RIKUGAN.md`
- **Loading**: First 200 lines loaded into the system prompt at the start of every session
- **Writing**: Via the `save_memory` pseudo-tool or plan persistence

### `save_memory` Pseudo-Tool

The LLM can persist facts:
```json
{"fact": "sub_401230 is the snake initializer, length at +0x1A", "category": "function_purpose"}
```

Categories: `function_purpose`, `architecture`, `naming_convention`, `prior_analysis`, `general`.

### Plan Persistence

Approved plans from exploration mode are saved to RIKUGAN.md with a timestamp, preserving analysis context across sessions.

### `/memory` Command

Shows the current contents of RIKUGAN.md in the chat.

---

## Session Management

**Files**: `rikugan/state/session.py`, `rikugan/state/history.py`, `rikugan/ui/session_controller_base.py`

### `SessionState`

```python
@dataclass
class SessionState:
    id: str                        # unique hex ID
    created_at: float
    messages: List[Message]        # full conversation history
    total_usage: TokenUsage        # cumulative token usage
    last_prompt_tokens: int        # most recent prompt size
    current_turn: int
    is_running: bool
    provider_name: str
    model_name: str
    idb_path: str
    metadata: Dict[str, str]
```

Key methods:
- `add_message(msg)` — Appends and updates token tracking
- `get_messages_for_provider(context_window)` — Returns sanitized, trimmed messages
- `_sanitize()` — Patches orphaned `tool_use` blocks with synthetic error results
- `_truncate_results()` — Caps tool result sizes
- `_trim_to_budget()` — Drops oldest messages if over budget

### Multi-Tab Sessions

`SessionControllerBase` manages multiple sessions:

```python
class SessionControllerBase:
    _sessions: Dict[str, SessionState]  # tab_id → session
    _active_tab_id: str

    def create_tab() -> str
    def close_tab(tab_id)
    def switch_tab(tab_id)
    def fork_session(source_tab_id) -> Optional[str]  # deep copy
```

### Session Fork

`fork_session()` creates a deep copy of a session's messages and state into a new tab. The forked session gets `metadata["forked_from"]` set to the source session ID. Useful for branching analysis from a checkpoint.

### Persistence

`SessionHistory` handles save/restore:
- Sessions are JSON-serialized to `<config_dir>/rikugan/sessions/`
- Auto-saved after each agent turn (if `checkpoint_auto_save` is enabled)
- Restored per-file when the same IDB is reopened
- Full round-trip: messages, token usage, tool calls, tool results all preserved

---

## MCP Integration

**Files**: `rikugan/mcp/client.py`, `rikugan/mcp/bridge.py`, `rikugan/mcp/manager.py`

### Architecture

```
mcp.json config → MCPManager → MCPClient (per server) → subprocess (stdio)
                      ↓
                 MCPBridge → ToolRegistry
```

### MCPClient

Communicates with an MCP server subprocess via JSON-RPC 2.0 + Content-Length framing.

Key features:
- **Heartbeat**: Background thread pings the server every 30s. Marks `_healthy=False` on failure
- **`is_healthy` property**: Returns False if heartbeat failed or process died
- **Per-request timeout**: Configurable default (from `MCP_DEFAULT_TIMEOUT`)
- **Tool discovery**: `tools/list` RPC call at startup populates `_tools`

### MCPBridge

Converts MCP tool schemas to `ToolDefinition` objects and registers them in the `ToolRegistry` with the prefix `mcp_<server>_<tool>`.

### `/mcp` Command

Shows the health status of all configured MCP servers (running, healthy, tool count).

---

## Provider Layer

**Files**: `rikugan/providers/base.py`, `rikugan/providers/registry.py`, `rikugan/providers/*.py`

### `LLMProvider` ABC

```python
class LLMProvider(ABC):
    def chat(self, messages, tools, temperature, max_tokens, system) -> Message
    def chat_stream(self, messages, tools, ...) -> Generator[StreamChunk]
    def list_models() -> List[ModelInfo]
```

### Providers

| Provider | File | Notes |
|----------|------|-------|
| Anthropic (Claude) | `anthropic_provider.py` | OAuth auto-detection, prompt caching |
| OpenAI | `openai_provider.py` | Standard OpenAI SDK |
| Gemini | `gemini_provider.py` | google-genai SDK |
| Ollama | `ollama_provider.py` | Local inference |
| OpenAI-Compatible | `openai_compat.py` | Custom API base |

### Prompt Caching (Anthropic)

`cache_control: {"type": "ephemeral"}` is set on:
1. The system prompt (stable across turns)
2. The last tool result message
3. The last user message

This enables Anthropic's server-side prompt caching for 2-10x cost reduction on long conversations.

### Retry Logic

In `_stream_llm_turn()`:
- `RateLimitError` triggers exponential backoff (1s, 2s, 4s) up to 3 retries
- `ProviderError` with `retryable=True` follows the same pattern
- User sees "Rate limited, retrying in Ns..." via `TEXT_DELTA` events

---

## System Prompt Architecture

**Files**: `rikugan/agent/system_prompt.py`, `rikugan/agent/prompts/`

### Prompt Structure

```
┌─────────────────────────────┐
│  Host-specific base prompt  │ ← ida.py
│  (tool usage guidelines,    │
│   discipline, safety)       │
├─────────────────────────────┤
│  Persistent Memory          │ ← RIKUGAN.md (first 200 lines)
├─────────────────────────────┤
│  Current Binary info        │ ← binary name, arch, entry point
├─────────────────────────────┤
│  Current Position           │ ← address + function name
├─────────────────────────────┤
│  Available Tools            │ ← comma-separated tool names
├─────────────────────────────┤
│  Active Skill               │ ← skill body (if any)
├─────────────────────────────┤
│  Exploration Addendum       │ ← only during exploration mode
└─────────────────────────────┘
```

### Shared Prompt Sections (`prompts/base.py`)

- `DISCIPLINE_SECTION` — "Do exactly what was asked"
- `RENAMING_SECTION` — Renaming/retyping guidelines
- `ANALYSIS_SECTION` — Analysis approach
- `SAFETY_SECTION` — Safety guidelines
- `TOKEN_EFFICIENCY_SECTION` — Prefer search over listing
- `CLOSING_SECTION` — Final reminders

---

## UI Layer

**Files**: `rikugan/ui/panel_core.py`, `rikugan/ui/chat_view.py`, `rikugan/ui/message_widgets.py`

### `RikuganPanelCore`

The main Qt widget. Layout:

```
┌─────────────────────────────────────────────┐
│ Tab Bar (+ button, close buttons)           │
├────────────────────────┬────────────────────┤
│                        │                    │
│   QTabWidget           │  MutationLogPanel  │
│   (ChatView per tab)   │  (toggle-able)     │
│                        │                    │
├────────────────────────┴────────────────────┤
│ [InputArea] [Send] [Stop] [New] [Export]    │
│             [Settings] [Mutations]          │
├─────────────────────────────────────────────┤
│ ContextBar (model name, token count)        │
└─────────────────────────────────────────────┘
```

### Event Polling

A `QTimer` fires every 50ms, calling `_poll_events()`:
1. Dequeues up to 20 events from `BackgroundAgentRunner`
2. Routes each to `ChatView.handle_event()`
3. Checks for `USER_QUESTION` / `SAVE_APPROVAL_REQUEST` to enable input
4. Updates token display on `USAGE_UPDATE`
5. Routes `MUTATION_RECORDED` to `MutationLogPanel`

### `ChatView`

Scrollable chat area. Renders `TurnEvent` → widget:

| Event | Widget |
|-------|--------|
| `TEXT_DELTA` / `TEXT_DONE` | `AssistantMessageWidget` (Markdown rendered) |
| `TOOL_CALL_*` | `ToolCallWidget` (collapsible, syntax-highlighted) |
| `TOOL_RESULT` | Updates `ToolCallWidget` result section |
| `TURN_START` | `ThinkingWidget` (animated dots) |
| `ERROR` | `ErrorMessageWidget` |
| `PLAN_GENERATED` | `PlanView` (step list with status indicators) |
| `TOOL_APPROVAL_REQUEST` | `ToolApprovalWidget` (Allow/Deny buttons) |
| `EXPLORATION_PHASE_CHANGE` | `ExplorationPhaseWidget` |
| `EXPLORATION_FINDING` | `ExplorationFindingWidget` |

Tool call batching: consecutive calls to the same tool are merged into a `ToolBatchWidget` to reduce visual noise. A preview budget of 3 tool previews per turn prevents UI clutter.

### `MutationLogPanel`

Side panel showing mutation history:
- `MutationEntryWidget` per mutation — shows timestamp, description, reversibility indicator, tool badge
- "Undo Last" button emits `undo_requested` signal → submits `/undo 1`
- Count label updates dynamically

---

## Thread Safety Model

### Background Thread

`BackgroundAgentRunner` runs the agent loop in a daemon thread. All `TurnEvent` objects are passed to the UI via `queue.Queue`.

### IDA API Marshalling

IDA Pro requires all API calls on the main thread. The `@idasync` decorator in `core/thread_safety.py` marshalls calls:
- If already on main thread: execute directly
- If on background thread: schedule via `ida_kernwin.execute_sync()` and wait

### User Answer/Approval Queues

Two `queue.Queue(maxsize=1)` instances replace the old `threading.Event` + mutable field pattern:
- `_user_answer_queue` — For `USER_QUESTION` responses (plan approval, save gate, etc.)
- `_tool_approval_queue` — For `execute_python` approval

The agent waits with `queue.get(timeout=0.5)` in a loop, checking for cancellation between attempts. The UI thread calls `put()`. No race condition possible.

---

## Error Handling and Retry

### Exception Hierarchy (`core/errors.py`)

```
RikuganError
├── AgentError          — loop-level errors
├── CancellationError   — user cancelled
├── ProviderError       — LLM API errors
│   └── RateLimitError  — HTTP 429
├── ToolError           — tool execution errors
├── ToolValidationError — argument validation
├── MCPError            — MCP protocol errors
│   ├── MCPConnectionError
│   └── MCPTimeoutError
└── SkillError          — skill loading errors
```

### Retry Logic

In `_stream_llm_turn()`:
```python
for attempt in range(max_retries):
    try:
        yield from stream
        break
    except RateLimitError as e:
        wait = e.retry_after or (2 ** attempt)
        yield TEXT_DELTA(f"Rate limited, retrying in {wait}s...")
        time.sleep(wait)
```

### Consecutive Error Tracking

`_consecutive_errors` counts sequential tool failures. After 3 consecutive errors, `_tools_disabled_for_turn` is set — the LLM receives tools as unavailable for the current turn, forcing it to respond with text instead of looping on broken calls.

---

## Logging

**File**: `rikugan/core/logging.py`

### Log Outputs

1. **IDA Output Window** — `IDAHandler`, INFO level, `[Rikugan] LEVEL: message`
2. **Debug File** — `_FlushFileHandler`, DEBUG level, flushed + fsynced after every write
   - Location: `<config_dir>/rikugan/rikugan_debug.log`
   - Survives crashes (fsync)
3. **Structured JSON** — `_JSONFormatter`, INFO level, JSONL format
   - Location: `<config_dir>/rikugan/rikugan_structured.jsonl`
   - Append mode, machine-parseable

### JSON Log Format

```json
{"ts": 1709500000.123, "level": "INFO", "thread": "Thread-1", "msg": "Subagent started"}
```

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `/plan <msg>` | Enter plan mode: generate plan, then execute step-by-step |
| `/modify <msg>` | Enter exploration mode: EXPLORE → PLAN → EXECUTE → SAVE |
| `/explore <msg>` | Enter explore-only mode: autonomous read-only analysis |
| `/memory` | Show current RIKUGAN.md contents |
| `/undo [N]` | Undo last N mutations (default 1) |
| `/mcp` | Show MCP server health status |
| `/doctor` | Diagnose provider, API key, tools, skills, config issues |
| `/<skill-slug>` | Activate a skill (e.g., `/malware-analysis`, `/ctf`) |

---

## Data Flow Diagrams

### Normal Turn

```
User "Explain main()"
  │
  ├─→ SessionState.add_message(USER)
  ├─→ build_system_prompt()
  ├─→ provider.chat_stream(messages, tools, system)
  │     ├─→ TEXT_DELTA "The main function..."
  │     ├─→ TOOL_CALL_START "decompile_function"
  │     ├─→ TOOL_CALL_DONE
  │     └─→ USAGE_UPDATE
  ├─→ ToolRegistry.execute("decompile_function", {"name": "main"})
  │     └─→ TOOL_RESULT "int main() { ... }"
  ├─→ SessionState.add_message(TOOL)
  ├─→ provider.chat_stream(messages + tool_result)
  │     ├─→ TEXT_DELTA "This function initializes..."
  │     └─→ TEXT_DONE
  └─→ TURN_END
```

### Exploration Mode (`/modify`)

```
User "/modify Change score from 100 to 999"
  │
  ├─→ Phase 1: EXPLORE (subagent)
  │     ├─→ SubagentRunner.run_exploration()
  │     │     ├─→ [subagent uses tools, logs findings]
  │     │     ├─→ exploration_report → KnowledgeBase
  │     │     └─→ phase_transition("plan") → KnowledgeBase returned
  │     └─→ Parent receives KnowledgeBase summary (~1-2KB)
  │
  ├─→ Phase 2: PLAN
  │     ├─→ PLAN_SYNTHESIS_PROMPT + KB summary → LLM
  │     ├─→ Parse plan → ModificationPlan
  │     └─→ User approves plan
  │
  ├─→ Phase 3: EXECUTE
  │     ├─→ For each PlannedChange:
  │     │     ├─→ EXECUTE_STEP_PROMPT → LLM
  │     │     ├─→ Smart patch skill activated
  │     │     ├─→ execute_python (with approval) → patch bytes
  │     │     ├─→ redecompile_function → verify
  │     │     └─→ exploration_report(category="patch_result") → PatchRecord
  │     └─→ All patches applied
  │
  └─→ Phase 4: SAVE
        ├─→ SAVE_APPROVAL_REQUEST → User
        ├─→ "Save All" → write to file → SAVE_COMPLETED
        └─→ "Discard All" → restore original bytes → SAVE_DISCARDED
```

### Mutation Tracking

```
LLM calls rename_function(old="sub_401000", new="main")
  │
  ├─→ capture_pre_state() → {} (no pre-state needed for renames)
  ├─→ ToolRegistry.execute("rename_function", {...})
  ├─→ build_reverse_record() → MutationRecord(
  │     reverse_tool="rename_function",
  │     reverse_args={"old_name": "main", "new_name": "sub_401000"})
  ├─→ _mutation_log.append(record)
  └─→ MUTATION_RECORDED event → UI (MutationLogPanel)

User "/undo"
  │
  ├─→ Pop last MutationRecord from _mutation_log
  ├─→ ToolRegistry.execute("rename_function", {"old_name": "main", "new_name": "sub_401000"})
  └─→ TEXT_DONE "Undone: Rename function main → sub_401000"
```

---

## IDA Headless Mode

### Process Model

```
┌─────────────────────────────────────────────────────────┐
│  User / External Client                                  │
│    │                                                      │
│    ▼                                                      │
│  rikugan-headless (CLI outside IDA)                      │
│    │                                                      │
│    │  Launches: idat.exe -A -S<rikugan/ida/headless_    │
│    │                          bootstrap.py> <binary>       │
│    ▼                                                      │
│  ┌─────────────────────────────────────────────────┐     │
│  │  IDA Process (headless, no Qt)                   │     │
│  │                                                    │     │
│  │  Main Thread                                       │     │
│  │    │                                               │     │
│  │    ├─ headless_bootstrap.main()                   │     │
│  │    │    ├─ RIKUGAN_HEADLESS=1                     │     │
│  │    │    ├─ ida_auto.auto_wait()                   │     │
│  │    │    ├─ IdaHeadlessDispatcher()                │     │
│  │    │    ├─ HeadlessSessionController()            │     │
│  │    │    └─ One-shot: _run_one_shot()               │     │
│  │    │    └─ Server:   _run_server()                │     │
│  │    │                                               │     │
│  │    └─ dispatcher.pump_forever()  ◄── Queue        │     │
│  │         (processes IDA API calls)                  │     │
│  │                                                    │     │
│  │  Background Threads                                 │     │
│  │    ├─ run_prompt() → AgentLoop.run()               │     │
│  │    │    └─ ToolRegistry.execute()                   │     │
│  │    │         └─ dispatcher.wrap(tool) ──► Queue   │     │
│  │    │                                               │     │
│  │    └─ ControlServer.serve_forever()                │     │
│  │         └─ HTTP endpoints (/prompt, /events, ...)  │     │
│  └─────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### One-Shot Mode Sequence

```
User: rikugan-headless ask sample.exe "summarize metadata"
  → CLI discovers IDA executable
  → Writes bootstrap JSON to temp file
  → Sets RIKUGAN_HEADLESS_BOOTSTRAP=<tempfile>
  → Spawns: idat.exe -A -S<rikugan/ida/headless_bootstrap.py> sample.exe
  → headless_bootstrap.main()
     → RIKUGAN_HEADLESS=1
     → ida_auto.auto_wait()
     → Load RikuganConfig
     → Create IdaHeadlessDispatcher
     → Create HeadlessSessionController(dispatcher, ida_ui=False)
     → bg_thread: run_prompt(controller, "summarize metadata")
     → main_thread: dispatcher.pump_once() loop until bg_thread finishes
     → Write result JSON to stdout/output_file
     → idc.qexit(exit_code)
  → CLI reads stdout → prints formatted result
```

### Server Mode Sequence

```
User: rikugan-headless serve sample.exe --ready-file rikugan-ready.json
  → (same IDA launch as one-shot)
  → headless_bootstrap.main()
     → ...
     → Start ControlServer on 127.0.0.1:0
     → Write ready-file: {"url": "http://127.0.0.1:PORT", "token": "..."}
     → main_thread: dispatcher.pump_once() loop until /shutdown
  → External client reads ready-file
     → GET  /health
     → POST /prompt {"prompt": "analyze function 0x401000"}
     → GET  /events?run_id=...&index=0&wait=1  (poll JSON envelope)
     → POST /tool-approval {"run_id": "...", "approved": true}
     → POST /shutdown
```

### Control API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/health` | GET | No | Readiness and running status — no paths, tokens, or provider names |
| `/tools` | GET | Yes | Available tool names and descriptions |
| `/prompt` | POST | Yes | Start a new agent run (`run_id` returned) |
| `/events?run_id=...&index=N&wait=1` | GET | Yes | JSON envelope event poll (long-poll with `wait`, optional `run_id` filter) |
| `/answer` | POST | Yes | Forward user answer to agent question (requires `run_id`) |
| `/tool-approval` | POST | Yes | Forward decision: `{"run_id":"...","decision":"allow|allow_all|deny"}` or `{"run_id":"...","approved":true|false}` |
| `/approval` | POST | Yes | Forward decision: `{"run_id":"...","decision":"approve|deny"}` or `{"run_id":"...","approved":true|false}` |
| `/cancel` | POST | Yes | Cancel the active run (requires `run_id`) |
| `/shutdown` | POST | Yes | Stop server and exit IDA |

### Event Serialization

``TurnEvent.to_dict()`` produces a stable JSON-compatible dict:

```json
{
  "type": "text_delta",
  "text": "This binary appears to...",
  "tool_call_id": "",
  "tool_name": "",
  "turn_number": 1
}
```

All event types include `type` as a string.  Optional fields (`text`,
`tool_name`, `error`, `usage`, `plan_steps`, `metadata`) are included
only when non-empty.

### Concurrency Model (Headless)

```
Main Thread (IDA API)          Background Threads
───────────────────             ──────────────────
dispatcher.pump_forever()       run_prompt()
  │                               ├─ start_agent()
  ├─ pump job from Queue ◄─────── ├─ AgentLoop.run()
  │   └─ execute tool             │    └─ tool call
  ├─ pump job from Queue          │       └─ dispatcher.wrap(tool)
  │   └─ idc.qexit(0)             │          └─ put job on Queue
  │                               │          └─ wait (Event)
  │                               └─ drain events → result
  │
  │                             ControlServer thread
  │                               └─ HTTP request handling
  │                                  ├─ /prompt → start_agent()
  │                                  └─ /events → broker.get_events_since()
  │
  │                             EventBroker thread
  │                               └─ drain runner queue → ring buffer
```

- No cross-thread Qt signals.
- ``IdaHeadlessDispatcher`` uses ``queue.Queue`` + ``threading.Event`` per job.
- ``EventBroker`` drains the runner queue regardless of connected clients.

### UI vs Headless Tool Differences

| Aspect | UI Mode | Headless Mode |
|--------|---------|---------------|
| ``get_cursor_position`` | Returns current cursor EA | Not exposed (requires ``ida_ui``) |
| ``get_current_function`` | Returns current function info | Not exposed (requires ``ida_ui``) |
| ``jump_to`` | Navigates IDA view | Not exposed (requires ``ida_ui``) |
| ``get_name_at`` | Returns name at address | Same (no UI needed) |
| ``get_address_of`` | Returns address of name | Same (no UI needed) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Generic error |
| 2 | Bad CLI arguments |
| 3 | IDA launch/load/bootstrap failure |
| 4 | Provider/config error |
| 5 | Analysis/tool failure |
| 6 | Cancelled |
| 7 | Approval required but unavailable/denied |
| 8 | Server unavailable/auth failed |
