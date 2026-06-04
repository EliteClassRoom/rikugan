# Rikugan Theme System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Rikugan's hardcoded dark theme with a configurable, reactive theme system that follows IDA Pro's theme in real time, supports a new Light theme, and removes all hardcoded color hex strings from widget code.

**Architecture:** A `ThemeManager` singleton holds the current `ThemeMode` (Auto/Dark/Light/IDA) and `ThemeTokens` (17 semantic colors). Widgets read colors from the manager instead of hardcoding hex. Theme switching fans out through two channels: (1) `QApplication.setStyleSheet()` for standard widgets, (2) `themeChanged` Qt signal for custom-paint widgets. An `IDAThemeWatcher` polls `QApplication.palette()` every 500ms when running in IDA with Auto/IDA mode.

**Tech Stack:** Python 3.11+, PySide6/PyQt5 (via `qt_compat` shim), `pytest`, existing `tests/qt_stubs.py` test infrastructure.

**Source spec:** `docs/superpowers/specs/2026-06-04-rikugan-theme-system-design.md`

---

## File Structure

**New files:**
- `rikugan/ui/theme/__init__.py` — public package init
- `rikugan/ui/theme/tokens.py` — `ThemeMode` enum + `ThemeTokens` dataclass
- `rikugan/ui/theme/palette_dark.py` — `DARK_TOKENS` constant
- `rikugan/ui/theme/palette_light.py` — `LIGHT_TOKENS` constant
- `rikugan/ui/theme/palette_ida.py` — `derive_ida_tokens()` + 5-token semantic derivation
- `rikugan/ui/theme/manager.py` — `ThemeManager` singleton + helpers (`format_template`, `blend_tokens`)
- `rikugan/ui/theme/watcher.py` — `IDAThemeWatcher` (QObject + QTimer)
- `tests/tools/conftest.py` — `qapp` fixture (shared QApplication for theme tests)
- `tests/tools/test_theme_tokens.py` — token dataclass invariants
- `tests/tools/test_theme_palettes.py` — DARK/LIGHT/IDA palette values
- `tests/tools/test_theme_manager.py` — singleton, set_mode, signals, debounce, reset
- `tests/tools/test_theme_watcher.py` — palette change detection
- `tests/tools/test_theme_migration.py` — config v1 → v2 + validation
- `tests/tools/test_theme_integration.py` — widget subscription round-trip
- `tests/tools/test_theme_pygments.py` — pygments style mapping + cache invalidation

**Refactored files (existing):**
- `rikugan/core/config.py` — rename `theme: str` → `theme_mode: str` + migration + validation
- `rikugan/ui/styles.py` — convert to thin wrapper delegating to `theme/manager.py`
- `rikugan/ui/markdown_renderer.py` — use `ThemeManager.tokens()` for inline-style HTML
- `rikugan/ui/highlight.py` — use luminance-based pygments style map + cache invalidation
- `rikugan/ui/settings_dialog.py` — add `_build_appearance_tab()` + insert tab at index 1
- `rikugan/ui/message_widgets.py` — 69 hex refs → QSS templates
- `rikugan/ui/tool_widgets.py` — 86 hex refs → QSS templates
- `rikugan/ui/bulk_renamer.py` — 44 hex refs → QSS templates
- `rikugan/ui/panel_core.py` — 2 inline styles → helper functions
- `rikugan/ui/tools_panel.py` — 15 hex refs → QSS templates
- `rikugan/ui/mutation_log_view.py` — 12 hex refs → QSS templates
- `rikugan/ui/plan_view.py` — 14 hex refs → QSS templates
- `rikugan/ui/tabs/profiles_tab.py` — 17 hex refs → QSS templates
- `rikugan/ui/input_area.py` — 5 hex refs
- `rikugan/ui/oauth_consent.py` — 6 hex refs
- `rikugan/ui/agent_tree.py` — 20 hex refs → QSS templates
- `rikugan_plugin.py` — wire `ThemeManager` init + watcher start
- `rikugan/binja/bootstrap.py` — wire `ThemeManager` init (no watcher)

---

## Task 1: Add ThemeTokens dataclass and ThemeMode enum

**Files:**
- Create: `rikugan/ui/theme/__init__.py`
- Create: `rikugan/ui/theme/tokens.py`
- Create: `tests/tools/test_theme_tokens.py`

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_theme_tokens.py`:

```python
"""Tests for rikugan.ui.theme.tokens — ThemeMode and ThemeTokens invariants."""

from __future__ import annotations

import re
import sys
import unittest
from dataclasses import asdict

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from rikugan.ui.theme.tokens import ThemeMode, ThemeTokens


