# Rikugan Theme System Design

**Date**: 2026-06-04
**Status**: Approved (pending user review of written spec)
**Author**: Brainstorming session with user

## Problem Statement

Rikugan's plugin UI does not synchronize with IDA Pro's theme. The user
cannot configure whether the plugin follows IDA's dark/light theme, uses
Rikugan's hardcoded dark theme, or uses a custom light theme. There are
~411 hardcoded color references across 14 files in `rikugan/ui/`, and the
existing `RikuganConfig.theme: str = "dark"` field is not exposed in the
Settings dialog. The plugin ships only one theme (`DARK_THEME`) plus a
transparent `IDA_NATIVE_THEME` that is auto-enabled when running inside
IDA — but there is no way for the user to choose.

## Goals

1. **Theme selection**: User picks one of four modes (Auto, Dark, Light, IDA
   Native) in Settings.
2. **Reactive sync**: When running in IDA with `Auto` or `IDA Native`, the
   plugin follows IDA's theme in real time (View → Theme → Light/Dark
   in IDA updates the plugin immediately).
3. **Full UI coverage**: All 14 UI files are refactored to use a single
   `ThemeManager` — no hardcoded color hex strings remain in widget code.
4. **Light theme**: Ship a clean, neutral light theme (VS Code Light+
   style) for users who prefer light backgrounds.
5. **Backward compatibility**: Existing user configs with `theme: "dark"`
   migrate cleanly to the new schema.

## Non-Goals

- User custom theme editor (no in-app color picker)
- Per-widget theme overrides
- Animated transitions between themes
- Theme export/import (sharing configs)
- Tailing the Binja native theme (Binja is not theme-aware in the same way
  IDA is; we ship a fixed Dark fallback for Binja)

## Section 1: Architecture Overview

A `ThemeManager` singleton is the single source of truth for theme state.
All widgets read color values from `ThemeManager.instance().tokens()`
instead of hardcoding hex strings. Theme switching fans out through two
parallel channels:

1. **QSS rebuild**: `ThemeManager.build_stylesheet()` returns a complete
   QSS string, applied to `QApplication.setStyleSheet()`. This restyles
   all standard widgets (QPushButton, QFrame, QLineEdit, QTabWidget,
   QMenu, QScrollBar, etc.) without per-widget code changes.
2. **Signal emit**: `ThemeManager.themeChanged: Signal[ThemeTokens]` is
   connected by custom-paint widgets (markdown labels, code highlight,
   error highlights, custom-drawn arrows) that need to rebuild their
   inline-styled HTML or repaint their canvas.

```python
# rikugan/ui/theme/manager.py (NEW)
class ThemeMode(str, Enum):
    AUTO = "auto"        # follow host: IDA→native, Binja→dark
    DARK = "dark"        # Rikugan hardcoded dark
    LIGHT = "light"      # Rikugan VS Code Light+
    IDA_NATIVE = "ida"   # always transparent, follow IDA palette

@dataclass(frozen=True)
class ThemeTokens:
    """17 semantic keys, QPalette-aligned."""
    window: str
    window_text: str
    base: str
    alt_base: str
    text: str
    button: str
    button_text: str
    highlight: str
    highlight_text: str
    mid: str
    light: str
    dark: str
    success: str
    warning: str
    error: str
    code_text: str
    code_bg: str

class ThemeManager(QObject):
    _instance: ClassVar[ThemeManager | None] = None

    themeChanged = Signal(object)  # emits ThemeTokens

    @classmethod
    def instance(cls) -> ThemeManager: ...
    def tokens(self) -> ThemeTokens: ...
    def mode(self) -> ThemeMode: ...
    def set_mode(self, mode: ThemeMode) -> None: ...
    def refresh_from_host(self) -> None: ...  # called by watcher
    def start_host_watcher(self, interval_ms: int) -> None: ...
    def stop_host_watcher(self) -> None: ...
    def build_stylesheet(self, tokens: ThemeTokens | None = None) -> str: ...
```

### File Structure

**New files**:
```
rikugan/ui/theme/
├── __init__.py
├── manager.py        # ThemeManager singleton
├── tokens.py         # ThemeTokens dataclass
├── palette_dark.py   # DARK_TOKENS
├── palette_light.py  # LIGHT_TOKENS (VS Code Light+)
├── palette_ida.py    # IDA_NATIVE_TOKENS (dynamic from QPalette)
└── watcher.py        # IDAThemeWatcher
tests/ui/theme/
├── __init__.py
├── test_tokens.py
├── test_palettes.py
├── test_manager.py
├── test_watcher.py
├── test_migration.py
├── test_integration.py
└── test_pygments.py
docs/superpowers/specs/
└── 2026-06-04-rikugan-theme-system-design.md  # this file
```

