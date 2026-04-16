"""Lightweight Markdown to HTML converter for QLabel rich text.

Handles the subset of Markdown that LLMs commonly produce:
- Fenced code blocks (```lang ... ```)
- Inline code (`code`)
- Bold (**text**), italic (*text*)
- Headers (# through ####)
- Bullet lists (- item, * item)
- Numbered lists (1. item)
- Links [text](url)
- Paragraphs (double newline)
- Horizontal rules (---, ***)

No external dependencies. Output targets Qt's supported HTML subset.

Color handling: When _use_theme_colors is True, colors are omitted from
inline styles so text inherits from the parent Qt stylesheet. This allows
IDA Pro / Binary Ninja Qt themes to control all text colors.
"""

from __future__ import annotations

import html
import re

# -- Dark theme colors (used as fallbacks when use_theme_colors=False) --
_CODE_BG = "#2d2d2d"
_CODE_FG = "#ce9178"
_CODE_BORDER = "#3c3c3c"
_BLOCK_BG = "#1a1a1a"
_BLOCK_FG = "#d4d4d4"
_LINK_COLOR = "#569cd6"
_HR_COLOR = "#3c3c3c"
_H_COLOR = "#569cd6"

# -- Module-level flag: when True, md_to_html() omits explicit colors --
# This allows parent Qt stylesheet to control text color (IDA Pro theme).
_use_theme_colors = False

# -- Explicit code block theme colors (set by host panel for ida/binja theme) --
# These override the transparent background when set.
_code_block_bg = ""
_code_block_border = ""
_code_block_text = ""


def set_markdown_theme_colors(enabled: bool) -> None:
    """Enable or disable explicit color injection in md_to_html().

    When enabled (default for dark/light themes), inline styles include
    explicit colors. When disabled (for 'ida'/'binja' themes), md_to_html()
    omits color attributes so text inherits from the parent Qt stylesheet.
    """
    global _use_theme_colors
    _use_theme_colors = enabled


def set_code_block_theme(bg: str, border: str, text: str) -> None:
    """Set explicit code block colors for theme-aware rendering.

    Args:
        bg: Background color hex string (e.g. "#f0ebe3")
        border: Border color hex string (e.g. "#d4cdc4")
        text: Text color hex string (e.g. "#595e6a")
    """
    global _code_block_bg, _code_block_border, _code_block_text
    _code_block_bg = bg
    _code_block_border = border
    _code_block_text = text


def clear_code_block_theme() -> None:
    """Clear explicit code block colors, reverting to transparent backgrounds."""
    global _code_block_bg, _code_block_border, _code_block_text
    _code_block_bg = ""
    _code_block_border = ""
    _code_block_text = ""


_INLINE_CODE_STYLE = (
    f"background-color:{_CODE_BG}; color:{_CODE_FG}; "
    f"padding:1px 4px; border-radius:3px; font-family:monospace; font-size:12px;"
)

_BLOCK_CODE_STYLE = (
    f"background-color:{_BLOCK_BG}; color:{_BLOCK_FG}; "
    f"border:1px solid {_CODE_BORDER}; border-radius:4px; "
    f"padding:8px; font-family:monospace; font-size:12px; "
    f"white-space:pre-wrap; word-break:break-all;"
)

# Theme-aware variants (transparent backgrounds — inherit from parent Qt stylesheet)
_BASE_INLINE_CODE_STYLE = (
    "background-color:transparent; padding:1px 4px; border-radius:3px; font-family:monospace; font-size:12px;"
)

_BASE_BLOCK_CODE_STYLE = (
    "background-color:transparent; border:1px solid; border-radius:4px; "
    "padding:8px; font-family:monospace; font-size:12px; "
    "white-space:pre-wrap; word-break:break-all;"
)


def _get_inline_code_style() -> str:
    if _use_theme_colors:
        return _INLINE_CODE_STYLE
    if _code_block_bg:
        return (
            f"background-color:{_code_block_bg}; color:{_code_block_text}; "
            f"padding:1px 4px; border-radius:3px; font-family:monospace; font-size:12px;"
        )
    return _BASE_INLINE_CODE_STYLE


def _get_block_code_style() -> str:
    if _use_theme_colors:
        return _BLOCK_CODE_STYLE
    if _code_block_bg:
        return (
            f"background-color:{_code_block_bg}; color:{_code_block_text}; "
            f"border:1px solid {_code_block_border}; border-radius:4px; "
            f"padding:8px; font-family:monospace; font-size:12px; "
            f"white-space:pre-wrap; word-break:break-all;"
        )
    return _BASE_BLOCK_CODE_STYLE


def _get_link_color() -> str:
    return _LINK_COLOR if _use_theme_colors else "inherit"


