# Fix Thinking Block Parsing: Inline Buffer Instead of QThread

## Problem

The `<think>...</think>` parsing in `chat_view.py` has multiple bugs causing thinking content to appear **after** the assistant output block instead of **before** it.

### Root Cause Chain

1. **Line 311 bug**: `has_think_close = "" in text` is **always `True`** (empty string is in every string). The intended check was `"</think>" in text`.
2. Because `has_think_close` is always `True`, the `elif` branch on line 328 (`elif "<think>" in text and not has_think_close:`) **never executes** — `not has_think_close` is always `False`.
3. The buffering path (`_waiting_think_close = True`) is dead code. The `ThinkingParserThread` is only spawned from that path, so it's effectively **never used**.
4. All text falls through to the `else` branch (line 342), which calls `_split_thinking(text)` on **each individual delta**.
5. When `<think>` and `</think>` arrive in **separate deltas**, `_split_thinking` can't match them because it only sees each delta independently. The `</think>` tag text and post-block content end up rendered as visible assistant text.
6. Even if the buffering path were reachable, spawning a `QThread` per `<think>...</think>` parse is massive overkill — `_split_thinking` is a single regex call taking microseconds. Thread creation overhead is orders of magnitude more expensive.

### What the User Sees

- Thinking content incorrectly appears **after** (below) the assistant output block
- The `</think>` tag text may leak into visible output
- Content after `</think>` may also get swallowed into the thinking block

## Plan

### Files to Modify

| File | Changes |
|------|---------|
| `ui/chat_view.py` | Remove `ThinkingParserThread`, `_on_thinking_parsed`, `_cleanup_parser_thread`, `_parser_thread` attribute, `QThread` import. Replace `_handle_text_event` TEXT_DELTA logic with inline buffer approach. Clean up `clear_chat`, `shutdown`, `TEXT_DONE` references. |
| `tests/test_message_widgets.py` | Delete `TestThinkingParserThread` class (lines 90-160). |

### Files NOT Modified

| File | Why |
|------|-----|
| `ui/message_widgets.py` | `_split_thinking` function is correct — no changes needed |
| `ui/panel_core.py` | No changes needed |
| `ui/qt_compat.py` | No changes needed (removing unused `QThread` from chat_view imports actually reduces dependencies) |

### Detailed Changes

---

#### 1. `ui/chat_view.py` — Remove `ThinkingParserThread` class (lines 52-68)

Delete the entire class. It was a `QThread` wrapping a single regex call — `_split_thinking` runs in microseconds and should be called inline on the main thread.

---

#### 2. `ui/chat_view.py` — Remove unused imports

- Remove `QThread` from qt_compat import (line 33)
- Remove `_split_thinking` needs to move closer (it already imports `_ThinkingBlock`, `_split_thinking` from `message_widgets` on line 6-24)

---

#### 3. `ui/chat_view.py` — Remove `_parser_thread` attribute (line 131)

In `__init__`, delete line 131:
```python
self._parser_thread: ThinkingParserThread | None = None
```

Keep `_think_buffer` and `_waiting_think_close` — they will be used by the new inline logic.

---

#### 4. `ui/chat_view.py` — Remove `_on_thinking_parsed` method (lines 133-143)

Delete entire method. Was only called from `ThinkingParserThread.thinking_ready`.

---

#### 5. `ui/chat_view.py` — Remove `_cleanup_parser_thread` method (lines 145-151)

Delete entire method. Was only called for QThread cleanup.

---

#### 6. `ui/chat_view.py` — Replace `_handle_text_event` TEXT_DELTA logic (lines 307-363)

Replace the broken `if/elif/else` with three clean branches:

**New logic:**

