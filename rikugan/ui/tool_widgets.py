"""Tool call, batch, group, and approval widgets."""

from __future__ import annotations

import json
import re as _re
from collections.abc import Callable
from typing import ClassVar

from .. import constants
from .qt_compat import (
    QColor,
    QFont,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSyntaxHighlighter,
    Qt,
    QTextCharFormat,
    QTimer,
    QToolButton,
    QVBoxLayout,
    QWidget,
    Signal,
)
from .styles import (
    get_tool_approval_allow_btn_style,
    get_tool_approval_always_btn_style,
    get_tool_approval_code_editor_style,
    get_tool_approval_deny_btn_style,
    get_tool_approval_disabled_btn_style,
    get_tool_approval_frame_style,
    get_tool_approval_header_style,
    get_tool_colors,
)
from .theme.manager import ThemeManager

_MAX_ARGS_DISPLAY = 2000
_MAX_RESULT_DISPLAY = 3000
_TOOL_PREVIEW_LINES = 3


# ---------------------------------------------------------------------------
# Tool card styling — border/background QSS for ToolCallWidget containers.
# Ported from the fork so tool calls render as bordered cards (matching the
# fork's appearance) instead of unbounded frames.
# ---------------------------------------------------------------------------


def _tool_bg(t) -> str:
    """Card background color for a tool call (alt-base tier)."""
    return t.alt_base


def _tool_border(t) -> str:
    """Card border color for a tool call (mid tier)."""
    return t.mid


def _tool_card_css(
    *,
    accent: str | None = None,
    background: str | None = None,
    radius: int = 6,
    object_name: str = "message_tool",
) -> str:
    """Border/background QSS for a tool-call card container.

    Targets the widget's object name (``#message_tool``) so the rule only
    applies to the card itself, not its child labels. Recomputed on
    ``themeChanged`` by :meth:`ToolCallWidget._apply_card_style`.
    """
    t = ThemeManager.instance().tokens()
    border = accent or _tool_border(t)
    bg = background or _tool_bg(t)
    return f"QFrame#{object_name} {{ background-color: {bg}; border: 1px solid {border}; border-radius: {radius}px;}}"


# ---------------------------------------------------------------------------
# MCP prefix stripping — works with any MCP server, not just a specific one
# ---------------------------------------------------------------------------


def _strip_mcp_prefix(name: str) -> str:
    """Strip MCP server prefix (``mcp__<server>__``) from tool names."""
    if name.startswith("mcp__"):
        rest = name[5:]  # after "mcp__"
        idx = rest.find("__")
        if idx >= 0:
            return rest[idx + 2 :]
    return name


# ---------------------------------------------------------------------------
# Tool-specific colors (by base name — MCP prefix is stripped before lookup)
# ---------------------------------------------------------------------------
_TOOL_COLORS: dict[str, str] = {}

# Analysis (read-only) -> teal/cyan
for _t in (
    "decompile_function",
    "read_disassembly",
    "read_function_disassembly",
    "get_binary_info",
    "list_imports",
    "list_exports",
    "list_functions",
    "search_functions",
    "list_strings",
    "search_strings",
    "get_string_at",
    "list_segments",
    "xrefs_to",
    "xrefs_from",
    "function_xrefs",
    "get_microcode",
    "get_microcode_block",
    "get_cursor_position",
    "get_current_function",
):
    _TOOL_COLORS[_t] = "#4ec9b0"  # teal/cyan

# Modification -> magenta/purple
for _t in (
    "rename_function",
    "rename_variable",
    "rename_address",
    "set_type",
    "set_function_prototype",
    "set_comment",
    "set_function_comment",
    "create_struct",
    "create_enum",
    "nop_microcode",
    "install_microcode_optimizer",
    "redecompile_function",
    "apply_struct_to_address",
    "apply_type_to_variable",
):
    _TOOL_COLORS[_t] = "#c586c0"  # magenta/purple

# Exploration -> gold/amber
for _t in ("exploration_report", "phase_transition"):
    _TOOL_COLORS[_t] = "#d7ba7d"

# Scripting -> green
for _t in (constants.EXECUTE_PYTHON_TOOL_NAME,):
    _TOOL_COLORS[_t] = "#6a9955"

_DEFAULT_TOOL_COLOR = "#569cd6"  # blue

_TOOL_GROUP_LABELS: dict[str, tuple[str, str]] = {
    "decompile_function": ("Decompiled", "function"),
    "read_disassembly": ("Disassembled", "function"),
    "read_function_disassembly": ("Disassembled", "function"),
    "search_strings": ("Searched", "string"),
    "list_strings_filter": ("Searched", "string"),
    "search_functions": ("Searched", "function"),
    "search_functions_by_name": ("Searched", "function"),
    "read_file": ("Read", "file"),
}