**Refactored files** (existing):
- `rikugan/ui/styles.py` — keeps public API (`blend_theme_color`,
  `use_native_host_theme`, etc.), delegates to `theme/manager.py`
- `rikugan/ui/markdown_renderer.py` — uses `ThemeManager.tokens()` for
  inline-style HTML generation
- `rikugan/ui/highlight.py` — uses `_THEME_PYGMENTS_MAP` keyed on mode
- 11 other UI files — replace hardcoded hex strings with QSS templates
  that read from `ThemeManager.tokens()`

## Section 2: Components & Data Flow

### Component Responsibilities

1. **ThemeManager** (singleton, QObject)
   - Holds current `ThemeTokens` and `ThemeMode`
   - Builds the QSS string from tokens
   - Emits `themeChanged` signal on switch
   - Lazily computes tokens (caches per `(mode, palette_signature)` pair)

2. **IDAThemeWatcher** (QObject, IDA host only)
   - Polls `QApplication.palette()` every 500 ms
   - Compares `(Window color, WindowText color)` signature against cache
   - On change → `ThemeManager.refresh_from_host()`
   - Started/stopped by `PanelCore` lifecycle
   - On Binja, this is not created — Binja host is treated as fixed-Dark

3. **SettingsService** (extend existing)
   - New Appearance tab with `QComboBox` for theme mode
   - Mini `_ThemePreviewChip` widget shows current theme colors
   - Wires combobox changes to `ThemeManager.set_mode` and persists

4. **Widget Subscribers**
   - Custom-paint widgets connect to `themeChanged` in their `__init__`
   - Standard widgets get theme via QSS (no per-widget code changes)
   - Both paths triggered simultaneously on theme switch

### Init Flow (Plugin Boot)

```python
# rikugan/ida/ui/panel.py:PLUGIN_ENTRY()
def PLUGIN_ENTRY():
    # 1. Load config (with v1→v2 migration)
    config = RikuganConfig.load()

    # 2. Init ThemeManager singleton
    theme_mgr = ThemeManager.instance()
    theme_mgr.set_mode(ThemeMode(config.theme_mode))

    # 3. Start IDA watcher (IDA only)
    if is_ida():
        theme_mgr.start_host_watcher(interval_ms=500)

    # 4. Build PanelCore (existing flow)
    panel = PanelCore(...)

    # 5. Apply initial QSS
    qApp.setStyleSheet(theme_mgr.build_stylesheet())
```

### Theme Switch Flow (User Choses in Settings)

```
User chọn 'Light' trong Settings dialog
   │
   ▼
ThemeManager.set_mode(ThemeMode.LIGHT)
   │
   ├─► Load LIGHT_TOKENS
   │
   ├─► qApp.setStyleSheet(build_stylesheet(LIGHT_TOKENS))
   │      └─► All standard widgets re-style
   │
   ├─► themeChanged.emit(LIGHT_TOKENS)
   │      ├─► ChatView: re-render markdown
   │      ├─► ToolsPanel: refresh tool widget colors
   │      ├─► BulkRenamer: refresh preview
   │      └─► ... (other subscribers)
   │
   └─► RikuganConfig.theme_mode = "light"; config.save()
```

### IDA Realtime Watch Flow (User Đổi Theme Ngoài IDA)

```
User: View → Theme → Light (in IDA)
   │
   ▼ (within 500 ms)
IDAThemeWatcher._tick()
   │
   ├─► palette = QApplication.palette()
   ├─► sig = (palette.window().color().name(),
   │          palette.windowText().color().name())
   │
   ├─► if sig != self._last_sig:
   │      └─► ThemeManager.refresh_from_host()
   │             │
   │             ├─► Re-derive IDA_NATIVE_TOKENS from new palette
   │             ├─► qApp.setStyleSheet(new_qss)
   │             └─► themeChanged.emit(IDA_NATIVE_TOKENS)
   │
   └─► Schedule next tick via QTimer.singleShot(500, self._tick)
```

### QSS Channel vs Signal Channel

