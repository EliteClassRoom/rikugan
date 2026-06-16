# Rikugan — Performance Audit

**Date:** 2026-06-16
**Scope:** per-turn / per-chunk hot paths across `agent/loop.py`, `tools/registry.py`,
`state/session.py`, `core/sanitize.py`, `core/thread_safety.py`, `ida/dispatch.py`,
and the streaming providers (`providers/*.py`).
**Method:** 6-dimension multi-agent sweep → adversarial verification, then every
high-value finding **re-verified by hand against source** (see "Audit honesty note" at bottom).

---

## TL;DR

**The codebase is in good performance health.** No CRITICAL or HIGH severity issues
were found. The agent loop is **network-bound** (multi-second LLM roundtrips + IDA
main-thread marshalling dominate), not CPU-bound. The findings below are constant-factor
cleanups — worth doing because they sit on the hot path (per-turn / per-tool-result),
but none is a bottleneck today.

Two themes recur: **dead/duplicate work in the provider streaming layer** and
**full-history re-processing every turn**.

---

## Confirmed findings (ranked)

### 1. `registry.py:191` — `deepcopy` of the full tool schema every turn
**Severity:** MEDIUM  ·  **Effort:** small  ·  **Category:** redundant-work

```python
# tools/registry.py
def to_provider_format(self) -> list[dict[str, Any]]:
    with self._lock:
        if self._schema_cache is None:
            self._schema_cache = [t.to_provider_format() for t in self._tools.values() ...]
        import copy                       # ← imported inside the method each call
        return copy.deepcopy(self._schema_cache)   # ← full deep copy of 60+ tool schemas
```

Called once per turn from `loop.py:1424` (`_build_tools_schema`). The schema *build*
is correctly cached, but the cache is deep-copied on every read "so callers can freely
mutate." With 60+ tools, each with nested `properties`/`required` dicts, that's a
non-trivial allocation + recursive walk per turn. It also `import copy` inline.

**Fix:** Either (a) build the list immutably and return a shallow `list(self._schema_cache)`
since the only mutation sites are the schema-filter list-comprehensions in `_build_tools_schema`
(which build a *new* list anyway), or (b) clone-on-write instead of clone-on-read. Move
`import copy` to module top either way.
**Correctness:** safe — no downstream code mutates the returned dicts in place today.

---

### 2. `loop.py:526–571` — full message history minified (up to) twice per turn
**Severity:** MEDIUM  ·  **Effort:** medium  ·  **Category:** redundant-work

```python
# agent/loop.py  _prepare_provider_messages
full_messages = minify_messages(self.session.get_messages_for_provider(context_window=0))  # 539
...
provider_messages = minify_messages(                                                       # 557
    self.session.get_messages_for_provider(context_window=ctx_window, preserve_context=preserve)
)
```

`minify_messages` (`minify.py:39`) calls `copy(msg)` **and** rebuilds every `ToolResult`
for every message. In a long conversation that's two full-history traversals + 2× the
message copies per turn (the line-539 path fires when `token_estimate ≥ 50%` of window).

**Fix:** Minify once on the post-trimmed list. Compute the compaction estimate from the
running `session.token_estimate` without re-traversing, then minify only the final
`provider_messages`. Note `get_messages_for_provider` already returns fresh `Message`
objects via `replace()`/construction in `_truncate_results` / `_sanitize`, so minifying
that single result is sufficient.
**Correctness:** safe — minify is a pure whitespace transform.

---

### 3. `codex_provider.py:568` — O(N²) tool-args accumulation that's used only as a gate
**Severity:** MEDIUM  ·  **Effort:** small  ·  **Category:** allocation

```python
# providers/codex_provider.py
buffers[call_id]["args"] += delta          # 568 — O(N²) string concat per chunk
...
if args and not buffers.get(call_id, {}).get("args"):   # 588 — used ONLY as non-empty gate
```

The accumulated string is **never** used for arg assembly — `loop.py:726` assembles args
from its own `current_tool_arg_parts` via `join`. The buffer is read only as a "have we
streamed any deltas?" gate.