def _tool_color(name: str) -> str:
    """Look up tool color by base name (MCP prefix stripped)."""
    return _TOOL_COLORS.get(_strip_mcp_prefix(name), _DEFAULT_TOOL_COLOR)


def _build_approval_header(tool_name: str) -> str:
    """Build the approval-gate header label for a tool call.

    The header names the *actual* tool being approved (with the MCP
    ``mcp__<server>__`` prefix stripped) instead of the historical
    hard-coded ``"Approve execute_python?"``. The same approval widget
    is reused for every mutating tool when ``config.approve_mutations``
    is set, so a label that always says ``execute_python`` left the user
    unable to tell whether they were authorising a rename, a type
    change, or arbitrary script execution.
    """
    return f"Approve {_strip_mcp_prefix(tool_name)}?"


def _format_tool_group_label(tool_names: list[str]) -> str:
    """Human-friendly group label for collapsed tool-call runs."""
    count = len(tool_names)
    if count <= 0:
        return "0 tools called"

    base_names = [_strip_mcp_prefix(name) for name in tool_names]
    unique_names = {name for name in base_names if name}

    if len(unique_names) == 1:
        only_name = base_names[0]
        template = _TOOL_GROUP_LABELS.get(only_name)
        if template:
            action, noun = template
            suffix = "" if count == 1 else "s"
            return f"{action} {count} {noun}{suffix}"

    return f"{count} tool called" if count == 1 else f"{count} tools called"


# ---------------------------------------------------------------------------
# Smart tool parameter summaries
# ---------------------------------------------------------------------------

#: Maximum length of a one-line tool summary (truncated with "..." if exceeded).
_SUMMARY_MAX_CHARS = 80