class TestThemeMode(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(ThemeMode.AUTO.value, "auto")
        self.assertEqual(ThemeMode.DARK.value, "dark")
        self.assertEqual(ThemeMode.LIGHT.value, "light")
        self.assertEqual(ThemeMode.IDA_NATIVE.value, "ida")

    def test_from_string_valid(self):
        self.assertIs(ThemeMode("auto"), ThemeMode.AUTO)
        self.assertIs(ThemeMode("dark"), ThemeMode.DARK)
        self.assertIs(ThemeMode("light"), ThemeMode.LIGHT)
        self.assertIs(ThemeMode("ida"), ThemeMode.IDA_NATIVE)

    def test_from_string_invalid_raises(self):
        with self.assertRaises(ValueError):
            ThemeMode("neon_pink")


class TestThemeTokens(unittest.TestCase):
    REQUIRED_KEYS = {
        "window", "window_text", "base", "alt_base", "text",
        "button", "button_text", "highlight", "highlight_text",
        "mid", "light", "dark", "success", "warning", "error",
        "code_text", "code_bg",
    }

    def _make_tokens(self) -> ThemeTokens:
        return ThemeTokens(
            window="#000000", window_text="#ffffff",
            base="#111111", alt_base="#1a1a1a", text="#e0e0e0",
            button="#222222", button_text="#e0e0e0",
            highlight="#007acc", highlight_text="#ffffff",
            mid="#666666", light="#888888", dark="#333333",
            success="#4ec9b0", warning="#dcdcaa", error="#f48771",
            code_text="#e0e0e0", code_bg="#1a1a1a",
        )

    def test_required_keys_present(self):
        tokens = self._make_tokens()
        keys = set(asdict(tokens).keys())
        self.assertEqual(keys, self.REQUIRED_KEYS)

    def test_keys_count_is_17(self):
        tokens = self._make_tokens()
        self.assertEqual(len(asdict(tokens)), 17)

    def test_all_values_are_hex_colors(self):
        tokens = self._make_tokens()
        pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for key, val in asdict(tokens).items():
            self.assertRegex(val, pattern, f"{key}={val} is not #rrggbb")

    def test_frozen_dataclass(self):
        tokens = self._make_tokens()
        with self.assertRaises(Exception):  # FrozenInstanceError or AttributeError
            tokens.window = "#ffffff"  # type: ignore[misc]

    def test_is_dark_helper_true_for_dark_window(self):
        from rikugan.ui.theme.tokens import is_dark_tokens
        tokens = self._make_tokens()  # window=#000000
        self.assertTrue(is_dark_tokens(tokens))

    def test_is_dark_helper_false_for_light_window(self):
        from rikugan.ui.theme.tokens import is_dark_tokens
        tokens = ThemeTokens(
            window="#ffffff", window_text="#000000",
            base="#fafafa", alt_base="#f0f0f0", text="#1a1a1a",
            button="#ffffff", button_text="#1a1a1a",
            highlight="#0066cc", highlight_text="#ffffff",
            mid="#cccccc", light="#ffffff", dark="#999999",
            success="#2c8a4a", warning="#a67900", error="#c42b1c",
            code_text="#1a1a1a", code_bg="#f0f0f0",
        )
        self.assertFalse(is_dark_tokens(tokens))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_theme_tokens.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rikugan.ui.theme'`

- [ ] **Step 3: Create the package**

Create `rikugan/ui/theme/__init__.py`:

```python
"""Rikugan theme system — single source of truth for color tokens."""

from .tokens import ThemeMode, ThemeTokens, is_dark_tokens

__all__ = ["ThemeMode", "ThemeTokens", "is_dark_tokens"]
```

Create `rikugan/ui/theme/tokens.py`:

```python
"""ThemeMode enum and ThemeTokens dataclass — 17 semantic color keys.

The 12 QPalette-aligned keys (window, window_text, base, alt_base, text,
button, button_text, highlight, highlight_text, mid, light, dark) are
derived from QPalette in IDA_NATIVE mode and hardcoded in DARK/LIGHT
modes. The 5 semantic keys (success, warning, error, code_text, code_bg)
are derived per-theme (no QPalette equivalent).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ThemeMode(str, Enum):
    """User-selectable theme mode.

    AUTO: follow host — IDA→native palette, Binja→Dark.
    DARK: Rikugan hardcoded dark theme.
    LIGHT: Rikugan VS Code Light+ theme.
    IDA_NATIVE: always transparent, follow IDA palette (Binja falls back
        to DARK with a warning).
    """

    AUTO = "auto"
    DARK = "dark"
    LIGHT = "light"
    IDA_NATIVE = "ida"


@dataclass(frozen=True)
class ThemeTokens:
    """17 semantic color tokens, immutable."""

    # QPalette-aligned (12)
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
    # Semantic (5) — derived per-theme
    success: str
    warning: str
    error: str
    code_text: str
    code_bg: str


def is_dark_tokens(tokens: ThemeTokens) -> bool:
    """Return True when the token's window color is dark (luminance < 0.5)."""
    from .manager import _hex_luminance  # late import to avoid cycle
    return _hex_luminance(tokens.window) < 0.5
```

> **Note on import cycle:** `is_dark_tokens` lazily imports `_hex_luminance`
> from `manager.py` (defined in Task 4). The cycle is one-way; this
> import only resolves at call time, never at module-load time.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_theme_tokens.py -v`
Expected: PASS for all 7 tests

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/theme/__init__.py rikugan/ui/theme/tokens.py tests/tools/test_theme_tokens.py
git commit -m "feat(theme): add ThemeMode enum and ThemeTokens dataclass"
```

---

## Task 2: Add DARK_TOKENS constant (palette_dark.py)

**Files:**
- Create: `rikugan/ui/theme/palette_dark.py`
- Create: `tests/tools/test_theme_palettes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/tools/test_theme_palettes.py`:

```python
"""Tests for rikugan.ui.theme palettes (DARK, LIGHT, IDA_NATIVE)."""

from __future__ import annotations

import re
import sys
import unittest
from dataclasses import asdict

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from rikugan.ui.theme.tokens import ThemeTokens


class TestDarkPalette(unittest.TestCase):
    def test_dark_tokens_is_dark(self):
        from rikugan.ui.theme.palette_dark import DARK_TOKENS
        # Window must be dark
        self.assertEqual(DARK_TOKENS.window.lower(), "#1e1e1e")

    def test_dark_tokens_has_all_keys(self):
        from rikugan.ui.theme.palette_dark import DARK_TOKENS
        self.assertEqual(len(asdict(DARK_TOKENS)), 17)

    def test_dark_tokens_hex_format(self):
        from rikugan.ui.theme.palette_dark import DARK_TOKENS
        pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for k, v in asdict(DARK_TOKENS).items():
            self.assertRegex(v, pattern, f"{k}={v}")

    def test_dark_text_contrast(self):
        """Text on window must have high luminance contrast for readability."""
        from rikugan.ui.theme.palette_dark import DARK_TOKENS
        from rikugan.ui.theme.manager import _hex_luminance
        win_lum = _hex_luminance(DARK_TOKENS.window)
        text_lum = _hex_luminance(DARK_TOKENS.text)
        self.assertGreater(abs(win_lum - text_lum), 0.5)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_theme_palettes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rikugan.ui.theme.palette_dark'`

- [ ] **Step 3: Write minimal implementation**

Create `rikugan/ui/theme/palette_dark.py`:

```python
"""Hardcoded dark theme — VS Code Dark+ inspired, matches existing Rikugan look."""

from __future__ import annotations

from .tokens import ThemeTokens

DARK_TOKENS = ThemeTokens(
    # QPalette-aligned (12)
    window="#1e1e1e",
    window_text="#d4d4d4",
    base="#1e1e1e",
    alt_base="#252526",
    text="#d4d4d4",
    button="#2d2d2d",
    button_text="#d4d4d4",
    highlight="#0e639c",
    highlight_text="#ffffff",
    mid="#3c3c3c",
    light="#5a5a5a",
    dark="#1a1a1a",
    # Semantic (5)
    success="#4ec9b0",
    warning="#dcdcaa",
    error="#f48771",
    code_text="#d4d4d4",
    code_bg="#1a1a1a",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_theme_palettes.py::TestDarkPalette -v`
Expected: PASS for all 4 tests

> **Note**: `test_dark_text_contrast` calls `_hex_luminance` which is in
> `manager.py` — defined in Task 4. If Task 4 isn't done yet, that import
> will fail. Skip this test class until Task 4 lands, OR move the
> `_hex_luminance` helper into `tokens.py` as a pure function. For this
> plan, mark this test as `@unittest.skip("requires Task 4 _hex_luminance")`
> and unskip in Task 4.

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/theme/palette_dark.py tests/tools/test_theme_palettes.py
git commit -m "feat(theme): add DARK_TOKENS palette"
```

---

## Task 3: Add LIGHT_TOKENS constant (palette_light.py)

**Files:**
- Create: `rikugan/ui/theme/palette_light.py`
- Modify: `tests/tools/test_theme_palettes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/tools/test_theme_palettes.py`:

```python
class TestLightPalette(unittest.TestCase):
    def test_light_tokens_window_is_light(self):
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        from rikugan.ui.theme.manager import _hex_luminance
        lum = _hex_luminance(LIGHT_TOKENS.window)
        self.assertGreater(lum, 0.8, f"Light window should be bright, got {lum}")

    def test_light_tokens_has_all_keys(self):
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        self.assertEqual(len(asdict(LIGHT_TOKENS)), 17)

    def test_light_tokens_hex_format(self):
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        for k, v in asdict(LIGHT_TOKENS).items():
            self.assertRegex(v, pattern, f"{k}={v}")

    def test_light_text_contrast(self):
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        from rikugan.ui.theme.manager import _hex_luminance
        win_lum = _hex_luminance(LIGHT_TOKENS.window)
        text_lum = _hex_luminance(LIGHT_TOKENS.text)
        self.assertGreater(abs(win_lum - text_lum), 0.5)

    def test_light_highlight_is_blue(self):
        """VS Code Light+ uses #0066cc for highlight."""
        from rikugan.ui.theme.palette_light import LIGHT_TOKENS
        self.assertEqual(LIGHT_TOKENS.highlight.lower(), "#0066cc")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_theme_palettes.py::TestLightPalette -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `rikugan/ui/theme/palette_light.py`:

```python
"""Hardcoded light theme — VS Code Light+ inspired, neutral with high readability."""

from __future__ import annotations

from .tokens import ThemeTokens

LIGHT_TOKENS = ThemeTokens(
    # QPalette-aligned (12)
    window="#ffffff",
    window_text="#1e1e1e",
    base="#ffffff",
    alt_base="#f3f3f3",
    text="#1e1e1e",
    button="#f0f0f0",
    button_text="#1e1e1e",
    highlight="#0066cc",
    highlight_text="#ffffff",
    mid="#cccccc",
    light="#ffffff",
    dark="#a0a0a0",
    # Semantic (5) — darker variants for light bg
    success="#2c8a4a",
    warning="#a67900",
    error="#c42b1c",
    code_text="#1e1e1e",
    code_bg="#f3f3f3",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_theme_palettes.py::TestLightPalette -v`
Expected: PASS (assuming Task 4 `_hex_luminance` exists; otherwise skip)

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/theme/palette_light.py tests/tools/test_theme_palettes.py
git commit -m "feat(theme): add LIGHT_TOKENS palette (VS Code Light+ inspired)"
```

---

## Task 4: Add manager.py with _hex_luminance, format_template, blend_tokens

**Files:**
- Create: `rikugan/ui/theme/manager.py`
- Modify: `rikugan/ui/theme/__init__.py`

> **Note**: This task adds the manager skeleton (helpers + singleton class)
> but no behavior. `set_mode` is a no-op, `themeChanged` is just a Signal
> declaration. Behavior (debounce, watcher integration) comes in later tasks.

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_theme_manager.py`:

```python
"""Tests for rikugan.ui.theme.manager — singleton, signals, helpers."""

from __future__ import annotations

import sys
import unittest
from dataclasses import asdict
from typing import Any

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from rikugan.ui.theme.manager import (
    ThemeManager,
    _hex_luminance,
    blend_tokens,
    format_template,
)
from rikugan.ui.theme.tokens import ThemeMode, ThemeTokens


class TestHexLuminance(unittest.TestCase):
    def test_black(self):
        self.assertAlmostEqual(_hex_luminance("#000000"), 0.0)

    def test_white(self):
        self.assertAlmostEqual(_hex_luminance("#ffffff"), 1.0, places=2)

    def test_gray(self):
        lum = _hex_luminance("#808080")
        self.assertGreater(lum, 0.2)
        self.assertLess(lum, 0.5)

    def test_short_form_unsupported(self):
        """3-char hex (#fff) is not supported; must raise or return fallback."""
        with self.assertRaises((ValueError, IndexError)):
            _hex_luminance("#fff")


class TestBlendTokens(unittest.TestCase):
    def _tokens(self) -> ThemeTokens:
        return ThemeTokens(
            window="#000000", window_text="#ffffff",
            base="#111111", alt_base="#1a1a1a", text="#e0e0e0",
            button="#222222", button_text="#e0e0e0",
            highlight="#007acc", highlight_text="#ffffff",
            mid="#666666", light="#888888", dark="#333333",
            success="#4ec9b0", warning="#dcdcaa", error="#f48771",
            code_text="#e0e0e0", code_bg="#1a1a1a",
        )

    def test_blend_full_amount_returns_toward(self):
        t = self._tokens()
        result = blend_tokens(t, "window", "window_text", 1.0)
        self.assertEqual(result.lower(), "#ffffff")

    def test_blend_zero_amount_returns_base(self):
        t = self._tokens()
        result = blend_tokens(t, "window", "window_text", 0.0)
        self.assertEqual(result.lower(), "#000000")

    def test_blend_half_amount(self):
        t = self._tokens()
        result = blend_tokens(t, "window", "window_text", 0.5)
        # Should be roughly mid-gray (#7f7f7f); allow small rounding.
        lum = _hex_luminance(result)
        self.assertGreater(lum, 0.3)
        self.assertLess(lum, 0.7)


class TestFormatTemplate(unittest.TestCase):
    def _tokens(self) -> ThemeTokens:
        return ThemeTokens(
            window="#1e1e1e", window_text="#d4d4d4",
            base="#1e1e1e", alt_base="#252526", text="#d4d4d4",
            button="#2d2d2d", button_text="#d4d4d4",
            highlight="#0e639c", highlight_text="#ffffff",
            mid="#3c3c3c", light="#5a5a5a", dark="#1a1a1a",
            success="#4ec9b0", warning="#dcdcaa", error="#f48771",
            code_text="#d4d4d4", code_bg="#1a1a1a",
        )

    def test_substitutes_token_keys(self):
        t = self._tokens()
        result = format_template("QWidget {{ background: {window}; color: {text}; }}", t)
        self.assertIn("background: #1e1e1e;", result)
        self.assertIn("color: #d4d4d4;", result)
        # Braces should be escaped in the source
        self.assertNotIn("{{", result.replace("background: #1e1e1e;", ""))

    def test_unknown_key_raises(self):
        t = self._tokens()
        with self.assertRaises(KeyError):
            format_template("{not_a_key}", t)


class TestThemeManagerSingleton(unittest.TestCase):
    def setUp(self):
        ThemeManager.reset_for_testing()

    def tearDown(self):
        ThemeManager.reset_for_testing()

    def test_instance_returns_same_object(self):
        a = ThemeManager.instance()
        b = ThemeManager.instance()
        self.assertIs(a, b)

    def test_reset_clears_instance(self):
        a = ThemeManager.instance()
        ThemeManager.reset_for_testing()
        b = ThemeManager.instance()
        self.assertIsNot(a, b)

    def test_initial_mode_is_auto(self):
        mgr = ThemeManager.instance()
        self.assertEqual(mgr.mode(), ThemeMode.AUTO)

    def test_set_mode_updates_mode(self):
        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.DARK)
        self.assertEqual(mgr.mode(), ThemeMode.DARK)

    def test_set_mode_same_value_is_noop(self):
        """Setting the same mode should not emit signal (avoids extra work)."""
        from PySide6.QtCore import QCoreApplication
        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.DARK)  # initial
        captured: list[Any] = []
        mgr.themeChanged.connect(lambda t: captured.append(t))
        mgr.set_mode(ThemeMode.DARK)  # same
        self.assertEqual(captured, [])

    def test_theme_changed_signal_fires_on_switch(self):
        mgr = ThemeManager.instance()
        captured: list[Any] = []
        mgr.themeChanged.connect(lambda t: captured.append(t))
        mgr.set_mode(ThemeMode.LIGHT)
        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], ThemeTokens)

    def test_subscribe_helper_replays_current_tokens(self):
        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.DARK)
        captured: list[Any] = []
        mgr.subscribe(lambda t: captured.append(t))
        # Should have received current tokens immediately
        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], ThemeTokens)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_theme_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rikugan.ui.theme.manager'`

- [ ] **Step 3: Write minimal implementation**

Create `rikugan/ui/theme/manager.py`:

```python
"""ThemeManager singleton — single source of truth for theme state.

Holds the current ThemeMode and ThemeTokens. Builds the QSS string from
tokens. Emits themeChanged signal on switch. Caches tokens per
(mode, palette_signature) tuple to avoid recomputation.

This is the SKELETON — no watcher integration, no debounce, no QSS build.
Those land in later tasks. This task only:
- Defines the singleton lifecycle (`instance`, `reset_for_testing`).
- Exposes `mode()` and a basic `set_mode()` (no-op if same value).
- Defines `themeChanged` signal.
- Provides pure helpers `_hex_luminance`, `blend_tokens`,
  `format_template` that don't need a manager instance.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, ClassVar

from PySide6.QtCore import QObject, Signal  # type: ignore[import-not-found]

from .palette_dark import DARK_TOKENS
from .tokens import ThemeMode, ThemeTokens

# Hex color pattern (6-char form only, lowercase canonical)
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{6})$")


def _hex_luminance(hex_color: str) -> float:
    """Compute relative luminance of a 6-char hex color (0.0..1.0).

    Uses the standard sRGB formula:
    L = 0.2126*R + 0.7152*G + 0.0722*B
    where R/G/B are linearized sRGB values.
    """
    m = _HEX_RE.match(hex_color)
    if not m:
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    raw = m.group(1)
    r = int(raw[0:2], 16) / 255.0
    g = int(raw[2:4], 16) / 255.0
    b = int(raw[4:6], 16) / 255.0

    def _linearize(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r_lin, g_lin, b_lin = _linearize(r), _linearize(g), _linearize(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    m = _HEX_RE.match(hex_color)
    if not m:
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    raw = m.group(1)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def blend_tokens(
    tokens: ThemeTokens, base_key: str, toward_key: str, amount: float
) -> str:
    """Blend two token fields by amount (0.0..1.0).

    `amount=0.0` returns the base; `amount=1.0` returns the toward field.
    """
    base_rgb = _hex_to_rgb(getattr(tokens, base_key))
    toward_rgb = _hex_to_rgb(getattr(tokens, toward_key))
    blended = tuple(
        int(round(base + (toward - base) * amount))
        for base, toward in zip(base_rgb, toward_rgb)
    )
    return _rgb_to_hex(*blended)


def format_template(template: str, tokens: ThemeTokens) -> str:
    """Format a QSS template with token values.

    Substitutes `{key}` with `getattr(tokens, key)`. Double braces `{{` and
    `}}` in the source are converted to single braces (CSS escaping).
    Unknown keys raise KeyError.
    """
    # First, escape CSS braces: {{ → { and }} → }
    css = template.replace("{{", "{").replace("}}", "}")

    # Substitute tokens. Use a regex to find all {key} patterns.
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if not hasattr(tokens, key):
            raise KeyError(f"Unknown token key: {key}")
        return getattr(tokens, key)

    return re.sub(r"\{([a-z_]+)\}", _replace, css)


class ThemeManager(QObject):
    """Singleton manager — holds current mode + tokens, emits themeChanged."""

    _instance: ClassVar[ThemeManager | None] = None

    themeChanged = Signal(object)  # emits ThemeTokens

    def __init__(self) -> None:
        super().__init__()
        self._mode: ThemeMode = ThemeMode.AUTO
        self._tokens_cache: ThemeTokens | None = None

    @classmethod
    def instance(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_testing(cls) -> None:
        """Clear the singleton instance. Test-only helper."""
        cls._instance = None

    def mode(self) -> ThemeMode:
        return self._mode

    def tokens(self) -> ThemeTokens:
        """Return the current tokens (lazily computed, cached)."""
        if self._tokens_cache is None:
            self._tokens_cache = self._compute_tokens()
        return self._tokens_cache

    def set_mode(self, mode: ThemeMode) -> None:
        """Set the theme mode. No-op if same value.

        SKELTON: does not apply QSS, does not emit signal. Behavior is
        added in Task 6 (apply + emit) and Task 7 (debounce).
        """
        if mode == self._mode:
            return
        self._mode = mode
        self._tokens_cache = None  # invalidate cache

    def _compute_tokens(self) -> ThemeTokens:
        """Compute tokens for the current mode. SKELTON — returns DARK only.

        Real logic (IDA_NATIVE derivation, etc.) is added in later tasks.
        """
        return DARK_TOKENS

    def subscribe(self, callback: Callable[[ThemeTokens], None]) -> None:
        """Subscribe to themeChanged AND immediately receive current tokens.

        Useful for widgets that initialize after a theme switch — they
        don't miss the initial state.
        """
        self.themeChanged.connect(callback)  # type: ignore[arg-type]
        callback(self.tokens())
```

Update `rikugan/ui/theme/__init__.py`:

```python
"""Rikugan theme system — single source of truth for color tokens."""

from .manager import ThemeManager, _hex_luminance, blend_tokens, format_template
from .palette_dark import DARK_TOKENS
from .palette_light import LIGHT_TOKENS
from .tokens import ThemeMode, ThemeTokens, is_dark_tokens

__all__ = [
    "ThemeManager",
    "ThemeMode",
    "ThemeTokens",
    "DARK_TOKENS",
    "LIGHT_TOKENS",
    "is_dark_tokens",
    "_hex_luminance",
    "blend_tokens",
    "format_template",
]
```

- [ ] **Step 4: Unskip the contrast tests from Tasks 2-3**

In `tests/tools/test_theme_palettes.py`:
- `TestDarkPalette.test_dark_text_contrast` — should now pass
- `TestLightPalette.test_light_tokens_window_is_light` — should pass
- `TestLightPalette.test_light_text_contrast` — should pass

If they had `@unittest.skip` decorators from Tasks 2-3, remove them now.

- [ ] **Step 5: Run all theme tests to verify they pass**

Run: `python -m pytest tests/tools/test_theme_tokens.py tests/tools/test_theme_palettes.py tests/tools/test_theme_manager.py -v`
Expected: PASS for all tests

- [ ] **Step 6: Commit**

```bash
git add rikugan/ui/theme/manager.py rikugan/ui/theme/__init__.py tests/tools/test_theme_manager.py tests/tools/test_theme_palettes.py
git commit -m "feat(theme): add ThemeManager singleton + helpers (skeleton)"
```

---

## Task 5: Add palette_ida.py with QPalette derivation + 5-token semantic derivation

**Files:**
- Create: `rikugan/ui/theme/palette_ida.py`
- Modify: `tests/tools/test_theme_palettes.py`

> **Note**: This module builds IDA_NATIVE tokens dynamically from the
> current `QApplication.palette()`. It also derives the 5 semantic tokens
> (`success/warning/error/code_text/code_bg`) since IDA QPalette has no
> equivalent.

- [ ] **Step 1: Write the failing test**

Append to `tests/tools/test_theme_palettes.py`:

```python
class TestIDAPaletteDerivation(unittest.TestCase):
    def test_derive_ida_tokens_dark(self):
        """Simulate IDA's dark palette and verify derivation."""
        from PySide6.QtGui import QColor, QPalette
        from rikugan.ui.theme.palette_ida import derive_ida_tokens

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#d4d4d4"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#252526"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#d4d4d4"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#2d2d2d"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#d4d4d4"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#0e639c"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Mid, QColor("#3c3c3c"))
        pal.setColor(QPalette.ColorRole.Dark, QColor("#1a1a1a"))
        pal.setColor(QPalette.ColorRole.Light, QColor("#5a5a5a"))

        tokens = derive_ida_tokens(source=_FakeApp(pal))
        self.assertEqual(len(asdict(tokens)), 17)
        self.assertEqual(tokens.window.lower(), "#1e1e1e")
        # Code text should match text in dark mode
        self.assertEqual(tokens.code_text.lower(), tokens.text.lower())

    def test_derive_ida_tokens_light(self):
        """Simulate IDA's light palette and verify derivation."""
        from PySide6.QtGui import QColor, QPalette
        from rikugan.ui.theme.palette_ida import derive_ida_tokens

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#fafafa"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f0f0f0"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#f0f0f0"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#1e1e1e"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#0066cc"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Mid, QColor("#cccccc"))
        pal.setColor(QPalette.ColorRole.Dark, QColor("#a0a0a0"))
        pal.setColor(QPalette.ColorRole.Light, QColor("#ffffff"))

        tokens = derive_ida_tokens(source=_FakeApp(pal))
        # Code bg should be alt_base
        self.assertEqual(tokens.code_bg.lower(), tokens.alt_base.lower())


class _FakeApp:
    """Stand-in for QApplication that returns a fixed palette."""
    def __init__(self, pal):
        self._pal = pal

    def palette(self):
        return self._pal
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_theme_palettes.py::TestIDAPaletteDerivation -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `rikugan/ui/theme/palette_ida.py`:

```python
"""Derive ThemeTokens from the current QApplication palette.

Used when ThemeMode is AUTO (in IDA) or IDA_NATIVE. Reads 12 QPalette
roles and derives 5 semantic tokens (success/warning/error/code_text/code_bg)
by blending fixed base hues toward the active text luminance.

Binja is NOT theme-aware in the same way — this module is IDA-specific.
For Binja, the manager falls back to DARK_TOKENS before calling here.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QPalette  # type: ignore[import-not-found]

from .manager import _hex_luminance, blend_tokens
from .tokens import ThemeTokens

# Fixed reference hues for semantic tokens.
# VS Code-inspired: teal-green, pale yellow, soft red.
_SUCCESS_BASE = "#4ec9b0"
_WARNING_BASE = "#dcdcaa"
_ERROR_BASE = "#f48771"

_ROLE_KEYS: list[tuple[QPalette.ColorRole, str]] = [
    (QPalette.ColorRole.Window, "window"),
    (QPalette.ColorRole.WindowText, "window_text"),
    (QPalette.ColorRole.Base, "base"),
    (QPalette.ColorRole.AlternateBase, "alt_base"),
    (QPalette.ColorRole.Text, "text"),
    (QPalette.ColorRole.Button, "button"),
    (QPalette.ColorRole.ButtonText, "button_text"),
    (QPalette.ColorRole.Highlight, "highlight"),
    (QPalette.ColorRole.HighlightedText, "highlight_text"),
    (QPalette.ColorRole.Mid, "mid"),
    (QPalette.ColorRole.Dark, "dark"),
    (QPalette.ColorRole.Light, "light"),
]


def _read_qpalette_colors(source: Any) -> dict[str, str]:
    """Read 12 QPalette role colors as a dict of hex strings.

    `source` must have a `palette()` method (QApplication or a test fake).
    """
    pal = source.palette()
    out: dict[str, str] = {}
    for role, key in _ROLE_KEYS:
        out[key] = pal.color(role).name()
    return out


def _derive_semantic_tokens(
    qp_colors: dict[str, str], as_dict: bool = True
) -> dict[str, str]:
    """Derive success/warning/error/code_text/code_bg from QPalette values.

    Strategy:
    - Saturate base hues toward text luminance for legibility (15% blend
      in dark, 35% in light — light needs more desaturation).
    - code_text = text (same as body text)
    - code_bg = alt_base (slightly recessed surface)
    """
    text = qp_colors["text"]
    alt_base = qp_colors["alt_base"]
    is_dark = _hex_luminance(qp_colors["window"]) < 0.5
    amount = 0.15 if is_dark else 0.35

    # We need a ThemeTokens object to use blend_tokens. Build a partial.
    partial = ThemeTokens(
        window=qp_colors["window"],
        window_text=qp_colors["window_text"],
        base=qp_colors["base"],
        alt_base=qp_colors["alt_base"],
        text=qp_colors["text"],
        button=qp_colors["button"],
        button_text=qp_colors["button_text"],
        highlight=qp_colors["highlight"],
        highlight_text=qp_colors["highlight_text"],
        mid=qp_colors["mid"],
        light=qp_colors["light"],
        dark=qp_colors["dark"],
        success=_SUCCESS_BASE,
        warning=_WARNING_BASE,
        error=_ERROR_BASE,
        code_text=text,
        code_bg=alt_base,
    )

    return {
        "success": blend_tokens(partial, "success", "text", amount),
        "warning": blend_tokens(partial, "warning", "text", amount),
        "error": blend_tokens(partial, "error", "text", amount),
        "code_text": text,
        "code_bg": alt_base,
    }


def derive_ida_tokens(source: Any) -> ThemeTokens:
    """Build a full ThemeTokens from a QApplication-like `source`.

    `source` must have a `palette()` method. Returns ThemeTokens with
    all 17 fields populated.
    """
    qp = _read_qpalette_colors(source)
    semantic = _derive_semantic_tokens(qp)
    return ThemeTokens(**qp, **semantic)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_theme_palettes.py::TestIDAPaletteDerivation -v`
Expected: PASS for both tests

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/theme/palette_ida.py tests/tools/test_theme_palettes.py
git commit -m "feat(theme): add IDA palette derivation with 5 semantic tokens"
```

---

## Task 6: Wire ThemeManager._compute_tokens to all 4 modes + emit signal on set_mode

**Files:**
- Modify: `rikugan/ui/theme/manager.py`
- Modify: `tests/tools/test_theme_manager.py`

> **Note**: At this point `set_mode` is a no-op (skeleton). This task
> makes it actually compute tokens and emit `themeChanged`. Still no
> QSS build / no debounce — those come in Task 7.

- [ ] **Step 1: Update existing test to verify signal now fires**

The existing test `test_theme_changed_signal_fires_on_switch` already
exercises this path. Re-run it to confirm it's still failing:

Run: `python -m pytest tests/tools/test_theme_manager.py::TestThemeManagerSingleton::test_theme_changed_signal_fires_on_switch -v`
Expected: FAIL because `set_mode` is still a no-op (skeleton).

- [ ] **Step 2: Implement the real `_compute_tokens` and `set_mode` behavior**

Replace the skeleton methods in `rikugan/ui/theme/manager.py`:

```python
# At top of file, add the new imports:
from PySide6.QtWidgets import QApplication  # type: ignore[import-not-found]
from .palette_ida import derive_ida_tokens
from .palette_light import LIGHT_TOKENS
from ..core.host import is_ida  # late import — host module is top-level
```

> **Import note**: `from ..core.host import is_ida` creates a cross-tree
> import (`ui.theme` → `core.host`). Verify the project does not have
> circular import issues by running:
> `python -c "from rikugan.ui.theme.manager import ThemeManager; ThemeManager.instance()"`
> If this fails, fall back to a lazy import inside `_compute_tokens`:
> `from rikugan.core.host import is_ida`.

Update the `set_mode` and `_compute_tokens` methods:

```python
    def set_mode(self, mode: ThemeMode) -> None:
        """Set the theme mode. No-op if same value. Emits themeChanged on change."""
        if mode == self._mode:
            return
        self._mode = mode
        self._tokens_cache = None
        # Apply and emit immediately (debounce comes in Task 7).
        self._apply_now()

    def _apply_now(self) -> None:
        """Compute current tokens, emit themeChanged. (No QSS yet — Task 7.)"""
        tokens = self.tokens()
        self.themeChanged.emit(tokens)

    def _compute_tokens(self) -> ThemeTokens:
        """Compute tokens for the current mode.

        AUTO: IDA → derive_ida_tokens; Binja/standalone → DARK_TOKENS.
        DARK: DARK_TOKENS.
        LIGHT: LIGHT_TOKENS.
        IDA_NATIVE: derive_ida_tokens (Binja → DARK_TOKENS + warning log).
        """
        from ..core.host import is_ida  # lazy to avoid top-level cycle
        from ..core.logging import log_warning
        from .palette_ida import derive_ida_tokens

        if self._mode == ThemeMode.DARK:
            return DARK_TOKENS
        if self._mode == ThemeMode.LIGHT:
            return LIGHT_TOKENS
        if self._mode == ThemeMode.AUTO:
            if is_ida():
                try:
                    app = QApplication.instance()
                    if app is not None:
                        return derive_ida_tokens(app)
                except Exception:
                    pass
            return DARK_TOKENS
        if self._mode == ThemeMode.IDA_NATIVE:
            if not is_ida():
                log_warning(
                    "IDA Native theme requested on non-IDA host; "
                    "falling back to Dark"
                )
                return DARK_TOKENS
            try:
                app = QApplication.instance()
                if app is not None:
                    return derive_ida_tokens(app)
            except Exception:
                pass
            return DARK_TOKENS
        return DARK_TOKENS  # unreachable; defensive
```

- [ ] **Step 3: Run all manager tests**

Run: `python -m pytest tests/tools/test_theme_manager.py -v`
Expected: PASS for all tests, including:
- `test_theme_changed_signal_fires_on_switch`
- `test_subscribe_helper_replays_current_tokens`
- `test_set_mode_updates_mode`

- [ ] **Step 4: Add a new test for AUTO mode behavior**

Append to `tests/tools/test_theme_manager.py`:

```python
class TestThemeManagerModeResolution(unittest.TestCase):
    def setUp(self):
        ThemeManager.reset_for_testing()

    def tearDown(self):
        ThemeManager.reset_for_testing()

    def test_auto_mode_ida_returns_ida_tokens(self, qapp=None):  # type: ignore[no-untyped-def]
        """AUTO + IDA host → derive from QPalette (mocked)."""
        from unittest.mock import patch
        from PySide6.QtGui import QColor, QPalette

        mgr = ThemeManager.instance()
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#abcdef"))
        with patch("rikugan.core.host.is_ida", return_value=True), \
             patch.object(QApplication, "instance", return_value=_FakeQApp(pal)):
            mgr.set_mode(ThemeMode.AUTO)
            self.assertEqual(mgr.tokens().window.lower(), "#abcdef")


class _FakeQApp:
    def __init__(self, pal):
        self._pal = pal
    def palette(self):
        return self._pal
```

> **Note**: This test needs `QApplication.instance()` to be patchable.
> If patching fails in the test environment, mark this test as
> `@unittest.skip("requires Qt app patching")` and verify manually.

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/theme/manager.py tests/tools/test_theme_manager.py
git commit -m "feat(theme): wire ThemeManager._compute_tokens for all 4 modes"
```

---

## Task 7: Add debounce (50ms) and QSS rebuild on set_mode

**Files:**
- Modify: `rikugan/ui/theme/manager.py`
- Modify: `tests/tools/test_theme_manager.py`

> **Note**: This task adds the `QApplication.setStyleSheet()` call and
> debounce timer (50ms) for rapid switches. The QSS template itself is
> a simple placeholder — full template lives in a later task.

- [ ] **Step 1: Add failing test for debounce**

Append to `tests/tools/test_theme_manager.py`:

```python
class TestThemeManagerDebounce(unittest.TestCase):
    def setUp(self):
        ThemeManager.reset_for_testing()

    def tearDown(self):
        ThemeManager.reset_for_testing()

    def test_rapid_set_mode_emits_only_once(self):
        """3 rapid set_mode calls within 50ms should emit 1 signal total."""
        mgr = ThemeManager.instance()
        captured: list[Any] = []
        mgr.themeChanged.connect(lambda t: captured.append(t))

        mgr.set_mode(ThemeMode.DARK)
        mgr.set_mode(ThemeMode.LIGHT)
        mgr.set_mode(ThemeMode.DARK)

        # Process events so the debounce timer fires
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        # Only the LAST mode should result in a single emission
        self.assertEqual(len(captured), 1)
        # tokens should be DARK
        self.assertEqual(captured[0].window.lower(), "#1e1e1e")

    def test_qss_applied_to_application(self):
        """After debounce flush, qApp.setStyleSheet should be called."""
        from unittest.mock import patch, MagicMock
        from PySide6.QtCore import QCoreApplication

        mgr = ThemeManager.instance()
        with patch.object(QApplication, "instance") as mock_inst:
            mock_app = MagicMock()
            mock_inst.return_value = mock_app
            mgr.set_mode(ThemeMode.LIGHT)
            QCoreApplication.processEvents()
            mock_app.setStyleSheet.assert_called()
            # The QSS should reference LIGHT's window color
            call_args = mock_app.setStyleSheet.call_args[0][0]
            self.assertIn("#ffffff", call_args.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_theme_manager.py::TestThemeManagerDebounce -v`
Expected: FAIL because `set_mode` doesn't apply QSS or debounce yet.

- [ ] **Step 3: Add debounce and QSS rebuild**

In `rikugan/ui/theme/manager.py`, add these imports at the top:

```python
from PySide6.QtCore import QTimer  # type: ignore[import-not-found]
```

Add these constants near the top of the class file (before the class):

```python
_DEBOUNCE_MS = 50

# Minimal QSS template — covers the most-common widget backgrounds. The
# full template is built incrementally as more widgets subscribe; for
# now this is enough to verify the rebuild path works.
_QSS_TEMPLATE = """
QWidget {{
    background-color: {window};
    color: {text};
}}
QFrame {{
    background-color: {base};
    border: 1px solid {mid};
}}
QPushButton {{
    background-color: {button};
    color: {button_text};
    border: 1px solid {mid};
    padding: 4px;
    border-radius: 4px;
}}
QPushButton:hover {{
    background-color: {alt_base};
}}
QToolButton {{
    background-color: {button};
    color: {button_text};
    border: 1px solid {mid};
    padding: 2px;
}}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {base};
    color: {text};
    border: 1px solid {mid};
    selection-background-color: {highlight};
    selection-color: {highlight_text};
}}
QTabWidget::pane {{
    border: 1px solid {mid};
    background-color: {window};
}}
QTabBar::tab {{
    background-color: {alt_base};
    color: {text};
    padding: 6px 12px;
    border: 1px solid {mid};
}}
QTabBar::tab:selected {{
    background-color: {window};
    color: {text};
}}
QMenu {{
    background-color: {window};
    color: {text};
    border: 1px solid {mid};
}}
QMenu::item:selected {{
    background-color: {highlight};
    color: {highlight_text};
}}
QScrollBar:vertical {{
    background-color: {alt_base};
    width: 12px;
}}
QScrollBar::handle:vertical {{
    background-color: {mid};
    border-radius: 4px;
}}
QScrollBar:horizontal {{
    background-color: {alt_base};
    height: 12px;
}}
QScrollBar::handle:horizontal {{
    background-color: {mid};
    border-radius: 4px;
}}
"""
```

Replace `set_mode` and `_apply_now` with the debounced version:

```python
    def __init__(self) -> None:
        super().__init__()
        self._mode: ThemeMode = ThemeMode.AUTO
        self._tokens_cache: ThemeTokens | None = None
        self._pending_apply: QTimer | None = None

    def set_mode(self, mode: ThemeMode) -> None:
        """Set the theme mode. No-op if same value. Debounces rapid switches."""
        if mode == self._mode:
            return
        self._mode = mode
        self._tokens_cache = None
        # Debounce: if a previous apply is pending, cancel it.
        if self._pending_apply is not None:
            self._pending_apply.stop()
        self._pending_apply = QTimer()
        self._pending_apply.setSingleShot(True)
        self._pending_apply.timeout.connect(self._apply_now)
        self._pending_apply.start(_DEBOUNCE_MS)

    def _apply_now(self) -> None:
        """Compute current tokens, apply QSS, emit themeChanged."""
        tokens = self.tokens()
        # Apply QSS to the QApplication if one exists.
        try:
            app = QApplication.instance()
            if app is not None:
                qss = self._build_stylesheet(tokens)
                app.setStyleSheet(qss)
        except Exception as e:
            from ..core.logging import log_error
            log_error(f"Failed to apply theme QSS: {e}", exc_info=True)
        self.themeChanged.emit(tokens)
        self._pending_apply = None

    def _build_stylesheet(self, tokens: ThemeTokens) -> str:
        """Build the QSS string from tokens. (Full template is in this file.)"""
        return format_template(_QSS_TEMPLATE, tokens)
```

- [ ] **Step 4: Run debounce tests to verify they pass**

Run: `python -m pytest tests/tools/test_theme_manager.py::TestThemeManagerDebounce -v`
Expected: PASS for both new tests

- [ ] **Step 5: Run all manager tests to verify no regressions**

Run: `python -m pytest tests/tools/test_theme_manager.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add rikugan/ui/theme/manager.py tests/tools/test_theme_manager.py
git commit -m "feat(theme): add 50ms debounce + QSS rebuild on set_mode"
```

---

## Task 8: Add IDAThemeWatcher (polls QPalette every 500ms)

**Files:**
- Create: `rikugan/ui/theme/watcher.py`
- Create: `tests/tools/test_theme_watcher.py`

> **Note**: The watcher only does anything when `ThemeMode` is `AUTO` or
> `IDA_NATIVE`. In other modes it polls but no-ops (or we can skip
> starting it). For simplicity, we always start it in IDA and let it
> check the mode internally.

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_theme_watcher.py`:

```python
"""Tests for rikugan.ui.theme.watcher — IDAThemeWatcher palette change detection."""

from __future__ import annotations

import sys
import unittest
from typing import Any

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtGui import QColor, QPalette

from rikugan.ui.theme.manager import ThemeManager
from rikugan.ui.theme.tokens import ThemeMode
from rikugan.ui.theme.watcher import IDAThemeWatcher, _palette_signature


class TestPaletteSignature(unittest.TestCase):
    def test_signature_changes_with_window_color(self):
        pal1 = QPalette()
        pal1.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal1.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        pal2 = QPalette()
        pal2.setColor(QPalette.ColorRole.Window, QColor("#222222"))
        pal2.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        self.assertNotEqual(_palette_signature(pal1), _palette_signature(pal2))

    def test_signature_unchanged_for_same_palette(self):
        pal1 = QPalette()
        pal1.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal2 = QPalette()
        pal2.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        self.assertEqual(_palette_signature(pal1), _palette_signature(pal2))


class TestIDAThemeWatcher(unittest.TestCase):
    def setUp(self):
        ThemeManager.reset_for_testing()

    def tearDown(self):
        ThemeManager.reset_for_testing()
        if hasattr(self, "_watcher") and self._watcher is not None:
            self._watcher.stop()

    def test_detects_palette_change(self):
        """When the palette changes, themeChanged should fire."""
        # Create a mock source that we can swap
        class _Source:
            def __init__(self, pal):
                self.pal = pal
            def palette(self):
                return self.pal

        pal1 = QPalette()
        pal1.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal1.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        pal1.setColor(QPalette.ColorRole.Base, QColor("#111111"))
        pal1.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a1a1a"))
        pal1.setColor(QPalette.ColorRole.Text, QColor("#eeeeee"))
        pal1.setColor(QPalette.ColorRole.Button, QColor("#222222"))
        pal1.setColor(QPalette.ColorRole.ButtonText, QColor("#eeeeee"))
        pal1.setColor(QPalette.ColorRole.Highlight, QColor("#007acc"))
        pal1.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        pal1.setColor(QPalette.ColorRole.Mid, QColor("#444444"))
        pal1.setColor(QPalette.ColorRole.Dark, QColor("#000000"))
        pal1.setColor(QPalette.ColorRole.Light, QColor("#888888"))

        source = _Source(pal1)
        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.AUTO)

        # Patch is_ida to return True and the manager's QApplication source
        from unittest.mock import patch
        with patch("rikugan.core.host.is_ida", return_value=True), \
             patch.object(mgr, "_app_source", return_value=source, create=True):
            watcher = IDAThemeWatcher(interval_ms=50)
            self._watcher = watcher
            captured: list[Any] = []
            mgr.themeChanged.connect(lambda t: captured.append(t))
            watcher.start()

            # Change the palette
            pal1.setColor(QPalette.ColorRole.Window, QColor("#fafafa"))
            pal1.setColor(QPalette.ColorRole.WindowText, QColor("#1a1a1a"))

            # Force a tick
            watcher._tick()
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 100)

            self.assertGreater(len(captured), 0)
            self.assertEqual(captured[-1].window.lower(), "#fafafa")

    def test_no_signal_on_no_change(self):
        class _Source:
            def __init__(self, pal):
                self.pal = pal
            def palette(self):
                return self.pal

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        source = _Source(pal)
        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.AUTO)

        from unittest.mock import patch
        with patch("rikugan.core.host.is_ida", return_value=True), \
             patch.object(mgr, "_app_source", return_value=source, create=True):
            watcher = IDAThemeWatcher(interval_ms=50)
            self._watcher = watcher
            captured: list[Any] = []
            mgr.themeChanged.connect(lambda t: captured.append(t))
            watcher.start()

            # First tick establishes the signature
            watcher._tick()
            # Second tick with same palette should not emit
            watcher._tick()

            self.assertEqual(len(captured), 0)

    def test_stop_prevents_further_ticks(self):
        watcher = IDAThemeWatcher(interval_ms=50)
        watcher.start()
        self.assertTrue(watcher._alive.is_set())
        watcher.stop()
        self.assertFalse(watcher._alive.is_set())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_theme_watcher.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the watcher**

Create `rikugan/ui/theme/watcher.py`:

```python
"""IDAThemeWatcher — polls QApplication.palette() and notifies ThemeManager.