def _get_hr_color() -> str:
    return _HR_COLOR if _use_theme_colors else "inherit"


def _get_h_color() -> str:
    return _H_COLOR if _use_theme_colors else "inherit"


def md_to_html(text: str) -> str:
    """Convert a Markdown string to Qt-compatible HTML."""
    if not text:
        return ""

    # Phase 1: extract fenced code blocks to protect them from inline processing
    blocks: list[str] = []

    def _stash_block(m: re.Match) -> str:
        lang = m.group(1) or ""
        code = html.escape(m.group(2).strip("\n"))
        # Use transparent for lang_tag color so it inherits from parent stylesheet
        if _use_theme_colors:
            lang_tag = f'<span style="color:#808080;font-size:10px;">{html.escape(lang)}</span><br>' if lang else ""
        else:
            lang_tag = f'<span style="font-size:10px;">{html.escape(lang)}</span><br>' if lang else ""
        block_style = _get_block_code_style()
        block_html = f'<div style="{block_style}">{lang_tag}{code}</div>'
        blocks.append(block_html)
        return f"\x00BLOCK{len(blocks) - 1}\x00"

    text = re.sub(r"```(\w*)\n(.*?)```", _stash_block, text, flags=re.DOTALL)

    # Phase 2: process line-by-line for block-level elements
    lines = text.split("\n")
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Block placeholder — pass through
        if re.match(r"^\x00BLOCK\d+\x00$", stripped):
            # Close any open paragraph before the block
            out_lines.append(stripped)
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            out_lines.append(f'<hr style="border:1px solid {_get_hr_color()};">')
            i += 1
            continue

        # Headers
        hm = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if hm:
            level = len(hm.group(1))
            sizes = {1: 18, 2: 16, 3: 14, 4: 13}
            size = sizes.get(level, 13)
            h_text = _inline(hm.group(2))
            h_color = _get_h_color()
            color_attr = f"color:{h_color};" if h_color != "inherit" else ""
            out_lines.append(
                f'<div style="{color_attr}font-weight:bold;font-size:{size}px;margin:6px 0 2px 0;">{h_text}</div>'
            )
            i += 1
            continue

        # Bullet list — collect consecutive items
        if re.match(r"^[-*]\s+", stripped):
            items: list[str] = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                item_text = re.sub(r"^\s*[-*]\s+", "", lines[i])
                items.append(f"<li>{_inline(item_text)}</li>")
                i += 1
            out_lines.append("<ul style='margin:2px 0 2px 16px;'>" + "".join(items) + "</ul>")
            continue

        # Numbered list — collect consecutive items
        if re.match(r"^\d+[.)]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+[.)]\s+", lines[i]):
                item_text = re.sub(r"^\s*\d+[.)]\s+", "", lines[i])
                items.append(f"<li>{_inline(item_text)}</li>")
                i += 1
            out_lines.append("<ol style='margin:2px 0 2px 16px;'>" + "".join(items) + "</ol>")
            continue

        # Empty line → paragraph break
        if not stripped:
            out_lines.append("<br>")
            i += 1
            continue

        # Regular text
        out_lines.append(_inline(stripped))
        i += 1

    result = "<br>".join(out_lines)

    # Phase 3: restore code blocks
    for idx, block_html in enumerate(blocks):
        result = result.replace(f"\x00BLOCK{idx}\x00", block_html)

    # Clean up double <br> from paragraph joins
    result = re.sub(r"(<br>\s*){3,}", "<br><br>", result)

    return result


def _inline(text: str) -> str:
    """Apply inline Markdown formatting to a line of text."""
    text = html.escape(text)

    # Stash inline code spans so bold/italic don't mangle their contents
    code_spans: list[str] = []

    def _stash_code(m: re.Match) -> str:
        code_style = _get_inline_code_style()
        code_spans.append(f'<span style="{code_style}">{m.group(1)}</span>')
        return f"\x01CODE{len(code_spans) - 1}\x01"

    text = re.sub(r"`([^`]+)`", _stash_code, text)

    # Now apply bold/italic/links on the text with code safely stashed
    text = _inline_formatting(text)

    # Restore code spans
    for idx, span_html in enumerate(code_spans):
        text = text.replace(f"\x01CODE{idx}\x01", span_html)

    return text


def _inline_formatting(text: str) -> str:
    """Apply bold, italic, and link formatting."""
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # Italic: *text* or _text_ (but not inside words for underscore)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)

    # Links: [text](url)
    link_color = _get_link_color()
    if link_color != "inherit":
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            rf'<a style="color:{link_color};" href="\2">\1</a>',
            text,
        )
    else:
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2">\1</a>',
            text,
        )

    return text
