# Rikugan Detailed Review and Implementation Plan

## Scope and review date

Reviewed current uncommitted working tree under `C:\Users\kiennd14\.rikugan` on 2026-05-25.

The previous plan in this file was stale: the original five provider/bulk-renamer review fixes are now present in the working tree, including the startup enumeration cleanup in `rikugan/ui/panel_core.py`. This document replaces that stale plan with a broader detailed review of the current diff.

Current diff scope at review time includes these tracked files:

- `rikugan/core/config.py`
- `rikugan/ida/tools/functions.py`
- `rikugan/ida/tools/registry.py`
- `rikugan/ida/ui/panel.py`
- `rikugan/ida/ui/session_controller.py`
- `rikugan/mcp/bridge.py`
- `rikugan/mcp/client.py`
- `rikugan/mcp/manager.py`
- `rikugan/providers/auth_cache.py`
- `rikugan/providers/registry.py`
- `rikugan/skills/loader.py`
- `rikugan/state/history.py`
- `rikugan/tools/__init__.py`
- `rikugan/tools/registry.py`
- `rikugan/tools/web.py`
- `rikugan/tools/web_fetch.py`
- `rikugan/ui/bulk_renamer.py`
- `rikugan/ui/panel_core.py`
- `rikugan/ui/qt_compat.py`
- `rikugan/ui/session_controller_base.py`
- `rikugan_plugin.py`

Current untracked files at review time:

- `.kilo/fixing-plan.md`
- `rikugan/core/startup_timing.py`

## Project rules and constraints to preserve

- Do not add test cases unless the project owner explicitly lifts the no-test-cases rule.
- Do not commit.
- Do not run `git add`.
- Do not add IDA imports to host-agnostic code.
- All IDA API imports should use `importlib.import_module()` inside `try/except ImportError` where possible.
- Do not use cross-thread Qt signals.
- Do not call IDA APIs from arbitrary background threads.
- Do not silently swallow failures; log failures with `log_error`, `log_warning`, or another appropriate project logger.
- Keep comments and docs in English.
- Do not rewrite unrelated code.
- Existing unrelated modified files may remain; do not clean them up unless directly necessary for these findings.

## Already verified fixes that must remain present

These original fixes were checked and should not be regressed:

1. `rikugan/providers/registry.py`: `ProviderRegistry.register_custom_providers()` skips built-in provider names with `if name in _BUILTIN_PROVIDER_SPECS: continue` before `_registered_names` and before `_openai_compat_names.add(name)`.
2. `rikugan/ui/panel_core.py`: `_renamer_chunk_step()` starts with safe `timer = getattr(self, "_renamer_chunk_timer", None)` and returns when `timer is None`.
3. `rikugan/ui/panel_core.py`: `_renamer_chunk_step()` wraps `self._ctrl.next_function_chunk(limit)` failure in nested `try/except/finally`, logs widget restoration failures, and always calls `_cleanup_renamer_chunk(cancel_controller=True)` in `finally`.
4. `rikugan/ui/bulk_renamer.py`: `BulkRenamerWidget.fail_function_load()` calls `self._cancel_chunked_load()` first.
5. `rikugan/ui/panel_core.py`: `_load_renamer_functions()` startup failure now logs widget restoration failures and always calls `_cleanup_renamer_chunk(cancel_controller=True)` in `finally`.

Regression smoke command already expected to pass:

```powershell
python -c "import sys; from rikugan.providers.registry import ProviderRegistry; r=ProviderRegistry(); r.register_custom_providers(['anthropic', 'custom-compatible']); p=r.new_instance('anthropic', api_key='sk-test', model='claude-test'); print('rikugan.providers.openai_compat' in sys.modules); print('custom-compatible' in r.list_providers())"
```

Expected output:

```text
False
True
```

---

# Priority 0: Critical/high fixes before merge

## P0.1 Fix `BulkRenamerWidget._populate_rows()` indexing regression

### Severity

High.

### Files and functions

- `rikugan/ui/bulk_renamer.py`
- `BulkRenamerWidget.load_functions()`
- `BulkRenamerWidget._load_next_chunk()`
- `BulkRenamerWidget.append_function_chunk()`
- `BulkRenamerWidget._populate_rows()`

