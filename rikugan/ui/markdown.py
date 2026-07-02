"""Markdown to HTML converter for QLabel rich text.

Uses markdown-it-py for parsing and a custom QtRenderer for producing
Qt-compatible HTML.  Falls back to a lightweight regex converter when
markdown-it-py is not installed.

Public API: ``md_to_html(text, source) -> str``

Performance note
----------------
The ``markdown_it`` package is heavy (~35ms cold import on CPython 3.13).
We probe for it via :func:`importlib.util.find_spec` at module load (cheap,
does not execute package code) and only import it on first use. This keeps
the user-click path from paying for markdown rendering when the panel is
opened but no message has been rendered yet.
"""

from __future__ import annotations

import hashlib as _hashlib
import html as _html
import importlib.util as _importlib_util
import re as _re

from .styles import is_host_theme
from .theme.manager import ThemeManager, blend_hex

# ---------------------------------------------------------------------------
# Emoji stripping (shared with markdown_renderer.py) — used by the
# legacy regex fallback so it stays in lock-step with the markdown-it
# path.  See :func:`rikugan.ui.markdown_renderer._strip_emoji` for the
# rationale (monospace fonts lack glyphs for keycap / pictograph
# codepoints; LLM output commonly decorates code with ``2️⃣``
# prefixes that render as tofu boxes).
# ---------------------------------------------------------------------------
_EMOJI_RE = _re.compile(
    "["
    "\u20e3"
    "\ufe0f"
    "\u200d"
    "\U0001f1e6-\U0001f1ff"
    "☀-➿"
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001faff"
    "]"
)


def _strip_emoji(s: str) -> str:
    """Drop emoji / keycap / variation-selector codepoints from *s*.

    Mirrors the helper in :mod:`rikugan.ui.markdown_renderer` so the
    legacy fallback and the markdown-it path produce identical output
    for code blocks.  See that module for the codepoint list and the
    reason this exists.
    """
    return _EMOJI_RE.sub("", s)


# ---------------------------------------------------------------------------
# markdown-it-py integration (preferred path) — lazy
# ---------------------------------------------------------------------------

# Probed at import time: cheap (~0.05ms) and tells us if the package is on
# sys.path without executing its top-level code.
_HAS_MARKDOWN_IT = _importlib_util.find_spec("markdown_it") is not None

# Resolved on first use. ``None`` means "not yet attempted".
_md_instance: object | None = None
_qt_renderer: object | None = None
_markdown_it_failed = False


def _resolve_markdown_it() -> tuple | None:
    """Lazily import ``markdown_it`` and the Qt renderer.

    Returns ``(MarkdownIt, QtRenderer)`` on success, ``None`` if the
    package is unavailable or has been seen to fail.  Cached after first
    successful call.
    """
    global _md_instance, _qt_renderer, _markdown_it_failed
    if _md_instance is not None:
        return _md_instance, _qt_renderer
    if _markdown_it_failed or not _HAS_MARKDOWN_IT:
        return None
    try:
        from markdown_it import MarkdownIt  # intentional lazy import

        from .markdown_renderer import QtRenderer
    except ImportError:
        _markdown_it_failed = True
        return None
    # ``html: False`` is deliberate: Rikugan renders untrusted binary
    # content (strings, decompiler output, function names) that has
    # flowed through the LLM and back into the assistant's markdown
    # response. With the default ``html: True``, markdown-it emits
    # ``html_block`` / ``html_inline`` tokens whose content this code's
    # renderer passes through verbatim — letting ``<script>`` /
    # ``<img onerror=...>`` reach the Qt rich-text engine. Disabling raw
    # HTML turns those into escaped text so the user sees the literal
    # markup instead of the browser interpreting it. See CLAUDE.md
    # section 3 (binary-as-prompt-injection attack surface).
    md = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")
    renderer = QtRenderer(md)
    _md_instance, _qt_renderer = md, renderer
    return md, renderer