| Channel | Used For | Examples |
|---------|----------|----------|
| **QSS rebuild** | Widgets styled via QSS properties | QPushButton, QFrame, QLineEdit, QTabWidget, QMenu, QScrollBar |
| **themeChanged signal** | Widgets that draw with QPainter or inline styles | Markdown labels (inline `style=...`), code highlight (Pygments HTML), error highlights, custom arrows |

## Section 3: Token Migration Strategy

### Hardcoded Pattern → Refactor Pattern

**Pattern 1: Direct hex in stylesheet** → Template with format helper
```python
# BEFORE
_SMALL_BTN_STYLE = (
    "QPushButton { background: #2d2d2d; color: #d4d4d4; "
    "border: 1px solid #3c3c3c; ... }"
)

# AFTER
_SMALL_BTN_STYLE_TEMPLATE = """
    QPushButton {{
        background: {button};
        color: {button_text};
        border: 1px solid {mid};
        ...
    }}
"""
def _small_btn_style() -> str:
    t = ThemeManager.instance().tokens()
    return _SMALL_BTN_STYLE_TEMPLATE.format(
        button=t.button, button_text=t.button_text, mid=t.mid
    )
```

**Pattern 2: Pygments style mapping** → Mode → style name map
```python
# BEFORE
style_name = "monokai" if is_dark else "default"

# AFTER
_THEME_PYGMENTS_MAP = {
    ThemeMode.DARK: "monokai",
    ThemeMode.LIGHT: "default",
    ThemeMode.IDA_NATIVE: "monokai",
}
```

**Pattern 3: Inline styles in markdown_renderer** → Tokens via manager
```python
# AFTER
code_text = ThemeManager.instance().tokens().code_text
```

**Pattern 4: Alpha/blended colors** → Helper or pre-computed token
```python
# AFTER (helper)
border = blend_tokens(ThemeManager.instance().tokens(), 'mid', 'window', 0.35)
# OR pre-compute all derived tokens in a ThemeTokens factory.
```

### Mapping Table for 14 UI Files

| File | Refs | Strategy |
|------|------|----------|
| `message_widgets.py` | 69 | Template-based QSS via `tokens()` lookup |
| `tool_widgets.py` | 86 | Template-based QSS + `code_text`/`code_bg` |
| `bulk_renamer.py` | 44 | Template-based QSS |
| `panel_core.py` | 45 | 2 inline styles → 2 helper functions + `tokens()` |
| `settings_dialog.py` | 20 | Template-based QSS |
| `tabs/profiles_tab.py` | 17 | Template-based QSS |
| `plan_view.py` | 14 | Template-based QSS |
| `tools_panel.py` | 15 | Template-based QSS |
| `mutation_log_view.py` | 12 | Template-based QSS |
| `input_area.py` | 5 | Light refactor |
| `oauth_consent.py` | 6 | Light refactor |
| `agent_tree.py` | 20 | Template-based QSS |
| `styles.py` | 56 | Refactor internals; keep public API |
| `markdown_renderer.py` | 2 | Replace inline builders with `build_styles(tokens)` |

### Helper Functions (in `rikugan/ui/theme/manager.py`)

```python
def format_template(template: str, tokens: ThemeTokens) -> str:
    """Format a QSS template with token values.

    Supports {key}, {key+N} (lighten), {key-N} (darken),
    and {key.alpha:N} for rgba.
    """
    ...

def blend_tokens(tokens: ThemeTokens, base: str, toward: str, amount: float) -> str:
    """Blend two token fields by amount (0.0..1.0)."""
    ...
```

### Backward Compatibility for `use_native_host_theme()`

```python
# styles.py keeps public API but delegates
def use_native_host_theme() -> bool:
    mode = ThemeManager.instance().mode()
    if mode == ThemeMode.AUTO:
        return is_ida()
    if mode == ThemeMode.IDA_NATIVE:
        return True
    return False
```

## Section 4: Config Persistence & Migration

### Config Schema Change

```python
# rikugan/core/config.py
@dataclass
class RikuganConfig:
    # ... existing fields ...
    # OLD: theme: str = "dark"
    # NEW:
    theme_mode: str = "auto"  # ThemeMode.AUTO.value
```

### Migration (v1 → v2)

