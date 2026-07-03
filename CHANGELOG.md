# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.7.0] — 2026-07-03

### Added
- `naming-convention` skill (`rikugan/skills/builtins/naming-convention/`) — comprehensive naming standard covering functions, variables, globals, structs, enums, and typedefs, plus edge cases (wrappers/thunks, C++ mangling, Go/Rust, vtable) and a confidence-based escalation ladder with `Unknown_<Hint>_<addr>` placeholders.

### Changed
- **BREAKING (behavior):** `bulk_renamer` Quick and Deep prompts now generate PascalCase function names (`InitializeGlobals`) instead of snake_case (`initialize_globals`). This unifies bulk-rename output with the system prompt and the new `naming-convention` skill. Existing IDBs are NOT migrated — old snake_case names persist; only new renames follow the standard. If you relied on snake_case output from Bulk Rename, regenerate names for affected functions.
- `RENAMING_SECTION` in the system prompt (`rikugan/agent/prompts/base.py`) expanded from 3 naming rules to 6 (now covers variables, enums, typedefs) and references the `/naming-convention` skill for edge cases. Also removes the ghost-tool reference to `rename_multi_variables` (which never existed).
- `malware-analysis` and `generic-re` skills: naming sections expanded from 1-3 rules to the full 6-rule summary, cross-referencing `/naming-convention`.
- Removed ghost-tool references to `rename_multi_variables` in `rikugan/agent/exploration_mode.py` and `rikugan/agent/modes/research.py` (the tool never existed — agents in `/explore` and research modes would attempt to call it and waste a turn).

## [1.6.0] — 2026-07-02

### Added
- `set_runtime_config` wiring in `rikugan/web/__init__.py` (fixes silent `getattr` no-op; security-constant-real-bug step 2).
- `EXECUTE_PYTHON_TOOL_NAME` constant in `rikugan/constants.py` (security-constant-real-bug step 1).

### Fixed
- CI: master trigger + push hook + concurrency + Python 3.12 matrix (`f191722`).
- CI: base_ref diff guard for push events + runtime deps install in test job (`d2545d0`).
- CI: pin Python 3.11 via uv for reproducible desloppify scores (`d518cb6`).
- Release: sync version check across 3 sources (`4270f69`).
- Subprocess injection guard in a2a (port from fork `57caf5e`).
- `a2a_widget` threading model refactored from `QThread`/`_A2AWorker(QObject)` to `threading.Thread` + `queue.Queue` + `QTimer` polling.

### Refactor / Quality
- Pseudo tool schemas extracted to `rikugan/agent/pseudo_tool_schemas.py` (6 of 7 schemas imported into `loop.py`; `DELEGATE_EXTERNAL_TASK_SCHEMA` import pending — see Phase 2).
- Purged IDA 8.x `ida_struct` paths from `types_tools.py` (step 8 of dead-code-purge).
- Removed duplicate `completed_tool_call_ids.add()` at `loop.py:775` (step 7).
- Removed 58 empty legacy `{dark:'', light:''}` dict constants (step 6).
- Applied ruff format to 9 files + removed invalid `noqa` (step 5).
- Extended `sanitize.py` with `strip_lone_surrogates` + `sanitize_messages_for_provider`.

### Tooling
- Added Dependabot weekly config with grouped updates.
- Added `CODEOWNERS` for security and CI paths.

## [1.6.1] — 2026-07-02

### Fixed
- `delegate_external_task` pseudo-tool is now visible to the LLM. The handler (`_handle_delegate_external_task_tool`) and dispatch (`elif tc.name == "delegate_external_task"`) were previously unreachable because `DELEGATE_EXTERNAL_TASK_SCHEMA` was never appended to the tool list in `_build_tools_schema`. The schema is now imported and wired in `rikugan/agent/loop.py` (C.4 final step).

## [1.5.0] — 2026-06-29

### Added
- **Tool substitution guard** (`rikugan.tools.tool_substitution`): when the agent
  calls `execute_python` with a script that re-implements an existing dedicated
  tool, the tool now emits a non-blocking suggestion pointing at the dedicated
  alternative. Suggest-only — the script still runs, but the LLM sees the
  hint and learns the pattern for future turns. Mapping table covers
  imports/exports/strings/functions/xrefs/segments plus contributed entries
  for annotations, decompiler, disassembly/IL, and type/struct APIs.
- **`search_imports` and `imports_by_module` tools**: fill the capability gap
  where `list_imports` could only return the full set. The LLM no longer
  needs to script a custom filter to find imports by name or by DLL.
