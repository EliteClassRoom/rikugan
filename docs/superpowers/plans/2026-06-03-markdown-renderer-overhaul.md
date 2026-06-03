# Markdown Renderer Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom regex Markdown converter with markdown-it-py + Pygments for richer rendering (tables, blockquotes, strikethrough, task lists, nested lists, syntax-highlighted code blocks) while keeping the `md_to_html(text, source)` API unchanged.

**Architecture:** 3-layer design — markdown-it-py parses Markdown into AST tokens, a custom `QtRenderer` converts tokens to Qt-compatible HTML with theme-aware inline styles, and `highlight.py` provides Pygments-based syntax highlighting for fenced code blocks.

**Tech Stack:** markdown-it-py 4.0, Pygments 2.19, Qt RichText (QLabel), Python 3.12

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `rikugan/ui/highlight.py` | **CREATE** | Pygments syntax highlighting with import guard |
| `rikugan/ui/markdown_renderer.py` | **CREATE** | QtRenderer — markdown-it tokens → Qt-compatible HTML |
| `rikugan/ui/markdown.py` | **MODIFY** | Entry point — delegates to markdown-it + QtRenderer, keeps legacy fallback |
| `requirements.txt` | **MODIFY** | Add `markdown-it-py>=3.0` |
| `tests/tools/test_markdown.py` | **MODIFY** | Update existing tests, add new test classes |

---

### Task 1: Add markdown-it-py dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add markdown-it-py to requirements.txt**

Append `markdown-it-py>=3.0` to `requirements.txt`:

```
anthropic>=0.39.0
openai>=1.50.0
google-genai>=1.0.0
mcp>=1.0.0
tomli>=2.0.0
cryptography>=43.0.0
ida-domain>=0.1.0
markdown-it-py>=3.0
```

- [ ] **Step 2: Install the dependency**

Run: `pip install markdown-it-py>=3.0`
Expected: Successfully installed (or "already satisfied")

- [ ] **Step 3: Verify import works**

Run: `python -c "from markdown_it import MarkdownIt; print(MarkdownIt().render('**test**'))"`
Expected: `<p><strong>test</strong></p>`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add markdown-it-py dependency for markdown rendering"
```

---

### Task 2: Create `highlight.py` — Pygments integration with import guard

**Files:**
- Create: `rikugan/ui/highlight.py`

This module wraps Pygments with graceful fallback. It must work when Pygments is absent.

- [ ] **Step 1: Write the module**

Create `rikugan/ui/highlight.py`:

```python
"""Pygments-based syntax highlighting for fenced code blocks.

Gracefully degrades when Pygments is not installed.
Output targets Qt RichText compatible HTML (inline styles only).
"""

from __future__ import annotations

import html as _html

_HAS_PYGMENTS = False
try:
    from pygments import highlight as _pygments_highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name, TextLexer
    from pygments.util import ClassNotFound

    _HAS_PYGMENTS = True
except ImportError:
    pass

# Cached formatters per style name (lazy singletons)
_formatter_cache: dict[str, HtmlFormatter] = {}


def _get_formatter(style_name: str) -> HtmlFormatter:
    """Return a cached HtmlFormatter with inline styles for Qt."""
    if style_name not in _formatter_cache:
        _formatter_cache[style_name] = HtmlFormatter(
            style=style_name,
            nowrap=True,
            noclasses=True,
            nobackground=True,
        )
    return _formatter_cache[style_name]


def highlight_code(code: str, language: str, is_dark: bool = True) -> str:
    """Highlight *code* in *language* using Pygments.

    Returns HTML with inline styles suitable for Qt RichText.
    Falls back to HTML-escaped plain text when Pygments is absent
    or the language is unknown.
    """
    if not _HAS_PYGMENTS or not language:
        return _plain_code(code)

    style_name = "monokai" if is_dark else "default"

    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        # Try common aliases for RE context
        alias_map = {
            "asm": "nasm",
            "x86": "nasm",
            "arm": "asm",
            "objective-c": "objc",
            "shell": "bash",
            "conf": "ini",
        }
        mapped = alias_map.get(language.lower())
        if mapped:
            try:
                lexer = get_lexer_by_name(mapped)
            except ClassNotFound:
                return _plain_code(code)
        else:
            return _plain_code(code)

    formatter = _get_formatter(style_name)
    highlighted = _pygments_highlight(code, lexer, formatter)
    return highlighted


def _plain_code(code: str) -> str:
    """Return HTML-escaped code for fallback rendering."""
    return _html.escape(code)