### Current problem

`_populate_rows()` currently uses chunk-relative indexing:

```python
func = functions[row - start]
```

This is correct for `append_function_chunk(chunk)`, where the passed `functions` argument is only the current chunk and `start` is the table row offset.

It is incorrect for the existing widget-side chunked `load_functions(functions)` path. For large lists, `_load_next_chunk()` passes the full pending list plus a nonzero `start`:

```python
funcs = self._pending_functions
start = self._load_cursor
end = min(start + self._LOAD_CHUNK_SIZE, len(funcs))
self._populate_rows(funcs, start, end)
```

For the second chunk, `start == 200`, so `_populate_rows()` reads `functions[0]`, `functions[1]`, etc. again instead of `functions[200]`, `functions[201]`, etc.

### Reproduction reasoning

Calling `widget.load_functions()` with 401 entries should produce row addresses `0..400`. Current code produces `0..199`, then repeats `0..199`, then repeats `0` for the final row.

Consequences:

- Missing tail functions.
- Duplicate rows.
- `_addr_to_entry` overwritten for duplicate addresses.
- Rename jobs can target wrong or incomplete function sets.
- Sorting/filtering operates on corrupted table data.

### Required implementation

Make the data indexing explicit so both caller shapes work. Recommended minimal approach:

```python
def _populate_rows(
    self,
    functions: list[dict],
    start: int,
    end: int,
    source_start: int = 0,
) -> None:
    for row in range(start, end):
        func = functions[row - source_start]
        ...
```

Then call it as follows:

```python
# Full-list paths:
self._populate_rows(functions, 0, len(functions), source_start=0)
self._populate_rows(funcs, start, end, source_start=0)

# External chunk path:
self._populate_rows(chunk, start, start + len(chunk), source_start=start)
```

Alternative acceptable implementation: split the helper into two helpers, one for full-list absolute indexing and one for chunk-relative indexing. The important requirement is that `load_functions()` with a list longer than `_LOAD_CHUNK_SIZE` no longer repeats the first chunk.

---

## P0.2 Ensure advanced tools are registered before bulk renamer starts

### Severity

High.

### Files and functions

- `rikugan/ui/session_controller_base.py`
- `SessionControllerBase.start_agent()`
- `SessionControllerBase` new method to add
- `rikugan/ui/panel_core.py`
- `RikuganPanelCore._get_or_create_renamer_engine()` or `_on_renamer_start()`
- `rikugan/ida/tools/registry.py`

### Current problem

Advanced IDA tools are now deferred until `SessionControllerBase.start_agent()` runs. However, the bulk renamer does not start through `start_agent()`. It creates `BulkRenamerEngine` directly with `self._ctrl.get_tool_registry()`.

`BulkRenamerEngine.preload_decompilation()` needs `decompile_function`, which comes from the advanced module `rikugan.ida.tools.decompiler`. If the user opens Bulk Renamer and starts it before sending a normal chat prompt, `decompile_function` may not be registered.

### Required implementation

Extract the advanced-tool registration logic currently embedded in `start_agent()` into a public/shared controller method, for example:

```python
def ensure_advanced_tools_ready(self) -> bool:
    """Ensure deferred advanced tools are registered. Return True when no known failures remain."""
    if self._advanced_tools_registered:
        return True
    if self._ensure_tools_ready is None:
        self._advanced_tools_registered = True
        return True
    try:
        result = self._ensure_tools_ready(self._tool_registry)
        if not result.ok:
            log_warning(...)
            return False
        self._advanced_tools_registered = True
        log_info(...)
        return True
    except Exception as e:
        log_warning(f"Advanced tool registration failed: {e}")
        return False
```

Then replace the duplicated logic in `start_agent()` with a call to this method.

Before creating or starting the renamer engine, call the method. If registration fails and `decompile_function` is still missing, do not silently proceed. Show/log a user-visible or at least logged error that bulk renaming cannot start because required tools are unavailable.

### Important constraints

- Do not import IDA modules in `SessionControllerBase`.
- Keep host-specific registration provided via callback.
- Preserve retry behavior for failed advanced modules.

