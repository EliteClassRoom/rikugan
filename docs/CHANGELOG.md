# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Theme system**: User-selectable themes (Auto, Dark, Light, IDA Native) via
  Settings -> Appearance tab. The plugin now ships a unified
  `ThemeManager` singleton as the single source of truth for colors.
- **Real-time IDA theme sync**: Rikugan follows IDA Pro's theme in real time
  via an `IDAThemeWatcher` that polls `QApplication.palette()` every 500 ms
  when running in IDA. Switching the theme from IDA's
  *View -> Theme* menu updates the plugin within ~500 ms.
- **Light theme**: VS Code Light+ inspired palette for users who prefer
  light backgrounds.
- **Pygments style switching**: Pygments formatter now picks its style
  (Monokai vs. default) from the active `ThemeTokens.window` luminance,
  so an IDA Light host gets a light code style rather than always Monokai.
- **`rikugan/ui/theme/`** package: `ThemeMode` enum, frozen
  `ThemeTokens` dataclass (17 semantic colors), three palette modules
  (Dark / Light / IDA), manager singleton, and watcher.

### Changed

- **Config schema v1 -> v2**: `theme: str` renamed to `theme_mode: str`.
  Existing user configs with the legacy `theme` field are auto-migrated
  on load (`dark` -> `dark`, `ida_native` -> `ida`, `light` -> `light`,
  unknown -> `auto`). Both fields present in a corrupt config: the new
  field wins.
- **`rikugan/ui/styles.py`**: Converted to a thin backward-compat
  wrapper. The 8 legacy public functions (`blend_theme_color`,
  `build_theme_stylesheet`, `build_small_button_stylesheet`, ...) and
  the `DARK_THEME` / `IDA_NATIVE_THEME` dict constants now delegate to
  `ThemeManager.instance().tokens()`. New code should use the manager
  directly.
- **14 UI files refactored**: Hardcoded color hex strings in widget
  code replaced with QSS templates that read from `ThemeManager.tokens()`
  (via `format_template` substitution). Affected files:
  `bulk_renamer.py`, `chat_view.py`, `context_bar.py`, `input_area.py`,
  `markdown_renderer.py`, `message_widgets.py`, `mutation_log_view.py`,
  `oauth_consent.py`, `panel_core.py`, `plan_view.py`, `settings_dialog.py`,
  `styles.py`, `tool_widgets.py`, `tools_panel.py`.
- **`rikugan/ida/rikugan_plugin.py`**: `PLUGIN_ENTRY` now initializes
  `ThemeManager` and starts `IDAThemeWatcher` for the IDA host.
- **`rikugan/binja/bootstrap.py`**: `register_plugin` initializes
  `ThemeManager` from saved config. No watcher is started on Binja
  (the host does not expose a poll-able QPalette); Binja gets the
  Dark fallback for AUTO and IDA_NATIVE modes.

### Fixed

- **Pygments code style**: Previously always used `monokai`, which
  produced unreadable code blocks when IDA's host theme was light. Now
  the formatter is luminance-aware and invalidates its cache on theme
  change, so an IDA Native + Light host gets a light Pygments style.
- **Theme system: 5 post-merge widget-level bugs (A-E)**: After
  merging the theme system, interactive testing surfaced 5 bugs at
  widget-construction seams that the unit tests had not caught.
  (A) `manager._apply_now` no longer calls
  `QApplication.setStyleSheet()` (which would bleed a global
  `QWidget` rule into every IDA/Binja host widget); (B) `panel_core`
  re-styles correctly when the user switches to DARK/LIGHT; (C)
  `input_area` and (D) all 11 widget classes in `message_widgets`
  subscribe to `themeChanged` and re-apply on switch; (E) the IDA
  palette watcher is no longer started in DARK/LIGHT modes (where
  it is pure polling overhead). See
  `docs/theme-system-VERIFICATION.md` §3j for the full table.

### Security

- No security-relevant changes. All new code paths use the existing
  sanitization boundaries (`sanitize_tool_result`, etc.).

---

## [1.3.1] - 2026-06-04

Prior releases were tracked via git history and the v1.0..v1.3.1 tags;
this is the first published CHANGELOG entry.
