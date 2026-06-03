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