def _trunc(text: str, limit: int) -> str:
    """Truncate *text* to *limit* chars, appending ``...`` when shortened."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


# Each formatter takes a ``_get(key, *fallbacks)`` accessor (which returns the
# first non-None arg as a string) and returns the summary for one tool. Tools
# sharing the same shape share the same callable, so adding a tool is a
# one-line table entry rather than a new elif branch.
def _fmt_address(getter) -> str:
    return getter("address", "ea", "name", "target", "func_id")


def _fmt_address_with_type(getter) -> str:
    target = getter("address", "ea", "func_address", "var_name")
    type_str = getter("type_str", "prototype", "type")
    return f"{target}: {type_str}" if target and type_str else ""


def _fmt_xref_target(getter) -> str:
    return getter("address", "ea", "name", "struct_name")


def _fmt_search_query(getter) -> str:
    query = getter("pattern", "query", "filter", "name")
    return f'"{query}"' if query else ""


def _fmt_define_types(getter) -> str:
    code = getter("c_code", "c_declaration", "types")
    return _trunc(code, 60) if code else ""


def _fmt_struct_name(getter) -> str:
    return getter("name", "struct_name")


def _fmt_execute_python(getter) -> str:
    code = getter("code", "script")
    if not code:
        return ""
    return _trunc(code.strip().split("\n")[0], 60)


def _fmt_read_disassembly(getter) -> str:
    return getter("name", "ea", "address", "start")


def _fmt_hexdump(getter) -> str:
    return getter("address", "ea", "name")


def _fmt_rename_function(getter) -> str:
    old = getter("old_name", "current_name", "ea")
    new = getter("new_name")
    return f"{old} → {new}" if old and new else ""


def _fmt_rename_variable(getter) -> str:
    func = getter("function_name", "func_address", "ea")
    old = getter("variable_name", "old_name")
    new = getter("new_name")
    if not (old and new):
        return ""
    return f"{func}: {old} → {new}" if func else f"{old} → {new}"


def _fmt_set_comment(getter) -> str:
    addr = getter("address", "ea")
    comment = _trunc(getter("comment", "text"), 50)
    if addr and comment:
        return f"{addr}: {comment}"
    return comment


def _fmt_exploration_report(getter) -> str:
    cat = getter("category")
    sm = _trunc(getter("summary"), 50)
    return f"[{cat}] {sm}" if cat and sm else (sm or cat or "")


def _fmt_phase_transition(getter) -> str:
    phase = getter("to_phase")
    reason = _trunc(getter("reason"), 40)
    return f"→ {phase}" + (f": {reason}" if reason else "")


#: Maps a stripped tool name to its summary formatter. Lookup happens after
#: ``_strip_mcp_prefix``, so e.g. ``mcp__bn__decompile_function`` resolves here
#: as ``decompile_function``.
_TOOL_SUMMARY_FORMATTERS: dict[str, Callable[[Callable[..., str]], str]] = {
    "decompile_function": _fmt_address,
    "rename_function": _fmt_rename_function,
    "rename_variable": _fmt_rename_variable,
    "set_comment": _fmt_set_comment,
    "set_function_comment": _fmt_set_comment,
    "set_type": _fmt_address_with_type,
    "set_function_prototype": _fmt_address_with_type,
    "apply_type_to_variable": _fmt_address_with_type,
    "xrefs_to": _fmt_xref_target,
    "xrefs_from": _fmt_xref_target,
    "function_xrefs": _fmt_xref_target,
    "search_strings": _fmt_search_query,
    "search_functions": _fmt_search_query,
    "search_functions_by_name": _fmt_search_query,
    "list_strings_filter": _fmt_search_query,
    "define_types": _fmt_define_types,
    "declare_c_type": _fmt_define_types,
    "create_struct": _fmt_struct_name,
    constants.EXECUTE_PYTHON_TOOL_NAME: _fmt_execute_python,
    "read_disassembly": _fmt_read_disassembly,
    "read_function_disassembly": _fmt_read_disassembly,
    "hexdump_address": _fmt_hexdump,
    "hexdump_data": _fmt_hexdump,
    "get_data_decl": _fmt_hexdump,
    "exploration_report": _fmt_exploration_report,
    "phase_transition": _fmt_phase_transition,
}

#: Generic fallback: first matching common parameter wins.
_GENERIC_SUMMARY_KEYS = (
    "target",
    "address",
    "ea",
    "name",
    "path",
    "query",
    "pattern",
    "command",
)


def _format_tool_summary(tool_name: str, args_text: str) -> str:
    """Extract the most relevant parameter for a compact one-line summary."""
    try:
        args = json.loads(args_text) if args_text else {}
    except (json.JSONDecodeError, TypeError):
        return ""

    if not isinstance(args, dict):
        return ""

    def _get(*keys: str) -> str:
        for k in keys:
            v = args.get(k)
            if v is not None:
                return str(v)
        return ""

    # Strip MCP prefix for matching (works with any MCP server)
    short_name = _strip_mcp_prefix(tool_name)

    fmt = _TOOL_SUMMARY_FORMATTERS.get(short_name)
    if fmt is not None:
        summary = fmt(_get)
    else:
        # Generic: try common parameter names
        summary = ""
        for key in _GENERIC_SUMMARY_KEYS:
            val = _get(key)
            if val:
                summary = val
                break

    return _trunc(summary, _SUMMARY_MAX_CHARS)


def _truncate_preview(text: str, max_lines: int = _TOOL_PREVIEW_LINES) -> str:
    """Return first N lines with a '… +M lines' indicator if truncated."""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    preview = "\n".join(lines[:max_lines])
    remaining = len(lines) - max_lines
    return f"{preview}\n… +{remaining} lines"


def _make_preview_label() -> QLabel:
    """Create a collapsed-state preview QLabel (shared by ToolCallWidget/ToolBatchWidget)."""
    lbl = QLabel()
    lbl.setObjectName("tool_content")
    lbl.setWordWrap(True)
    tool_colors = get_tool_colors()
    lbl.setStyleSheet(f"color: {tool_colors['preview']}; font-size: inherit; margin-left: 28px;")
    lbl.setVisible(False)
    return lbl


# ---------------------------------------------------------------------------
# Shared spinner timer
# ---------------------------------------------------------------------------


class _SharedSpinnerTimer:
    """Single QTimer shared across all ToolCallWidget instances.

    Instead of N timers (one per widget), one 100ms timer ticks all
    active spinners.  Starts automatically when the first widget
    registers and stops when the last one unregisters.
    """

    _instance: _SharedSpinnerTimer | None = None

    def __init__(self) -> None:
        self._timer = QTimer()
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self._widgets: set[ToolCallWidget] = set()

    @classmethod
    def get(cls) -> _SharedSpinnerTimer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, widget: ToolCallWidget) -> None:
        self._widgets.add(widget)
        # NOTE: Do NOT connect to widget.destroyed here.  PySide6/Shiboken
        # under IDA may GC the lambda slot, leaving a dangling C++ pointer
        # in Qt's connection list.  When *any* QWidget is later destroyed,
        # the stale slot pointer causes a SIGBUS (0xaaaa freed-memory read).
        # Stale widgets are already handled safely in _tick() via RuntimeError.
        if not self._timer.isActive():
            self._timer.start()

    def unregister(self, widget: ToolCallWidget) -> None:
        self._widgets.discard(widget)
        if not self._widgets and self._timer.isActive():
            self._timer.stop()

    def _tick(self) -> None:
        stale: set = set()
        for w in list(self._widgets):
            try:
                w._spin_tick()
            except RuntimeError:
                # Shiboken raises RuntimeError when the C++ object was already deleted.
                stale.add(w)
        if stale:
            self._widgets -= stale
            if not self._widgets and self._timer.isActive():
                self._timer.stop()

    @classmethod
    def shutdown(cls) -> None:
        """Stop and discard the singleton so the QTimer doesn't outlive QApplication."""
        inst = cls._instance
        if inst is not None:
            inst._widgets.clear()
            inst._timer.stop()
            inst._timer.deleteLater()
            cls._instance = None


