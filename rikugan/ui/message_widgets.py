"""Message display widgets for the chat view."""

from __future__ import annotations

import random
import re as _re
import time as _time
from typing import ClassVar

from .markdown import md_to_html
from .qt_compat import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    Qt,
    QTimer,
    QToolButton,
    QVBoxLayout,
    QWidget,
    qt_flags,
)
from .styles import host_stylesheet
from .theme.manager import ThemeManager, _blend_hex

_THINKING_PHRASES = [
    "analyzing binary structure...",
    "examining control flow...",
    "tracing cross-references...",
    "inspecting disassembly...",
    "reading function signatures...",
    "correlating data references...",
    "mapping call graph...",
    "evaluating type patterns...",
    "scanning string references...",
    "deobfuscating logic...",
    "checking import table...",
    "inferring variable types...",
    "analyzing stack layout...",
    "tracing data flow...",
    "examining vtable references...",
    "decoding encoded values...",
]


# ---------------------------------------------------------------------------
# Token-aware color resolvers
# ---------------------------------------------------------------------------
# Each helper takes a ``ThemeTokens`` and returns a hex color. Callers fetch
# the current tokens once per render via ``ThemeManager.instance().tokens()``
# so the resolved colors track the active theme.


def _user_role(t) -> str:
    return t.success


def _assistant_role(t) -> str:
    return t.highlight


def _body_text(t) -> str:
    return t.text


def _muted_text(t) -> str:
    return _blend_hex(t.text, t.mid, 0.5)


def _subtle_text(t) -> str:
    return t.light


def _hex_luminance(hex_str: str) -> float:
    """Return the relative luminance of a ``#rrggbb`` string (0..1)."""
    s = hex_str.lstrip("#")
    if len(s) < 6:
        return 0.5
    r = int(s[0:2], 16) / 255.0
    g = int(s[2:4], 16) / 255.0
    b = int(s[4:6], 16) / 255.0
    # Per WCAG, square the channel first to approximate sRGB→linear.
    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _pick_contrasting_text(bg_hex: str, dark_candidate: str, light_candidate: str) -> str:
    """Return whichever candidate has higher contrast against ``bg_hex``.

    Used by widgets that paint a colored foreground over a
    brand-colored background. ``highlight_text`` works for dark themes
    but collapses to invisible on light themes (because both the bg
    and the fg are near-white), so we pick the higher-contrast
    candidate by computing the actual WCAG contrast ratio for each
    side and taking the max.

    Returning the dark candidate when it wins means light-mode users
    see dark text on a light-blue button (readable), while dark-mode
    users still get the light ``highlight_text`` they expect.
    """
    bg_l = _hex_luminance(bg_hex)
    dark_l = _hex_luminance(dark_candidate)
    light_l = _hex_luminance(light_candidate)

    def _ratio(a: float, b: float) -> float:
        hi, lo = max(a, b), min(a, b)
        return (hi + 0.05) / (lo + 0.05)

    dark_contrast = _ratio(bg_l, dark_l)
    light_contrast = _ratio(bg_l, light_l)
    return dark_candidate if dark_contrast >= light_contrast else light_candidate


def _user_bubble_bg(t) -> str:
    # Darker user bubble: blend highlight toward base.
    return _blend_hex(t.highlight, t.base, 0.4)


def _user_bubble_border(t) -> str:
    return t.highlight


def _assistant_bubble_bg(t) -> str:
    return t.alt_base


def _assistant_bubble_border(t) -> str:
    return t.mid


def _thinking_surface_bg(t) -> str:
    return t.base


def _thinking_block_bg(t) -> str:
    return t.alt_base


def _thinking_block_border(t) -> str:
    return t.mid


def _tool_bg(t) -> str:
    return t.alt_base


def _tool_border(t) -> str:
    return t.mid


def _frame_css(*, background: str, border: str | None = None, radius: int = 8) -> str:
    border_css = f"border: 1px solid {border}; " if border else "border: none; "
    return f"background-color: {background}; {border_css}border-radius: {radius}px;"


def _bubble_css(
    *,
    background: str,
    text_color: str,
    border: str | None = None,
    radius: int = 10,
    padding: str = "8px 12px",
    size: int = 13,
) -> str:
    border_css = f"border: 1px solid {border}; " if border else "border: none; "
    return (
        f"background-color: {background}; color: {text_color}; "
        f"{border_css}border-radius: {radius}px; "
        f"padding: {padding}; font-size: {size}px;"
    )


