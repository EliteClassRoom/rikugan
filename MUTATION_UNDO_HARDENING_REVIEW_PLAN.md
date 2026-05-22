# Mutation Undo Hardening Review Plan

Date: 2026-05-22
Scope reviewed: uncommitted mutation undo hardening changes, especially:
- `tests/agent/test_exploration_loop.py`
- `tests/tools/test_tool_coercion.py`
- `rikugan/agent/loop.py`
- `rikugan/agent/mutation.py`
- `rikugan/tools/registry.py`
- `rikugan/tools/coercion.py`

## Overall assessment

The current changes are directionally correct and substantially improve mutation undo safety:
- Mutating tools now use coerced execution arguments consistently for pre-state capture, execution, reverse-record construction, and post-state verification.
- High-confidence mutating tools now require post-state getter verification before any reversible undo record is appended.
- Non-reversible successful mutations are visible to the UI but do not pollute `_mutation_log`.
- Tests now cover malformed pseudocode JSON, non-dict decoded JSON, `ok=false`, non-string pseudocode comments, whitespace-sensitive comment verification, failed tool results, missing verification getters, and non-reversible UI-only events.

No blocking production bug was found in the reviewed changes. The remaining improvements are test-quality and maintainability hardening.

## Required changes to improve the current patch

### 1. Make the sequential pseudocode getter test helper fail clearly

**File:** `tests/agent/test_exploration_loop.py`

**Current state:**
`_register_pseudocode_comment_tools()` uses:

```python
handler=lambda func_address="", target_address="", it=results_iter: next(it)
```

This works for the current tests because the getter is expected to be called exactly twice: once during pre-state capture and once during post-state verification.

**Problem:**
If a future loop change calls `get_pseudocode_comment_state` an unexpected extra time, the test will fail with a raw `StopIteration` from the helper. That is not self-explanatory and does not prove which assumption broke.

**Plan:**
- Replace the inline `next(it)` lambda with a small nested helper function.
- Track calls in a list or counter.
- If no values remain, raise `AssertionError` with a clear message such as:
  `get_pseudocode_comment_state called more times than expected`.
- Optionally assert after the loop that exactly two getter calls occurred in pseudocode post-state tests.

**Expected benefit:**
Future regressions fail with a meaningful test error instead of an incidental iterator exception.

### 2. Strengthen `ToolRegistry.coerce_arguments_for()` coverage for no-parameter tools

**File:** `tests/tools/test_tool_coercion.py`

**Current state:**
`test_coerce_arguments_returns_fresh_dict()` checks:
- `_coerce_arguments()` returns a fresh dict for empty, non-empty, and unknown-param args.
- `coerce_arguments_for()` returns a fresh dict for empty and non-empty args for a parameterized registered tool.
- `_coerce_arguments()` returns a fresh dict for a no-parameter `ToolDefinition`.

**Problem:**
The user requirement explicitly asked to cover “a no-parameter registered tool returning a fresh dict.” The current no-parameter coverage only checks `_coerce_arguments()` directly, not the registered public path `coerce_arguments_for()`.

**Plan:**
- Register a no-parameter tool under a distinct name, e.g. `no_param_tool`.
- Call `registry.coerce_arguments_for("no_param_tool", empty_args)` where `empty_args = {}`.
- Assert returned dict equals `{}` and is not `empty_args`.
- Avoid using `assertIsNot(ToolRegistry._coerce_arguments(no_param_defn, {}), {})` as the only no-param proof because it compares against a new literal rather than preserving the original input identity.
- Prefer:
  ```python
  no_param_args = {}
  no_param_result = registry.coerce_arguments_for("no_param_tool", no_param_args)
  self.assertEqual(no_param_result, {})
  self.assertIsNot(no_param_result, no_param_args)
  ```

**Expected benefit:**
The test directly proves the public API behavior requested in the review finding.

### 3. Assert mutation event payload consistency in the exact-match comment control test

**File:** `tests/agent/test_exploration_loop.py`

**Current state:**
`test_comment_whitespace_exact_match_is_reversible()` asserts:
- exactly one `MUTATION_RECORDED` event,
- `metadata["reversible"]` is true,
- exactly one `_mutation_log` entry,
- `loop._mutation_log[0].reverse_arguments["comment"] == "old comment"`.

