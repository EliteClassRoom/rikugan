"""Message display widgets for the chat view.

All color styling is handled via the RikuganPanel stylesheet (LIGHT_THEME /
DARK_THEME / IDA-propagated stylesheet). Widgets set structural properties
(background, borders, padding, font size hints) via setStyleSheet but
delegate text color to inheritance from the parent panel, so they
automatically follow the active theme.
"""

from __future__ import annotations

import random
import re as _re
from typing import ClassVar

from .markdown import md_to_html
from .qt_compat import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPalette,
    QPushButton,
    QSizePolicy,
    Qt,
    QColor,
    QTextCursor,
    QTextEdit,
    QTimer,
    QToolButton,
    QVBoxLayout,
    QWidget,
    Signal,
)

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
# Thinking / chain-of-thought parsing
# ---------------------------------------------------------------------------

_THINK_RE = _re.compile(r"<think>(.*?)</think>", _re.DOTALL)


def _split_thinking(text: str) -> tuple[str, str]:
    """Split text into (thinking_content, visible_content).

    Handles:
    - One or more complete ``<think>...</think>`` blocks
    - An unclosed ``<think>`` during streaming
    """
    thinking_parts: list[str] = []

    # Extract all complete <think>...</think> blocks
    last_end = 0
    visible_parts: list[str] = []
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
        # Only structural styles here; background and text colors come from the
        # panel's QFrame#thinking_block / QLabel#thinking_content rules.

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
        self._header_label.setObjectName("thinking_header")
        header.addWidget(self._header_label, 1)
        layout.addLayout(header)

        self._content = QLabel()
        self._content.setWordWrap(True)
        self._content.setTextFormat(Qt.TextFormat.RichText)
        self._content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._content.setObjectName("thinking_content")
        self._content.hide()
        layout.addWidget(self._content)

        self._expanded = False
        self.hide()

    def _on_toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._toggle.setText("\u25bc" if self._expanded else "\u25b6")

    def set_thinking(self, text: str, in_progress: bool = False) -> None:
        self._content.setText(md_to_html(text))
        label = "Thinking\u2026" if in_progress else "Thinking"
        self._header_label.setText(label)
        self.show()

    def hide_block(self) -> None:
        """Hide the thinking block."""
        self.hide()


# Re-export tool widgets so existing consumers that import from this module
# continue to work without changes.

# ---------------------------------------------------------------------------
# Collapsible section (unchanged, used internally)
# ---------------------------------------------------------------------------


class CollapsibleSection(QFrame):
    """A widget with a clickable header that shows/hides content."""

    def __init__(self, title: str, parent: QWidget = None):
        super().__init__(parent)
        self._expanded = False

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

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout


# ---------------------------------------------------------------------------
# Thinking indicator
# ---------------------------------------------------------------------------


class ThinkingWidget(QFrame):
    """Animated thinking indicator shown while the LLM is processing."""

    _STAR_FRAMES = ["✳", "✴", "✵", "✶"]

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_thinking")
        self._phrase_idx = random.randint(0, len(_THINKING_PHRASES) - 1)
        self._star_idx = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._star_label = QLabel(self._STAR_FRAMES[0])
        self._star_label.setObjectName("star_label")
        self._star_label.setFixedWidth(18)
        layout.addWidget(self._star_label)

        self._phrase_label = QLabel(_THINKING_PHRASES[self._phrase_idx])
        self._phrase_label.setObjectName("phrase_label")
        layout.addWidget(self._phrase_label, 1)

        self._stopped = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(900)

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
            pass


# ---------------------------------------------------------------------------
# User message
# ---------------------------------------------------------------------------