Only meaningful in IDA hosts. Started by PLUGIN_ENTRY for the IDA host.
No-op on Binja (do not start the watcher there).

Behavior:
- Polls every `interval_ms` (default 500) via QTimer.singleShot (recursive).
- Compares (Window, WindowText) color signature against the last seen.
- On change → calls `ThemeManager.refresh_from_host()` which recomputes
  IDA_NATIVE tokens and emits themeChanged.
- Catches all exceptions in the tick loop to avoid crashing the Qt event
  loop on transient palette access errors.
"""

from __future__ import annotations

import threading
from typing import Any, ClassVar

from PySide6.QtCore import QObject, QTimer  # type: ignore[import-not-found]
from PySide6.QtGui import QPalette  # type: ignore[import-not-found]

from ..core.logging import log_error
from .manager import ThemeManager


def _palette_signature(pal: QPalette) -> tuple[str, str]:
    """Two-color signature (Window, WindowText) used for change detection."""
    return (
        pal.color(QPalette.ColorRole.Window).name(),
        pal.color(QPalette.ColorRole.WindowText).name(),
    )


class IDAThemeWatcher(QObject):
    """Polls QApplication.palette() and notifies the manager on change."""

    def __init__(self, interval_ms: int = 500) -> None:
        super().__init__()
        self._interval_ms = interval_ms
        self._last_sig: tuple[str, str] | None = None
        self._alive = threading.Event()

    def start(self) -> None:
        """Begin polling. Idempotent."""
        if self._alive.is_set():
            return
        self._alive.set()
        # Use QTimer.singleShot (recursive) so we don't hold a QTimer
        # object that would need explicit deletion.
        QTimer.singleShot(self._interval_ms, self._tick)

    def stop(self) -> None:
        """Stop polling. Subsequent ticks will not reschedule."""
        self._alive.clear()

    def _tick(self) -> None:
        """Single poll cycle. Reschedules itself if still alive."""
        if not self._alive.is_set():
            return
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return
            sig = _palette_signature(app.palette())
            if sig != self._last_sig:
                self._last_sig = sig
                ThemeManager.instance().refresh_from_host()
        except Exception as e:
            log_error(f"ThemeWatcher tick failed: {e}", exc_info=True)
        finally:
            if self._alive.is_set():
                QTimer.singleShot(self._interval_ms, self._tick)
```

Add `refresh_from_host` to `ThemeManager` in `rikugan/ui/theme/manager.py`:

```python
    def refresh_from_host(self) -> None:
        """Re-derive tokens from current QApplication palette.

        Called by IDAThemeWatcher when QPalette changes. Invalidates the
        token cache and re-applies (QSS + signal emit).
        """
        self._tokens_cache = None
        # Bypass debounce — watcher tick is already rate-limited.
        if self._pending_apply is not None:
            self._pending_apply.stop()
            self._pending_apply = None
        self._apply_now()
```

- [ ] **Step 4: Run all watcher tests**

Run: `python -m pytest tests/tools/test_theme_watcher.py -v`
Expected: PASS for all tests (assuming the `_app_source` patch in tests
works; if not, refactor tests to use a `_Source` class injected into
the manager directly).

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/theme/watcher.py tests/tools/test_theme_watcher.py rikugan/ui/theme/manager.py
git commit -m "feat(theme): add IDAThemeWatcher (polls QPalette every 500ms)"
```

---

## Task 9: Add conftest.py with qapp fixture + add _app_source helper to manager

**Files:**
- Create: `tests/tools/conftest.py`
- Modify: `tests/tools/test_theme_watcher.py`
- Modify: `rikugan/ui/theme/manager.py`

> **Note**: Pytest auto-loads `conftest.py` files. The `qapp` fixture
> provides a single `QApplication` per test session (Qt requires
> exactly one QApplication instance per process).

- [ ] **Step 1: Create the conftest**

Create `tests/tools/conftest.py`:

```python
"""Shared pytest fixtures for UI tests."""

from __future__ import annotations

import sys
import pytest

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Session-scoped QApplication. Pytest-qt equivalent without the dep."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Do not call app.quit() — other fixtures may need it.
```

- [ ] **Step 2: Add `_app_source` to ThemeManager for testability**

In `rikugan/ui/theme/manager.py`, add a method that the watcher can use
to get the palette source. For production it returns `QApplication.instance()`;
for tests, it can be patched.

```python
    def _app_source(self) -> Any:
        """Return the object to read QPalette from. Patchable for tests."""
        return QApplication.instance()
```

> **Note**: This adds a test seam without breaking production. The
> watcher in Task 8 already calls `QApplication.instance()` directly —
> for the watcher's tick to use this seam, refactor it to call
> `ThemeManager.instance()._app_source()` instead. Update `watcher.py`
> in the next step.

Update `rikugan/ui/theme/watcher.py` `_tick` method:

```python
    def _tick(self) -> None:
        if not self._alive.is_set():
            return
        try:
            source = ThemeManager.instance()._app_source()
            if source is None:
                return
            pal = source.palette()
            sig = _palette_signature(pal)
            if sig != self._last_sig:
                self._last_sig = sig
                ThemeManager.instance().refresh_from_host()
        except Exception as e:
            log_error(f"ThemeWatcher tick failed: {e}", exc_info=True)
        finally:
            if self._alive.is_set():
                QTimer.singleShot(self._interval_ms, self._tick)
```

- [ ] **Step 3: Update test_theme_watcher.py to use qapp fixture and remove inline mock**

The current watcher test mocks `QApplication.instance` indirectly via
`_app_source` patch. Now that the watcher uses `_app_source` directly,
the test must patch `ThemeManager._app_source`. Simplify the test:

```python
class TestIDAThemeWatcher(unittest.TestCase):
    def setUp(self):
        ThemeManager.reset_for_testing()

    def tearDown(self):
        ThemeManager.reset_for_testing()
        if hasattr(self, "_watcher") and self._watcher is not None:
            self._watcher.stop()

    def test_detects_palette_change(self):
        class _Source:
            def __init__(self, pal):
                self.pal = pal
            def palette(self):
                return self.pal

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#111111"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#111111"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a1a1a"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#eeeeee"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#222222"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#eeeeee"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#007acc"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Mid, QColor("#444444"))
        pal.setColor(QPalette.ColorRole.Dark, QColor("#000000"))
        pal.setColor(QPalette.ColorRole.Light, QColor("#888888"))

        source = _Source(pal)
        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.AUTO)
        # Patch the manager's source seam
        mgr._app_source = lambda: source  # type: ignore[assignment]

        watcher = IDAThemeWatcher(interval_ms=50)
        self._watcher = watcher
        captured: list[Any] = []
        mgr.themeChanged.connect(lambda t: captured.append(t))
        watcher.start()

        # Change the palette
        pal.setColor(QPalette.ColorRole.Window, QColor("#fafafa"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#1a1a1a"))

        watcher._tick()
        QCoreApplication.processEvents(
            QEventLoop.ProcessEventsFlag.AllEvents, 100
        )

        self.assertGreater(len(captured), 0)
        self.assertEqual(captured[-1].window.lower(), "#fafafa")

    # ... (other tests similarly simplified)
```

- [ ] **Step 4: Run all tests to verify**

Run: `python -m pytest tests/tools/test_theme_watcher.py tests/tools/test_theme_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/tools/conftest.py rikugan/ui/theme/manager.py rikugan/ui/theme/watcher.py tests/tools/test_theme_watcher.py
git commit -m "feat(theme): add qapp fixture and test seam for watcher"
```

---

## Task 10: Add config migration (theme → theme_mode) and validation

**Files:**
- Modify: `rikugan/core/config.py`
- Create: `tests/tools/test_theme_migration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_theme_migration.py`:

```python
"""Tests for rikugan.core.config theme_mode migration and validation."""

from __future__ import annotations

import sys
import unittest
from dataclasses import asdict

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from rikugan.core.config import (
    RikuganConfig,
    _migrate_v1_to_v2,
    _validate_theme_mode,
)


class TestV1ToV2Migration(unittest.TestCase):
    def test_v1_dark_maps_to_dark(self):
        data = {"theme": "dark", "other_field": "x"}
        result = _migrate_v1_to_v2(data)
        self.assertEqual(result["theme_mode"], "dark")
        self.assertNotIn("theme", result)
        self.assertEqual(result["other_field"], "x")

    def test_v1_ida_native_maps_to_ida(self):
        data = {"theme": "ida_native"}
        self.assertEqual(_migrate_v1_to_v2(data)["theme_mode"], "ida")

    def test_v1_light_maps_to_light(self):
        data = {"theme": "light"}
        self.assertEqual(_migrate_v1_to_v2(data)["theme_mode"], "light")

    def test_v1_unknown_falls_back_to_auto(self):
        data = {"theme": "rainbow"}
        self.assertEqual(_migrate_v1_to_v2(data)["theme_mode"], "auto")

    def test_v2_passthrough(self):
        data = {"theme_mode": "light"}
        self.assertEqual(_migrate_v1_to_v2(data), {"theme_mode": "light"})

    def test_both_theme_and_theme_mode_prefers_v2(self):
        """If both keys exist (corrupt config), theme_mode wins."""
        data = {"theme": "dark", "theme_mode": "light"}
        result = _migrate_v1_to_v2(data)
        self.assertEqual(result["theme_mode"], "light")
        # The "theme" key is still removed to normalize
        self.assertNotIn("theme", result)


class TestThemeModeValidation(unittest.TestCase):
    def test_valid_modes_unchanged(self):
        for mode in ("auto", "dark", "light", "ida"):
            data = {"theme_mode": mode}
            self.assertEqual(_validate_theme_mode(data)["theme_mode"], mode)

    def test_invalid_mode_falls_back_to_auto(self):
        data = {"theme_mode": "neon_pink"}
        result = _validate_theme_mode(data)
        self.assertEqual(result["theme_mode"], "auto")

    def test_missing_mode_gets_default(self):
        data: dict = {}
        self.assertEqual(_validate_theme_mode(data)["theme_mode"], "auto")


class TestRikuganConfigDefault(unittest.TestCase):
    def test_default_theme_mode_is_auto(self):
        config = RikuganConfig()
        self.assertEqual(config.theme_mode, "auto")

    def test_old_theme_field_does_not_exist(self):
        config = RikuganConfig()
        # The 'theme' field should be gone (renamed to theme_mode)
        self.assertFalse(hasattr(config, "theme") or "theme" in asdict(config))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_theme_migration.py -v`
Expected: FAIL — `_migrate_v1_to_v2` and `RikuganConfig.theme_mode` don't exist

- [ ] **Step 3: Update `rikugan/core/config.py`**

Add the migration and validation functions, and rename `theme` → `theme_mode`:

```python
# Near the top of the file, add this import:
import logging

# Add these constants near the top:
_VALID_THEME_MODES = {"auto", "dark", "light", "ida"}


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate v1 schema (theme: "dark"/"ida_native"/"light") to v2
    (theme_mode: "auto"/"dark"/"light"/"ida").

    If both `theme` and `theme_mode` exist (corrupt config),
    `theme_mode` wins. The legacy `theme` key is removed in all cases.
    """
    if "theme" in data and "theme_mode" not in data:
        old = data.pop("theme")
        mapping = {
            "dark": "dark",
            "ida_native": "ida",
            "light": "light",
        }
        data["theme_mode"] = mapping.get(old, "auto")
    elif "theme" in data and "theme_mode" in data:
        # Both present — drop the legacy key, keep theme_mode.
        data.pop("theme")
    return data