---

## P0.3 Fix bulk-renamer preload deadlock caused by `ToolRegistry.execute()` from IDA main thread

### Severity

High.

### Files and functions

- `rikugan/ui/panel_core.py`
- `RikuganPanelCore._on_renamer_start()`
- `rikugan/agent/bulk_renamer.py`
- `BulkRenamerEngine.preload_decompilation()`
- `rikugan/tools/registry.py`
- `ToolRegistry.execute()`
- `rikugan/core/thread_safety.py`
- `idasync()`

### Current problem

`_on_renamer_start()` schedules `engine.preload_decompilation()` via `QTimer.singleShot(0, ...)`, so it runs on the Qt/IDA main thread. But `preload_decompilation()` calls `self._tools.execute("decompile_function", ...)`. `ToolRegistry.execute()` submits the handler to a worker thread and waits on `future.result()`. IDA handlers are wrapped in `idasync`; the worker thread calls `ida_kernwin.execute_sync()` and waits for the main thread. The main thread is already blocked waiting for the worker future. This can deadlock.

### Required implementation options

Choose one minimal safe approach:

1. Add direct current-thread execution API in `ToolRegistry` and use it for preload when knowingly on the IDA/UI thread.
2. Move preload off the main thread and let `idasync` marshal individual IDA API calls while the Qt event loop remains free.
3. Add an IDA-specific controller/helper preload path that performs direct IDA calls on the UI thread without `ToolRegistry.execute()`.

Requirements:

- Do not call IDA APIs directly from arbitrary background threads.
- Do not block the IDA main thread waiting for a worker that needs `execute_sync`.
- Preserve timeout/error behavior where possible.
- Log failures.

---

## P0.4 Fix session manifest unknown-file and read-only restore regressions

### Severity

High.

### Files and functions

- `rikugan/state/history.py`
- `SessionHistory.save_session()`
- `SessionHistory._update_manifest_entry()`
- `SessionHistory._write_manifest()`
- `SessionHistory._rebuild_manifest()`
- `SessionHistory.list_sessions()`

### Current problems

The new session manifest improves startup performance, but introduces persistence/recovery regressions.

1. If `_session_manifest.json` exists with `last_full_scan > 0`, `list_sessions()` trusts it and iterates only manifest entries. It does not detect valid `*.json` session files absent from the manifest.
2. If no manifest exists, `list_sessions()` calls `_rebuild_manifest()`, which unconditionally writes the manifest. If the directory is read-only or manifest write is blocked, listing/restoring fails even though JSON files are readable.
3. `_update_manifest_entry()` reads manifest, modifies entries, and writes it back with no lock. Concurrent saves can lose entries.

### Required implementation

Minimum safe changes:

1. Add unknown-file detection before trusting a non-empty manifest:

```python
try:
    json_ids = {
        fname[:-5]
        for fname in os.listdir(self._dir)
        if fname.endswith(".json") and fname != MANIFEST_FILE
    }
except OSError as e:
    log_warning(f"Failed to scan sessions directory for manifest validation: {e}")
    json_ids = set()
if json_ids and not json_ids.issubset(set(entries.keys())):
    need_rebuild = True
```

2. Make `_rebuild_manifest()` recovery-first and manifest-write best-effort: scan and return entries even if writing `_session_manifest.json` fails.
3. Make manifest update failure after successful session JSON write non-fatal to the saved session. Log a warning.
4. Add at least a process-local class-level `threading.RLock()` around manifest read-modify-write operations.
5. Prefer validating stale known entries before filtering, or otherwise ensure stale entries outside the current filter are eventually repaired.

Requirements:

- Listing sessions should return readable JSON sessions even when the manifest cannot be written.
- A successfully written session JSON must not become unrecoverable because manifest update failed.
- Manifest should remain an optimization, not the source of truth.

---

## P0.5 Restore provider model updates and `get_instance()` compatibility

### Severity

High for model update; medium for public API compatibility.

### Files and functions

- `rikugan/providers/registry.py`
- `ProviderRegistry.get_or_create()`
- `ProviderRegistry.get_instance()` method to restore

### Current problems