def _native_text_style(
    *,
    size: int | None = None,
    bold: bool = False,
    italic: bool = False,
    monospace: bool = False,
) -> str:
    parts: list[str] = []
    if size is not None:
        parts.append(f"font-size: {size}px;")
    if bold:
        parts.append("font-weight: bold;")
    if italic:
        parts.append("font-style: italic;")
    if monospace:
        parts.append('font-family: Consolas, "Courier New", monospace;')
    return " ".join(parts)


def _tool_frame_style(
    source=None,
    *,
    tokens=None,
    accent: str | None = None,
    background: str | None = None,
    object_name: str = "message_tool",
) -> str:
    del source
    if tokens is None:
        tokens = ThemeManager.instance().tokens()
    border = accent or _tool_border(tokens)
    bg = background or _tool_bg(tokens)
    return f"QFrame#{object_name} {{ {_frame_css(background=bg, border=border, radius=6)} }}"


# Re-export tool widgets so existing consumers that import from this module
# continue to work without changes.


# ---------------------------------------------------------------------------
# Height-caching QLabel — eliminates O(text_length) layout-pass cost
# ---------------------------------------------------------------------------


class _HeightCachedLabel(QLabel):
    """QLabel that opts out of the layout heightForWidth protocol.

    QLabel with wordWrap forces an O(text_length) heightForWidth() call on
    every layout pass (e.g. when any sibling widget changes size).  In a chat
    with many long assistant messages this makes tool expand/collapse and
    parallel-tool completion O(N x msg_length) instead of O(N).

    By returning False from hasHeightForWidth() and pinning the height after
    each render, layout passes cost O(1) for this widget.  The correct height
    is still computed — just once per render instead of on every layout event.
    """

    def hasHeightForWidth(self) -> bool:
        return False

    def pin_height(self) -> None:
        """Fix widget height to the value heightForWidth returns for the current width."""
        w = self.width()
        if w <= 0:
            return
        h = QLabel.heightForWidth(self, w)
        if h > 0:
            self.setFixedHeight(h)


# ---------------------------------------------------------------------------
# Collapsible section (unchanged, used internally)
# ---------------------------------------------------------------------------


class CollapsibleSection(QFrame):
    """A widget with a clickable header that shows/hides content."""

    def __init__(self, title: str, parent: QWidget = None):
        super().__init__(parent)
        self._expanded = False
        # Re-apply on theme change. ``update()`` alone is not enough
        # because the toggle button needs an explicit QSS — Qt's default
        # QToolButton palette in light mode is dark text, but IDA's
        # host overrides it with a light-on-light style that becomes
        # white text on a white background. Same applies to the title
        # label which inherits from the QFrame default.
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Header
        header = QHBoxLayout()
        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("collapse_button")
        self._toggle_btn.setText("▶")
        self._toggle_btn.setFixedSize(16, 16)
        self._toggle_btn.clicked.connect(self.toggle)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("tool_header")
        header.addWidget(self._toggle_btn)
        header.addWidget(self._title_label, 1)
        layout.addLayout(header)

        self._apply_styles()

        # Content area
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 0, 0, 0)
        self._content.setVisible(False)
        layout.addWidget(self._content)

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._toggle_btn.setText("▼" if self._expanded else "▶")

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._content.setVisible(expanded)
        self._toggle_btn.setText("▼" if expanded else "▶")

    def _apply_styles(self, _tokens: object = None) -> None:
        # The toggle button has no parent QSS that can theme it
        # reliably across IDA/Binja host palettes, so we set the
        # foreground explicitly. We use a *secondary-tier* color
        # (``_muted_text`` = blend of text and mid) plus bold weight
        # so the ▶/▼ glyph stands out from the adjacent title —
        # otherwise the toggle and title share the same color and
        # the affordance visually merges into the title text.
        tokens = ThemeManager.instance().tokens()
        toggle_color = _muted_text(tokens)
        self._toggle_btn.setStyleSheet(
            host_stylesheet(
                f"QToolButton {{ color: {toggle_color}; background: transparent; "
                f"border: none; padding: 0; font-weight: bold; }}",
                f"QToolButton {{ color: {toggle_color}; background: transparent; "
                f"border: none; padding: 0; font-weight: bold; {_native_text_style(size=10)}; }}",
            )
        )
        self._title_label.setStyleSheet(
            host_stylesheet(
                f"color: {tokens.text}; font-size: 11px;",
                f"color: {tokens.text}; {_native_text_style(size=11)};",
            )
        )

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout


# ---------------------------------------------------------------------------
# User message
# ---------------------------------------------------------------------------


