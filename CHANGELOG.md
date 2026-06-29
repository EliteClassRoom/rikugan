# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