class ToolCallWidget(QFrame):
    """Compact tool call display.

    Shows:  ● tool_name  summary_text
    With a collapsible detail section for args and result.
    """

    _SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, tool_name: str, tool_call_id: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_tool")
        self._tool_name = tool_name
        self._tool_call_id = tool_call_id
        self._args_text = ""
        self._result_text = ""
        self._is_error = False
        self._expanded = False
        self._spin_idx = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(2)

        layout.addLayout(self._build_header(tool_name))
        _SharedSpinnerTimer.get().register(self)
        layout.addWidget(self._build_preview())
        layout.addWidget(self._build_detail_section())

        # Bordered card background. Subscribed *after* the header is built
        # so an early themeChanged signal finds the widget fully constructed.
        self._apply_card_style()
        ThemeManager.instance().themeChanged.connect(self._apply_card_style)

    def _apply_card_style(self, _tokens: object = None) -> None:
        """Re-apply the border/background QSS on theme change."""
        self.setStyleSheet(_tool_card_css())

    def _build_header(self, tool_name: str) -> QHBoxLayout:
        """Build the compact header row: toggle ● name  summary  status."""
        display_name = _strip_mcp_prefix(tool_name)
        color = _tool_color(tool_name)
        tool_colors = get_tool_colors()

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("collapse_button")
        self._toggle_btn.setText("▶")
        self._toggle_btn.setFixedSize(14, 14)
        self._toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._toggle_btn)

        self._bullet = QLabel("●")
        self._bullet.setStyleSheet(f"color: {color}; font-size: inherit;")
        self._bullet.setFixedWidth(14)
        header_layout.addWidget(self._bullet)

        self._name_label = QLabel(display_name)
        self._name_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: inherit;")
        header_layout.addWidget(self._name_label)

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(f"color: {tool_colors['preview']}; font-size: inherit; margin-left: 6px;")
        header_layout.addWidget(self._summary_label, 1)

        self._status_label = QLabel(self._SPINNER_FRAMES[0])
        self._status_label.setStyleSheet(f"color: {tool_colors['status_spinner']}; font-size: inherit;")
        header_layout.addWidget(self._status_label)

        return header_layout

    def _build_preview(self) -> QLabel:
        """Build the preview label (truncated args, shown when collapsed)."""
        self._preview_label = _make_preview_label()
        return self._preview_label

    def _build_detail_section(self) -> QWidget:
        """Build the expandable detail area (args + result)."""
        tool_colors = get_tool_colors()

        self._detail_widget = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_widget)
        self._detail_layout.setContentsMargins(28, 2, 0, 2)
        self._detail_layout.setSpacing(2)

        self._args_label = QLabel()
        self._args_label.setObjectName("tool_content")
        self._args_label.setWordWrap(True)
        self._args_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._detail_layout.addWidget(self._args_label)

        self._result_header = QLabel("Result:")
        self._result_header.setStyleSheet(
            f"color: {tool_colors['result_header']}; font-size: inherit; font-weight: bold;"
        )
        self._result_header.setVisible(False)
        self._detail_layout.addWidget(self._result_header)

        self._result_label = QLabel()
        self._result_label.setObjectName("tool_content")
        self._result_label.setWordWrap(True)
        self._result_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._result_label.setVisible(False)
        self._detail_layout.addWidget(self._result_label)

        self._detail_widget.setVisible(False)
        return self._detail_widget

    def _spin_tick(self) -> None:
        """Advance the spinner animation frame."""
        self._spin_idx = (self._spin_idx + 1) % len(self._SPINNER_FRAMES)
        self._status_label.setText(self._SPINNER_FRAMES[self._spin_idx])

    def _stop_spinner(self) -> None:
        """Unregister from the shared spinner timer."""
        _SharedSpinnerTimer.get().unregister(self)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._detail_widget.setVisible(self._expanded)
        self._preview_label.setVisible(not self._expanded and bool(self._args_text))
        self._toggle_btn.setText("▼" if self._expanded else "▶")

    def set_arguments(self, args_text: str) -> None:
        self._args_text = args_text
        # Update summary
        summary = _format_tool_summary(self._tool_name, args_text)
        if summary:
            self._summary_label.setText(summary)
        # Preview (truncated)
        if args_text.strip():
            self._preview_label.setText(_truncate_preview(args_text.strip()))
            self._preview_label.setVisible(not self._expanded)
        # Full args in detail area
        display = args_text[:_MAX_ARGS_DISPLAY] + "..." if len(args_text) > _MAX_ARGS_DISPLAY else args_text
        self._args_label.setText(display)

    def append_args_delta(self, delta: str) -> None:
        self._args_text += delta
        # Don't update preview during streaming — wait for set_arguments

    def set_result(self, result: str, is_error: bool = False) -> None:
        self._stop_spinner()
        self._result_text = result
        self._is_error = is_error
        tool_colors = get_tool_colors()
        display = result[:_MAX_RESULT_DISPLAY] + "\n... (truncated)" if len(result) > _MAX_RESULT_DISPLAY else result
        self._result_label.setText(display)
        self._result_label.setVisible(True)
        self._result_header.setVisible(True)
        if is_error:
            self._result_label.setStyleSheet(f"color: {tool_colors['status_error']}; font-size: inherit;")
            self._status_label.setText("✗")
            self._status_label.setStyleSheet(f"color: {tool_colors['status_error']}; font-size: inherit;")
            self._bullet.setStyleSheet(f"color: {tool_colors['status_error']}; font-size: inherit;")
            # Auto-expand on error
            self._expanded = True
            self._detail_widget.setVisible(True)
            self._preview_label.setVisible(False)
            self._toggle_btn.setText("▼")
        else:
            self._status_label.setText("✓")
            self._status_label.setStyleSheet(f"color: {tool_colors['status_success']}; font-size: inherit;")

    def mark_done(self) -> None:
        self._stop_spinner()
        tool_colors = get_tool_colors()
        if self._status_label.text() not in ("✓", "✗"):
            self._status_label.setText("✓")
            self._status_label.setStyleSheet(f"color: {tool_colors['status_success']}; font-size: inherit;")

    def hide_preview(self) -> None:
        """Hide the args preview (used when preview budget exhausted)."""
        self._preview_label.setVisible(False)