class UserMessageWidget(QFrame):
    """Displays a user message."""

    def __init__(self, text: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_user")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self._role_label = QLabel("You")
        layout.addWidget(self._role_label)

        self._content = QLabel(text)
        self._content.setWordWrap(True)
        self._content.setTextInteractionFlags(
            qt_flags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
                Qt.TextInteractionFlag.TextSelectableByKeyboard,
            )
        )
        self._content.setMinimumWidth(0)
        self._content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._content)

        self._apply_styles()
        # Re-apply on theme change so DARK <-> LIGHT actually updates
        # the bubble colors. ``update()`` is not enough because the
        # per-widget stylesheet was set in __init__ with stale tokens.
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        self._role_label.setStyleSheet(
            host_stylesheet(
                f"color: {_user_role(tokens)}; font-weight: bold; font-size: 11px;",
                f"color: {_user_role(tokens)}; {_native_text_style(size=11, bold=True)}",
            )
        )
        self._content.setStyleSheet(
            host_stylesheet(
                f"background-color: {_user_bubble_bg(tokens)}; "
                f"color: {_pick_contrasting_text(_user_bubble_bg(tokens), tokens.text, tokens.highlight_text)}; "
                "border-radius: 10px; padding: 8px 12px; font-size: 13px;",
                _bubble_css(
                    background=_user_bubble_bg(tokens),
                    text_color=_pick_contrasting_text(
                        _user_bubble_bg(tokens), tokens.text, tokens.highlight_text
                    ),
                    border=_user_bubble_border(tokens),
                ),
            )
        )


# ---------------------------------------------------------------------------
# Thinking content parser
# ---------------------------------------------------------------------------

_THINK_RE = _re.compile(r"<think>(.*?)</think>", _re.DOTALL)


def _split_thinking(text: str):
    """Split text into (thinking_content, visible_content).

    Handles:
    - One or more complete ``<think>...</think>`` blocks
    - An unclosed ``<think>`` during streaming
    """
    thinking_parts: list = []

    # Extract all complete <think>...</think> blocks
    last_end = 0
    visible_parts: list = []
    for m in _THINK_RE.finditer(text):
        visible_parts.append(text[last_end : m.start()])
        thinking_parts.append(m.group(1).strip())
        last_end = m.end()
    visible_parts.append(text[last_end:])
    remaining = "".join(visible_parts)

    # Check for unclosed <think> (still streaming)
    open_idx = remaining.rfind("<think>")
    if open_idx >= 0:
        partial = remaining[open_idx + 7 :].strip()
        if partial:
            thinking_parts.append(partial)
        remaining = remaining[:open_idx]

    return "\n\n".join(thinking_parts), remaining.strip()


# ---------------------------------------------------------------------------
# Collapsible thinking block
# ---------------------------------------------------------------------------