```

- [ ] **Step 2: Verify import works without Pygments (mock test)**

Run: `python -c "from rikugan.ui.highlight import highlight_code; print(highlight_code('x=1', 'python'))"`
Expected: HTML output with Pygments `<span style="...">` tags

- [ ] **Step 3: Verify fallback for unknown language**

Run: `python -c "from rikugan.ui.highlight import highlight_code; print(highlight_code('x=1', 'xyz_unknown'))"`
Expected: `x=1` (plain escaped text)

- [ ] **Step 4: Verify fallback for empty language**

Run: `python -c "from rikugan.ui.highlight import highlight_code; print(highlight_code('x=1', ''))"`
Expected: `x=1`

- [ ] **Step 5: Commit**

```bash
git add rikugan/ui/highlight.py
git commit -m "feat: add Pygments syntax highlighting module with import guard"
```

---

### Task 3: Create `markdown_renderer.py` — QtRenderer

**Files:**
- Create: `rikugan/ui/markdown_renderer.py`

This is the largest new file. It subclasses `RendererHTML` and overrides every token handler to produce `<div style="...">`-based HTML with theme-aware inline styles.

- [ ] **Step 1: Write the QtRenderer module**

Create `rikugan/ui/markdown_renderer.py`:

```python
"""Custom markdown-it renderer that produces Qt RichText-compatible HTML.

All styling uses inline ``style=`` attributes because QLabel's RichText
engine does not support CSS classes.  The renderer receives a theme
style dict from ``markdown._theme_markdown_styles()`` and produces
self-contained HTML fragments.
"""

from __future__ import annotations

import html as _html
import re as _re
from collections.abc import Sequence
from typing import Any

from markdown_it.common.utils import escapeHtml
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict

from .highlight import highlight_code
from .styles import _hex_luminance, get_host_palette_colors

# ---------------------------------------------------------------------------
# Theme style generation
# ---------------------------------------------------------------------------


def _build_theme_styles(source: Any = None) -> dict[str, str]:
    """Build a complete style dict for the renderer.

    This expands the old ``_theme_markdown_styles`` with entries for
    tables, blockquotes, and improved spacing.
    """
    from .styles import blend_theme_color, use_native_host_theme

    if use_native_host_theme():
        return _native_theme_styles()

    colors = get_host_palette_colors(source)
    base = colors["base"]
    window = colors["window"]
    text = colors["text"]
    highlight = colors["highlight"]
    mid = colors["mid"]
    border = blend_theme_color(mid, window, 0.35)
    heading_color = blend_theme_color(highlight, text, 0.15)
    code_bg = blend_theme_color(base, window, 0.15)
    inline_fg = blend_theme_color(highlight, text, 0.3)
    muted = blend_theme_color(text, window, 0.45)
    accent_border = blend_theme_color(highlight, window, 0.25)
    is_dark = _hex_luminance(window) < 0.5

    return {
        # Inline code
        "inline_code": (
            f"background-color:{code_bg}; color:{inline_fg}; "
            "padding:1px 4px; border-radius:3px; font-family:monospace; font-size:12px;"
        ),
        # Fenced code block container
        "code_block": (
            f"background-color:{base}; color:{text}; "
            f"border-left:3px solid {accent_border}; border-radius:6px; "
            "padding:8px; font-family:monospace; font-size:12px; "
            "white-space:pre-wrap; word-break:break-all;"
        ),
        # Language tag label
        "lang_tag": f"color:{muted}; font-size:10px;",
        # Links
        "link": f"color:{highlight};",
        # Headings
        "heading": f"color:{heading_color}; font-weight:bold;",
        # h1/h2 bottom border
        "heading_border": f"border-bottom:1px solid {border};",
        # Horizontal rule
        "hr": f"border:1px solid {border};",
        # Paragraph
        "paragraph": "margin:0 0 4px 0;",
        # Blockquote
        "blockquote": (
            f"border-left:3px solid {accent_border}; "
            f"color:{muted}; font-style:italic; "
            "padding:4px 12px; margin:4px 0;"
        ),
        # Table
        "table": f"border-collapse:collapse; width:100%;",
        "table_cell": (
            f"border:1px solid {border}; padding:4px 8px; "
            "vertical-align:top; word-wrap:break-word;"
        ),
        "table_header": (
            f"border:1px solid {border}; padding:4px 8px; "
            f"font-weight:bold; background-color:{blend_theme_color(base, window, 0.08)};"
        ),
        "table_row_even": f"background-color:{blend_theme_color(base, window, 0.05)};",
        # List
        "list_item": "margin:1px 0;",
        # Task list
        "task_unchecked": "☐",
        "task_checked": "☑",
        # Is dark theme (for Pygments style selection)
        "is_dark": is_dark,
    }