```python
# rikugan/core/config.py
_VALID_THEME_MODES = {"auto", "dark", "light", "ida"}

def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate theme → theme_mode with sensible defaults."""
    if "theme" in data and "theme_mode" not in data:
        old = data.pop("theme")
        mapping = {
            "dark": "dark",
            "ida_native": "ida",
            "light": "light",  # safe even though v1 had no Light
        }
        data["theme_mode"] = mapping.get(old, "auto")
    return data

def _validate_theme_mode(data: dict) -> dict:
    mode = data.get("theme_mode", "auto")
    if mode not in _VALID_THEME_MODES:
        log_warning(f"Invalid theme_mode '{mode}', falling back to 'auto'")
        data["theme_mode"] = "auto"
    return data

@classmethod
def load(cls) -> RikuganConfig:
    raw = _read_json_file(...)
    raw = _migrate_v1_to_v2(raw)
    raw = _validate_theme_mode(raw)
    return cls(**raw)
```

### Settings UI Binding

```python
# rikugan/ui/settings_dialog.py (extend _build_appearance_tab)
def _build_appearance_tab(self) -> QWidget:
    widget = QWidget()
    layout = QFormLayout(widget)

    self._theme_combo = QComboBox()
    self._theme_combo.addItem("Auto (follow host)", "auto")
    self._theme_combo.addItem("Dark", "dark")
    self._theme_combo.addItem("Light", "light")
    self._theme_combo.addItem("IDA Native (transparent)", "ida")

    current = self._config.theme_mode
    for i in range(self._theme_combo.count()):
        if self._theme_combo.itemData(i) == current:
            self._theme_combo.setCurrentIndex(i)
            break

    self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
    self._theme_preview = _ThemePreviewChip()

    layout.addRow("Theme:", self._theme_combo)
    layout.addRow("Preview:", self._theme_preview)
    return widget

def _on_theme_changed(self, idx: int) -> None:
    mode_str = self._theme_combo.itemData(idx)
    self._config.theme_mode = mode_str
    ThemeManager.instance().set_mode(ThemeMode(mode_str))
    self._theme_preview.refresh()
```

### Preview Chip Widget

```python
# rikugan/ui/settings_dialog.py
class _ThemePreviewChip(QWidget):
    """Mini-preview showing window/text/accent colors of current theme."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(120, 60)
        self.setObjectName("theme_preview_chip")

    def paintEvent(self, event):
        t = ThemeManager.instance().tokens()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(t.window))
        p.setPen(QColor(t.text))
        p.drawText(self.rect().adjusted(8, 8, -8, -8),
                   Qt.AlignmentFlag.AlignTopLeft, "Sample text")
        p.fillRect(8, 32, 12, 12, QColor(t.highlight))
        p.fillRect(24, 32, 12, 12, QColor(t.success))
        p.fillRect(40, 32, 12, 12, QColor(t.warning))
        p.fillRect(56, 32, 12, 12, QColor(t.error))
```

## Section 5: Testing Strategy

### Test Pyramid

```
                       ▲
                      ╱ ╲
                     ╱   ╲
                    ╱ E2E ╲          ← Manual smoke + visual snapshot
                   ╱       ╲
                  ╱─────────╲
                 ╱ Integration╲       ← Theme switch round-trips,
                ╱   (theme +   ╲        widget re-render
               ╱    widgets)    ╲
              ╱─────────────────╲
             ╱   Unit tests       ╲   ← ThemeManager logic, token
            ╱ (manager, tokens,    ╲    validation, migration
           ╱  palette derivation)  ╲
          ╱─────────────────────────╲
```

### Test Files

```
tests/ui/theme/
├── __init__.py
├── test_tokens.py        # dataclass invariants
├── test_palettes.py      # DARK, LIGHT, IDA_NATIVE values
├── test_manager.py       # singleton, set_mode, signals
├── test_watcher.py       # palette change detection
├── test_migration.py     # config v1 → v2
├── test_integration.py   # widget subscription round-trip
└── test_pygments.py      # theme → pygments style mapping
```

### Unit Test Examples

