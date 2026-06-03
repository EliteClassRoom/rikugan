# Markdown Renderer Overhaul — Design Spec

**Date:** 2026-06-03
**Status:** Approved
**Scope:** `rikugan/ui/markdown.py`, new files in `rikugan/ui/`

## Problem

The current custom regex-based Markdown converter (`md_to_html()` in `rikugan/ui/markdown.py`) handles a limited subset of Markdown. LLM outputs commonly include tables, blockquotes, nested lists, strikethrough, and task lists — none of which are rendered. Code blocks are displayed as plain monospace text without syntax highlighting, making assembly/C/Python output harder to scan.

## Decision

Replace the custom regex converter with a 3-layer architecture:

1. **markdown-it-py** — parse Markdown into AST tokens
2. **QtRenderer** — custom renderer that produces Qt-compatible HTML from AST
3. **Pygments** — syntax highlighting for fenced code blocks with language tags

### Rationale

- **markdown-it-py** provides correct parsing for edge cases the regex approach cannot handle (nested structures, ambiguous delimiters). Its plugin system adds tables, strikethrough, and task lists with zero custom parsing code.
- **Pygments** is already present in most IDA Python environments and supports asm, C, Python, and hundreds of other languages.
- The public API (`md_to_html(text, source)`) remains unchanged — no breaking changes to consumers.

## Architecture

```
md_to_html(text, source)
  │
  ├─ markdown-it-py (parse)
  │   ├─ plugins: tables, strikethrough, task lists
  │   └─ output: token list (AST)
  │
  ├─ QtRenderer (render)
  │   ├─ iterate tokens → generate Qt-compatible HTML
  │   ├─ theme-aware styles from get_host_palette_colors()
  │   └─ delegate code blocks to highlight.py
  │
  └─ highlight.py (code blocks only)
      ├─ Pygments lexer lookup by language tag
      ├─ HtmlFormatter with Qt-compatible inline styles
      └─ fallback: plain monospace for unknown/untagged blocks
```

## New Syntax Support

| Syntax | Example | markdown-it-py Feature |
|--------|---------|----------------------|
| Tables | `\| col1 \| col2 \|` | `table` rule (built-in, `.enable('table')`) |
| Blockquotes | `> quote text` | Core (blockquote token) |
| Strikethrough | `~~text~~` | `strikethrough` rule (built-in, `.enable('strikethrough')`) |
| Task lists | `- [ ] / - [x]` | Custom post-processing on list items — render as Unicode ☐/☑ |
| Nested lists | `  - sub item` | Core (nested token tree) |

**Note on task lists:** markdown-it-py does not ship a `tasklists` extension (unlike the JS markdown-it). Task list rendering is implemented as a post-processing step in `QtRenderer`: detect `[- ]` / `[x]` patterns in list item content and replace with Unicode checkbox symbols.

## Visual Styling Improvements

### Headings
- Size gradient: h1=20px, h2=17px, h3=15px, h4=13px (slightly larger than current)
- h1/h2 get a subtle bottom border (theme-derived color)
- Margin: 8px top, 4px bottom

### Code Blocks
- Left border accent (3px, highlight color)
- Rounded corners (6px)
- Background from theme `base` color
- Language tag displayed as small muted label top-right
- When syntax-highlighted: Pygments inline styles override base colors

### Inline Code
- Background tinted from theme
- Softer border-radius (3px)
- Monospace font, slightly smaller (12px)

### Lists
- Proper nested indentation (20px per level via `margin-left`)
- Tighter spacing (2px between items)
- Bullet style: disc → circle → square for nesting levels
- Ordered lists: decimal numbering

### Blockquotes
- Left border accent (3px, muted highlight color)
- Italic text, muted foreground
- Padding: 8px 12px
- Nested blockquotes get progressively more indented

### Tables
- Bordered cells (1px, theme border color)
- Header row: bold, slightly different background
- Alternating row shading (zebra stripes)
- Cell padding: 4px 8px
- Word-wrap enabled in cells

### Paragraphs
- 4px margin between paragraphs instead of bare `<br>`
- No double-`<br>` collapsing needed (proper `<p>` or `<div>` with margin)

## Syntax Highlighting (Pygments)

### Style Selection
- **Dark theme** (IDA native or built-in dark): `monokai` style
- **Light theme** (if detected): `default` style
- Detection: check `_hex_luminance(window_color) < 0.5`