def _native_theme_styles() -> dict[str, str]:
    """Minimal styles for IDA native theme — let host handle colors."""
    return {
        "inline_code": "font-family:monospace; font-size:12px;",
        "code_block": "font-family:monospace; white-space:pre-wrap;",
        "lang_tag": "font-size:10px;",
        "link": "text-decoration:underline;",
        "heading": "font-weight:bold;",
        "heading_border": "",
        "hr": "",
        "paragraph": "",
        "blockquote": "font-style:italic; padding:4px 12px; border-left:3px solid gray;",
        "table": "border-collapse:collapse; width:100%;",
        "table_cell": "border:1px solid gray; padding:4px 8px;",
        "table_header": "border:1px solid gray; padding:4px 8px; font-weight:bold;",
        "table_row_even": "",
        "list_item": "",
        "task_unchecked": "☐",
        "task_checked": "☑",
        "is_dark": True,
    }


# ---------------------------------------------------------------------------
# Task list detection
# ---------------------------------------------------------------------------

_TASK_CHECKED_RE = _re.compile(r"^\[x\]\s?", _re.IGNORECASE)
_TASK_UNCHECKED_RE = _re.compile(r"^\[\s?\]\s?")


def _process_task_list_item(content_html: str, styles: dict[str, str]) -> str:
    """Replace [x] / [ ] at the start of list item content with Unicode checkboxes."""
    if _TASK_CHECKED_RE.search(content_html):
        icon = styles["task_checked"]
        return _TASK_CHECKED_RE.sub(icon + " ", content_html, count=1)
    if _TASK_UNCHECKED_RE.search(content_html):
        icon = styles["task_unchecked"]
        return _TASK_UNCHECKED_RE.sub(icon + " ", content_html, count=1)
    return content_html


# ---------------------------------------------------------------------------
# Heading sizes
# ---------------------------------------------------------------------------

_HEADING_SIZES = {1: 20, 2: 17, 3: 15, 4: 13}


# ---------------------------------------------------------------------------
# QtRenderer
# ---------------------------------------------------------------------------