class UserMessageWidget(QFrame):
    """Displays a user message."""

    def __init__(self, text: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_user")
        self.setStyleSheet("QFrame#message_user { border-radius: 8px; padding: 8px; margin: 4px 8px 4px 8px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self._role_label = QLabel("You")
        self._role_label.setObjectName("msg_role_label")
        self._role_label.setProperty("class", "user_label")
        layout.addWidget(self._role_label)

        self._content = QLabel(text)
        self._content.setWordWrap(True)
        self._content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._content.setObjectName("message_content")
        layout.addWidget(self._content)

        self._badge = QLabel("[queued]")
        self._badge.setObjectName("queued_badge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._badge.setVisible(False)
        layout.addWidget(self._badge)


# ---------------------------------------------------------------------------
# Assistant message
# ---------------------------------------------------------------------------


class AssistantMessageWidget(QFrame):
    """Displays an assistant message with markdown support and streaming."""

    # Block-level markdown markers that require full re-render
    _BLOCK_MARKERS = ('```', '# ', '## ', '### ', '- ', '* ', '> ', '\n\n', '---', '***')

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_assistant")
        self.setStyleSheet("QFrame#message_assistant { border-radius: 8px; padding: 8px; margin: 4px 8px 4px 8px; }")
        self.setMinimumHeight(150)
        self._text = ""
        self._in_code_block = False  # Track if we're inside a code block

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self._role_label = QLabel("Rikugan")
        self._role_label.setObjectName("msg_role_label")
        self._role_label.setProperty("class", "assistant_label")
        layout.addWidget(self._role_label)

        self._content = QTextEdit()
        self._content.setReadOnly(True)
        self._content.setMinimumHeight(120)
        self._content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._content.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._content.document().setDocumentMargin(0)
        # Make QTextEdit look like the old QLabel - transparent background, no border
        self._content.viewport().setAutoFillBackground(False)
        transparent = self._content.palette()
        transparent.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        self._content.setPalette(transparent)
        self._content.setFrameShape(QFrame.Shape.NoFrame)
        self._content.setObjectName("message_content")
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._content)

    def append_text(self, text: str) -> None:
        """Append text (for streaming) using incremental HTML append."""
        self._text += text

        # Handle code block state transitions
        if '```' in text:
            # Toggle based on parity of fence count
            count = text.count('```')
            if count % 2 == 1:
                self._in_code_block = not self._in_code_block
            if not self._in_code_block:
                self._content.setHtml(md_to_html(self._text))
                return

        # If we're inside a code block, escape and append directly
        if self._in_code_block:
            escaped = self._escape_html(text)
            cursor = self._content.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertHtml(escaped)
            self._content.setTextCursor(cursor)
            return

        # Normal text - use simple append if no block markers
        if self._is_simple_text(text):
            escaped = self._escape_html(text)
            cursor = self._content.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertHtml(escaped)
            self._content.setTextCursor(cursor)
        else:
            # Complex markdown (headers, lists) - fall back to full render
            self._content.setHtml(md_to_html(self._text))

    def set_text(self, text: str) -> None:
        """Set final text (rendered as markdown)."""
        self._text = text
        self._in_code_block = False  # Reset state
        self._content.setHtml(md_to_html(text))

    @staticmethod
    def _is_simple_text(text: str) -> bool:
        """Check if text contains no block-level markdown."""
        return not any(m in text for m in AssistantMessageWidget._BLOCK_MARKERS)

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape text for HTML display."""
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


class UserQuestionWidget(QFrame):
    """Displays a question from the agent to the user with clickable option buttons."""

    option_selected = Signal(str)  # emitted with the chosen option text

    def __init__(self, question: str, options: list | None = None, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_question")
        self.setStyleSheet("QFrame#message_question { }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self._header = QLabel("Rikugan asks:")
        self._header.setObjectName("question_header")
        layout.addWidget(self._header)

        self._q_label = QLabel(question)
        self._q_label.setWordWrap(True)
        self._q_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._q_label.setObjectName("question_content")
        layout.addWidget(self._q_label)

        if options:
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(0, 4, 0, 0)
            btn_layout.setSpacing(8)
            for opt in options:
                btn = QPushButton(opt)
                btn.setObjectName("option_btn")
                btn.clicked.connect(lambda checked, o=opt: self._on_option(o))
                btn_layout.addWidget(btn)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)
            self._buttons = btn_layout

    def _on_option(self, option: str) -> None:
        # Disable all buttons after selection
        for i in range(self._buttons.count()):
            item = self._buttons.itemAt(i)
            if item and item.widget():
                item.widget().setEnabled(False)
        self.option_selected.emit(option)


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
        # Empty stylesheet — border, background, and text colors come from the
        # panel's QFrame#message_tool rule to support light/dark themes.

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        icon = self._PHASE_ICONS.get(to_phase, "\u2192")
        self._phase_label = QLabel(f"{icon}  Phase: {to_phase.upper()}")
        self._phase_label.setObjectName("phase_label")
        layout.addWidget(self._phase_label)

        if reason:
            self._reason_label = QLabel(reason)
            self._reason_label.setWordWrap(True)
            self._reason_label.setObjectName("reason_label")
            layout.addWidget(self._reason_label, 1)


class ExplorationFindingWidget(QFrame):
    """Displays a single exploration finding."""

    _CATEGORY_COLORS: ClassVar[dict[str, str]] = {
        "function_purpose": "#4ec9b0",
        "hypothesis": "#d7ba7d",
        "constant": "#b5cea8",
        "data_structure": "#c586c0",
        "string_ref": "#ce9178",
        "import_usage": "#569cd6",
        "patch_result": "#6a9955",
        "general": "#808080",
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
        self.setObjectName("finding_tool")
        color = self._CATEGORY_COLORS.get(category, "#808080")
        self.setStyleSheet(f"QFrame#finding_tool {{ border: 1px solid {color}; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._cat_label = QLabel(f"[{category}]")
        self._cat_label.setObjectName("cat_label")
        layout.addWidget(self._cat_label)

        if address:
            self._addr_label = QLabel(address)
            self._addr_label.setObjectName("addr_label")
            layout.addWidget(self._addr_label)

        self._summary_label = QLabel(summary)
        self._summary_label.setWordWrap(True)
        self._summary_label.setObjectName("finding_summary")
        layout.addWidget(self._summary_label, 1)

        if relevance == "high":
            rel_label = QLabel("\u2605")
            rel_label.setObjectName("relevance_star")
            rel_label.setToolTip("High relevance")
            layout.addWidget(rel_label)


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
        self.setObjectName("note_tool")
        # Border accent is semantic (green/yellow) — keep hardcoded for semantic meaning.
        # Background and other colors come from the panel's theme stylesheet.

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        # Header row
        header = QHBoxLayout()
        icon = "\u2705" if review_passed else "\u270f"  # checkmark or pencil
        self._title_label = QLabel(f"{icon}  {title}")
        self._title_label.setObjectName("note_title")
        header.addWidget(self._title_label)

        self._genre_label = QLabel(f"#{genre}")
        self._genre_label.setObjectName("note_genre")
        header.addWidget(self._genre_label)
        header.addStretch()
        layout.addLayout(header)

        # Path
        self._path_label = QLabel(path)
        self._path_label.setObjectName("note_path")
        layout.addWidget(self._path_label)

        # Preview
        if preview:
            self._preview_label = QLabel(preview)
            self._preview_label.setWordWrap(True)
            self._preview_label.setObjectName("note_preview")
            layout.addWidget(self._preview_label)


class SubagentEventWidget(QFrame):
    """Displays a subagent lifecycle event (spawned, completed, failed)."""

    _STATUS_COLORS: ClassVar[dict[str, str]] = {
        "spawned": "#569cd6",
        "completed": "#4ec9b0",
        "failed": "#f44747",
    }

    def __init__(
        self,
        status: str,
        name: str,
        detail: str = "",
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.setObjectName("subagent_tool")
        color = self._STATUS_COLORS.get(status, "#808080")
        self.setStyleSheet(f"QFrame#subagent_tool {{ border: 1px solid {color}; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        icon_map = {"spawned": "\u25b6", "completed": "\u2714", "failed": "\u2718"}
        icon = icon_map.get(status, "\u2022")
        self._icon = QLabel(icon)
        self._icon.setObjectName("subagent_icon")
        layout.addWidget(self._icon)

        label_text = f"Subagent \u201c{name}\u201d {status}"
        self._label = QLabel(label_text)
        self._label.setObjectName("subagent_label")
        layout.addWidget(self._label)

        if detail:
            self._detail = QLabel(detail)
            self._detail.setWordWrap(True)
            self._detail.setObjectName("subagent_detail")
            layout.addWidget(self._detail, 1)


class QueuedMessageWidget(QFrame):
    """Displays a queued user message with dashed border."""

    def __init__(self, text: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_queued")
        # Only set structural properties here; border and background come from
        # the panel's theme stylesheet via QFrame#message_queued to allow proper
        # light/dark theme switching.
        self.setStyleSheet("QFrame#message_queued { border-radius: 6px; padding: 0px; margin: 4px 8px 4px 8px; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        content_layout = QVBoxLayout()

        role_label = QLabel("You")
        role_label.setObjectName("msg_role_label")
        role_label.setProperty("class", "user_label")
        content_layout.addWidget(role_label)

        content = QLabel(text)
        content.setWordWrap(True)
        content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        content.setObjectName("message_content")
        content_layout.addWidget(content)

        layout.addLayout(content_layout, 1)

        badge = QLabel("[queued]")
        badge.setObjectName("queued_badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(badge)


class ErrorMessageWidget(QFrame):
    """Displays an error message."""

    def __init__(self, error_text: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_tool")
        self.setStyleSheet("QFrame#message_tool { border-color: #f44747; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self._header = QLabel("Error")
        self._header.setObjectName("error_header")
        layout.addWidget(self._header)

        self._content = QLabel(error_text)
        self._content.setWordWrap(True)
        self._content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._content.setObjectName("error_content")
        self._content.setMinimumWidth(0)
        self._content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._content)