### Integration
- Only applied when fenced code block has a language tag (e.g. ` ```python `)
- Untagged blocks render as plain monospace (current behavior)
- Uses Pygments `HtmlFormatter` with `nowrap=True` and `noclasses=True` (inline styles)
- Lexer lookup via `get_lexer_by_name()` with `TextLexer` fallback

### Performance
- Cache `HtmlFormatter` instances per style (lazy singleton)
- No caching of lexer instances (lightweight to create)
- `monokai` → dark, `default` → light; selected once per render call based on theme

### Common Languages for RE Context
- `asm` / `nasm` / `x86` — assembly
- `c` / `cpp` — decompiled output
- `python` — scripting
- `json`, `yaml` — data
- `bash` / `shell` — commands
- Falls back to `TextLexer` for unknown language tags

## File Structure

```
rikugan/ui/
├── markdown.py             # MODIFIED: entry point, keeps md_to_html() API
├── markdown_renderer.py    # NEW: QtRenderer class (token → Qt HTML)
└── highlight.py            # NEW: Pygments integration
```

### `markdown.py` (modified)
- Public API unchanged: `md_to_html(text, source) -> str`
- `_has_markdown_syntax()` removed (no longer needed — markdown-it-py handles everything)
- `_theme_markdown_styles()` kept and expanded (new entries for tables, blockquotes, etc.)
- `_inline()` and `_inline_formatting()` removed (handled by renderer)
- Delegates parsing to `markdown-it-py` and rendering to `QtRenderer`

### `markdown_renderer.py` (new)
- `QtRenderer` class with methods per token type:
  - `render_heading()` — h1-h4 with border accent
  - `render_code_block()` — fenced blocks, delegates to `highlight.py`
  - `render_inline_code()` — backtick spans
  - `render_list()` — nested bullet/ordered lists
  - `render_blockquote()` — with left border
  - `render_table()` — bordered, striped
  - `render_paragraph()` — with margin
  - `render_hr()` — horizontal rule
  - `render_inline()` — bold, italic, strikethrough, links, images
- Theme-aware: receives style dict from `_theme_markdown_styles()`
- State management for nesting level tracking (lists, blockquotes)

### `highlight.py` (new)
- `highlight_code(code, language, theme_styles) -> str`
- Pygments lexer resolution with fallback
- Formatter caching per style variant (dark/light)
- Graceful degradation: if Pygments not available, return plain escaped text
- Import guard: `try/except ImportError` at module level

## Dependencies

```
# requirements.txt — add
markdown-it-py>=3.0
```

**Pygments is already available** in the IDA venv (`D:\ProgramFiles\IDAdata\.venv`, v2.19.2) and does not need to be added as a new dependency. The `highlight.py` module uses `try/except ImportError` to gracefully degrade when Pygments is absent.

**markdown-it-py** is also present in the IDA venv (v4.0.0). Adding it to `requirements.txt` ensures it's available in dev environments and future installs.

Both are pure-Python packages with no native compilation required. `markdown-it-py` depends only on `mdurl` (small URL parser).

## Error Handling

- **Pygments not installed**: `highlight.py` catches `ImportError`, falls back to plain monospace code blocks
- **markdown-it-py not installed**: `markdown.py` falls back to the current regex-based converter (kept as `_legacy_md_to_html()`)
- **Unknown lexer**: Pygments `TextLexer` renders as plain text (no highlighting)
- **Malformed tables**: markdown-it-py handles gracefully — malformed pipes render as text

## Testing Plan

### Unit Tests (`tests/tools/test_markdown.py` — expanded)

Existing tests remain valid (API unchanged). New tests:

- **Tables**: basic table, aligned columns, header-only table
- **Blockquotes**: single, nested, with other inline formatting
- **Strikethrough**: `~~text~~` renders `<s>` or `<del>` tag
- **Task lists**: unchecked `[ ]` and checked `[x]` rendering
- **Nested lists**: 2-3 levels deep, mixed bullet/ordered
- **Syntax highlighting**: code block with `python` tag produces colored spans
- **Fallback**: untagged code block, unknown language tag
- **Theme integration**: verify styles adapt to dark/light palette

### Integration Tests
- `AssistantMessageWidget.append_text()` streaming still works
- `_ThinkingBlock` rendering with new converter
- Session restore (`restore_from_messages`) with new HTML format

## Migration Strategy

1. **Phase 1**: Add `markdown-it-py` + `Pygments` to dependencies
2. **Phase 2**: Implement `highlight.py` and `markdown_renderer.py`
3. **Phase 3**: Wire into `markdown.py` with fallback to legacy converter
4. **Phase 4**: Update tests, verify all existing tests pass
5. **Phase 5**: Remove legacy converter (after release testing)

The legacy converter is kept as `_legacy_md_to_html()` during transition. It is used automatically when `markdown-it-py` is not installed.

## Constraints

- **Python 3.12+**: IDA venv at `D:\ProgramFiles\IDAdata\.venv` uses Python 3.12.11. Code must remain compatible with 3.10+ for other deployment scenarios.
- **No Qt signals in renderer**: Pure functions, stateless rendering
- **QLabel RichText limits**: No `<table>` styling via CSS classes (must use inline styles). Qt's RichText engine supports `<table>`, `<tr>`, `<td>`, `<th>` with inline `style=` attributes only.
- **Streaming compatible**: `md_to_html()` is called repeatedly during streaming (every 120 chars); must be fast enough and handle incomplete Markdown gracefully
- **Thread safety**: Renderer is stateless per call; no shared mutable state

## Streaming Behavior

`md_to_html()` is called incrementally during LLM streaming — every 120 characters of new text. The input is frequently **incomplete Markdown** (unclosed code blocks, broken tables, half-written bold markers).

**markdown-it-py handles incomplete input well:**

| Incomplete Input | Result | Acceptable? |
|-----------------|--------|-------------|
| `` ```python\ndef foo(` `` | Renders as code block with partial content | ✅ Yes |
| `\| Name \| Type \|\n\|---` | Renders as plain text (table not complete enough) | ✅ Yes |
| `Some **bold te` | Renders literal `**bold te` | ✅ Yes |
| `> quote text (no trailing newline)` | Renders as blockquote | ✅ Yes |

**Key design decisions for streaming:**
1. No special streaming mode — markdown-it-py's default behavior is sufficient
2. Each call to `md_to_html()` is independent (stateless) — re-parses full accumulated text
3. The `_RENDER_BATCH = 120` interval in `AssistantMessageWidget` remains unchanged
4. On `TEXT_DONE`, the final `set_text()` call produces the definitive render

**HTML output format:** Use `<div style="...">` wrappers (not native `<h1>`, `<p>`, etc.) to match current behavior and avoid Qt RichText spacing inconsistencies. Native HTML tags (`<table>`, `<ul>`, `<ol>`, `<pre>`) are used only where Qt's rendering requires them.