class _ThinkingBlock(QFrame):
    """Collapsible block for model reasoning / chain-of-thought."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("thinking_block")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)

        self._toggle = QToolButton()
        self._toggle.setObjectName("collapse_button")
        self._toggle.setText("\u25b6")  # ▶
        self._toggle.setFixedSize(14, 14)
        self._toggle.clicked.connect(self._on_toggle)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        header.addWidget(self._toggle)
        self._header_label = QLabel("Thinking")
        header.addWidget(self._header_label, 1)
        layout.addLayout(header)

        self._content = QLabel()
        self._content.setWordWrap(True)
        self._content.setTextFormat(Qt.TextFormat.RichText)
        self._content.setTextInteractionFlags(
            qt_flags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
                Qt.TextInteractionFlag.TextSelectableByKeyboard,
            )
        )
        self._content.hide()
        layout.addWidget(self._content)

        # Initialize state that ``_apply_styles`` and the re-render
        # helper read BEFORE the first paint, so the signal connection
        # below can fire safely even if the theme changes between
        # construction and the first ``set_thinking`` call.
        self._expanded = False
        # Source text cache — ``md_to_html`` produces HTML with inline
        # color/border styles baked from the current theme tokens.
        # Re-rendering on theme change is the only way to update those
        # colors, so we keep the text and re-call ``md_to_html`` from
        # ``_apply_styles`` when the theme fires.
        self._source_text: str = ""
        self._in_progress: bool = False
        self._tokens = None  # set by _apply_styles on each call

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

        self.hide()

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        # Stash for any sub-widget that needs to re-paint without
        # re-querying the manager (and so tests can assert the
        # theme-subscribe contract from the previous bug report).
        self._tokens = tokens
        # The toggle ▶/▼ must be visually distinct from the italic
        # "Thinking" header — use a secondary-tier color and bold
        # weight so the glyph reads as an affordance, not a letter.
        self._toggle.setStyleSheet(
            host_stylesheet(
                f"QToolButton {{ color: {_muted_text(tokens)}; background: transparent; "
                f"border: none; padding: 0; font-weight: bold; }}",
                f"QToolButton {{ color: {_muted_text(tokens)}; background: transparent; "
                f"border: none; padding: 0; font-weight: bold; }}",
            )
        )
        self.setStyleSheet(
            _tool_frame_style(
                tokens=tokens,
                accent=_thinking_block_border(tokens),
                background=_thinking_block_bg(tokens),
                object_name="thinking_block",
            )
        )
        self._header_label.setStyleSheet(
            host_stylesheet(
                f"color: {_muted_text(tokens)}; font-size: 11px; font-style: italic;",
                f"color: {_muted_text(tokens)}; {_native_text_style(size=11, italic=True)}",
            )
        )
        self._content.setStyleSheet(
            host_stylesheet(
                f"color: {_muted_text(tokens)}; font-size: 12px;",
                f"color: {_muted_text(tokens)}; {_native_text_style(size=12, italic=True)}",
            )
        )
        # The cached HTML embeds inline color/border styles from the
        # *previous* theme. Re-render with the new tokens so code blocks,
        # backticks, tables, and tool calls inside the thinking content
        # all match the active theme.
        if self._source_text:
            self._content.setText(md_to_html(self._source_text, self))

    def _on_toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._toggle.setText("\u25bc" if self._expanded else "\u25b6")

    def set_thinking(self, text: str, in_progress: bool = False) -> None:
        self._source_text = text
        self._in_progress = in_progress
        self._content.setText(md_to_html(text, self))
        label = "Thinking\u2026" if in_progress else "Thinking"
        self._header_label.setText(label)
        self.show()


# ---------------------------------------------------------------------------
# Assistant message (with streaming + Markdown)
# ---------------------------------------------------------------------------


class AssistantMessageWidget(QFrame):
    """Displays an assistant message with streaming support and Markdown rendering."""

    # Render at most every 100ms during streaming regardless of message length.
    # This caps the O(n) md_to_html cost to ~10 fps as messages grow.
    _RENDER_INTERVAL_S: float = 0.10
    # Minimum pending chars before a time-gated render fires (avoids renders for tiny deltas).
    _RENDER_BATCH_MIN: int = 30
    # Unconditional render threshold — ensures we flush even when the interval
    # hasn't elapsed (e.g. burst of 500+ chars in a single poll tick).
    _RENDER_BATCH_MAX: int = 500

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_assistant")
        self._full_text = ""
        self._pending_delta = 0
        self._last_render_time: float = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self._role_label = QLabel("Rikugan")
        layout.addWidget(self._role_label)

        self._thinking_block = _ThinkingBlock()
        layout.addWidget(self._thinking_block)

        self._content = QLabel()
        self._content.setWordWrap(True)
        self._content.setTextFormat(Qt.TextFormat.RichText)
        self._content.setTextInteractionFlags(
            qt_flags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
                Qt.TextInteractionFlag.TextSelectableByKeyboard,
                Qt.TextInteractionFlag.LinksAccessibleByMouse,
            )
        )
        self._content.setOpenExternalLinks(True)
        # Prevent the label from requesting more width than its parent
        self._content.setMinimumWidth(0)
        self._content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._content)
        self._content.hide()  # shown in _render() when visible text arrives

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        self._role_label.setStyleSheet(
            host_stylesheet(
                f"color: {_assistant_role(tokens)}; font-weight: bold; font-size: 11px;",
                f"color: {_assistant_role(tokens)}; {_native_text_style(size=11, bold=True)}",
            )
        )
        self._content.setStyleSheet(
            host_stylesheet(
                f"background-color: {_assistant_bubble_bg(tokens)}; color: {_body_text(tokens)}; "
                "border-radius: 10px; padding: 8px 12px; font-size: 13px;",
                _bubble_css(
                    background=_assistant_bubble_bg(tokens),
                    text_color=_body_text(tokens),
                    border=_assistant_bubble_border(tokens),
                ),
            )
        )
        # The HTML rendered by ``_render`` bakes inline color/border
        # styles from the *previous* theme. Re-render with the new
        # tokens so code blocks, backticks, tables, and tool calls all
        # match the active theme. Skipped when no text has streamed in
        # yet (avoids a wasted render on plugin startup).
        if self._full_text:
            self._render()

    def _render(self) -> None:
        thinking, visible = _split_thinking(self._full_text)
        if thinking:
            in_progress = "<think>" in self._full_text and "</think>" not in self._full_text
            self._thinking_block.set_thinking(thinking, in_progress=in_progress)
        else:
            self._thinking_block.hide()
        if visible:
            self._content.setText(md_to_html(visible, self))
            self._content.show()
        else:
            self._content.hide()
        self._pending_delta = 0
        self._last_render_time = _time.monotonic()

    def append_text(self, delta: str) -> None:
        self._full_text += delta
        self._pending_delta += len(delta)
        # Unconditional flush for very large bursts (prevents queue build-up).
        if self._pending_delta >= self._RENDER_BATCH_MAX:
            self._render()
            return
        # Time-gated render: fire once per interval when enough chars are pending.
        # This caps md_to_html cost to ~10 fps regardless of how long the message
        # has grown — avoids O(n²) total render work over a long response.
        if (
            self._pending_delta >= self._RENDER_BATCH_MIN
            and _time.monotonic() - self._last_render_time >= self._RENDER_INTERVAL_S
        ):
            self._render()

    def set_text(self, text: str) -> None:
        self._full_text = text
        self._render()

    def full_text(self) -> str:
        return self._full_text


# ---------------------------------------------------------------------------
# Thinking indicator
# ---------------------------------------------------------------------------


class ThinkingWidget(QFrame):
    """Animated thinking indicator shown while the LLM is processing."""

    _STAR_FRAMES: ClassVar[list[str]] = ["✳", "✴", "✵", "✶"]

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_thinking")
        self._phrase_idx = random.randint(0, len(_THINKING_PHRASES) - 1)
        self._star_idx = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._star_label = QLabel(self._STAR_FRAMES[0])
        self._star_label.setFixedWidth(18)
        layout.addWidget(self._star_label)

        self._phrase_label = QLabel(_THINKING_PHRASES[self._phrase_idx])
        layout.addWidget(self._phrase_label, 1)

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

        self._stopped = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(900)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        self.setStyleSheet(
            _tool_frame_style(
                tokens=tokens,
                background=_thinking_surface_bg(tokens),
                object_name="message_thinking",
            )
        )
        self._star_label.setStyleSheet(
            host_stylesheet(
                f"color: {tokens.warning}; font-size: 14px;",
                f"color: {tokens.warning}; {_native_text_style(size=14)}",
            )
        )
        self._phrase_label.setStyleSheet(
            host_stylesheet(
                f"color: {_muted_text(tokens)}; font-style: italic; font-size: 12px;",
                f"color: {_muted_text(tokens)}; {_native_text_style(size=12, italic=True)}",
            )
        )

    def _tick(self) -> None:
        if self._stopped:
            return
        self._star_idx = (self._star_idx + 1) % len(self._STAR_FRAMES)
        self._star_label.setText(self._STAR_FRAMES[self._star_idx])

        if self._star_idx == 0:
            self._phrase_idx = (self._phrase_idx + 1) % len(_THINKING_PHRASES)
            self._phrase_label.setText(_THINKING_PHRASES[self._phrase_idx])

    def stop(self) -> None:
        self._stopped = True
        try:
            self._timer.stop()
            self._timer.timeout.disconnect(self._tick)
        except (RuntimeError, TypeError):
            return  # timer already stopped or signal already disconnected — harmless


# ---------------------------------------------------------------------------
# Other message widgets
# ---------------------------------------------------------------------------


class QueuedMessageWidget(QFrame):
    """Displays a queued user message with dashed border."""

    def __init__(self, text: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_queued")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        content_layout = QVBoxLayout()

        self._role_label = QLabel("You")
        content_layout.addWidget(self._role_label)

        self._content = QLabel(text)
        self._content.setWordWrap(True)
        self._content.setTextInteractionFlags(
            qt_flags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
                Qt.TextInteractionFlag.TextSelectableByKeyboard,
            )
        )
        content_layout.addWidget(self._content)

        layout.addLayout(content_layout, 1)

        self._badge = QLabel("[queued]")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._badge)

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        queued_css = (
            f"QFrame#message_queued {{ border: 1px dashed {tokens.highlight}; "
            f"border-radius: 6px; background: {_thinking_block_bg(tokens)}; }}"
        )
        self.setStyleSheet(host_stylesheet(queued_css, queued_css))
        self._role_label.setStyleSheet(
            host_stylesheet(
                f"color: {_user_role(tokens)}; font-weight: bold; font-size: 11px;",
                f"color: {_user_role(tokens)}; {_native_text_style(size=11, bold=True)}",
            )
        )
        self._content.setStyleSheet(
            host_stylesheet(
                f"color: {_body_text(tokens)}; font-size: 13px;",
                f"color: {_body_text(tokens)}; {_native_text_style(size=13)}",
            )
        )
        self._badge.setStyleSheet(
            host_stylesheet(
                f"color: {_muted_text(tokens)}; font-size: 10px; font-style: italic;",
                f"color: {_muted_text(tokens)}; {_native_text_style(size=10, italic=True)}",
            )
        )


class UserQuestionWidget(QFrame):
    """Displays a question from the agent to the user with clickable option buttons."""

    def __init__(self, question: str, options: list | None = None, parent: QWidget = None):
        super().__init__(parent)
        self._option_selected_callback = None
        self.setObjectName("message_question")
        # Capture option labels so _apply_styles can rebuild button
        # chrome after a theme change without re-running the full
        # __init__ (which would rewire signals and duplicate widgets).
        self._option_labels: list[str] = []
        if options:
            for opt in options:
                self._option_labels.append(opt if isinstance(opt, str) else str(opt.get("label", opt)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self._header = QLabel("Rikugan asks:")
        layout.addWidget(self._header)

        self._q_label = QLabel(question)
        self._q_label.setWordWrap(True)
        self._q_label.setTextInteractionFlags(
            qt_flags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
                Qt.TextInteractionFlag.TextSelectableByKeyboard,
            )
        )
        layout.addWidget(self._q_label)

        if self._option_labels:
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(0, 4, 0, 0)
            btn_layout.setSpacing(8)
            self._buttons: list[QPushButton] = []
            for label in self._option_labels:
                btn = QPushButton(label)
                btn.clicked.connect(lambda checked, o=label: self._on_option(o))
                btn_layout.addWidget(btn)
                self._buttons.append(btn)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)
        else:
            self._buttons = []

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        self.setStyleSheet(
            _tool_frame_style(
                tokens=tokens,
                accent=tokens.warning,
                background=_blend_hex(tokens.warning, tokens.base, 0.85),
                object_name="message_question",
            )
        )
        self._header.setStyleSheet(
            host_stylesheet(
                f"color: {tokens.warning}; font-weight: bold; font-size: 11px;",
                f"color: {tokens.warning}; {_native_text_style(size=11, bold=True)}",
            )
        )
        self._q_label.setStyleSheet(
            host_stylesheet(
                f"color: {_body_text(tokens)}; font-size: 13px;",
                f"color: {_body_text(tokens)}; {_native_text_style(size=13)}",
            )
        )
        if self._buttons:
            btn_bg = _blend_hex(tokens.highlight, tokens.base, 0.55)
            btn_bg_hover = _blend_hex(tokens.highlight, tokens.base, 0.40)
            btn_bg_pressed = _blend_hex(tokens.highlight, tokens.base, 0.70)
            # Foreground must contrast with the button background, not
            # with the highlight itself. In dark mode ``highlight_text``
            # is white-ish and reads well on the bluish bg; in light
            # mode it is also white-ish, which collapses to invisible
            # on a light-blue bg. Pick the higher-contrast side: if
            # ``base`` is darker than the bg, prefer ``text``; else
            # prefer ``highlight_text``.
            btn_fg = _pick_contrasting_text(
                btn_bg, tokens.text, tokens.highlight_text
            )
            btn_border = _blend_hex(tokens.highlight, tokens.mid, 0.5)
            disabled_bg = _blend_hex(tokens.base, tokens.alt_base, 0.5)
            button_css = (
                f"QPushButton {{ background: {btn_bg}; color: {btn_fg}; "
                f"border: 1px solid {btn_border}; border-radius: 4px; "
                f"padding: 4px 14px; font-size: 12px; }}"
                f"QPushButton:hover {{ background: {btn_bg_hover}; }}"
                f"QPushButton:pressed {{ background: {btn_bg_pressed}; }}"
                f"QPushButton:disabled {{ color: {_muted_text(tokens)}; "
                f"background: {disabled_bg}; border-color: {tokens.mid}; }}"
            )
            for btn in self._buttons:
                btn.setStyleSheet(host_stylesheet(button_css, button_css))

    def set_option_selected_callback(self, callback) -> None:
        self._option_selected_callback = callback

    def _on_option(self, option: str) -> None:
        # Disable all buttons after selection
        for i in range(self._buttons.count()):
            item = self._buttons.itemAt(i)
            if item and item.widget():
                item.widget().setEnabled(False)
        if self._option_selected_callback is not None:
            self._option_selected_callback(option)


class ExplorationPhaseWidget(QFrame):
    """Displays an exploration phase transition."""

    _PHASE_ICONS: ClassVar[dict[str, str]] = {
        "explore": "\u25b6",  # play
        "plan": "\u270e",  # pencil
        "execute": "\u2699",  # gear
        "save": "\u2714",  # checkmark
    }

    def __init__(self, from_phase: str, to_phase: str, reason: str = "", parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_tool")
        self._reason_text = reason

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        icon = self._PHASE_ICONS.get(to_phase, "\u2192")
        self._phase_label = QLabel(f"{icon}  Phase: {to_phase.upper()}")
        layout.addWidget(self._phase_label)

        if reason:
            self._reason_label = QLabel(reason)
            self._reason_label.setWordWrap(True)
            layout.addWidget(self._reason_label, 1)

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        phase_accent = _blend_hex(tokens.warning, tokens.text, 0.25)
        phase_bg = _blend_hex(tokens.warning, tokens.base, 0.9)
        phase_reason = _blend_hex(tokens.warning, tokens.text, 0.45)
        self.setStyleSheet(
            _tool_frame_style(
                tokens=tokens,
                accent=phase_accent,
                background=phase_bg,
            )
        )
        self._phase_label.setStyleSheet(
            host_stylesheet(
                f"color: {phase_accent}; font-weight: bold; font-size: 11px;",
                f"color: {phase_accent}; {_native_text_style(size=11, bold=True)}",
            )
        )
        if self._reason_text:
            self._reason_label.setStyleSheet(
                host_stylesheet(
                    f"color: {phase_reason}; font-size: 11px;",
                    f"color: {phase_reason}; {_native_text_style(size=11)}",
                )
            )


class ExplorationFindingWidget(QFrame):
    """Displays a single exploration finding."""

    # Category color keys (resolved through tokens at render time).
    _CATEGORY_TOKEN_KEYS: ClassVar[dict[str, str]] = {
        "function_purpose": "success",
        "hypothesis": "warning",
        "constant": "success",
        "data_structure": "highlight",
        "string_ref": "warning",
        "import_usage": "highlight",
        "patch_result": "success",
        "general": "light",
    }

    def __init__(
        self,
        category: str,
        summary: str,
        address: str | None = None,
        relevance: str = "medium",
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.setObjectName("message_tool")
        self._category = category
        self._address = address
        self._summary = summary
        self._relevance = relevance

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._cat_label = QLabel(f"[{category}]")
        layout.addWidget(self._cat_label)

        if address:
            self._addr_label = QLabel(address)
            layout.addWidget(self._addr_label)

        self._summary_label = QLabel(summary)
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label, 1)

        if relevance == "high":
            self._rel_label = QLabel("\u2605")
            self._rel_label.setToolTip("High relevance")
            layout.addWidget(self._rel_label)
        else:
            self._rel_label = None

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        key = self._CATEGORY_TOKEN_KEYS.get(self._category, "light")
        color = getattr(tokens, key)
        self.setStyleSheet(_tool_frame_style(tokens=tokens, accent=color))
        self._cat_label.setStyleSheet(
            host_stylesheet(
                f"color: {color}; font-weight: bold; font-size: 10px;",
                f"color: {color}; {_native_text_style(size=10, bold=True)}",
            )
        )
        if self._address:
            self._addr_label.setStyleSheet(
                host_stylesheet(
                    f"color: {_muted_text(tokens)}; font-family: monospace; font-size: 10px;",
                    f"color: {_muted_text(tokens)}; {_native_text_style(size=10, monospace=True)}",
                )
            )
        self._summary_label.setStyleSheet(
            host_stylesheet(
                f"color: {_body_text(tokens)}; font-size: 11px;",
                f"color: {_body_text(tokens)}; {_native_text_style(size=11)}",
            )
        )
        if self._rel_label is not None:
            self._rel_label.setStyleSheet(
                host_stylesheet(
                    f"color: {tokens.warning}; font-size: 12px;",
                    f"color: {tokens.warning}; {_native_text_style(size=12, bold=True)}",
                )
            )


class ResearchNoteWidget(QFrame):
    """Displays a research note saved event."""

    def __init__(
        self,
        title: str,
        genre: str,
        path: str,
        preview: str = "",
        review_passed: bool = True,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.setObjectName("message_tool")
        self._title = title
        self._genre = genre
        self._path = path
        self._preview_text = preview
        self._review_passed = review_passed

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Header row
        header = QHBoxLayout()
        self._title_label = QLabel(title)
        header.addWidget(self._title_label)

        self._genre_label = QLabel(f"#{genre}")
        header.addWidget(self._genre_label)
        header.addStretch()
        layout.addLayout(header)

        # Path
        self._path_label = QLabel(path)
        layout.addWidget(self._path_label)

        # Preview
        if preview:
            self._preview_label = QLabel(preview)
            self._preview_label.setWordWrap(True)
            layout.addWidget(self._preview_label)
        else:
            self._preview_label = None

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        accent = tokens.success if self._review_passed else tokens.warning
        icon = "\u2705" if self._review_passed else "\u270f"  # checkmark or pencil
        self.setStyleSheet(_tool_frame_style(tokens=tokens, accent=accent))
        self._title_label.setText(f"{icon}  {self._title}")
        self._title_label.setStyleSheet(
            host_stylesheet(
                f"color: {accent}; font-weight: bold; font-size: 11px;",
                f"color: {accent}; {_native_text_style(size=11, bold=True)}",
            )
        )
        self._genre_label.setStyleSheet(
            host_stylesheet(
                f"color: {_muted_text(tokens)}; font-size: 10px; font-style: italic;",
                f"color: {_muted_text(tokens)}; {_native_text_style(size=10, italic=True)}",
            )
        )
        self._path_label.setStyleSheet(
            host_stylesheet(
                f"color: {_blend_hex(tokens.text, tokens.mid, 0.3)}; "
                f"font-family: monospace; font-size: 10px;",
                f"color: {_blend_hex(tokens.text, tokens.mid, 0.3)}; "
                f"{_native_text_style(size=10, monospace=True)}",
            )
        )
        if self._preview_label is not None:
            self._preview_label.setStyleSheet(
                host_stylesheet(
                    f"color: {_subtle_text(tokens)}; font-size: 11px;",
                    f"color: {_subtle_text(tokens)}; {_native_text_style(size=11)}",
                )
            )


class SubagentEventWidget(QFrame):
    """Displays a subagent lifecycle event (spawned, completed, failed)."""

    # Maps a status to the token name whose color is used for accent + label.
    _STATUS_TOKEN_KEYS: ClassVar[dict[str, str]] = {
        "spawned": "highlight",
        "completed": "success",
        "failed": "error",
    }

    def __init__(
        self,
        status: str,
        name: str,
        detail: str = "",
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.setObjectName("message_tool")
        self._status = status
        self._name = name
        self._detail_text = detail

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        icon_map = {"spawned": "\u25b6", "completed": "\u2714", "failed": "\u2718"}
        self._icon = QLabel(icon_map.get(status, "\u2022"))
        layout.addWidget(self._icon)

        label_text = f"Subagent \u201c{name}\u201d {status}"
        self._label = QLabel(label_text)
        layout.addWidget(self._label)

        if detail:
            self._detail = QLabel(detail)
            self._detail.setWordWrap(True)
            layout.addWidget(self._detail, 1)
        else:
            self._detail = None

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        key = self._STATUS_TOKEN_KEYS.get(self._status, "light")
        color = getattr(tokens, key)
        self.setStyleSheet(
            _tool_frame_style(
                tokens=tokens,
                accent=color,
                background=_blend_hex(tokens.alt_base, tokens.mid, 0.85),
            )
        )
        self._icon.setStyleSheet(
            host_stylesheet(
                f"color: {color}; font-size: 14px;",
                f"color: {color}; {_native_text_style(size=14)}",
            )
        )
        self._label.setStyleSheet(
            host_stylesheet(
                f"color: {color}; font-weight: bold; font-size: 11px;",
                f"color: {color}; {_native_text_style(size=11, bold=True)}",
            )
        )
        if self._detail is not None:
            self._detail.setStyleSheet(
                host_stylesheet(
                    f"color: {_subtle_text(tokens)}; font-size: 11px;",
                    f"color: {_subtle_text(tokens)}; {_native_text_style(size=11)}",
                )
            )


class ErrorMessageWidget(QFrame):
    """Displays an error message."""

    def __init__(self, error_text: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_tool")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self._header = QLabel("Error")
        layout.addWidget(self._header)

        self._content = QLabel(error_text)
        self._content.setWordWrap(True)
        self._content.setTextInteractionFlags(
            qt_flags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
                Qt.TextInteractionFlag.TextSelectableByKeyboard,
            )
        )
        self._content.setMinimumWidth(0)
        self._content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._content)

        self._apply_styles()
        ThemeManager.instance().themeChanged.connect(self._apply_styles)

    def _apply_styles(self, _tokens: object = None) -> None:
        tokens = ThemeManager.instance().tokens()
        self.setStyleSheet(
            _tool_frame_style(
                tokens=tokens,
                accent=tokens.error,
            )
        )
        self._header.setStyleSheet(
            host_stylesheet(
                f"color: {tokens.error}; font-weight: bold; font-size: 11px;",
                f"color: {tokens.error}; {_native_text_style(size=11, bold=True)}",
            )
        )
        self._content.setStyleSheet(
            host_stylesheet(
                f"color: {tokens.error}; font-size: 12px;",
                f"color: {tokens.error}; {_native_text_style(size=12)}",
            )
        )