- **Categorized tool catalog in the system prompt** (`format_tools_catalog`):
  the `## Available Tools` section is now a per-category markdown table
  with one-line description hints, replacing the bare comma-separated list.
  The LLM can scan it to find the right tool without reading the full
  provider schema.

### Changed
- **Tool descriptions use the full docstring**, not just the first line.
  Each `database` tool now documents its output format, capacity limits,
  and sibling tools (search/filter variants) so the LLM has enough
  context to choose correctly instead of falling through to `execute_python`.
- `list_imports`, `list_exports`, `list_segments`, `get_binary_info`,
  `read_bytes`, and `read_global_value` got multi-line docstrings
  covering output format and "use the search variant when filtering".

### Security
- Tool-substitution layer is suggest-only; no new auto-approval path.
  `execute_python` still requires explicit user approval for every call
  regardless of suggestion presence.

## [1.4.0] — 2026-06-26

### Changed
- **Breaking:** Removed the obsolete `ida-docs` and `ida-pro-mcp` built-in skills.
  These were no longer maintained and have been deleted from `rikugan/skills/builtins/`.
- Bumped version to 1.4.0.

### Security
- Closed a markdown XSS vector: the `javascript:` scheme (and other executable
  URL schemes) in markdown links are now stripped before rendering, so they no
  longer become clickable `<a>` tags in the Qt rich-text panel.
- Hardened the `execute_python` script sandbox (`script_guard.py`) and added
  SSRF guards.
- Marked the SHA1 hash used as an HTML-cache key in `markdown.py` as
  `usedforsecurity=False` — it is a non-security cache key, not a cryptographic
  primitive.
- Refactored the headless `--token` validation into dedicated helpers
  (`_validate_token_format` / `_reject_bad_token_format`) that keep the
  rejection text separate from the secret-bearing variable.
- Documented why the sandboxed `exec` in `microcode_optim.py` (user-supplied
  optimizer code run inside `safe_builtins`) is intentional.

### Removed
- Deleted `rikugan/providers/auth_compat.py` — a 61-LOC compatibility shim
  ported from the upstream fork whose two public functions had zero callers.

### Fixed
- Silenced spurious `themeChanged` disconnect warnings.
- Curated the subprocess environment passed to a2a agents and tightened event
  typing.

### Refactor / Quality
- Extracted markdown export helpers from `panel_core.py` into a dedicated
  `rikugan/ui/export_formatting.py` module (`panel_core.py` 2039 → 1937 LOC).
- Documented the mutable-state contract on `RikuganConfig` (instances owned by
  the host entry point, intentionally mutable for settings edit-in-place).
- Replaced silent `except: pass` blocks in `a2a/registry.py` and
  `bulk_renamer.py` with `log_debug` so best-effort failures are traceable.
- Added `from __future__ import annotations` to `pseudo_tool_schemas.py`.
- Extracted the `_PARSE_ERROR_PREVIEW_BYTES` magic constant in `mcp/protocol.py`.
- Added `TestMutationContractConsistency` — 6 tests enforcing that every
  mutating tool's reverse builder has a matching `capture_pre_state` branch
  (and vice versa), plus graceful failure handling for unknown tools.
- Scoped mypy per-file error overrides for shiboken-safe modules.

### Tooling
- Added `pytest`, `pytest-cov`, `ruff`, and `mypy` to the uv dev
  dependency-group so `uv sync` provisions a working local CI environment.
- Added `ci-local.ps1`, a PowerShell port of `ci-local.sh` for Windows
  development (uses `uvx` for ruff/mypy, `uv run python -m pytest` for tests).

## [1.3.0]

### Added
- Pygments syntax-highlight caching keyed by `(code, lang, style)` to speed up
  repeated markdown renders.
- Skill rescan is now skipped on non-skill config changes.

### Changed
- Unified the theme system: routed widget QSS through theme tokens, fixed
  contrast failures, removed dead `LIGHT_THEME` / `DARK_THEME` constants and
  the `build_theme_stylesheet` helper.
- Re-applies the IDA host's minimal style on theme change via the extracted
  `_reapply_minimal_style` helper.

### Fixed
- Disabled raw HTML in markdown to close an earlier injection vector.
- Removed a confusing dead Orchestra tab and dialog class.
- Reverted config when the settings dialog is cancelled.
- Named the actual tool in the approval gate and rendered its description.

## [1.2]

Initial public release line.