def _validate_theme_mode(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure `theme_mode` is a valid mode, falling back to 'auto' if not.

    Also adds a default if the key is missing entirely.
    """
    mode = data.get("theme_mode", "auto")
    if mode not in _VALID_THEME_MODES:
        logging.warning(
            f"Invalid theme_mode {mode!r} in config, falling back to 'auto'"
        )
        data["theme_mode"] = "auto"
    elif "theme_mode" not in data:
        data["theme_mode"] = "auto"
    return data
```

Rename the field in `RikuganConfig`:

```python
# BEFORE:
    theme: str = "dark"

# AFTER:
    theme_mode: str = "auto"
```

Update the `load` method to call the migration + validation:

```python
    def load(self) -> None:
        if not os.path.exists(self.config_path):
            return
        with open(self.config_path) as f:
            data = json.load(f)
        # Schema version check (for future migrations)
        _stored_version = data.pop("schema_version", 0)

        # Theme migration: v1 (theme: "dark") → v2 (theme_mode: "auto")
        data = _migrate_v1_to_v2(data)
        data = _validate_theme_mode(data)

        # ... (rest of existing load code unchanged)
```

- [ ] **Step 4: Find all references to `config.theme` and update them**

Run this grep to find all usages:

```bash
grep -rn "config.theme\|\.theme\b" rikugan/ --include="*.py" | grep -v "_theme\|theme_mode\|test_\|tokens\."
```

For each non-test match, replace `config.theme` with `config.theme_mode`.

- [ ] **Step 5: Run migration tests**

Run: `python -m pytest tests/tools/test_theme_migration.py -v`
Expected: PASS for all tests

- [ ] **Step 6: Run the full test suite to verify no regressions**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: ALL PASS (or only pre-existing failures unrelated to this change)

- [ ] **Step 7: Commit**

```bash
git add rikugan/core/config.py tests/tools/test_theme_migration.py
git commit -m "feat(theme): migrate config.theme → theme_mode with validation"
```

---

## Task 11: Refactor styles.py to delegate to ThemeManager

**Files:**
- Modify: `rikugan/ui/styles.py`
- Modify: `tests/tools/test_settings_dialog.py` (verify mocks still work)

> **Note**: `styles.py` exposes 8 public functions. The refactor converts
> it to thin wrappers. Existing widget code continues to work without
> import changes.

- [ ] **Step 1: Verify existing styles.py test mocks pass**

Run: `python -m pytest tests/tools/test_settings_dialog.py tests/tools/test_panel_core.py -v`
Expected: PASS (these tests mock `rikugan.ui.styles`)

- [ ] **Step 2: Read the current styles.py to plan the refactor**

Read `rikugan/ui/styles.py` end-to-end. Identify all 8 public functions
and their callers.

- [ ] **Step 3: Replace each public function with a thin wrapper**

In `rikugan/ui/styles.py`, replace the implementation of each public
function while keeping the same signature:

```python
"""Backward-compat wrapper around rikugan.ui.theme.manager.

This module preserves the public API that widget code has depended on
since pre-theme-system refactors. New code should use
``rikugan.ui.theme.ThemeManager.instance()`` directly.
"""

from __future__ import annotations

from .theme.manager import (
    DARK_TOKENS as _DARK_TOKENS,
    _hex_luminance as _hex_luminance_inner,
    blend_tokens,
    format_template,
)
from .theme.manager import ThemeManager
from .theme.palette_ida import derive_ida_tokens, _read_qpalette_colors
from .theme.tokens import ThemeMode, ThemeTokens

# Re-export for backward compat
__all__ = [
    "blend_theme_color",
    "get_host_palette_colors",
    "use_native_host_theme",
    "maybe_host_stylesheet",
    "host_stylesheet",
    "build_theme_stylesheet",
    "build_small_button_stylesheet",
    "_hex_luminance",
    "DARK_THEME",
    "IDA_NATIVE_THEME",
    "_FALLBACK_COLORS",
]


# Alias: blend_theme_color was a free function. It becomes a manager method.
def blend_theme_color(a: str, b: str, amount: float) -> str:
    """Blend two hex colors. Kept as free function for backward compat."""
    from .theme.manager import _hex_to_rgb, _rgb_to_hex
    a_rgb = _hex_to_rgb(a)
    b_rgb = _hex_to_rgb(b)
    blended = tuple(
        int(round(ax + (bx - ax) * amount)) for ax, bx in zip(a_rgb, b_rgb)
    )
    return _rgb_to_hex(*blended)


def _hex_luminance(hex_color: str) -> float:
    """Backward-compat alias for the manager's _hex_luminance."""
    return _hex_luminance_inner(hex_color)


# Hardcoded fallback colors (QPalette defaults) — used when QApplication
# is not available or palette access raises.
_FALLBACK_COLORS = {
    "window": "#1e1e1e",
    "window_text": "#d4d4d4",
    "base": "#1e1e1e",
    "alt_base": "#252526",
    "text": "#d4d4d4",
    "button": "#2d2d2d",
    "button_text": "#d4d4d4",
    "highlight": "#0e639c",
    "highlight_text": "#ffffff",
    "mid": "#3c3c3c",
    "dark": "#1a1a1a",
    "light": "#5a5a5a",
}

# DARK_THEME kept for backward compat — points to DARK_TOKENS as a dict.
DARK_THEME = {
    "window": _DARK_TOKENS.window,
    "window_text": _DARK_TOKENS.window_text,
    "base": _DARK_TOKENS.base,
    "alt_base": _DARK_TOKENS.alt_base,
    "text": _DARK_TOKENS.text,
    "button": _DARK_TOKENS.button,
    "button_text": _DARK_TOKENS.button_text,
    "highlight": _DARK_TOKENS.highlight,
    "highlight_text": _DARK_TOKENS.highlight_text,
    "mid": _DARK_TOKENS.mid,
    "dark": _DARK_TOKENS.dark,
    "light": _DARK_TOKENS.light,
}

# IDA_NATIVE_THEME is now derived at runtime. Keep a placeholder dict
# with the fallback values for backward compat; the manager is the real
# source of truth.
IDA_NATIVE_THEME = dict(_FALLBACK_COLORS)


def get_host_palette_colors(source=None) -> dict[str, str]:
    """Return the 12 QPalette-role colors as a dict.

    Delegates to ThemeManager; falls back to _FALLBACK_COLORS if no
    QApplication is available.
    """
    try:
        from PySide6.QtWidgets import QApplication
        if source is None:
            source = QApplication.instance()
        if source is None:
            return dict(_FALLBACK_COLORS)
        return _read_qpalette_colors(source)
    except Exception:
        return dict(_FALLBACK_COLORS)


def use_native_host_theme() -> bool:
    """Return True when the active theme follows the host's native palette."""
    from ..core.host import is_ida
    mode = ThemeManager.instance().mode()
    if mode == ThemeMode.AUTO:
        return is_ida()
    if mode == ThemeMode.IDA_NATIVE:
        return is_ida()  # Binja returns False (manager falls back to DARK)
    return False


def maybe_host_stylesheet(css: str) -> str:
    """Return CSS if not in native mode, else empty string."""
    return "" if use_native_host_theme() else css


def host_stylesheet(custom_css: str, native_css: str = "") -> str:
    """Return the stylesheet for the active theme mode."""
    if use_native_host_theme():
        return native_css
    return custom_css


def build_theme_stylesheet(css: str) -> str:
    """Build the full QSS by combining the manager's template with caller CSS."""
    tokens = ThemeManager.instance().tokens()
    base_qss = format_template(_BASE_QSS_TEMPLATE, tokens)
    return base_qss + "\n" + css


# Internal QSS template (moved from manager to keep styles.py self-contained
# for callers that import _BASE_QSS_TEMPLATE).
_BASE_QSS_TEMPLATE = """
QWidget {
    background-color: {window};
    color: {text};
}
"""


def build_small_button_stylesheet() -> str:
    """Build a QSS string for small buttons using current tokens."""
    tokens = ThemeManager.instance().tokens()
    return format_template(_SMALL_BTN_QSS, tokens)


_SMALL_BTN_QSS = """
QPushButton {
    background-color: {button};
    color: {button_text};
    border: 1px solid {mid};
    border-radius: 6px;
    padding: 4px;
    font-size: 11px;
}
QPushButton:hover {
    background-color: {alt_base};
}
"""
```

> **Note**: This refactor preserves the public API. The implementations
> delegate to `ThemeManager` so the same `tokens()` are used everywhere.
> Existing widget code (e.g., `panel_core.py`) imports these functions
> and continues to work without changes.

- [ ] **Step 4: Run all UI tests to verify no regressions**

Run: `python -m pytest tests/tools/ -v --timeout=60`
Expected: ALL PASS (existing tests should still pass because the public
API is preserved)

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/styles.py
git commit -m "refactor(theme): convert styles.py to thin wrapper around ThemeManager"
```

---

## Task 12: Refactor markdown_renderer.py to use ThemeManager

**Files:**
- Modify: `rikugan/ui/markdown_renderer.py`

> **Note**: `markdown_renderer.py` reads colors from `get_host_palette_colors()`
> and `use_native_host_theme()`. After Task 11, these still work — they
> delegate to ThemeManager. But we can simplify the renderer to read
> tokens directly. This is a quality-of-life refactor; the existing
> approach also works.

- [ ] **Step 1: Read the current markdown_renderer.py to identify color-reading sites**

Read `rikugan/ui/markdown_renderer.py` end-to-end. Find:
- `_native_theme_styles()` — uses QPalette directly
- `_dark_theme_styles()` — uses hardcoded DARK_THEME
- `_build_theme_styles()` — entry point that calls one of the above

- [ ] **Step 2: Refactor `_build_theme_styles` to use ThemeManager.tokens()**

Replace the implementation:

```python
def _build_theme_styles(source: Any = None) -> dict[str, str]:
    """Build a complete style dict for the renderer.

    Uses ThemeManager.tokens() for all 17 colors. No more use_native_host_theme()
    branching — the manager already accounts for AUTO/IDA_NATIVE mode.
    """
    from .theme.manager import ThemeManager, blend_tokens
    from .theme.tokens import is_dark_tokens

    tokens = ThemeManager.instance().tokens()

    base = tokens.base
    window = tokens.window
    text = tokens.text
    highlight = tokens.highlight
    mid = tokens.mid
    code_bg = tokens.code_bg
    code_text = tokens.code_text
    success = tokens.success
    warning = tokens.warning
    error = tokens.error

    # Recessed border for code blocks: blend mid toward window at 35%
    border = blend_tokens(tokens, "mid", "window", 0.35)
    # Heading color: blend highlight toward text at 15%
    heading_color = blend_tokens(tokens, "highlight", "text", 0.15)
    # Inline code: slightly lighter than code_bg, slightly darker than text
    inline_code_bg = blend_tokens(tokens, "code_bg", "base", 0.5)
    inline_fg = tokens.text
    # Muted text: blend text toward mid at 50%
    muted = blend_tokens(tokens, "text", "mid", 0.5)
    # Accent border: use highlight
    accent_border = highlight

    return {
        "is_dark": is_dark_tokens(tokens),
        "inline_code": (
            f"background-color:{inline_code_bg}; color:{inline_fg}; "
            "padding:1px 4px; border-radius:3px; font-family:monospace; font-size:12px;"
        ),
        "code_block": (
            f"background-color:{code_bg}; color:{code_text}; "
            f"border-left:3px solid {accent_border}; border-radius:6px; "
            "padding:8px; font-family:monospace; font-size:12px; "
            "white-space:pre-wrap; word-break:break-all;"
        ),
        "lang_tag": f"color:{muted}; font-size:10px;",
        "link": f"color:{highlight};",
        "heading": f"color:{heading_color}; font-weight:bold;",
        "heading_border": f"border-bottom:1px solid {border};",
        "hr": f"border:1px solid {border};",
        "paragraph": "margin:0 0 4px 0;",
        "blockquote": (
            f"border-left:3px solid {accent_border}; "
            f"color:{muted}; font-style:italic; "
            "padding:4px 12px; margin:4px 0;"
        ),
        "table": "border-collapse:collapse; width:100%;",
        "table_cell": (
            f"border:1px solid {border}; padding:4px 8px; "
            "vertical-align:top; word-wrap:break-word;"
        ),
        "table_header": (
            f"border:1px solid {border}; padding:4px 8px; "
            f"font-weight:bold; background-color:{blend_tokens(tokens, 'base', 'window', 0.08)};"
        ),
        "table_row_even": f"background-color:{blend_tokens(tokens, 'base', 'window', 0.05)};",
        "list_item": "margin:1px 0;",
        "task_unchecked": "☐",
        "task_checked": "☑",
    }
```

Delete `_native_theme_styles()` and `_dark_theme_styles()` — they are
no longer called.

- [ ] **Step 3: Run markdown tests**

Run: `python -m pytest tests/tools/test_markdown.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add rikugan/ui/markdown_renderer.py
git commit -m "refactor(theme): use ThemeManager.tokens() in markdown_renderer"
```

---

## Task 13: Add pygments style mapping + cache invalidation in highlight.py

**Files:**
- Modify: `rikugan/ui/highlight.py`
- Create: `tests/tools/test_theme_pygments.py`

- [ ] **Step 1: Read the current highlight.py**

Read `rikugan/ui/highlight.py`. Find:
- `highlight_code()` function
- `_formatter_cache` global (if present)
- `_THEME_PYGMENTS_MAP` (likely does not exist yet)

- [ ] **Step 2: Write the failing test**

Create `tests/tools/test_theme_pygments.py`:

```python
"""Tests for pygments style mapping + cache invalidation on theme change."""

from __future__ import annotations

import sys
import unittest
from typing import Any

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from rikugan.ui.theme.manager import ThemeManager
from rikugan.ui.theme.tokens import ThemeMode


class TestPygmentsStyleMap(unittest.TestCase):
    def setUp(self):
        ThemeManager.reset_for_testing()

    def tearDown(self):
        ThemeManager.reset_for_testing()

    def test_dark_mode_uses_monokai(self):
        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.DARK)
        from rikugan.ui.highlight import _pygments_style_for_tokens
        self.assertEqual(_pygments_style_for_tokens(mgr.tokens()), "monokai")

    def test_light_mode_uses_default(self):
        mgr = ThemeManager.instance()
        mgr.set_mode(ThemeMode.LIGHT)
        from rikugan.ui.highlight import _pygments_style_for_tokens
        self.assertEqual(_pygments_style_for_tokens(mgr.tokens()), "default")

    def test_ida_native_dark_palette_uses_monokai(self):
        from rikugan.ui.theme.palette_ida import derive_ida_tokens
        from PySide6.QtGui import QColor, QPalette
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
        # ... (set all 12 roles to dark values)
        tokens = derive_ida_tokens(source=_FakeApp(pal))
        from rikugan.ui.highlight import _pygments_style_for_tokens
        self.assertEqual(_pygments_style_for_tokens(tokens), "monokai")


class _FakeApp:
    def __init__(self, pal):
        self.pal = pal
    def palette(self):
        return self.pal
```

- [ ] **Step 3: Add `_pygments_style_for_tokens` and cache invalidation in highlight.py**

In `rikugan/ui/highlight.py`, add:

```python
from .theme.manager import ThemeManager
from .theme.tokens import is_dark_tokens


def _pygments_style_for_tokens(tokens) -> str:
    """Return the pygments style name for a given token set.

    Uses luminance check (not mode name) so that IDA_NATIVE in a light
    IDA theme also gets a light code style. The bug this fixes: pre-
    theme-system, code highlighting used monokai whenever the mode was
    'dark', but in IDA Native + Light IDA theme, monokai clashes with
    the light background.
    """
    return "monokai" if is_dark_tokens(tokens) else "default"


# Module-level formatter cache, keyed by style name
_formatter_cache: dict[str, Any] = {}


def _get_formatter(style_name: str) -> Any:
    """Get (or create) a pygments HtmlFormatter for the given style.

    Cache is keyed by style name. Invalidate on theme change via
    ``clear_formatter_cache()``.
    """
    if style_name not in _formatter_cache:
        try:
            from pygments.formatters import HtmlFormatter
            _formatter_cache[style_name] = HtmlFormatter(style=style_name)
        except Exception:
            _formatter_cache[style_name] = None
    return _formatter_cache[style_name]


def clear_formatter_cache() -> None:
    """Clear the pygments formatter cache. Call on theme change."""
    _formatter_cache.clear()


# Subscribe to themeChanged to clear the cache automatically
def _on_theme_changed(_tokens) -> None:
    clear_formatter_cache()


ThemeManager.instance().themeChanged.connect(_on_theme_changed)
```

Update `highlight_code()` to use the new style mapping:

```python
def highlight_code(code: str, language: str, is_dark: bool = None) -> str:
    """Highlight code with pygments, using the active theme's style.

    `is_dark` is now optional — if None, derive from the active theme's
    tokens. The signature is preserved for backward compat.
    """
    if not _HAS_PYGMENTS:
        return _plain_code(code)
    if is_dark is None:
        tokens = ThemeManager.instance().tokens()
        is_dark = is_dark_tokens(tokens)
    style_name = "monokai" if is_dark else "default"
    formatter = _get_formatter(style_name)
    if formatter is None:
        return _plain_code(code)
    # ... (rest of existing highlight logic, using `formatter` instead of
    # creating a new one each time)
```

- [ ] **Step 4: Run pygments tests**

Run: `python -m pytest tests/tools/test_theme_pygments.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/highlight.py tests/tools/test_theme_pygments.py
git commit -m "feat(theme): pygments style map + cache invalidation on theme change"
```

---

## Task 14: Add Settings UI — _build_appearance_tab() with combo + preview chip

**Files:**
- Modify: `rikugan/ui/settings_dialog.py`
- Create: `tests/tools/test_settings_dialog.py` (additions, file already exists)

- [ ] **Step 1: Read the existing test_settings_dialog.py to understand its pattern**

Read `tests/tools/test_settings_dialog.py` end-to-end. Note the
`MagicMock` stubs and `ensure_pyside6_stubs` setup. New tests must
follow the same pattern.

- [ ] **Step 2: Add a failing test for the new Appearance tab**

Append to `tests/tools/test_settings_dialog.py`:

```python
class TestAppearanceTab(unittest.TestCase):
    def setUp(self):
        # Add theme subsystem to the stub list
        from rikugan.ui import theme
        for _attr in ["ThemeManager", "ThemeMode", "ThemeTokens",
                      "DARK_TOKENS", "LIGHT_TOKENS"]:
            if not hasattr(theme, _attr):
                setattr(theme, _attr, MagicMock())
        ThemeManager.reset_for_testing()

    def tearDown(self):
        ThemeManager.reset_for_testing()

    def test_appearance_tab_in_dialog(self):
        """SettingsDialog should have an 'Appearance' tab at index 1."""
        config = RikuganConfig()
        dlg = SettingsDialog(config=config)
        # The tab labels in order
        labels = [dlg._tabs.tabText(i) for i in range(dlg._tabs.count())]
        self.assertIn("Appearance", labels)
        appearance_idx = labels.index("Appearance")
        self.assertEqual(appearance_idx, 1)

    def test_theme_combo_has_four_modes(self):
        config = RikuganConfig()
        dlg = SettingsDialog(config=config)
        # Find the combo by objectName or by walking the tab
        # (For this test, assume _theme_combo is exposed)
        self.assertTrue(hasattr(dlg, "_theme_combo"))
        self.assertEqual(dlg._theme_combo.count(), 4)
        modes = [dlg._theme_combo.itemData(i) for i in range(4)]
        self.assertEqual(modes, ["auto", "dark", "light", "ida"])

    def test_theme_combo_reflects_config(self):
        config = RikuganConfig()
        config.theme_mode = "light"
        dlg = SettingsDialog(config=config)
        # Combo should be set to "light"
        idx = dlg._theme_combo.currentIndex()
        self.assertEqual(dlg._theme_combo.itemData(idx), "light")

    def test_changing_combo_updates_manager(self):
        config = RikuganConfig()
        dlg = SettingsDialog(config=config)
        # Simulate user selecting "dark"
        for i in range(dlg._theme_combo.count()):
            if dlg._theme_combo.itemData(i) == "dark":
                dlg._theme_combo.setCurrentIndex(i)
                break
        self.assertEqual(ThemeManager.instance().mode().value, "dark")
        self.assertEqual(config.theme_mode, "dark")
```

> **Note**: The exact attribute names (`_theme_combo`, `_theme_preview`)
> must match what the implementation in Step 4 uses. Adjust the tests
> if naming changes.

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/tools/test_settings_dialog.py::TestAppearanceTab -v`
Expected: FAIL — no Appearance tab exists yet

- [ ] **Step 4: Add `_build_appearance_tab` and `_ThemePreviewChip`**

In `rikugan/ui/settings_dialog.py`, add the following imports near the
top (with the other `rikugan.ui.*` imports):

```python
from .theme.manager import ThemeManager
from .theme.tokens import ThemeMode
```

Add the `_ThemePreviewChip` class (place it before `SettingsDialog`):

```python
class _ThemePreviewChip(QWidget):
    """Mini-preview showing the current theme's window/text/accent colors."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(140, 64)
        self.setObjectName("theme_preview_chip")
        ThemeManager.instance().themeChanged.connect(self.update)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        from .qt_compat import QColor, QPainter
        t = ThemeManager.instance().tokens()
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor(t.window))
            p.setPen(QColor(t.text))
            p.drawText(
                self.rect().adjusted(8, 6, -8, -8),
                Qt.AlignmentFlag.AlignTopLeft, "Sample text",
            )
            swatch_y = 30
            for i, key in enumerate(("highlight", "success", "warning", "error")):
                p.fillRect(8 + i * 18, swatch_y, 14, 14, QColor(getattr(t, key)))
        finally:
            p.end()
```

Insert the new tab into `_build_ui`. Find this section in `SettingsDialog._build_ui`:

```python
        # Tab 1-3: Skills, MCP, Profiles — all use a shared SettingsService
        from .settings_service import SettingsService
        ...
        self._service = SettingsService(self._config, tool_registry=self._tool_registry)
        self._skills_tab = SkillsTab(self._config, service=self._service)
        self._tabs.addTab(self._skills_tab, "Skills")
```

Insert the Appearance tab BEFORE the Skills/MCP/Profiles block:

```python
        # Tab 1: Appearance (theme settings)
        appearance_tab = self._build_appearance_tab()
        self._tabs.addTab(appearance_tab, "Appearance")

        # Tab 2-4: Skills, MCP, Profiles (existing, indices shift +1)
        from .settings_service import SettingsService
        ...
```

Add the `_build_appearance_tab` and `_on_theme_changed` methods to
`SettingsDialog` (place near the other `_build_*` methods):

```python
    def _build_appearance_tab(self) -> QWidget:
        """Build the Appearance tab (theme selection)."""
        from .qt_compat import QComboBox, QFormLayout, QLabel
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
        ThemeManager.instance().themeChanged.connect(self._theme_preview.update)

        layout.addRow("Theme:", self._theme_combo)
        layout.addRow("Preview:", self._theme_preview)

        note = QLabel(
            "Auto uses IDA's native theme when running in IDA Pro, and "
            "Rikugan Dark in Binary Ninja. 'IDA Native' updates in real "
            "time when you switch IDA's theme via View → Theme."
        )
        note.setWordWrap(True)
        layout.addRow(note)
        return widget

    def _on_theme_changed(self, idx: int) -> None:
        mode_str = self._theme_combo.itemData(idx)
        self._config.theme_mode = mode_str
        ThemeManager.instance().set_mode(ThemeMode(mode_str))
        self._theme_preview.update()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/tools/test_settings_dialog.py -v`
Expected: PASS for `TestAppearanceTab` and existing tests

- [ ] **Step 6: Commit**

```bash
git add rikugan/ui/settings_dialog.py tests/tools/test_settings_dialog.py
git commit -m "feat(theme): add Appearance tab in Settings with combo + preview"
```

---

## Task 15: Wire ThemeManager init into PLUGIN_ENTRY (IDA) and bootstrap (Binja)

**Files:**
- Modify: `rikugan_plugin.py` (IDA entry)
- Modify: `rikugan/binja/bootstrap.py` (Binja entry)

- [ ] **Step 1: Read the IDA entry point**

Read `rikugan_plugin.py`. Find:
- `RikuganPlugmod.run()` — entry point
- `_toggle_panel()` — where the panel is created

- [ ] **Step 2: Add ThemeManager init to the IDA run path**

In `rikugan_plugin.py`, add the import at the top:

```python
from rikugan.core.config import RikuganConfig
from rikugan.ui.theme.manager import ThemeManager
from rikugan.ui.theme.tokens import ThemeMode
from rikugan.core.host import is_ida
```

In `RikuganPlugmod.run()` (or wherever the panel is first toggled),
add theme initialization BEFORE creating the panel:

```python
    def run(self, arg: int) -> bool:
        # 1. Load config (with v1→v2 migration)
        config = RikuganConfig.load()

        # 2. Init ThemeManager singleton
        theme_mgr = ThemeManager.instance()
        theme_mgr.set_mode(ThemeMode(config.theme_mode))

        # 3. Start IDA watcher (IDA only — no-op for non-IDA hosts)
        from rikugan.ui.theme.watcher import IDAThemeWatcher
        if is_ida() and not getattr(self, "_theme_watcher", None):
            self._theme_watcher = IDAThemeWatcher(interval_ms=500)
            self._theme_watcher.start()

        # 4. Toggle panel
        self._toggle_panel()
        return True
```

Also add cleanup in `term()`:

```python
    def term(self) -> None:
        # ... (existing code)
        # Stop theme watcher
        if getattr(self, "_theme_watcher", None) is not None:
            self._theme_watcher.stop()
            self._theme_watcher = None
        # ... (existing cleanup)
```

- [ ] **Step 3: Add ThemeManager init to the Binja bootstrap path**

In `rikugan/binja/bootstrap.py`, find the `_toggle_panel()` function
(or equivalent). Add the init at the top of that function:

```python
    # Binja equivalent — no watcher (Binja is not theme-aware)
    from rikugan.core.config import RikuganConfig
    from rikugan.ui.theme.manager import ThemeManager
    from rikugan.ui.theme.tokens import ThemeMode

    config = RikuganConfig.load()
    theme_mgr = ThemeManager.instance()
    theme_mgr.set_mode(ThemeMode(config.theme_mode))
    # Note: no IDAThemeWatcher for Binja — falls back to DARK
```

- [ ] **Step 4: Run plugin tests**

Run: `python -m pytest tests/tools/test_rikugan_plugin.py tests/tools/test_rikugan_binaryninja.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rikugan_plugin.py rikugan/binja/bootstrap.py
git commit -m "feat(theme): wire ThemeManager init in PLUGIN_ENTRY and Binja bootstrap"
```

---

## Task 16: Refactor 14 UI files to use ThemeManager (largest task)

**Files:**
- Modify: 14 UI files (see mapping table in spec)

> **Note**: This task is the largest by volume but mechanical. Each
> file's pattern is the same: replace hardcoded hex with QSS templates
> that read from `ThemeManager.instance().tokens()`. This task is split
> into 3 sub-tasks for incremental progress.

### Task 16a: Refactor `message_widgets.py` and `tool_widgets.py` (highest ref count)

- [ ] **Step 1: Identify the color constants at the top of each file**

In `message_widgets.py`:
```python
_USER_ROLE = "#4ec9b0"
_ASSISTANT_ROLE = "#569cd6"
_BODY_TEXT = "#d4d4d4"
_MUTED_TEXT = "#808080"
_SUBTLE_TEXT = "#b0b0b0"
_USER_BUBBLE_BG = "#0e639c"
_USER_BUBBLE_BORDER = "#1177bb"
_ASSISTANT_BUBBLE_BG = "#151515"
_ASSISTANT_BUBBLE_BORDER = "#2c2c2c"
_THINKING_SURFACE_BG = "#1e1e1e"
_THINKING_BLOCK_BG = "#1a1a2e"
_THINKING_BLOCK_BORDER = "#2a2a3e"
_TOOL_BG = "#252526"
_TOOL_BORDER = "#3c3c3c"
```

Map each to a token:
```python
# Mapping for message_widgets.py
_USER_ROLE            = lambda t: t.success    # greenish role
_ASSISTANT_ROLE       = lambda t: t.highlight  # blue accent
_BODY_TEXT            = lambda t: t.text
_MUTED_TEXT           = lambda t: t.mid       # 50% text/mid blend via blend_tokens if needed
_SUBTLE_TEXT          = lambda t: t.light
_USER_BUBBLE_BG       = lambda t: t.highlight
_USER_BUBBLE_BORDER   = lambda t: t.highlight  # blend with text at 0.2 for lighter border
_ASSISTANT_BUBBLE_BG  = lambda t: t.alt_base
_ASSISTANT_BUBBLE_BORDER = lambda t: t.mid
_THINKING_SURFACE_BG  = lambda t: t.base
_THINKING_BLOCK_BG    = lambda t: t.alt_base
_THINKING_BLOCK_BORDER= lambda t: t.mid
_TOOL_BG              = lambda t: t.alt_base
_TOOL_BORDER          = lambda t: t.mid
```

- [ ] **Step 2: Convert each constant to a function call**

Replace every usage like `_USER_ROLE` with a function call that reads
from the manager. For example, in `_frame_css` calls:

```python
# BEFORE
_frame_css(background=_USER_BUBBLE_BG, border=_USER_BUBBLE_BORDER)

# AFTER
tokens = ThemeManager.instance().tokens()
_frame_css(background=tokens.highlight, border=tokens.highlight)
```

> **Note**: This is invasive — the existing code uses module-level
> constants for performance. After conversion, every widget construction
> does a manager lookup. The performance impact is negligible (< 1ms)
> because the manager caches tokens.

- [ ] **Step 3: Run message_widgets and tool_widgets tests**

Run: `python -m pytest tests/tools/test_message_widgets.py tests/tools/test_tool_widget_logic.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add rikugan/ui/message_widgets.py rikugan/ui/tool_widgets.py
git commit -m "refactor(theme): replace hardcoded hex in message_widgets + tool_widgets"
```

### Task 16b: Refactor `bulk_renamer.py`, `panel_core.py`, `settings_dialog.py`, `tools_panel.py`, `mutation_log_view.py`, `plan_view.py`, `tabs/profiles_tab.py`

- [ ] **Step 1: Repeat the pattern from 16a for each file**

For each file:
1. Identify the color constants (top of file or inline).
2. Map to token names (or `blend_tokens` for derived colors).
3. Replace each usage.

- [ ] **Step 2: Run tests for each refactored file**

```bash
python -m pytest tests/tools/test_bulk_renamer.py tests/tools/test_panel_core.py tests/tools/test_settings_dialog.py tests/tools/test_plan_view.py tests/tools/test_mutation_log_view.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add rikugan/ui/bulk_renamer.py rikugan/ui/panel_core.py rikugan/ui/settings_dialog.py rikugan/ui/tools_panel.py rikugan/ui/mutation_log_view.py rikugan/ui/plan_view.py rikugan/ui/tabs/profiles_tab.py
git commit -m "refactor(theme): replace hardcoded hex in 7 UI files"
```

### Task 16c: Refactor remaining 5 files: `input_area.py`, `oauth_consent.py`, `agent_tree.py`, `markdown_renderer.py` (already done in Task 12), `highlight.py` (already done in Task 13)

- [ ] **Step 1: Refactor `input_area.py` (5 refs)**

Identify and replace 5 hex colors. The file is small; likely a few
border/background constants.

- [ ] **Step 2: Refactor `oauth_consent.py` (6 refs)**

Similar pattern.

- [ ] **Step 3: Refactor `agent_tree.py` (20 refs)**

Tree widget styling. Map to tokens.

- [ ] **Step 4: Run all UI tests**

```bash
python -m pytest tests/tools/ -v --timeout=60
```

Expected: ALL PASS

- [ ] **Step 5: Verify no hardcoded hex remains**

```bash
grep -rn "#[0-9a-fA-F]\{6\}" rikugan/ui/ --include="*.py" | grep -v "theme/" | grep -v "^Binary"
```

Expected: Only references in `rikugan/ui/theme/` (the legitimate location).

- [ ] **Step 6: Commit**

```bash
git add rikugan/ui/input_area.py rikugan/ui/oauth_consent.py rikugan/ui/agent_tree.py
git commit -m "refactor(theme): replace hardcoded hex in input_area + oauth_consent + agent_tree"
```

---

## Task 17: Final integration test + coverage check

**Files:**
- Create: `tests/tools/test_theme_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/tools/test_theme_integration.py`:

```python
"""End-to-end tests for the theme system — widget subscription round-trip."""

from __future__ import annotations

import sys
import unittest
from typing import Any

from tests.qt_stubs import ensure_pyside6_stubs
ensure_pyside6_stubs()

from PySide6.QtCore import QCoreApplication, QEventLoop

from rikugan.ui.theme.manager import ThemeManager
from rikugan.ui.theme.tokens import ThemeMode, ThemeTokens


class TestThemeIntegration(unittest.TestCase):
    def setUp(self):
        ThemeManager.reset_for_testing()

    def tearDown(self):
        ThemeManager.reset_for_testing()

    def test_custom_widget_subscribes_and_receives_initial(self):
        """A widget that subscribes should get initial tokens + future updates."""

        class _FakeWidget:
            def __init__(self) -> None:
                self.last_tokens: ThemeTokens | None = None
                ThemeManager.instance().subscribe(self._on_change)

            def _on_change(self, t: ThemeTokens) -> None:
                self.last_tokens = t

        # Initial subscription replays current tokens
        ThemeManager.instance().set_mode(ThemeMode.DARK)
        widget = _FakeWidget()
        self.assertIsNotNone(widget.last_tokens)
        self.assertEqual(widget.last_tokens.window.lower(), "#1e1e1e")

        # Switch theme — widget should receive new tokens
        ThemeManager.instance().set_mode(ThemeMode.LIGHT)
        QCoreApplication.processEvents(
            QEventLoop.ProcessEventsFlag.AllEvents, 100
        )
        self.assertEqual(widget.last_tokens.window.lower(), "#ffffff")

    def test_qss_rebuild_visible_to_widgets(self):
        """QApplication.setStyleSheet should be called after debounce."""
        from unittest.mock import patch, MagicMock

        mgr = ThemeManager.instance()
        captured_qss: list[str] = []

        with patch.object(__import__("PySide6.QtWidgets", fromlist=["QApplication"]),
                          "QApplication") as MockQApp:
            mock_instance = MagicMock()
            mock_instance.setStyleSheet.side_effect = lambda css: captured_qss.append(css)
            MockQApp.instance.return_value = mock_instance

            mgr.set_mode(ThemeMode.LIGHT)
            QCoreApplication.processEvents(
                QEventLoop.ProcessEventsFlag.AllEvents, 100
            )

            self.assertGreater(len(captured_qss), 0)
            qss = captured_qss[-1].lower()
            self.assertIn("#ffffff", qss)  # LIGHT window color

    def test_full_switch_round_trip(self):
        """Dark → Light → Auto → Dark should emit 3 signals (assuming no-op on same)."""
        mgr = ThemeManager.instance()
        captured: list[Any] = []
        mgr.themeChanged.connect(lambda t: captured.append(t))

        mgr.set_mode(ThemeMode.DARK)
        mgr.set_mode(ThemeMode.LIGHT)
        mgr.set_mode(ThemeMode.AUTO)
        mgr.set_mode(ThemeMode.DARK)  # same as initial, but mode was changed → emits

        QCoreApplication.processEvents(
            QEventLoop.ProcessEventsFlag.AllEvents, 200
        )

        # 3 changes, 3 signals (after debounce collapses if any rapid succession)
        self.assertGreaterEqual(len(captured), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the integration test**

Run: `python -m pytest tests/tools/test_theme_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run the FULL test suite**

```bash
python -m pytest tests/ -v --timeout=60
```

Expected: ALL PASS (or only pre-existing failures unrelated to this change)

- [ ] **Step 4: Verify coverage for the new theme package**

```bash
python -m pytest tests/tools/test_theme_*.py --cov=rikugan.ui.theme --cov-report=term-missing
```

Expected: Coverage ≥ 85% for `rikugan/ui/theme/`

- [ ] **Step 5: Commit**

```bash
git add tests/tools/test_theme_integration.py
git commit -m "test(theme): add end-to-end integration tests"
```

---

## Task 18: Update CHANGELOG and verify acceptance criteria

**Files:**
- Modify: `docs/CHANGELOG.md` (create if not exists)

- [ ] **Step 1: Check if CHANGELOG exists**

```bash
ls docs/CHANGELOG.md 2>/dev/null || echo "NOT_FOUND"
```

- [ ] **Step 2: Add a CHANGELOG entry**

If `docs/CHANGELOG.md` does not exist, create it. Add an entry under
"Unreleased":

```markdown
# Changelog

## [Unreleased]

### Added

- **Theme system**: User-selectable themes (Auto, Dark, Light, IDA Native)
  via Settings → Appearance tab.
- **Real-time IDA theme sync**: Rikugan follows IDA Pro's theme in
  real time (View → Theme updates within 500ms).
- **Light theme**: VS Code Light+ style for users who prefer light backgrounds.
- **`ThemeManager` singleton** as the single source of truth for colors.

### Changed

- **Config schema**: `theme: str` renamed to `theme_mode: str`. Existing
  configs auto-migrate (v1 → v2).
- **`rikugan/ui/styles.py`**: Converted to thin wrapper; delegates to
  `ThemeManager`.
- **14 UI files**: Hardcoded color hex strings replaced with QSS
  templates that read from `ThemeManager.tokens()`.

### Fixed

- **Pygments code style**: Now luminance-based, so IDA Native + Light
  IDA theme gets a light code style (previously always used monokai).
```

- [ ] **Step 3: Run the verification checklist from the spec**

Walk through each acceptance criterion in the spec:

```markdown
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
```

- [ ] **Step 4: Final commit**

```bash
git add docs/CHANGELOG.md
git commit -m "docs: add CHANGELOG entry for theme system"
```

---

## Self-Review Checklist (run before handoff)

- [ ] **Spec coverage**: All 5 goals covered (theme selection, reactive
      sync, full UI coverage, light theme, backward compat). All 17
      ThemeTokens keys. All 4 ThemeMode values. Watcher 500ms, debounce
      50ms, all 14 UI files mentioned.

- [ ] **No placeholders**: No "TBD"/"TODO"/"implement later" in the plan.
      All code blocks are complete. No "similar to Task N" — each task
      repeats the code inline.

- [ ] **Type consistency**: `ThemeMode` is a `str, Enum` with values
      `"auto"/"dark"/"light"/"ida"`. `ThemeTokens` is a frozen dataclass
      with 17 fields. `ThemeManager` is a `QObject` singleton with
      `themeChanged = Signal(object)`. `set_mode(mode: ThemeMode)` is
      consistent across all callers.

- [ ] **File paths are absolute or repo-relative**: All paths use the
      form `rikugan/ui/...` (repo-relative) and `tests/tools/...`.

- [ ] **No task references undefined code**: All functions/classes
      referenced in a task's "Step 3" are defined in an earlier task's
      "Step 3" (or in the same task).

- [ ] **Frequent commits**: Each task ends with a `git commit`. Most
      tasks have 1-2 commits. Large refactor tasks (16a/b/c) are split
      into separate commits.

- [ ] **TDD discipline**: Every task writes a failing test first
      (Step 1), runs it to confirm failure (Step 2), then implements
      (Step 3), then runs to confirm pass (Step 4).

---

## Execution Estimate

| Task | Description | Est. effort | Risk |
|------|-------------|-------------|------|
| 1 | ThemeTokens + ThemeMode | 15 min | low |
| 2 | DARK_TOKENS | 10 min | low |
| 3 | LIGHT_TOKENS | 10 min | low |
| 4 | Manager skeleton + helpers | 30 min | low |
| 5 | palette_ida.py + 5-token derivation | 25 min | med |
| 6 | Wire _compute_tokens for 4 modes | 30 min | med |
| 7 | Debounce + QSS rebuild | 30 min | med |
| 8 | IDAThemeWatcher | 30 min | med |
| 9 | conftest.py + test seam | 20 min | low |
| 10 | Config migration | 30 min | med |
| 11 | styles.py delegation | 30 min | med |
| 12 | markdown_renderer refactor | 20 min | low |
| 13 | pygments mapping + cache | 25 min | low |
| 14 | Settings UI tab | 40 min | med |
| 15 | Wire into entry points | 20 min | low |
| 16a | message_widgets + tool_widgets | 60 min | high |
| 16b | 7 medium files | 90 min | med |
| 16c | 3 small files | 30 min | low |
| 17 | Integration test + coverage | 30 min | low |
| 18 | CHANGELOG + verification | 15 min | low |

**Total: ~9-11 hours** of focused work, assuming no major surprises.
Tasks 5, 7, 8, 11, 14, 16a have the highest risk — allocate buffer time.

---