class QtRenderer(RendererHTML):
    """markdown-it renderer that produces Qt QLabel-compatible HTML.

    Every method receives ``(tokens, idx, options, env)`` per the
    markdown-it renderer protocol.  ``self._styles`` is set per render
    call via ``render_with_styles()``.
    """

    _styles: dict[str, str] = {}
    _in_list_item: bool = False
    _list_item_content: str = ""

    def render_with_styles(
        self, tokens: Sequence[Token], options: OptionsDict, env: EnvType, styles: dict[str, str]
    ) -> str:
        """Entry point — render tokens using *styles*."""
        self._styles = styles
        return self.render(tokens, options, env)

    # ---- Block-level --------------------------------------------------

    def heading_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return ""

    def heading_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return ""

    def paragraph_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        token = tokens[idx]
        if token.hidden:
            return ""
        s = self._styles
        para_style = s.get("paragraph", "")
        if para_style:
            return f'<div style="{para_style}">'
        return ""

    def paragraph_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        token = tokens[idx]
        if token.hidden:
            return ""
        return "</div>"

    # The actual heading content is in the "inline" child of heading_open/close.
    # We intercept inline rendering inside headings to wrap them.
    _in_heading_level: int = 0

    def render(self, tokens: Sequence[Token], options: OptionsDict, env: EnvType) -> str:
        """Override render to track heading context."""
        result = ""
        self._in_heading_level = 0

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token.type == "heading_open":
                level = int(token.tag[1]) if token.tag and token.tag[0] == "h" else 3
                # Collect heading_open + inline + heading_close
                content = ""
                if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                    content = self.renderInline(tokens[i + 1].children or [], options, env)
                    i += 2  # skip inline + heading_close
                else:
                    i += 1
                if i < len(tokens) and tokens[i].type == "heading_close":
                    i += 1
                result += self._render_heading(content, level)
                continue

            elif token.type == "inline":
                if token.children:
                    inline_html = self.renderInline(token.children, options, env)
                    if self._in_list_item:
                        self._list_item_content += inline_html
                    result += inline_html
                i += 1
                continue

            elif token.type in self.rules:
                result += self.rules[token.type](tokens, i, options, env)
                i += 1
                continue

            else:
                result += self.renderToken(tokens, i, options, env)
                i += 1
                continue

        return result

    def _render_heading(self, content: str, level: int) -> str:
        s = self._styles
        size = _HEADING_SIZES.get(level, 13)
        parts = [s.get("heading", ""), f"font-size:{size}px;", "margin:8px 0 4px 0;"]
        if level <= 2 and s.get("heading_border"):
            parts.append(s["heading_border"])
        style_str = " ".join(parts)
        return f'<div style="{style_str}">{content}</div>'

    # ---- Fenced code blocks -------------------------------------------

    def fence(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        s = self._styles
        token = tokens[idx]
        lang = (token.info or "").strip().split()[0] if token.info.strip() else ""
        code = token.content

        is_dark = s.get("is_dark", True)

        if lang:
            highlighted = highlight_code(code, lang, is_dark=is_dark)
        else:
            highlighted = escapeHtml(code)

        lang_tag = ""
        if lang:
            lang_tag = f'<div style="{s.get("lang_tag", "")}">{escapeHtml(lang)}</div>'

        block_style = s.get("code_block", "")
        return f'<div style="{block_style}">{lang_tag}{highlighted}</div>'

    def code_block(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        """Indented code block (less common from LLMs)."""
        s = self._styles
        token = tokens[idx]
        code = escapeHtml(token.content)
        block_style = s.get("code_block", "")
        return f'<div style="{block_style}">{code}</div>'

    # ---- Inline code --------------------------------------------------

    def code_inline(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        s = self._styles
        code = escapeHtml(tokens[idx].content)
        style = s.get("inline_code", "")
        return f'<span style="{style}">{code}</span>'

    # ---- Lists --------------------------------------------------------

    def bullet_list_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return '<ul style="margin:2px 0 2px 20px; padding-left:0; list-style-type:disc;">'

    def bullet_list_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</ul>"

    def ordered_list_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        start_attr = ""
        token = tokens[idx]
        start = token.attrGet("start")
        if start and int(start) != 1:
            start_attr = f' start="{int(start)}"'
        return f'<ol style="margin:2px 0 2px 20px; padding-left:0;"{start_attr}>'

    def ordered_list_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</ol>"

    def list_item_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        self._in_list_item = True
        self._list_item_content = ""
        return "<li>"

    def list_item_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        self._in_list_item = False
        return "</li>"

    # ---- Blockquotes --------------------------------------------------

    def blockquote_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        s = self._styles
        style = s.get("blockquote", "")
        return f'<div style="{style}">'

    def blockquote_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</div>"

    # ---- Tables -------------------------------------------------------

    def table_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        s = self._styles
        style = s.get("table", "")
        return f'<table style="{style}">'

    def table_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</table>"

    def thead_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "<thead>"

    def thead_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</thead>"

    def tbody_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "<tbody>"

    def tbody_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</tbody>"

    def tr_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "<tr>"

    def tr_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</tr>"

    def th_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        s = self._styles
        style = s.get("table_header", "")
        return f'<th style="{style}">'

    def th_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</th>"

    def td_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        s = self._styles
        # Check if this row is even (for zebra striping) — we track via tr index
        style = s.get("table_cell", "")
        return f'<td style="{style}">'

    def td_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</td>"

    # ---- Horizontal rule -----------------------------------------------

    def hr(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        s = self._styles
        style = s.get("hr", "")
        if style:
            return f'<hr style="{style}">'
        return "<hr>"

    # ---- Inline formatting --------------------------------------------

    def strong_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "<b>"

    def strong_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</b>"

    def em_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "<i>"

    def em_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</i>"

    def s_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "<s>"

    def s_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</s>"

    def link_open(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        s = self._styles
        style = s.get("link", "")
        href = tokens[idx].attrGet("href") or ""
        href_escaped = escapeHtml(str(href))
        return f'<a style="{style}" href="{href_escaped}">'

    def link_close(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "</a>"

    def text(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        content = escapeHtml(tokens[idx].content)
        # Replace task list markers with Unicode checkboxes when inside a list item
        if self._in_list_item:
            content = _process_task_list_item(content, self._styles)
        return content

    def softbreak(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "<br>"

    def hardbreak(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        return "<br>"

    def image(
        self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
    ) -> str:
        """Images are not supported in QLabel RichText — render alt text."""
        token = tokens[idx]
        alt = ""
        if token.children:
            alt = self.renderInlineAsText(token.children, options, env)
        return escapeHtml(alt)
```

- [ ] **Step 2: Verify import**

Run: `python -c "from rikugan.ui.markdown_renderer import QtRenderer; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add rikugan/ui/markdown_renderer.py
git commit -m "feat: add QtRenderer — markdown-it tokens to Qt-compatible HTML"
```

---

### Task 4: Rewrite `markdown.py` — wire markdown-it-py with legacy fallback

**Files:**
- Modify: `rikugan/ui/markdown.py`

This is the critical integration point. The public API `md_to_html(text, source)` stays the same. Internally it tries markdown-it-py first, falls back to the old regex converter.

- [ ] **Step 1: Rewrite `rikugan/ui/markdown.py`**

Replace the entire file contents:

```python
"""Markdown to HTML converter for QLabel rich text.

Uses markdown-it-py for parsing and a custom QtRenderer for producing
Qt-compatible HTML.  Falls back to a lightweight regex converter when
markdown-it-py is not installed.

Public API: ``md_to_html(text, source) -> str``
"""

from __future__ import annotations

import html as _html
import re as _re

from .styles import blend_theme_color, get_host_palette_colors, use_native_host_theme

# ---------------------------------------------------------------------------
# markdown-it-py integration (preferred path)
# ---------------------------------------------------------------------------

_HAS_MARKDOWN_IT = False
_md_instance = None
_qt_renderer = None

try:
    from markdown_it import MarkdownIt

    from .markdown_renderer import QtRenderer, _build_theme_styles

    _HAS_MARKDOWN_IT = True
except ImportError:
    pass


def _init_markdown_it() -> tuple[MarkdownIt | None, QtRenderer | None]:
    """Lazily initialize the MarkdownIt parser and QtRenderer."""
    if not _HAS_MARKDOWN_IT:
        return None, None
    md = (
        MarkdownIt("commonmark")
        .enable("table")
        .enable("strikethrough")
    )
    renderer = QtRenderer(md)
    return md, renderer


def _render_with_markdown_it(text: str, source=None) -> str | None:
    """Render using markdown-it-py. Returns None if unavailable."""
    global _md_instance, _qt_renderer

    if not _HAS_MARKDOWN_IT:
        return None

    if _md_instance is None:
        _md_instance, _qt_renderer = _init_markdown_it()

    if _md_instance is None:
        return None

    styles = _build_theme_styles(source)
    tokens = _md_instance.parse(text)
    return _qt_renderer.render_with_styles(tokens, _md_instance.options, {}, styles)


# ---------------------------------------------------------------------------
# Legacy regex converter (fallback when markdown-it-py is absent)
# ---------------------------------------------------------------------------

_MARKDOWN_HINT_RE = _re.compile(
    r"(^#{1,4}\s)|(^\s*[-*]\s+)|(^\s*\d+[.)]\s+)|```|`[^`]+`|\*\*|__|(?<!\w)\*(.+?)\*(?!\w)|(?<!\w)_(.+?)_(?!\w)|\[[^\]]+\]\([^)]+\)|^[-*_]{3,}\s*$",
    _re.MULTILINE,
)


def _legacy_theme_styles(source=None) -> dict[str, str]:
    if use_native_host_theme():
        return {
            "inline_code_style": "font-family:monospace;",
            "block_code_style": "font-family:monospace; white-space:pre-wrap;",
            "link_style": "text-decoration: underline;",
            "hr_style": "",
            "heading_style": "font-weight:bold;",
            "lang_tag_style": "font-size:10px;",
        }

    colors = get_host_palette_colors(source)
    code_bg = blend_theme_color(colors["base"], colors["window"], 0.15)
    inline_fg = blend_theme_color(colors["highlight"], colors["text"], 0.3)
    border = blend_theme_color(colors["mid"], colors["window"], 0.35)
    heading = blend_theme_color(colors["highlight"], colors["text"], 0.15)
    return {
        "inline_code_style": (
            f"background-color:{code_bg}; color:{inline_fg}; "
            "padding:1px 4px; border-radius:3px; font-family:monospace; font-size:12px;"
        ),
        "block_code_style": (
            f"background-color:{colors['base']}; color:{colors['text']}; "
            f"border:1px solid {border}; border-radius:4px; "
            "padding:8px; font-family:monospace; font-size:12px; "
            "white-space:pre-wrap; word-break:break-all;"
        ),
        "link_style": f"color:{colors['highlight']};",
        "hr_style": f"border:1px solid {border};",
        "heading_style": f"color:{heading}; font-weight:bold;",
        "lang_tag_style": f"color:{blend_theme_color(colors['text'], colors['window'], 0.45)};font-size:10px;",
    }


def _has_markdown_syntax(text: str) -> bool:
    """Return True when the input likely needs markdown processing."""
    return bool(text and _MARKDOWN_HINT_RE.search(text))


def _legacy_md_to_html(text: str, source=None) -> str:
    """Legacy regex-based converter. Kept as fallback."""
    if not text:
        return ""
    theme = _legacy_theme_styles(source)
    if not _has_markdown_syntax(text):
        escaped = _html.escape(text).replace("\n", "<br>")
        return _re.sub(r"(<br>\s*){3,}", "<br><br>", escaped)

    blocks: list[str] = []

    def _stash_block(m: _re.Match) -> str:
        lang = m.group(1) or ""
        code = _html.escape(m.group(2).strip("\n"))
        lang_tag = f'<span style="{theme["lang_tag_style"]}">{_html.escape(lang)}</span><br>' if lang else ""
        block_html = f'<div style="{theme["block_code_style"]}">{lang_tag}{code}</div>'
        blocks.append(block_html)
        return f"\x00BLOCK{len(blocks) - 1}\x00"

    text = _re.sub(r"```(\w*)\n(.*?)```", _stash_block, text, flags=_re.DOTALL)

    lines = text.split("\n")
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if _re.match(r"^\x00BLOCK\d+\x00$", stripped):
            out_lines.append(stripped)
            i += 1
            continue

        if _re.match(r"^[-*_]{3,}\s*$", stripped):
            hr_style = f' style="{theme["hr_style"]}"' if theme["hr_style"] else ""
            out_lines.append(f"<hr{hr_style}>")
            i += 1
            continue

        hm = _re.match(r"^(#{1,4})\s+(.*)", stripped)
        if hm:
            level = len(hm.group(1))
            sizes = {1: 18, 2: 16, 3: 14, 4: 13}
            size = sizes.get(level, 13)
            h_text = _legacy_inline(hm.group(2), theme)
            out_lines.append(
                f'<div style="{theme["heading_style"]}font-size:{size}px;margin:6px 0 2px 0;">{h_text}</div>'
            )
            i += 1
            continue

        if _re.match(r"^[-*]\s+", stripped):
            items: list[str] = []
            while i < len(lines) and _re.match(r"^\s*[-*]\s+", lines[i]):
                item_text = _re.sub(r"^\s*[-*]\s+", "", lines[i])
                items.append(f"<li>{_legacy_inline(item_text, theme)}</li>")
                i += 1
            out_lines.append("<ul style='margin:2px 0 2px 16px;'>" + "".join(items) + "</ul>")
            continue

        if _re.match(r"^\d+[.)]\s+", stripped):
            items = []
            while i < len(lines) and _re.match(r"^\s*\d+[.)]\s+", lines[i]):
                item_text = _re.sub(r"^\s*\d+[.)]\s+", "", lines[i])
                items.append(f"<li>{_legacy_inline(item_text, theme)}</li>")
                i += 1
            out_lines.append("<ol style='margin:2px 0 2px 16px;'>" + "".join(items) + "</ol>")
            continue

        if not stripped:
            out_lines.append("<br>")
            i += 1
            continue

        out_lines.append(_legacy_inline(stripped, theme))
        i += 1

    result = "<br>".join(out_lines)

    for idx, block_html in enumerate(blocks):
        result = result.replace(f"\x00BLOCK{idx}\x00", block_html)

    result = _re.sub(r"(<br>\s*){3,}", "<br><br>", result)

    return result


def _legacy_inline(text: str, theme: dict[str, str]) -> str:
    text = _html.escape(text)
    code_spans: list[str] = []

    def _stash_code(m: _re.Match) -> str:
        code_spans.append(f'<span style="{theme["inline_code_style"]}">{m.group(1)}</span>')
        return f"\x01CODE{len(code_spans) - 1}\x01"

    text = _re.sub(r"`([^`]+)`", _stash_code, text)
    text = _legacy_inline_formatting(text, theme["link_style"])

    for idx, span_html in enumerate(code_spans):
        text = text.replace(f"\x01CODE{idx}\x01", span_html)

    return text


def _legacy_inline_formatting(text: str, link_style: str | None = None) -> str:
    link_style = link_style or _legacy_theme_styles()["link_style"]
    text = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = _re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = _re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", text)
    text = _re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)
    text = _re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        rf'<a style="{link_style}" href="\2">\1</a>',
        text,
    )
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def md_to_html(text: str, source=None) -> str:
    """Convert a Markdown string to Qt-compatible HTML.

    Uses markdown-it-py when available; falls back to the legacy
    regex converter otherwise.
    """
    if not text:
        return ""

    result = _render_with_markdown_it(text, source)
    if result is not None:
        return result

    return _legacy_md_to_html(text, source)
```

- [ ] **Step 2: Verify import and basic rendering**

Run: `python -c "from rikugan.ui.markdown import md_to_html; print(md_to_html('**bold**'))"`
Expected: HTML output containing `<b>bold</b>`

- [ ] **Step 3: Verify table rendering**

Run: `python -c "from rikugan.ui.markdown import md_to_html; print(md_to_html('| A | B |\n|---|---|\n| 1 | 2 |'))"`
Expected: HTML output containing `<table>` and `<th>` tags

- [ ] **Step 4: Verify blockquote rendering**

Run: `python -c "from rikugan.ui.markdown import md_to_html; print(md_to_html('> quoted text'))"`
Expected: HTML output containing `<div style="...blockquote...">`

- [ ] **Step 5: Verify strikethrough rendering**

Run: `python -c "from rikugan.ui.markdown import md_to_html; print(md_to_html('~~deleted~~'))"`
Expected: HTML output containing `<s>deleted</s>`

- [ ] **Step 6: Commit**

```bash
git add rikugan/ui/markdown.py
git commit -m "feat: rewrite markdown.py — markdown-it-py with legacy fallback"
```

---

### Task 5: Update existing tests

**Files:**
- Modify: `tests/tools/test_markdown.py`

The existing tests import `_has_markdown_syntax`, `_inline`, and `_inline_formatting` — these are now renamed to `_has_markdown_syntax` (kept in legacy), `_legacy_inline`, and `_legacy_inline_formatting`. The new public API test surface is just `md_to_html()`.

- [ ] **Step 1: Rewrite `tests/tools/test_markdown.py`**

Replace the entire file:

```python
"""Tests for rikugan.ui.markdown — Markdown-to-HTML converter."""

from __future__ import annotations

import unittest

from rikugan.ui.markdown import md_to_html


class TestMdToHtmlEmptyAndPlain(unittest.TestCase):
    def test_empty_string_returns_empty(self):
        self.assertEqual(md_to_html(""), "")

    def test_plain_text_passthrough(self):
        result = md_to_html("hello world")
        self.assertIn("hello world", result)

    def test_plain_text_with_newlines(self):
        result = md_to_html("hello\nworld")
        self.assertIn("hello", result)
        self.assertIn("world", result)


class TestMdToHtmlHeaders(unittest.TestCase):
    def test_h1(self):
        result = md_to_html("# Title")
        self.assertIn("Title", result)
        self.assertIn("20px", result)

    def test_h2(self):
        result = md_to_html("## Heading")
        self.assertIn("17px", result)

    def test_h3(self):
        result = md_to_html("### Sub")
        self.assertIn("15px", result)

    def test_h4(self):
        result = md_to_html("#### Small")
        self.assertIn("13px", result)

    def test_heading_with_bold(self):
        result = md_to_html("# **Bold Title**")
        self.assertIn("<b>Bold Title</b>", result)


class TestMdToHtmlHorizontalRule(unittest.TestCase):
    def test_triple_dash(self):
        result = md_to_html("---")
        self.assertIn("<hr", result)

    def test_triple_star(self):
        result = md_to_html("***")
        self.assertIn("<hr", result)


class TestMdToHtmlBulletList(unittest.TestCase):
    def test_dash_list(self):
        result = md_to_html("- item one\n- item two")
        self.assertIn("<ul", result)
        self.assertIn("<li>", result)
        self.assertIn("item one", result)
        self.assertIn("item two", result)

    def test_star_list(self):
        result = md_to_html("* alpha\n* beta")
        self.assertIn("<ul", result)
        self.assertIn("alpha", result)


class TestMdToHtmlNumberedList(unittest.TestCase):
    def test_numbered_list(self):
        result = md_to_html("1. first\n2. second")
        self.assertIn("<ol", result)
        self.assertIn("first", result)
        self.assertIn("second", result)


class TestMdToHtmlFencedCodeBlock(unittest.TestCase):
    def test_code_block_rendered(self):
        result = md_to_html("```python\nx = 1\n```")
        self.assertIn("x = 1", result)

    def test_code_block_with_lang_tag(self):
        result = md_to_html("```python\ncode\n```")
        self.assertIn("python", result)

    def test_code_block_without_lang(self):
        result = md_to_html("```\nraw code\n```")
        self.assertIn("raw code", result)

    def test_code_block_escapes_html(self):
        result = md_to_html("```\n<script>alert(1)</script>\n```")
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_code_block_not_processed_for_inline(self):
        result = md_to_html("```\n**not bold**\n```")
        self.assertNotIn("<b>not bold</b>", result)


class TestMdToHtmlParagraph(unittest.TestCase):
    def test_paragraph_break(self):
        result = md_to_html("para one\n\npara two")
        self.assertIn("para one", result)
        self.assertIn("para two", result)


class TestInlineFormatting(unittest.TestCase):
    def test_bold(self):
        result = md_to_html("**bold**")
        self.assertIn("<b>bold</b>", result)

    def test_italic(self):
        result = md_to_html("*italic*")
        self.assertIn("<i>italic</i>", result)

    def test_link(self):
        result = md_to_html("[text](http://example.com)")
        self.assertIn("href", result)
        self.assertIn("text", result)
        self.assertIn("http://example.com", result)

    def test_inline_code(self):
        result = md_to_html("use `foo()` here")
        self.assertIn("foo()", result)

    def test_bold_inside_code_not_applied(self):
        result = md_to_html("`**not bold**`")
        self.assertNotIn("<b>not bold</b>", result)

    def test_html_escaped(self):
        result = md_to_html("<b>not bold</b>")
        self.assertNotIn("<b>not bold</b>", result)
        self.assertIn("&lt;b&gt;", result)


class TestMdToHtmlIntegration(unittest.TestCase):
    def test_mixed_content(self):
        md = "# Title\n\nSome **bold** and `code`.\n\n- item\n- item2"
        result = md_to_html(md)
        self.assertIn("<b>bold</b>", result)
        self.assertIn("<ul", result)
        self.assertIn("Title", result)

    def test_link_in_list(self):
        result = md_to_html("- [link](http://x.com)")
        self.assertIn("href", result)
        self.assertIn("<li>", result)


class TestMdToHtmlTables(unittest.TestCase):
    def test_basic_table(self):
        result = md_to_html("| Name | Type |\n|------|------|\n| foo  | int  |")
        self.assertIn("<table", result)
        self.assertIn("<th", result)
        self.assertIn("<td", result)
        self.assertIn("Name", result)
        self.assertIn("foo", result)

    def test_table_with_many_rows(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        result = md_to_html(md)
        self.assertIn("<table", result)
        self.assertIn("1", result)
        self.assertIn("3", result)


class TestMdToHtmlBlockquotes(unittest.TestCase):
    def test_single_blockquote(self):
        result = md_to_html("> quoted text")
        self.assertIn("quoted text", result)

    def test_blockquote_has_border_style(self):
        result = md_to_html("> quoted text")
        self.assertIn("border-left", result)


class TestMdToHtmlStrikethrough(unittest.TestCase):
    def test_strikethrough(self):
        result = md_to_html("~~deleted~~")
        self.assertIn("<s>deleted</s>", result)


class TestMdToHtmlTaskLists(unittest.TestCase):
    def test_unchecked_task(self):
        result = md_to_html("- [ ] todo item")
        self.assertIn("☐", result)

    def test_checked_task(self):
        result = md_to_html("- [x] done item")
        self.assertIn("☑", result)


class TestMdToHtmlNestedLists(unittest.TestCase):
    def test_nested_bullet_list(self):
        md = "- item one\n  - nested item\n- item two"
        result = md_to_html(md)
        self.assertIn("item one", result)
        self.assertIn("nested item", result)
        # Should have nested <ul> inside <li>
        self.assertEqual(result.count("<ul"), 2)

    def test_mixed_nested_list(self):
        md = "1. first\n   - nested bullet\n2. second"
        result = md_to_html(md)
        self.assertIn("first", result)
        self.assertIn("nested bullet", result)
        self.assertIn("<ul", result)
        self.assertIn("<ol", result)


class TestMdToHtmlStreaming(unittest.TestCase):
    def test_incomplete_code_block(self):
        """Streaming often delivers unclosed code blocks."""
        result = md_to_html("```python\ndef foo(")
        self.assertIn("def foo(", result)

    def test_incomplete_bold(self):
        result = md_to_html("Some **bold te")
        self.assertIn("**bold te", result)

    def test_incomplete_table(self):
        result = md_to_html("| Name | Type |\n|---")
        self.assertIn("Name", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/tools/test_markdown.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/tools/test_markdown.py
git commit -m "test: update markdown tests for new renderer — tables, blockquotes, strikethrough, task lists, streaming"
```

---

### Task 6: Verify no breaking changes in consumers

**Files:**
- No file changes — verification only

- [ ] **Step 1: Verify `message_widgets.py` import still works**

Run: `python -c "from rikugan.ui.message_widgets import AssistantMessageWidget; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS (no regressions)

- [ ] **Step 3: Run linter**

Run: `python -m ruff check rikugan/ui/markdown.py rikugan/ui/markdown_renderer.py rikugan/ui/highlight.py --fix`
Expected: No errors

- [ ] **Step 4: Run type checker**

Run: `python -m mypy rikugan/ui/markdown.py rikugan/ui/markdown_renderer.py rikugan/ui/highlight.py --ignore-missing-imports`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 5: Final commit (if any lint fixes)**

```bash
git add -A
git commit -m "fix: lint fixes for markdown renderer overhaul"
```

---

### Task 7: Clean up — remove legacy converter's internal exports

**Files:**
- Modify: `rikugan/ui/markdown.py` (if safe)

This step is optional and should only be done after all tests pass. The legacy converter is kept as `_legacy_md_to_html()` for fallback, but the old internal helpers `_inline` and `_inline_formatting` are no longer exported from the public module interface.

- [ ] **Step 1: Verify no external imports of internal functions**

Run: `grep -r "from rikugan.ui.markdown import _" tests/ rikugan/`
Expected: No matches (test file was updated in Task 5)

- [ ] **Step 2: Add deprecation note to legacy functions**

In `rikugan/ui/markdown.py`, add a docstring note to `_legacy_md_to_html`:

```python
def _legacy_md_to_html(text: str, source=None) -> str:
    """Legacy regex-based converter.

    Kept as fallback when markdown-it-py is not installed.
    Do not use directly — call md_to_html() instead.
    """
```

- [ ] **Step 3: Commit**

```bash
git add rikugan/ui/markdown.py
git commit -m "docs: add deprecation note to legacy markdown converter"
```