`get_or_create()` now returns cached provider immediately when API key and normalized API base match. Previous behavior updated `cached.model` when only the model changed. Current behavior can keep sending requests with the old model after a settings model switch.

`ProviderRegistry.get_instance(name)` existed before and returned cached instances. It is no longer present. Internal code may not call it, but external integrations/tests/plugins may.

### Required implementation

Restore model update behavior:

```python
if normalized_new == normalized_old and api_key == cached.api_key:
    if model and cached.model != model:
        cached.model = model
    return cached
```

Restore public API:

```python
def get_instance(self, name: str) -> LLMProvider | None:
    return self._instances.get(name)
```

Do not import provider modules for `get_instance()`.

---

# Priority 1: Important correctness and lifecycle fixes

## P1.1 Fix settings dialog custom-provider registration call

### Severity

Medium.

### Files and functions

- `rikugan/ui/settings_dialog.py`
- `SettingsDialog._on_add_custom_provider()`
- `rikugan/providers/registry.py`
- `ProviderRegistry.register_custom_providers()`

### Current problem

`register_custom_providers()` now has synchronizing semantics: providers absent from the passed list are removed if config-managed. But `_on_add_custom_provider()` still calls:

```python
self._registry.register_custom_providers([name])
```

This can unregister previously configured custom providers from the dialog registry during the same settings session.

### Required implementation

After adding the provider to config, pass the full current custom-provider set:

```python
self._registry.register_custom_providers(list(self._config.custom_providers.keys()))
```

---

## P1.2 Add default function enumeration cursor APIs to `SessionControllerBase`

### Severity

Medium.

### Files and functions

- `rikugan/ui/session_controller_base.py`
- `SessionControllerBase`
- `rikugan/ui/panel_core.py`
- `_load_renamer_functions()`

### Current problem

Shared `panel_core.py` now assumes controllers implement:

- `begin_function_enumeration()`
- `next_function_chunk(limit)`
- `cancel_function_enumeration()`

`IdaSessionController` implements these, but `SessionControllerBase` does not. Non-IDA hosts or test controllers can hit an AttributeError and show a failure instead of an empty renamer list.

### Required implementation

Add no-op defaults to `SessionControllerBase`:

```python
def begin_function_enumeration(self) -> None:
    pass

def next_function_chunk(self, limit: int) -> tuple[list[dict], bool]:
    return [], False

def cancel_function_enumeration(self) -> None:
    pass
```

Keep them host-agnostic and free of IDA imports.

---

## P1.3 Clean up renamer and tools timers during shutdown

### Severity

Medium.

### Files and functions

- `rikugan/ui/panel_core.py`
- `RikuganPanelCore.shutdown()`
- `_cleanup_renamer_chunk()`
- `_renamer_chunk_step()`
- `_poll_tools_events()`

### Current problem

`shutdown()` does not explicitly stop `_renamer_chunk_timer` or `_tools_poll_timer`. The renamer timer can continue into widget/controller teardown and call into `_bulk_renamer` or IDA enumeration after shutdown starts.

### Required implementation

At the beginning of `shutdown()` after setting `_is_shutdown`, call:

```python
self._cleanup_renamer_chunk(cancel_controller=True, cancel_widget=True)
self._stop_tools_poll_timer()
```

Add helper:

```python
def _stop_tools_poll_timer(self) -> None:
    timer = getattr(self, "_tools_poll_timer", None)
    if timer is not None:
        timer.stop()
        timer.deleteLater()
        self._tools_poll_timer = None
```

Also guard `_renamer_chunk_step()`:

```python
if self._is_shutdown:
    self._cleanup_renamer_chunk(cancel_controller=True)
    return
```

If a renamer engine can be active during shutdown, cancel it as well.

---

## P1.4 Clear/cancel bulk-renamer state on database changes

### Severity

Medium.

### Files and functions

- `rikugan/ui/panel_core.py`
- `RikuganPanelCore.on_database_changed()`
- `RikuganPanelCore._cleanup_renamer_chunk()`
- `BulkRenamerWidget` optional new `clear_functions()`

### Current problem