```python
# tests/ui/theme/test_tokens.py
def test_tokens_required_keys():
    expected_keys = {
        "window", "window_text", "base", "alt_base", "text",
        "button", "button_text", "highlight", "highlight_text",
        "mid", "light", "dark", "success", "warning", "error",
        "code_text", "code_bg",
    }
    for tokens in (DARK_TOKENS, LIGHT_TOKENS, _make_ida_tokens(QPalette())):
        missing = expected_keys - set(asdict(tokens).keys())
        assert not missing, f"Missing keys: {missing}"

def test_tokens_are_hex_colors():
    for tokens in (DARK_TOKENS, LIGHT_TOKENS):
        for key, val in asdict(tokens).items():
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", val), \
                f"{key}={val} is not #rrggbb"

# tests/ui/theme/test_palettes.py
def test_light_palette_is_actually_light():
    lum = _hex_luminance(LIGHT_TOKENS.window)
    assert lum > 0.5, f"Light theme window should be bright, got {lum}"

def test_dark_palette_is_actually_dark():
    lum = _hex_luminance(DARK_TOKENS.window)
    assert lum < 0.5, f"Dark theme window should be dark, got {lum}"

# tests/ui/theme/test_manager.py
def test_singleton_returns_same_instance():
    ThemeManager._instance = None
    assert ThemeManager.instance() is ThemeManager.instance()

def test_set_mode_emits_signal():
    ThemeManager._instance = None
    mgr = ThemeManager.instance()
    captured: list[ThemeTokens] = []
    mgr.themeChanged.connect(lambda t: captured.append(t))

    mgr.set_mode(ThemeMode.LIGHT)

    assert len(captured) == 1
    assert captured[0].window == LIGHT_TOKENS.window

def test_set_mode_same_value_is_noop():
    ThemeManager._instance = None
    mgr = ThemeManager.instance()
    mgr.set_mode(ThemeMode.DARK)
    captured: list = []
    mgr.themeChanged.connect(lambda t: captured.append(t))

    mgr.set_mode(ThemeMode.DARK)

    assert captured == []

# tests/ui/theme/test_migration.py
def test_v1_theme_dark_maps_to_dark():
    data = {"theme": "dark", "other_field": "x"}
    migrated = _migrate_v1_to_v2(data)
    assert migrated["theme_mode"] == "dark"
    assert "theme" not in migrated

def test_v1_theme_ida_native_maps_to_ida():
    data = {"theme": "ida_native"}
    assert _migrate_v1_to_v2(data)["theme_mode"] == "ida"

def test_v2_passthrough():
    data = {"theme_mode": "light"}
    assert _migrate_v1_to_v2(data) == {"theme_mode": "light"}

def test_invalid_mode_falls_back_to_auto():
    data = {"theme_mode": "neon_pink"}
    assert _validate_theme_mode(data)["theme_mode"] == "auto"
```

### Integration Test Example

```python
# tests/ui/theme/test_integration.py
def test_chat_view_re_renders_on_theme_change(qapp):
    chat = ChatView()
    chat.append_assistant_message("**hello** world")
    qapp.processEvents()

    initial_html = _extract_text(chat)

    ThemeManager.instance().set_mode(ThemeMode.LIGHT)
    qapp.processEvents()

    after_html = _extract_text(chat)
    assert initial_html != after_html

def test_tool_widget_subscribes_to_theme(qapp):
    widget = ToolCallWidget(name="rename", args={"ea": "0x401000"})
    qapp.processEvents()

    initial_qss = widget.styleSheet()

    ThemeManager.instance().set_mode(ThemeMode.LIGHT)
    qapp.processEvents()

    palette_after = widget.palette()
    assert palette_after.window().color() != QColor(DARK_TOKENS.window)
```

**Coverage target**: ≥85% for `rikugan/ui/theme/` package.
**Test isolation**: `ThemeManager._instance = None` in `setup_method`.

## Section 6: Edge Cases & Error Handling

### Edge Case Matrix

| Case | Behavior |
|------|----------|
| User chọn `IDA_NATIVE` trên Binja | Fallback về `DARK` + log warning |
| Binja host + mode `AUTO` | Dùng `DARK_TOKENS` (Binja fixed) |
| IDA host + mode `AUTO` | Follow IDA palette realtime |
| Pygments không install | `highlight_code` trả về plain HTML, không crash |
| Pygments style không tồn tại | Try/except → fallback "default" |
| QApplication.palette() raise exception | Watcher catch + log, tiếp tục polling |
| Widget chưa subscribe khi theme switch lần đầu | `subscribe()` helper replays current tokens |
| Theme switch giữa lúc user đang scroll/typing | QSS apply instant; markdown re-render async (QTimer.singleShot 0) |
| Theme switch liên tiếp nhanh (rapid) | Debounce 50 ms; chỉ apply lần cuối |
| Widget bị destroy trước khi signal emit | Qt auto-disconnect (uses QObject, not raw callback) |
| `theme_mode` invalid trong config | Validation fallback về `AUTO` |
| `theme_mode` missing (corrupt config) | Default `AUTO` |
| `RikuganConfig` không load được (file missing) | Default constructor → `AUTO` |