def _render_with_markdown_it(text: str, source=None) -> str | None:
    """Render using markdown-it-py. Returns None if unavailable."""
    resolved = _resolve_markdown_it()
    if resolved is None:
        return None
    md, qt_renderer = resolved

    # Imported lazily — pulls in pygments via markdown_renderer only on
    # the first markdown render, not at module load.
    from .markdown_renderer import _build_theme_styles

    styles = _build_theme_styles(source)
    tokens = md.parse(text)
    return qt_renderer.render_with_styles(tokens, md.options, {}, styles)


# ---------------------------------------------------------------------------
# Legacy regex converter (fallback when markdown-it-py is absent)
# ---------------------------------------------------------------------------

_MARKDOWN_HINT_RE = _re.compile(
    r"(^#{1,4}\s)|(^\s*[-*]\s+)|(^\s*\d+[.)]\s+)|```|`[^`]+`|\*\*|__|(?<!\w)\*(.+?)\*(?!\w)|(?<!\w)_(.+?)_(?!\w)|\[[^\]]+\]\([^)]+\)|^[-*_]{3,}\s*$",
    _re.MULTILINE,
)


def _legacy_theme_styles(source=None) -> dict[str, str]:
    if is_host_theme():
        return {
            "inline_code_style": "font-family:monospace;",
            "block_code_style": "font-family:monospace; white-space:pre-wrap;",
            "link_style": "text-decoration: underline;",
            "hr_style": "",
            "heading_style": "font-weight:bold;",
        }

    tokens = ThemeManager.instance().tokens()
    code_bg = _CODE_BLOCK_OVERRIDES.get("bg") or blend_hex(tokens.base, tokens.window, 0.15)
    inline_fg = blend_hex(tokens.highlight, tokens.text, 0.3)
    border = _CODE_BLOCK_OVERRIDES.get("border") or blend_hex(tokens.mid, tokens.window, 0.35)
    text_color = _CODE_BLOCK_OVERRIDES.get("text") or tokens.text
    heading = blend_hex(tokens.highlight, tokens.text, 0.15)
    return {
        "inline_code_style": (
            f"background-color:{code_bg}; color:{inline_fg}; "
            "padding:1px 4px; border-radius:3px; font-family:monospace; font-size:12px;"
        ),
        "block_code_style": (
            f"background-color:{code_bg}; color:{text_color}; "
            f"border:1px solid {border}; border-radius:4px; "
            "padding:8px; font-family:monospace; font-size:12px; "
            "white-space:pre-wrap; word-break:break-all;"
        ),
        "link_style": f"color:{tokens.highlight};",
        "hr_style": f"border:1px solid {border};",
        "heading_style": f"color:{heading}; font-weight:bold;",
    }


def _has_markdown_syntax(text: str) -> bool:
    """Return True when the input likely needs markdown processing."""
    return bool(text and _MARKDOWN_HINT_RE.search(text))


def _legacy_md_to_html(text: str, source=None) -> str:
    """Legacy regex-based converter.

    Kept as fallback when markdown-it-py is not installed.
    Do not use directly — call ``md_to_html()`` instead.
    """
    if not text:
        return ""
    theme = _legacy_theme_styles(source)
    if not _has_markdown_syntax(text):
        escaped = _html.escape(text).replace("\n", "<br>")
        return _re.sub(r"(<br>\s*){3,}", "<br><br>", escaped)

    blocks: list[str] = []

    def _stash_block(m: _re.Match) -> str:
        # ``lang`` is captured only for symmetry with the markdown-it
        # path; the language name is used to pick a Pygments lexer in
        # the markdown-it renderer but is NOT rendered into the HTML.
        # Earlier versions emitted it as a small label above the code
        # body that users misread as the first line of code.
        #
        # ``_strip_emoji`` mirrors the markdown-it path: code blocks
        # in a monospace font can't render keycap / pictograph glyphs,
        # and LLM output frequently decorates decompiler dumps with
        # ``2️⃣ func_name`` style prefixes.
        code = _html.escape(_strip_emoji(m.group(2).strip("\n")))
        block_html = f'<div style="{theme["block_code_style"]}">{code}</div>'
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