When the IDB/database changes, chat/session state resets, but bulk-renamer state may still show functions from the old database. Active enumeration or an active renamer engine may also continue.

### Required implementation

In `on_database_changed()`:

1. Cancel active renamer enumeration:

```python
self._cleanup_renamer_chunk(cancel_controller=True, cancel_widget=True)
```

2. Cancel and reset active bulk renamer engine if present.
3. Clear the widget table. Prefer adding a dedicated `BulkRenamerWidget.clear_functions()` method that cancels widget timers, clears rows/maps, restores loading state, and updates selection count.
4. If tools are initialized and the new DB is ready, schedule reload with `QTimer.singleShot(0, self._load_renamer_functions)`.

---

## P1.5 Disable or safely handle Refresh while bulk renamer job is running

### Severity

Low/medium.

### Files and functions

- `rikugan/ui/bulk_renamer.py`
- Refresh button setup and running-state methods
- `rikugan/ui/panel_core.py`
- `_load_renamer_functions()`
- `_on_renamer_start()`
- `_on_renamer_cancel()` / completion handling

### Current problem

The new Refresh button can be clicked while a renamer engine is running. It can clear/repopulate the table while engine events are still updating rows by address, creating inconsistent UI state.

### Required implementation

Choose one:

- Disable Refresh while a renamer job is active; re-enable on cancel/completion.
- Or make Refresh explicitly cancel the active engine before clearing/reloading.

Recommended widget API:

```python
def set_refresh_enabled(self, enabled: bool) -> None:
    self._refresh_btn.setEnabled(enabled)
```

Use it when starting, stopping, and completing jobs.

---

## P1.6 Reapply filters and reset header checkbox after loading functions

### Severity

Low/medium.

### Files and functions

- `rikugan/ui/bulk_renamer.py`
- `begin_function_load()`
- `load_functions()`
- `_finish_load()`

### Current problems

- `_on_filter_changed()` returns while `_loading` is true. If the user types a filter during loading, the filter is not applied after finish.
- Header checkbox state can remain checked across refresh even though new rows are only partially selected by auto-name/import heuristics.

### Required implementation

1. In load start paths, reset header checkbox without toggling rows:

```python
self._header_check.blockSignals(True)
self._header_check.setChecked(False)
self._header_check.blockSignals(False)
```

2. In `_finish_load()` after `_restore_after_load("")`, call:

```python
self._on_filter_changed()
self._update_selection_count()
```

Ensure `_restore_after_load()` sets `_loading = False` before `_on_filter_changed()`.

---

## P1.7 Harden `auth_cache` consent/cache races

### Severity

Low/medium.

### Files and functions

- `rikugan/providers/auth_cache.py`
- `set_keychain_consent()`
- `resolve_auth_cached()`
- `invalidate_cache()`

### Current problem

`_cached_oauth` and `_keychain_consent` are unsynchronized globals. Startup OAuth warm-up can resolve/cache a keychain OAuth token while the user revokes consent, leaving cached credentials available after consent is revoked.

### Required implementation

Add lock and generation tracking:

```python
_lock = threading.Lock()
_consent_generation = 0
```

Pattern:

1. Snapshot consent and generation under lock.
2. Resolve outside lock.
3. Reacquire lock before caching.
4. Cache only if generation and consent still match.
5. Returning cached keychain-derived OAuth should only happen when current consent permits it.

Avoid holding the lock while spawning subprocesses or doing slow auth resolution.

---

# Priority 2: Infrastructure, compatibility, and instrumentation hardening

## P2.1 Fix MCP manager generation/config locking races

### Severity

Medium.

### Files and functions

- `rikugan/mcp/manager.py`
- `load_config()`
- `add_external_configs()`
- `start_servers()`
- `_start_one()`
- `reload()`
- `shutdown()`

### Current problems

1. `_configs` is read and mutated without consistently holding `_lock`.
2. `_start_one()` stores a client after checking generation, then registers tools outside the lock. A reload/shutdown can occur between the generation check and tool registration, allowing stale MCP tools to be registered after unregister/reload.

### Required implementation

