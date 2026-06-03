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
    from pygments.lexers import get_lexer_by_name
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