# ---------------------------------------------------------------------------
# Tool batch widget — groups N consecutive calls to the same tool
# ---------------------------------------------------------------------------


class ToolBatchWidget(QFrame):
    """Groups consecutive calls to the same tool.

    Shows:  ● tool_name  (N calls)
    With preview of the first call's args.
    """

    def __init__(self, tool_name: str, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_tool")
        self._tool_name = tool_name
        self._count = 0
        self._expanded = False
        self._first_args: str = ""
        self._tool_call_ids: list[str] = []
        self._results: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self._entry_labels: list[QLabel] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(2)

        layout.addLayout(self._build_header(tool_name))
        layout.addWidget(self._build_preview())
        layout.addWidget(self._build_detail_section())

        # Bordered card background (same as ToolCallWidget). Applied after
        # the header is built; refreshed on theme change.
        self._apply_card_style()
        ThemeManager.instance().themeChanged.connect(self._apply_card_style)

    def _apply_card_style(self, _tokens: object = None) -> None:
        """Re-apply the border/background QSS on theme change."""
        self.setStyleSheet(_tool_card_css())

    def _build_header(self, tool_name: str) -> QHBoxLayout:
        """Build the compact header row: toggle ● name  count  status."""
        display_name = _strip_mcp_prefix(tool_name)
        color = _tool_color(tool_name)
        tool_colors = get_tool_colors()

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("collapse_button")
        self._toggle_btn.setText("▶")
        self._toggle_btn.setFixedSize(14, 14)
        self._toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._toggle_btn)

        self._bullet = QLabel("●")
        self._bullet.setStyleSheet(f"color: {color}; font-size: inherit;")
        self._bullet.setFixedWidth(14)
        header_layout.addWidget(self._bullet)

        self._name_label = QLabel(display_name)
        self._name_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: inherit;")
        header_layout.addWidget(self._name_label)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet(f"color: {tool_colors['preview']}; font-size: inherit; margin-left: 6px;")
        header_layout.addWidget(self._count_label, 1)

        self._status_label = QLabel("…")
        self._status_label.setStyleSheet(f"color: {tool_colors['status_spinner']}; font-size: inherit;")
        header_layout.addWidget(self._status_label)

        return header_layout

    def _build_preview(self) -> QLabel:
        """Build the preview label for the first call's args."""
        self._preview_label = _make_preview_label()
        return self._preview_label

    def _build_detail_section(self) -> QWidget:
        """Build the expandable detail area for all calls."""
        self._detail_widget = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_widget)
        self._detail_layout.setContentsMargins(28, 2, 0, 2)
        self._detail_layout.setSpacing(4)
        self._detail_widget.setVisible(False)
        return self._detail_widget

    def add_call(self, tool_call_id: str, args_text: str = "") -> None:
        """Add another call to this batch."""
        self._count += 1
        self._tool_call_ids.append(tool_call_id)
        self._count_label.setText(f"({self._count} calls)")
        tool_colors = get_tool_colors()

        if self._count == 1 and args_text.strip():
            self._first_args = args_text
            summary = _format_tool_summary(self._tool_name, args_text)
            # For first call, show summary alongside count
            preview = _truncate_preview(args_text.strip())
            self._preview_label.setText(preview)
            self._preview_label.setVisible(not self._expanded)

        # Add entry in detail area
        summary = _format_tool_summary(self._tool_name, args_text) if args_text else ""
        entry = QLabel(f"#{self._count}: {summary}" if summary else f"#{self._count}")
        entry.setStyleSheet(f"color: {tool_colors['preview']}; font-size: inherit;")
        entry.setWordWrap(True)
        self._entry_labels.append(entry)  # prevent Shiboken GC
        self._detail_layout.addWidget(entry)

    def set_args_for_call(self, tool_call_id: str, args_text: str) -> None:
        """Update args for a specific call (used when streaming completes)."""
        idx = -1
        for i, tid in enumerate(self._tool_call_ids):
            if tid == tool_call_id:
                idx = i
                break
        if idx < 0:
            return

        if idx == 0 and not self._first_args:
            self._first_args = args_text
            preview = _truncate_preview(args_text.strip())
            self._preview_label.setText(preview)
            self._preview_label.setVisible(not self._expanded)

        # Update detail entry
        summary = _format_tool_summary(self._tool_name, args_text)
        item = self._detail_layout.itemAt(idx)
        if item and item.widget():
            label_text = f"#{idx + 1}: {summary}" if summary else f"#{idx + 1}"
            item.widget().setText(label_text)

    def set_result_for_call(self, tool_call_id: str, result: str, is_error: bool) -> None:
        """Record a result for one call in the batch."""
        if is_error:
            self._errors[tool_call_id] = result
        else:
            self._results[tool_call_id] = result
        self._update_status()

    def _update_status(self) -> None:
        tool_colors = get_tool_colors()
        done = len(self._results) + len(self._errors)
        if done >= self._count:
            if self._errors:
                self._status_label.setText(f"✓{len(self._results)} ✗{len(self._errors)}")
                self._status_label.setStyleSheet(f"color: {tool_colors['status_error']}; font-size: inherit;")
            else:
                self._status_label.setText("✓")
                self._status_label.setStyleSheet(f"color: {tool_colors['status_success']}; font-size: inherit;")
        else:
            self._status_label.setText(f"{done}/{self._count}")

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._detail_widget.setVisible(self._expanded)
        self._preview_label.setVisible(not self._expanded and bool(self._first_args))
        self._toggle_btn.setText("▼" if self._expanded else "▶")

    @property
    def tool_name(self) -> str:
        return self._tool_name

    @property
    def count(self) -> int:
        return self._count