```python
def _handle_text_event(self, event: TurnEvent) -> None:
    self._hide_thinking()
    self._reset_tool_run()
    if event.type == TurnEventType.TEXT_DELTA:
        text = event.text

        if self._waiting_think_close:
            # Buffer text until </think> arrives
            self._think_buffer += text
            if "</think>" in text:
                # Complete — parse accumulated buffer
                thinking_text, visible_text = _split_thinking(self._think_buffer)
                self._waiting_think_close = False
                if thinking_text:
                    if self._message_thinking is None:
                        self._message_thinking = _ThinkingBlock()
                        self._insert_widget(self._message_thinking)
                    self._message_thinking.set_thinking(thinking_text, in_progress=False)
                if visible_text:
                    if self._current_assistant is None:
                        self._current_assistant = AssistantMessageWidget()
                        self._insert_widget(self._current_assistant)
                    self._current_assistant.append_text(visible_text)
        elif "<think>" in text and "</think>" not in text:
            # Opening <think> without closing — start buffering
            self._waiting_think_close = True
            self._think_buffer = text
            thinking_text, visible_text = _split_thinking(text)
            if thinking_text:
                if self._message_thinking is None:
                    self._message_thinking = _ThinkingBlock()
                    self._insert_widget(self._message_thinking)
                self._message_thinking.set_thinking(thinking_text, in_progress=True)
            if visible_text:
                if self._current_assistant is None:
                    self._current_assistant = AssistantMessageWidget()
                    self._insert_widget(self._current_assistant)
                self._current_assistant.append_text(visible_text)
        else:
            # Normal text (no thinking, or complete <think>...</think> in one delta)
            thinking_text, visible_text = _split_thinking(text)
            if thinking_text:
                if self._message_thinking is None:
                    self._message_thinking = _ThinkingBlock()
                    self._insert_widget(self._message_thinking)
                self._message_thinking.set_thinking(thinking_text, in_progress=False)
            if visible_text:
                if self._current_assistant is None:
                    self._current_assistant = AssistantMessageWidget()
                    self._insert_widget(self._current_assistant)
                self._current_assistant.append_text(visible_text)

        self._scroll_to_bottom()
    else:  # TEXT_DONE
        ...
```

**Key design decisions:**
- No thread — `_split_thinking` is a single regex, runs inline on main thread
- When `<think>` opens without `</think>`, all subsequent deltas are **buffered** until `</think>` appears, then parsed together
- Complete `<think>...</think>` blocks within a single delta are handled immediately in the normal path
- `_message_thinking` is inserted at the correct position (before `_current_assistant`) via the normal path's existing logic

---

#### 7. `ui/chat_view.py` — Clean up `TEXT_DONE` path (lines 364-388)

- Remove `self._cleanup_parser_thread()` on line 366
- Keep the rest unchanged — the final `_split_thinking` on the accumulated text correctly finalizes both thinking and visible content

---

#### 8. `ui/chat_view.py` — Clean up `clear_chat` (line 645)

- Remove `self._cleanup_parser_thread()` on line 645
- Keep `self._think_buffer = ""` and `self._waiting_think_close = False`

---

#### 9. `ui/chat_view.py` — Clean up `shutdown` (line 697)

- Remove `self._cleanup_parser_thread()` on line 697

---

#### 10. `tests/test_message_widgets.py` — Delete `TestThinkingParserThread` class (lines 90-160)

The class being tested is removed. Delete lines 90-160 plus the pytest import if no longer needed elsewhere in file (check: `TestAssistantMessageWidgetUI` also uses it, so keep the `import pytest`).

---

### What This Fixes

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Thinking appears after output | `"" in text` always True → dead buffering path → `_split_thinking` called per-delta, can't match cross-delta `<think>`/`</think>` | Inline buffer: accumulate deltas until `</think>`, then parse once |
| `</think>` leaks into visible text | Same as above — individual deltas can't match tags across boundaries | Parsing the full buffered text correctly strips all thinking tags |
| Unnecessary QThread overhead | `ThinkingParserThread` wraps a one-line regex call | Removed entirely — inline call is microseconds |
| Cross-thread Qt signal violation | AGENTS.md specifies no Qt signals across threads | Removed — everything runs inline on main thread |

### Performance

- **Before (if bug were fixed)**: One QThread created/destroyed per thinking block → ~milliseconds overhead per block
- **After**: One inline `_split_thinking()` call per delta (when buffering) or one per complete block → ~microseconds
- **No additional allocations**: `_think_buffer` string is the only buffering state, reused across deltas

### Risk

- **Zero risk**: The code path being removed was effectively dead (unreachable due to `"" in text` bug). The new code is strictly simpler — no threading, no signals, just string accumulation and regex.
- The existing `_split_thinking` function is battle-tested and handles all edge cases (complete blocks, partial blocks, multiple blocks, no blocks, unclosed blocks).