# URL schemes permitted in markdown links rendered to Qt rich-text.
# ``javascript:`` (and other executable schemes) are deliberately excluded to
# prevent XSS when a user clicks a link in the chat panel.
_SAFE_URL_SCHEMES = frozenset({"http", "https", "mailto", "ftp", "file", "data", ""})
_UNSAFE_HREF_RE = _re.compile(r"href=(['\"]?)\s*([a-zA-Z][a-zA-Z0-9+.\-]*):", _re.IGNORECASE)


def _render_link(link_style: str, label: str, url: str) -> str:
    """Render a markdown link as an ``<a>`` tag, dropping unsafe URL schemes.

    Qt's rich-text engine honours ``javascript:`` (and similar) hrefs when a
    user clicks a link, so any executable scheme is stripped before rendering.
    """
    scheme = ""
    match = _re.match(r"\s*([a-zA-Z][a-zA-Z0-9+.\-]*):", url)
    if match:
        scheme = match.group(1).lower()
    elif url.lstrip().startswith("#"):
        scheme = ""  # fragment — safe
    if scheme not in _SAFE_URL_SCHEMES:
        return label  # unsafe scheme — render as plain text, no anchor
    return f'<a style="{link_style}" href="{url}">{label}</a>'


def _legacy_inline_formatting(text: str, link_style: str | None = None) -> str:
    link_style = link_style or _legacy_theme_styles()["link_style"]
    text = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = _re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = _re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", text)
    text = _re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)

    def _link_sub(match: _re.Match) -> str:
        return _render_link(link_style, match.group(1), match.group(2))

    text = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link_sub, text)
    return text


# ---------------------------------------------------------------------------
# Backward-compat aliases
# ---------------------------------------------------------------------------
#
# ``tests/tools/test_markdown.py`` (and any other legacy caller)
# imports the pre-markdown-it inline helpers as ``_inline`` and
# ``_inline_formatting``.  The production code only references
# the ``_legacy_*`` versions now that the markdown-it
# integration is the primary path, but we keep the unprefixed
# names alive as aliases so the import continues to work.
#
# Both helpers take an optional ``theme`` argument so callers
# that pre-date the markdown-it refactor (which always passed
# a theme dict) keep working without changes.
_inline = _legacy_inline
_inline_formatting = _legacy_inline_formatting


def _legacy_inline_compat(text: str, theme: dict[str, str] | None = None) -> str:
    """Backward-compat wrapper for ``_inline`` that accepts the
    old single-argument signature used by ``test_markdown.py``
    (which predates the markdown-it refactor).  Falls back to
    the default legacy theme when the caller does not pass one.
    """
    return _legacy_inline(text, theme or _legacy_theme_styles())


_inline = _legacy_inline_compat
_inline_formatting = _legacy_inline_formatting


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def md_to_html(text: str, source=None) -> str:
    """Convert a Markdown string to Qt-compatible HTML.

    Uses markdown-it-py when available; falls back to the legacy
    regex converter otherwise.

    Emoji / keycap / variation-selector codepoints are stripped from
    the full input *before* markdown parsing.  The chat uses a
    monospace-derived font that lacks glyphs for these codepoints,
    so they render as tofu boxes regardless of whether they sit
    inside a fenced code block, an inline `` `code` `` span, a list
    item, a heading, or a plain paragraph.  Stripping at the input
    layer covers every output path (markdown-it + legacy fallback)
    without threading the strip through every per-token handler.

    Results are memoized in :data:`_HTML_CACHE` keyed by a hash of the
    input text and the current ``ThemeManager.tokens()`` identity.
    The cache is invalidated automatically when the theme changes
    (see :func:`_on_theme_changed`).
    """
    if not text:
        return ""

    # Input-level emoji strip.  The per-token handlers in
    # ``markdown_renderer`` and the legacy ``_stash_block`` apply
    # the same strip to fenced/indented code blocks; keeping them
    # is a defense-in-depth safety net for any caller that
    # bypasses this public entry point.
    text = _strip_emoji(text)

    key = _cache_key(text)
    cached = _HTML_CACHE.get(key)
    if cached is not None:
        return cached

    result = _render_with_markdown_it(text, source)
    if result is None:
        result = _legacy_md_to_html(text, source)

    # Bounded cache: cap at 256 entries to keep memory in check.
    if len(_HTML_CACHE) >= 256:
        # Drop the oldest half (insertion order dict).
        for k in list(_HTML_CACHE.keys())[:128]:
            _HTML_CACHE.pop(k, None)
    _HTML_CACHE[key] = result
    return result


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