# ---------------------------------------------------------------------------
# Tool group widget — collapsible container for runs of tool calls
# ---------------------------------------------------------------------------


class ToolGroupWidget(QFrame):
    """Collapsible group for a consecutive run of tool calls."""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("message_tool")
        self._expanded = False
        self._count = 0
        self._done = 0
        self._errors = 0
        self._tool_names: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(0)

        # Header: ▶ <summary label>  ✓
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("collapse_button")
        self._toggle_btn.setText("▶")
        self._toggle_btn.setFixedSize(14, 14)
        self._toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._toggle_btn)

        tool_colors = get_tool_colors()
        self._label = QLabel("0 tools called")
        self._label.setStyleSheet(f"color: {tool_colors['preview']}; font-size: inherit; font-weight: bold;")
        header_layout.addWidget(self._label, 1)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {tool_colors['status_spinner']}; font-size: inherit;")
        header_layout.addWidget(self._status_label)

        layout.addLayout(header_layout)

        # Container for child widgets (hidden by default)
        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 2, 0, 2)
        self._body_layout.setSpacing(2)
        self._body.setVisible(False)
        layout.addWidget(self._body)

    def add_widget(self, widget: QWidget, tool_name: str = "") -> None:
        """Add a tool widget into this group."""
        self._count += 1
        self._tool_names.append(tool_name)
        self._body_layout.addWidget(widget)
        self._update_label()

    def notify_result(self, is_error: bool = False) -> None:
        """Called when a tool inside this group finishes."""
        self._done += 1
        if is_error:
            self._errors += 1
        self._update_status()

    def _update_label(self) -> None:
        self._label.setText(_format_tool_group_label(self._tool_names))

    def _update_status(self) -> None:
        tool_colors = get_tool_colors()
        if self._done >= self._count:
            if self._errors:
                ok = self._done - self._errors
                self._status_label.setText(f"✓{ok} ✗{self._errors}")
                self._status_label.setStyleSheet(f"color: {tool_colors['status_error']}; font-size: inherit;")
            else:
                self._status_label.setText("✓")
                self._status_label.setStyleSheet(f"color: {tool_colors['status_success']}; font-size: inherit;")
        else:
            self._status_label.setText(f"{self._done}/{self._count}")
            self._status_label.setStyleSheet(f"color: {tool_colors['status_spinner']}; font-size: inherit;")

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._toggle_btn.setText("▼" if self._expanded else "▶")

    @property
    def count(self) -> int:
        return self._count