- Protect `_configs` access with `_lock`.
- In `start_servers()`, snapshot enabled configs under lock and iterate the snapshot.
- Re-check generation immediately before and after `register_mcp_tools()`.
- If generation changed after registration, unregister stale tools and stop the client.
- Ideally use exact registered tool names or server-specific prefixes for cleanup.

---

## P2.2 Fix startup timing flush lifecycle and lock races

### Severity

Medium.

### Files and functions

- `rikugan/core/startup_timing.py`
- `rikugan_plugin.py`
- `rikugan/ui/session_controller_base.py`

### Current problems

1. `rikugan_plugin.py` flushes startup timing immediately after `panel.show()`, while background runtime init may still be running. Runtime timing records can be dropped or stranded.
2. `_StartupSession.end()` checks `_flushed` outside the lock and can append after flush due to races.
3. `count()` and `set_metadata()` append even after flush.

### Required implementation

Choose a clear report lifecycle:

- Option A: keep one UI-startup report and add a second runtime-init report after runtime init completes.
- Option B: defer flush until runtime init finishes or a timeout expires.
- Option C: keep immediate flush but do not claim it includes runtime phases; ensure late metadata is ignored or separately flushed.

Also fix locking:

- Check `_flushed` under `_lock` in `start()`, `end()`, `count()`, and `set_metadata()`.
- Recheck before appending records.
- Make `count()`/`set_metadata()` no-op after flush unless a second-report design is implemented.

Do not silently swallow flush failures. Current plugin swallows `_flush_timing()` exceptions; log to IDA output or stderr if possible.

---

## P2.3 Reset advanced tool failed-module cache on settings reload

### Severity

Medium.

### Files and functions

- `rikugan/ida/tools/registry.py`
- `reset_failed_advanced_modules()`
- `rikugan/ui/session_controller_base.py`
- `update_settings()`
- `rikugan/ida/ui/session_controller.py`

### Current problem

`reset_failed_advanced_modules()` exists, but `SessionControllerBase.update_settings()` only sets `_advanced_tools_registered = False`. If `_failed_advanced_modules` is non-empty, the next registration attempt retries only failed modules and does not refresh successful advanced modules after settings/environment changes.

### Required implementation

Preserve host-agnostic layering. Do not import `rikugan.ida.*` from shared `SessionControllerBase`.

Recommended: add optional callback to `SessionControllerBase`, e.g. `reset_deferred_tools: Callable[[], None] | None`, pass `reset_failed_advanced_modules` from `IdaSessionController`, and call it in `update_settings()` before setting `_advanced_tools_registered = False`.

---

## P2.4 Preserve lazy module compatibility for `rikugan.tools.web` and `web_fetch`

### Severity

Low/medium.

### Files and functions

- `rikugan/tools/__init__.py`

### Current problem

`rikugan.tools.__all__` no longer includes `web` and `web_fetch`, and `import rikugan.tools; rikugan.tools.web` no longer works unless something else imported the submodule. This may break external integrations or tests.

### Required implementation

Preserve lazy imports using module-level `__getattr__`:

```python
def __getattr__(name: str):
    if name in {"web", "web_fetch"}:
        import importlib
        mod = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = mod
        return mod
    raise AttributeError(name)

__all__ = ["base", "functions", "web", "web_fetch"]
```

Do not eagerly import `web` or `web_fetch`.

---

## P2.5 Make skill frontmatter lazy reader match previous parser behavior

### Severity

Medium for skill metadata compatibility; low for the doubled newline detail.

### Files and functions

- `rikugan/skills/loader.py`
- `_read_frontmatter_only()`
- `discover_skills()`

### Current problems

1. Previous `_split_frontmatter()` tolerated leading BOM/newlines with `text.lstrip("\ufeff\n")`. New `_read_frontmatter_only()` only checks the first physical line. Skills with leading blank lines before `---` lose metadata.
2. `_read_frontmatter_only()` appends lines including newline characters and then joins with `"\n"`, creating extra blank lines.

### Required implementation

Make `_read_frontmatter_only()` skip leading blank lines and BOM before detecting the opening marker, while still reading only until closing `---`.

Use either:

```python
lines.append(line.rstrip("\n"))
return "\n".join(lines)
```

or:

```python
return "".join(lines)
```

