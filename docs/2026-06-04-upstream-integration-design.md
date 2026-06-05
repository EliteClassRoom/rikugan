# Upstream Integration Design: buzzer-re/main → local

**Date**: 2026-06-04
**Status**: Approved
**Scope**: IDA Pro only

## What We Skip

- Chat sidebar (ChatThreadList/ChatThreadRow) — large UI, separate effort
- Fuzzy tool name lookup removal (we need it for GLM/MCP)
- `_capabilities.get(req, True)` change (unsafe default)
- Cancel button style changes (cosmetic)
- Script guard simplification (keeping our _guarded_import approach)

## Integration Order

### B1. Stream abort v2 — `_track_request_handle`

**Files**: `rikugan/providers/base.py`, all 4 streaming providers

**Changes**:
- Replace `_active_stream` + `Lock` with `_active_request_handles` list + `RLock`
- Add `_track_request_handle()` context manager
- Rewrite `cancel_current_request()` to iterate handles + close `_client`
- Add `_close_request_handle()` helper
- Add `context_window()` method
- Wrap stream loops in all providers with `_track_request_handle()`

### B2. Pagination module + tool paging

**Files**: New `rikugan/tools/pagination.py`, then 6 IDA tool files

**Changes**:
- Create `pagination.py` with `normalize_page()` + `format_page()`
- Update IDA tools to accept `offset`/`limit` params and use pagination:
  - `rikugan/ida/tools/database.py`: list_imports, list_exports
  - `rikugan/ida/tools/disassembly.py`: read_disassembly, read_function_disassembly
  - `rikugan/ida/tools/xrefs.py`: xrefs_to, xrefs_from
  - `rikugan/ida/tools/decompiler.py`: decompile_function (paginated pseudocode)

### B3. `read_global_value` tool

**Files**: New `rikugan/tools/value_format.py`, `rikugan/ida/tools/database.py`

**Changes**:
- Create `value_format.py` with `format_global_value()` + helpers
- Add `read_global_value` tool in `database.py`
- Register in IDA tool registry

### B4. Model list updates

**Files**: 3 provider files

**Changes**:
- `anthropic_provider.py`: Add claude-opus-4-7, increase output limits, inline billing header
- `gemini_provider.py`: Add gemini-3-pro-preview, gemini-2.5-flash-lite, fix context to 1048576
- `openai_provider.py`: Already updated via stream abort wrap

### B9. Context window from provider

**Files**: `rikugan/providers/base.py`, `rikugan/agent/loop.py`

**Changes**:
- Add `context_window()` method to `LLMProvider` base
- Replace `config.provider.context_window` with `self.provider.context_window()` in loop

### B6. `finish_reason` propagation

**Files**: `rikugan/agent/loop.py`, `rikugan/agent/modes/turn_helpers.py`, `rikugan/agent/modes/plan.py`

**Changes**:
- `_stream_llm_turn()` and `_stream_llm_turn_inner()` return 5-tuple with `finish_reason`
- Add `finish_reason` to `TurnResult` dataclass
- Add `finish_reason_notice()` function in `turn_helpers.py`
- Propagate through normal loop and plan mode

### B7. Session state refactor

**Files**: `rikugan/core/types.py`, `rikugan/state/session.py`, `rikugan/agent/loop.py`

**Changes**:
- Move `INTERNAL_EVENT_KEY` from `types.py` to `session.py`
- Change value from `"internal"` to `"rikugan_event"` + add `INTERNAL_EVENT_CANCELLED = "cancelled"`
- Internal event messages: token estimate = 0
- Fix indentation bug in `get_messages_for_provider()`

### B10. Minor improvements

**Files**: `rikugan/agent/loop.py`, `rikugan/tools/registry.py`

**Changes**:
- `cancel()`: getattr + callable pattern
- `_record_cancelled_message()`: extracted method
- `_estimate_prompt_tokens()`: str() instead of json.dumps()
- `_accumulate_chunk_usage()`: remove redundant `or 0`
- Tool registry truncation hint
- Ask user: simplify options normalization

### B5. Schema inline (last — lowest priority)

**Files**: `rikugan/agent/loop.py`, delete `rikugan/agent/pseudo_tool_schemas.py`

**Changes**:
- Move 6 schema dicts into `loop.py` as module-level constants
- Delete `pseudo_tool_schemas.py`
- Update imports and references