# ---------------------------------------------------------------------------
# Python syntax highlighter (used by ToolApprovalWidget)
# ---------------------------------------------------------------------------


class _PythonHighlighter(QSyntaxHighlighter):
    """Minimal VS Code-dark-style Python syntax highlighter."""

    _RULES: ClassVar[list] = []  # built once in __init_subclass__ — see below

    def __init__(self, parent=None):
        super().__init__(parent)
        if not _PythonHighlighter._RULES:
            _PythonHighlighter._RULES = self._build_rules()

    @staticmethod
    def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    @staticmethod
    def _build_rules():
        rules = []
        kw_fmt = _PythonHighlighter._fmt("#c586c0", bold=True)
        for kw in (
            "and",
            "as",
            "assert",
            "async",
            "await",
            "break",
            "class",
            "continue",
            "def",
            "del",
            "elif",
            "else",
            "except",
            "finally",
            "for",
            "from",
            "global",
            "if",
            "import",
            "in",
            "is",
            "lambda",
            "nonlocal",
            "not",
            "or",
            "pass",
            "raise",
            "return",
            "try",
            "while",
            "with",
            "yield",
        ):
            rules.append((_re.compile(rf"\b{kw}\b"), kw_fmt))
        # Built-ins
        bi_fmt = _PythonHighlighter._fmt("#dcdcaa")
        for bi in (
            "print",
            "len",
            "range",
            "int",
            "str",
            "bytes",
            "list",
            "dict",
            "set",
            "tuple",
            "hex",
            "ord",
            "chr",
            "type",
            "isinstance",
            "enumerate",
            "zip",
            "map",
            "filter",
            "sorted",
            "open",
            "True",
            "False",
            "None",
        ):
            rules.append((_re.compile(rf"\b{bi}\b"), bi_fmt))
        # Numbers
        rules.append((_re.compile(r"\b0[xX][0-9a-fA-F]+\b"), _PythonHighlighter._fmt("#b5cea8")))
        rules.append((_re.compile(r"\b\d+\.?\d*\b"), _PythonHighlighter._fmt("#b5cea8")))
        # Strings (single/double, including f/r/b prefixes)
        str_fmt = _PythonHighlighter._fmt("#ce9178")
        rules.append((_re.compile(r'[brfu]?""".*?"""', _re.DOTALL), str_fmt))
        rules.append((_re.compile(r"[brfu]?'''.*?'''", _re.DOTALL), str_fmt))
        rules.append((_re.compile(r'[brfu]?"[^"\n]*"'), str_fmt))
        rules.append((_re.compile(r"[brfu]?'[^'\n]*'"), str_fmt))
        # Comments
        rules.append((_re.compile(r"#[^\n]*"), _PythonHighlighter._fmt("#6a9955", italic=True)))
        # Decorators
        rules.append((_re.compile(r"@\w+"), _PythonHighlighter._fmt("#dcdcaa")))
        # self
        rules.append((_re.compile(r"\bself\b"), _PythonHighlighter._fmt("#9cdcfe", italic=True)))
        return rules

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in _PythonHighlighter._RULES:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class ToolApprovalWidget(QFrame):
    """Displays a tool approval request with syntax-highlighted code preview."""

    approved = Signal(str, str)  # (tool_call_id, "allow" or "deny")

    def __init__(
        self,
        tool_call_id: str,
        tool_name: str,
        args_text: str,
        description: str,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.setObjectName("message_question")
        self.setStyleSheet(get_tool_approval_frame_style())
        self._tool_call_id = tool_call_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self._header = QLabel(_build_approval_header(tool_name))
        self._header.setStyleSheet(get_tool_approval_header_style())
        layout.addWidget(self._header)

        # ``description`` is the human-readable summary of what the tool
        # will do (e.g. "rename sub_1000 → process_data"). The agent
        # loop builds it via ``_describe_tool_call`` for mutating tools
        # that have no ``code`` field; rendering it prominently lets the
        # user decide whether to approve without having to decode the
        # raw JSON args below.
        if description and description.strip():
            desc_label = QLabel(description.strip())
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("font-weight: bold; font-size: inherit;")
            layout.addWidget(desc_label)

        code = self._extract_code(args_text)
        code_lines = code.strip().splitlines() if code.strip() else []

        if code.strip():
            # Only label the preview "Python code" when there is code to
            # show. For mutating tools without a ``code`` field the
            # description above already says what will happen.
            self._info = QLabel(f"Python code — {len(code_lines)} line{'s' if len(code_lines) != 1 else ''}")
            self._info.setStyleSheet("color: #808080; font-size: inherit;")
            layout.addWidget(self._info)

        editor = self._build_code_editor(code, code_lines)
        if editor is not None:
            layout.addWidget(editor)

        layout.addLayout(self._build_approval_buttons())

    @staticmethod
    def _extract_code(args_text: str) -> str:
        """Extract the code/script value from JSON args, falling back to raw text."""
        try:
            args = json.loads(args_text) if args_text.strip() else {}
            return args.get("code", args.get("script", ""))
        except (json.JSONDecodeError, TypeError, AttributeError):
            return args_text

    def _build_code_editor(self, code: str, lines: list) -> QPlainTextEdit | None:
        """Build a read-only syntax-highlighted code editor, or None if no code."""
        if not code.strip():
            return None
        self._code_edit = QPlainTextEdit()
        self._code_edit.setReadOnly(True)
        self._code_edit.setPlainText(code)
        self._code_edit.setStyleSheet(get_tool_approval_code_editor_style())
        self._code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        visible_lines = min(len(lines), 15)
        line_height = self._code_edit.fontMetrics().lineSpacing()
        self._code_edit.setFixedHeight(line_height * visible_lines + 16)
        self._highlighter = _PythonHighlighter(self._code_edit.document())
        return self._code_edit

    def _build_approval_buttons(self) -> QHBoxLayout:
        """Build the Allow / Always Allow / Deny button row."""
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._allow_btn = QToolButton()
        self._allow_btn.setText("  Allow  ")
        self._allow_btn.setStyleSheet(get_tool_approval_allow_btn_style())
        self._allow_btn.clicked.connect(self._on_allow)
        btn_layout.addWidget(self._allow_btn)

        self._always_btn = QToolButton()
        self._always_btn.setText("  Always Allow  ")
        self._always_btn.setStyleSheet(get_tool_approval_always_btn_style())
        self._always_btn.clicked.connect(self._on_always_allow)
        btn_layout.addWidget(self._always_btn)

        self._deny_btn = QToolButton()
        self._deny_btn.setText("  Deny  ")
        self._deny_btn.setStyleSheet(get_tool_approval_deny_btn_style())
        self._deny_btn.clicked.connect(self._on_deny)
        btn_layout.addWidget(self._deny_btn)

        btn_layout.addStretch()
        return btn_layout

    def _disable_buttons(self):
        self._allow_btn.setEnabled(False)
        self._always_btn.setEnabled(False)
        self._deny_btn.setEnabled(False)

    def _on_allow(self):
        self._disable_buttons()
        self._allow_btn.setText("  Allowed  ")
        self._allow_btn.setStyleSheet(get_tool_approval_disabled_btn_style())
        self.approved.emit(self._tool_call_id, "allow")

    def _on_always_allow(self):
        self._disable_buttons()
        self._always_btn.setText("  Always Allowed  ")
        self._always_btn.setStyleSheet(get_tool_approval_disabled_btn_style())
        self.approved.emit(self._tool_call_id, "allow_all")

    def _on_deny(self):
        self._disable_buttons()
        self._deny_btn.setText("  Denied  ")
        self._deny_btn.setStyleSheet(get_tool_approval_disabled_btn_style())
        self.approved.emit(self._tool_call_id, "deny")