# Bounded dict cache. Keyed by (text_hash, theme_token_id). The theme
# token id is the id() of the live ThemeTokens object — when the theme
# changes, ThemeManager produces a new instance, so id() differs and we
# miss the cache. This avoids re-rendering after theme change but
# allows the same content to be re-rendered with the same theme
# without re-running markdown-it-py.
_HTML_CACHE: dict[tuple[str, int], str] = {}

# Explicit code-block colour overrides from
# :func:`set_code_block_theme`.  ``None`` slots mean "use the
# ThemeManager-derived value".  Stored globally so the legacy
# stylesheet builder can pick it up.
_CODE_BLOCK_OVERRIDES: dict[str, str | None] = {"bg": None, "border": None, "text": None}


def _cache_key(text: str) -> tuple[str, int]:
    """Build a (text_hash, theme_token_id) cache key."""
    from .theme.manager import ThemeManager

    # SHA1 is fine here — this hash is a non-security HTML-cache key, not a
    # cryptographic primitive. ``usedforsecurity=False`` documents that intent
    # and silences the B324 false-positive.
    text_hash = _hashlib.sha1(
        text.encode("utf-8", errors="replace"),
        usedforsecurity=False,
    ).hexdigest()
    return (text_hash, id(ThemeManager.instance().tokens()))


def _on_theme_changed(_tokens) -> None:
    """Invalidate the HTML cache when the active theme changes."""
    _HTML_CACHE.clear()


# Wire the cache invalidation exactly once. ``themeChanged`` is emitted
# on every theme swap, so the next call to ``md_to_html`` will compute
# fresh HTML for the new palette.
try:
    from .theme.manager import ThemeManager

    ThemeManager.instance().themeChanged.connect(_on_theme_changed)
except Exception:  # host may not be ready; safe to ignore.
    pass


# ---------------------------------------------------------------------------
# Compatibility shims for legacy IDA panel code
# ---------------------------------------------------------------------------
#
# ``rikugan/ida/ui/panel.py`` (and any older host wrapper) historically
# called ``rikugan.ui.markdown.set_code_block_theme(bg=, border=, text=)``
# and ``rikugan.ui.markdown.clear_code_block_theme()`` to override the
# code-block colours used by the markdown renderer.  The new theme
# pipeline routes the same intent through ``ThemeManager`` instead, so
# we expose thin wrappers that keep the old call sites working.


def set_code_block_theme(bg: str | None = None, border: str | None = None, text: str | None = None) -> None:
    """Compatibility shim — record IDA host code-block colours.

    Stores the explicit overrides (when provided) so that the legacy
    ``_legacy_theme_styles`` path embeds them into the block-code
    stylesheet, then invalidates the HTML cache.  The ``markdown-it-py``
    path always uses :class:`ThemeManager` tokens; callers that need
    host-derived colours there should call
    :meth:`ThemeManager.refresh_from_host` instead.
    """
    global _CODE_BLOCK_OVERRIDES
    _CODE_BLOCK_OVERRIDES = {"bg": bg, "border": border, "text": text}
    _HTML_CACHE.clear()


def clear_code_block_theme() -> None:
    """Compatibility shim — restore default code-block theme.

    With the ThemeManager pipeline, "default" is whatever the active
    mode resolves to. Clearing the cache forces a re-render with
    the current tokens.
    """
    global _CODE_BLOCK_OVERRIDES
    _CODE_BLOCK_OVERRIDES = {"bg": None, "border": None, "text": None}
    _HTML_CACHE.clear()