**Improvement:**
Also assert that the UI event reverse payload agrees with the log entry:
- `mutation_events[0].metadata["reverse_tool"] == "set_comment"`
- `mutation_events[0].metadata["reverse_args"]["comment"] == "old comment"`
- `mutation_events[0].metadata["reverse_args"]["repeatable"] is False`

**Expected benefit:**
The test verifies both internal undo state and UI-facing mutation event metadata, preventing a future split-brain regression.

### 4. Add explicit `TOOL_RESULT` / no-`ERROR` assertions to more negative mutation tests

**File:** `tests/agent/test_exploration_loop.py`

**Current state:**
The pseudocode post-state test asserts the mutating tool produced a `TOOL_RESULT` and emitted no `ERROR` event. Some other negative mutation tests only assert no mutation event/log entry.

**Plan:**
For consistency, strengthen these tests with the same proof pattern:
- `test_non_string_pseudocode_comment_matches_coerces_to_fail()`
- `test_comment_whitespace_mismatch_no_reversible_record()`
- `test_non_high_confidence_mutation_failure_no_undo()`
- The two branches inside `test_failed_or_missing_getter_no_reversible_record()`

Add helper(s), for example:
```python
def _assert_tool_result_without_error(self, events: list[TurnEvent], tool_name: str) -> None:
    tool_results = [e for e in events if e.type == TurnEventType.TOOL_RESULT and e.tool_name == tool_name]
    self.assertEqual(len(tool_results), 1)
    self.assertFalse(tool_results[0].tool_is_error)
    self.assertEqual([e for e in events if e.type == TurnEventType.ERROR], [])
```

For tests where the tool result intentionally represents a failure string but is not a `ToolError`, keep `tool_is_error == False` if that is the current behavior; the purpose is to prove the loop did not crash.

**Expected benefit:**
All negative mutation tests prove the important distinction: the tool call completes and returns a result, but mutation recording is safely skipped.

### 5. Consider a small production observability improvement for skipped mutation recording

**File:** `rikugan/agent/loop.py`

**Current state:**
When post-state verification fails, the loop logs a debug message and emits the tool result, but does not expose the verification failure to the UI.

**Assessment:**
This is acceptable for current behavior because avoiding false undo records is the priority. However, users may not know why `/undo` is empty after a successful-looking mutation tool result.

**Optional plan:**
Do not change behavior unless desired. If improved observability is wanted later, add a non-error diagnostic metadata event or enrich debug logs. Avoid emitting an `ERROR` event because the tests intentionally require no `ERROR` event for verification-skip cases.

**Expected benefit:**
Improved troubleshooting without polluting `_mutation_log`.

## Implementation order

1. Update `_register_pseudocode_comment_tools()` in `tests/agent/test_exploration_loop.py` to use a nested getter with explicit call tracking and clear `AssertionError` on overuse.
2. Add a no-parameter registered-tool `coerce_arguments_for()` case to `test_coerce_arguments_returns_fresh_dict()` in `tests/tools/test_tool_coercion.py`.
3. Strengthen `test_comment_whitespace_exact_match_is_reversible()` with UI event reverse payload assertions.
4. Add `_assert_tool_result_without_error()` helper in `TestMutationTracking` and use it in negative mutation tests where appropriate.
5. Run the required focused validation commands.

## Verification commands

Run from repository root `C:\Users\kiennd14\.rikugan`:

```powershell
python -m compileall -q rikugan tests 2>&1
python -m pytest tests/agent/test_exploration_loop.py::TestMutationTracking -q -v 2>&1
python -m pytest tests/tools/test_tool_coercion.py -q 2>&1
python -m pytest tests/agent/test_mutation.py -q 2>&1
python -m pytest tests/agent/test_exploration_loop.py -q 2>&1
python -m pytest tests -q 2>&1
python -m ruff format --check rikugan/agent/loop.py rikugan/agent/mutation.py rikugan/tools/registry.py tests/agent/test_mutation.py tests/tools/test_tool_coercion.py tests/agent/test_exploration_loop.py 2>&1
python -m ruff check rikugan/agent/loop.py rikugan/agent/mutation.py rikugan/tools/registry.py 2>&1
python -m mypy rikugan/core rikugan/providers 2>&1
```

## Notes for the coding agent

- Do not add new test files.
- Prefer strengthening existing helpers and test methods.
- Keep comments and documentation in English.
- Do not modify unrelated files.
- Do not reintroduce Binary Ninja support, docs, skills, examples, tests, imports, or naming traces.
- Only touch source files if a test reveals an actual production bug. Current plan should only require test-file updates.