**Fix:** Replace the `args` string with a `seen` boolean:
```python
buffers.setdefault(call_id, {"name": "", "seen": False})
buffers[call_id]["seen"] = True
# gate:
if args and not buffers.get(call_id, {}).get("seen"):
```
**Correctness caveat:** the gate semantics ("emit full args from the done-event only if no
deltas were already streamed") are preserved exactly by the boolean flip. Don't swap in a
join-based string *without* updating the gate, or the empty-args fallback breaks.

---

### 4. `anthropic_provider.py:489,501,521,541` — dead `tool_args_buf` writes
**Severity:** LOW  ·  **Effort:** trivial  ·  **Category:** dead code / allocation

`tool_args_buf` is initialized, accumulated via `+= delta.partial_json` (line 521), and
reset — but **never read anywhere**. Downstream arg assembly is entirely in `loop.py:726`.
Same O(N²) shape as Codex #3, but here it's *pure waste* (no consumer at all).

**Fix:** Delete all four references. `grep` confirms no read consumer exists.
**Correctness:** zero risk — pure deletion, no behavior change, no sanitization impact.

---

### 5. `sanitize.py:189` — redundant second regex scan over already-sanitized text
**Severity:** LOW  ·  **Effort:** trivial  ·  **Category:** redundant-work (hot path)

```python
# core/sanitize.py  strip_injection_markers
for m in reversed(list(_ANTHROPIC_CONTROL_RE.finditer(normalized))):   # 184 — homoglyph-aware, position-preserving
    text = text[: m.start()] + "[FILTERED]" + text[m.end():]
...
text = _ANTHROPIC_CONTROL_RE.sub("[FILTERED]", text)                   # 189 — REDUNDANT
```

After the 184–185 loop, every matchable occurrence is already replaced with the literal
`[FILTERED]` (which doesn't match the regex), so line 189 is a correctness no-op that only
costs a redundant full-text scan. This runs on **every** tool result, MCP response, memory
load, and skill body per turn (up to 50KB each).

**Fix:** Delete line 189 and leave a comment that the homoglyph-aware loop covers all cases
(so a future maintainer doesn't re-add it).
**Correctness caveat (security-sensitive):** the 184–185 loop is *strictly stronger* — it
covers every ASCII match *plus* homoglyph-obfuscated variants that the plain `.sub()` at 189
cannot catch. Removing 189 cannot weaken injection stripping. **Do not** remove the 184–185
loop.

---

## Themes worth fixing as a group (not individual bugs)

1. **Provider streaming accumulates tool-args deltas with `+=`.** The agent loop already
   does correct `list`+`join` accumulation downstream (`loop.py:726`), so provider-level
   string buffers are at best redundant, at worst O(N²). Audit **all** providers
   (anthropic ✓, codex ✓, openai, gemini) and converge on one strategy.

2. **Full-history re-processing every turn.** `minify_messages`, `_estimate_prompt_tokens`,
   and `get_messages_for_provider` (which itself runs `_sanitize` + `_sanitize_assistant_output`
   + `_truncate_results` + `_trim_to_budget`, each an O(n) pass) are composed so that the
   whole history is walked several times per turn. The session already maintains an O(1)
   `token_estimate` running counter — lean on it harder to skip the full re-estimate.

3. **Buffer roles are conflated.** In Codex, one mechanism serves two purposes: *gating*
   (emit full args from done-event?) and *accumulation* (the args themselves). Decoupling
   these (boolean gate vs. accumulation) would prevent the O(N²) class from recurring.

---

## Hot-path reality check (do NOT over-invest here)

- Every finding above is **sub-millisecond per call** on a path dominated by the LLM network
  roundtrip (seconds) and IDA main-thread marshalling. Fix them because they're cheap, clean,
  and on the hot path — not because they'll be felt by the user.
- `_ANTHROPIC_CONTROL_RE` and all sanitize regexes are **already compiled at module load**
  (`sanitize.py:116–119` and the module-level `_..._RE` constants). There is no
  per-call compilation to optimize.
- `_DEFAULT_JOB_TIMEOUT = 30.0` and the dispatcher's per-job `Event`+`Lock` allocation
  (`dispatch.py`) were flagged but are **intentional** — one IDA API call per dispatch is the
  design, and the cost is dwarfed by the marshalled work itself. Not worth changing.

---

# Part 2 — UI layer & dispatch layer (deep read)

Followup read of the two layers the first audit couldn't verify (the base-model
workflow stalled before verifying them). **Every claim below is hand-verified
against source.** The headline finding: **these two layers are already well-optimized** —
the workflow's stalled UI/dispatch claims were mostly **refuted** on close reading.

## UI render path — REFUTED, correctly throttled

The stall log flagged ~8 UI-render concerns (`Per-gated-render full markdown`, `md_to_html
SHA-1 cache key`, `setUpdatesEnabled batching`, `QTimer interval 50ms drains 30 events`,
etc.). On inspection, **the code already implements the defenses a naive reviewer would
demand** — and documents why:

| Concern flagged | Reality (hand-verified) | Verdict |
|---|---|---|
| Full markdown re-render per text delta (O(n²)) | `AssistantMessageWidget.append_text` (message_widgets.py:644) is **time-gated** at `_RENDER_INTERVAL_S = 0.10` (~10fps) + batch-min/max thresholds + unconditional flush above MAX. Caps total render work at O(n)×10fps. | **REFUTED** |
| `md_to_html` recomputed on every render | `_HTML_CACHE` keyed by SHA-1(text, source) (markdown.py). Repeat renders of same text (showEvent, restore, theme change) are O(1) lookups. | **REFUTED** |
| Render cost paid for hidden widgets | `set_text_deferred` (line 664) skips render; pays `md_to_html` **lazily on first showEvent** — inactive-tab messages aren't rendered. | **REFUTED** |
| `QTimer.start(50)` polls too aggressively | 50ms = 20fps poll, but `_poll_events` drains **up to 30 events per tick** inside a single `setUpdatesEnabled(False)`/`(True)` batch (panel_core.py:1362-1374). Comment explicitly: "cuts O(k·n) to O(n) per tick." One tick does the work of 30 naive ones. | **REFUTED** |
| Per-event container re-enable | The whole 30-event batch is wrapped in one `setUpdatesEnabled` pair, so layout invalidation happens **once per tick**, not once per event. | **REFUTED** |

**One genuine nuance (not a bug):** `ThemeManager.themeChanged.connect(self._apply_styles)`
(message_widgets.py:475) re-calls `md_to_html` on theme change because the rendered HTML has
**inline theme colors baked in**. This is intentional and cache-aware (the `_HTML_CACHE` key
includes `source`, so a theme swap doesn't poison it). Not worth changing.

**Net:** UI layer needs no perf work. The design here is the bar the rest of the codebase
should clear — explicit comments tying each optimization to the complexity class it kills.

## Dispatch layer — sound; one minor queue cleanup

`IdaHeadlessDispatcher` (dispatch.py:137-274) marshals every IDA API call from worker threads
to the IDA main thread via a `Queue[_DispatchJob]`. Each call = one thread-sync round-trip.

| Aspect | Verdict | Evidence |
|---|---|---|
| Per-job `Event` + `Lock` allocation | **Acceptable** | One IDA API call per dispatch by design; the alloc (~µs) is dwarfed by the marshalled work. Not worth a pooled design. |
| `_DispatchJob` state machine (`try_claim`/`cancel`/`mark_completed`) | **Correct + necessary** | Prevents the classic "late-but-successful execution after caller gave up" race: a timed-out worker can't double-consume a job the pump already claimed (dispatch.py:190-206). |
| Timeout handling | **Correct** | `_DEFAULT_JOB_TIMEOUT=30s`; worker cancels if still QUEUED, else waits for pump to finish RUNNING job (never signals the event itself — only the pump does). |
| Shutdown wake-up | **Correct** | `request_shutdown` wakes all `_pending_jobs` with `DispatcherShutdownError`; no thread left blocked. |
| `pump_until` processes **one job then returns** (dispatch.py:262-274) | **Minor: latency** | The headless loop (headless_bootstrap.py:269-272) is `while True: pump_until(timeout=1.0); if shutdown: break`. When multiple jobs are queued, the loop does **one job, one shutdown-check, repeat** — but each iteration also re-enters the `get(timeout=1.0)`. With jobs in the queue, `get` returns immediately (no 1s wait), so throughput is fine. The 1.0s only bites on an **empty** queue (idle wait), which is correct backpressure, not a bug. |

**The only real cleanup** (LOW, optional): `_pending_jobs` is a `list` with O(n)
`remove(job)` under `_pending_lock` (dispatch.py:184-188). Under normal load there's at most
a handful of in-flight jobs, so O(n) is trivial. It would only matter if dozens of worker
threads hammered IDA simultaneously — and the single-threaded IDA pump is the real ceiling
there anyway. Leave it unless profiling shows contention.

**Net:** dispatch layer needs no perf work. The state machine is a good piece of concurrent
design — the late-execution guard is exactly the kind of subtle correctness that's easy to
get wrong and they got it right.

## Conclusion for Part 2

Both layers are **net clean**. The first audit's confirmed findings (Part 1) remain the
actionable list. The UI and dispatch claims that the stalled workflow couldn't verify were
the right things to be suspicious of — but the code already handles them. Nothing to fix
here.

---

## Audit honesty note

This audit used a 6-dimension multi-agent workflow (review → adversarial verify → synthesize).
The **base model stalled heavily** under the large fan-out: ~35 distinct findings were flagged
by reviewers, but the verifier stage retried (6× × 180s) then failed for most dimensions, so
only 2 findings reached the workflow's own synthesis. **Every finding in this report was
therefore re-verified by hand against the source code** (file:line cited for each), including
the high-value ones the starved verifiers never confirmed (#1, #2). Findings I could *not*
confirm from source (e.g. some UI-render claims I didn't read in full) were dropped rather
than carried forward on trust.