### Error Handling Patterns

```python
# 1. Pygments fallback
def highlight_code(code: str, language: str, is_dark: bool) -> str:
    if not _HAS_PYGMENTS:
        return _plain_code(code)
    style_name = _THEME_PYGMENTS_MAP.get(current_mode(), "default")
    try:
        return _highlight_with_pygments(code, language, style_name)
    except ClassNotFound:
        log_warning(f"Pygments style '{style_name}' missing, using default")
        return _highlight_with_pygments(code, language, "default")

# 2. Watcher resilience
class IDAThemeWatcher:
    def _tick(self):
        try:
            palette = QApplication.instance().palette()
            sig = _palette_signature(palette)
            if sig != self._last_sig:
                self._last_sig = sig
                ThemeManager.instance().refresh_from_host()
        except Exception as e:
            log_error(f"ThemeWatcher tick failed: {e}")
        finally:
            if self._alive.is_set():
                QTimer.singleShot(self._interval_ms, self._tick)

# 3. Manager debouncing
class ThemeManager(QObject):
    def set_mode(self, mode: ThemeMode) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        if self._pending_apply is not None:
            self._pending_apply.stop()
        self._pending_apply = QTimer()
        self._pending_apply.setSingleShot(True)
        self._pending_apply.timeout.connect(self._apply_now)
        self._pending_apply.start(50)

    def _apply_now(self) -> None:
        tokens = self._compute_tokens()
        QApplication.instance().setStyleSheet(self._build_stylesheet(tokens))
        self.themeChanged.emit(tokens)

# 4. Late subscriber pattern
class ThemeManager(QObject):
    def __init__(self):
        super().__init__()
        self._tokens_cache: ThemeTokens | None = None

    def tokens(self) -> ThemeTokens:
        if self._tokens_cache is None:
            self._tokens_cache = self._compute_tokens()
        return self._tokens_cache

    def subscribe(self, callback: Callable[[ThemeTokens], None]) -> None:
        self.themeChanged.connect(callback)
        callback(self.tokens())  # replay current state

# 5. Binja + IDA_NATIVE guard
def _resolve_effective_mode(mode: ThemeMode, host: str) -> ThemeMode:
    if mode == ThemeMode.IDA_NATIVE and host != "ida":
        log_warning(
            f"IDA Native mode requested on {host}; falling back to DARK"
        )
        return ThemeMode.DARK
    return mode
```

### Logging Policy

- **INFO**: theme mode changed
- **WARNING**: graceful fallbacks (Pygments style missing, Binja + IDA_NATIVE)
- **ERROR**: unexpected failures (watcher tick, QSS build) with `exc_info=True`

### Performance Budget

- Theme switch end-to-end (QSS + signal): **< 50 ms** p95
- Watcher tick: **< 1 ms** per cycle
- Token computation: **< 5 ms** first time, **< 0.1 ms** cached
- QSS rebuild: **< 10 ms**

## Implementation Order

1. Add `ThemeTokens`, `ThemeMode`, and `ThemeManager` skeleton (no behavior)
2. Add `DARK_TOKENS` and `LIGHT_TOKENS` (hardcoded values)
3. Add `palette_ida.py` for QPalette-derived tokens
4. Add `IDAThemeWatcher` (no-op for Binja)
5. Refactor `rikugan/ui/styles.py` to delegate to `ThemeManager`
6. Refactor each of the 14 UI files in order of ref count (highest first)
7. Add `_THEME_PYGMENTS_MAP` to `highlight.py`
8. Refactor `markdown_renderer.py` to use `build_styles(tokens)`
9. Add Settings UI combo + preview chip
10. Add config migration in `core/config.py`
11. Wire all tests
12. Add `docs/CHANGELOG.md` entry

## Acceptance Criteria

- [ ] No hardcoded color hex strings remain in `rikugan/ui/` outside of
      `theme/palette_*.py` (verified by grep)
- [ ] User can switch theme at runtime via Settings dialog
- [ ] Theme switch visible within 50 ms p95
- [ ] Plugin follows IDA's theme in real time when `Auto` or `IDA Native`
      is selected and the host is IDA
- [ ] Existing user configs with `theme: "dark"` load as `theme_mode: "dark"`
- [ ] All 7 new test files pass
- [ ] Coverage ≥ 85% for `rikugan/ui/theme/`
- [ ] No regressions in `tests/` (full suite green)
- [ ] Binja host gets Dark regardless of mode (Binja is not theme-aware)