Do not return doubled newlines.

---

## P2.6 Do not permanently suppress bootstrap file logging after one `_log()` import failure

### Severity

Low/medium.

### Files and functions

- `rikugan_plugin.py`
- `_log()`

### Current problem

`_log()` caches `_LOG_TRIED` after the first failure to import `rikugan.core.logging`, then never retries. Early import failure can be transient; later logs should retry once logging is available.

### Required implementation

Cache successful imports only. On failure, write to stderr/IDA output but do not store a permanent sentinel. If avoiding repeated imports is important, use short backoff rather than permanent suppression.

---

## Verification commands

Run from workspace root `C:\Users\kiennd14\.rikugan` after implementation.

### Syntax compile for touched/critical files

```powershell
python -m py_compile "rikugan\providers\registry.py" "rikugan\providers\auth_cache.py" "rikugan\state\history.py" "rikugan\skills\loader.py" "rikugan\mcp\manager.py" "rikugan\tools\__init__.py" "rikugan\tools\registry.py" "rikugan\ui\bulk_renamer.py" "rikugan\ui\panel_core.py" "rikugan\ui\session_controller_base.py" "rikugan\ida\ui\session_controller.py" "rikugan\ida\tools\registry.py" "rikugan_plugin.py" "rikugan\core\startup_timing.py"
```

Expected output: no output.

### Provider lazy-import smoke test

```powershell
python -c "import sys; from rikugan.providers.registry import ProviderRegistry; r=ProviderRegistry(); r.register_custom_providers(['anthropic', 'custom-compatible']); p=r.new_instance('anthropic', api_key='sk-test', model='claude-test'); print('rikugan.providers.openai_compat' in sys.modules); print('custom-compatible' in r.list_providers())"
```

Expected output:

```text
False
True
```

### Provider model cache smoke test

```powershell
python -c "from rikugan.providers.registry import ProviderRegistry; r=ProviderRegistry(); p=r.get_or_create('anthropic', api_key='sk-test', model='model-a'); q=r.get_or_create('anthropic', api_key='sk-test', model='model-b'); print(p is q); print(q.model)"
```

Expected output:

```text
True
model-b
```

### Tools package lazy compatibility smoke test

```powershell
python -c "import sys, rikugan.tools; print('rikugan.tools.web' in sys.modules); mod = rikugan.tools.web; print(mod.__name__); print('rikugan.tools.web' in sys.modules)"
```

Expected output:

```text
False
rikugan.tools.web
True
```

### Diff/status inspection

```powershell
git diff --check
git diff -- rikugan/providers/registry.py rikugan/providers/auth_cache.py rikugan/state/history.py rikugan/skills/loader.py rikugan/mcp/manager.py rikugan/tools/__init__.py rikugan/tools/registry.py rikugan/ui/bulk_renamer.py rikugan/ui/panel_core.py rikugan/ui/session_controller_base.py rikugan/ida/ui/session_controller.py rikugan/ida/tools/registry.py rikugan_plugin.py rikugan/core/startup_timing.py
git status --short
```

Expected:

- No whitespace errors from `git diff --check`.
- Only intended changes in the listed files.
- No staged files.
- No commits.

---

# Ready-to-use coding agent prompt

Use this prompt for the next coding agent:

```text
You are working in C:\Users\kiennd14\.rikugan.

First, read `.kilo/fixing-plan.md` completely before editing any source code. It contains a detailed review and implementation plan for the current uncommitted working tree.

Preserve all project rules:
- Do not add test cases unless explicitly authorized.
- Do not commit.
- Do not run git add.
- Do not add IDA imports to host-agnostic code.
- Use importlib.import_module() inside try/except ImportError for IDA API imports where possible.
- Do not use cross-thread Qt signals.
- Do not call IDA APIs from arbitrary background threads.
- Do not silently swallow failures; log them with log_error/log_warning/log_debug as appropriate.
- Keep comments/docs in English.
- Do not rewrite unrelated code.

Primary implementation goals, in priority order:

1. Fix `BulkRenamerWidget._populate_rows()` so both `load_functions()` widget-side chunking and `append_function_chunk()` external chunking index the correct function records. The current code repeats the first chunk for lists larger than `_LOAD_CHUNK_SIZE`.
2. Extract/introduce `SessionControllerBase.ensure_advanced_tools_ready()` and call it before bulk renamer startup so `decompile_function` is registered even if no chat prompt was sent.
3. Fix the bulk-renamer preload deadlock: do not call `ToolRegistry.execute()` from the IDA main thread in a way that blocks while `idasync` needs the same main thread. Choose the smallest safe direct-execution or background-preload design described in the plan.
4. Fix `SessionHistory` manifest reliability: unknown JSON detection, read-only listing fallback, best-effort manifest writes after successful session save, process-local manifest locking, and stale-entry validation improvements.
5. Restore provider cache model updates and restore `ProviderRegistry.get_instance()`.
6. Fix `SettingsDialog._on_add_custom_provider()` to pass the full custom provider set to `register_custom_providers()`.
7. Add default no-op function enumeration cursor methods to `SessionControllerBase`.
8. Stop renamer chunk and tools poll timers during `RikuganPanelCore.shutdown()`, guard renamer chunk callbacks during shutdown, and cancel/clear/reload bulk-renamer state on database changes.
9. Disable or safely handle Refresh while a bulk renamer job is active; reapply filters and reset the header checkbox after function loading.
10. Harden `auth_cache` consent/cache races with locking and generation checks.
11. Harden MCP manager config/generation races.
12. Fix startup timing flush lifecycle/locking, preserving useful runtime timing or clearly separating UI and runtime reports.
13. Reset deferred advanced-tool failed-module cache on settings reload without importing IDA modules from host-agnostic code.
14. Preserve lazy compatibility for `rikugan.tools.web` and `rikugan.tools.web_fetch` via `__getattr__` and `__all__` without eager imports.
15. Make `_read_frontmatter_only()` tolerate leading blank lines/BOM like the old parser and avoid doubled newlines.
16. Do not permanently suppress bootstrap debug-file logging after one transient `_log()` import failure.

After changes, run these commands from `C:\Users\kiennd14\.rikugan` and report exact outputs:

1. `python -m py_compile "rikugan\providers\registry.py" "rikugan\providers\auth_cache.py" "rikugan\state\history.py" "rikugan\skills\loader.py" "rikugan\mcp\manager.py" "rikugan\tools\__init__.py" "rikugan\tools\registry.py" "rikugan\ui\bulk_renamer.py" "rikugan\ui\panel_core.py" "rikugan\ui\session_controller_base.py" "rikugan\ida\ui\session_controller.py" "rikugan\ida\tools\registry.py" "rikugan_plugin.py" "rikugan\core\startup_timing.py"`
2. `python -c "import sys; from rikugan.providers.registry import ProviderRegistry; r=ProviderRegistry(); r.register_custom_providers(['anthropic', 'custom-compatible']); p=r.new_instance('anthropic', api_key='sk-test', model='claude-test'); print('rikugan.providers.openai_compat' in sys.modules); print('custom-compatible' in r.list_providers())"`
3. `python -c "from rikugan.providers.registry import ProviderRegistry; r=ProviderRegistry(); p=r.get_or_create('anthropic', api_key='sk-test', model='model-a'); q=r.get_or_create('anthropic', api_key='sk-test', model='model-b'); print(p is q); print(q.model)"`
4. `python -c "import sys, rikugan.tools; print('rikugan.tools.web' in sys.modules); mod = rikugan.tools.web; print(mod.__name__); print('rikugan.tools.web' in sys.modules)"`
5. `git diff --check`
6. `git diff -- rikugan/providers/registry.py rikugan/providers/auth_cache.py rikugan/state/history.py rikugan/skills/loader.py rikugan/mcp/manager.py rikugan/tools/__init__.py rikugan/tools/registry.py rikugan/ui/bulk_renamer.py rikugan/ui/panel_core.py rikugan/ui/session_controller_base.py rikugan/ida/ui/session_controller.py rikugan/ida/tools/registry.py rikugan_plugin.py rikugan/core/startup_timing.py`
7. `git status --short`

Do not claim completion unless all required command outputs are shown and inspected.
```
