"""Chat view: scrollable area containing message widgets."""

from __future__ import annotations

import json
import time

from ..agent.turn import TurnEvent, TurnEventType
from ..core.types import Message, Role
from .message_widgets import (
    AssistantMessageWidget,
    ErrorMessageWidget,
    ExplorationFindingWidget,
    ExplorationPhaseWidget,
    QueuedMessageWidget,
    ResearchNoteWidget,
    SubagentEventWidget,
    ThinkingWidget,
    UserMessageWidget,
    UserQuestionWidget,
    _split_thinking,
    _ThinkingBlock,
)
from .plan_view import PlanView
from .qt_compat import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
)
from .styles import (
    get_history_nav_button_style,
    get_history_nav_frame_style,
    get_history_nav_label_style,
    is_host_theme,
)
from .tool_widgets import ToolApprovalWidget, ToolCallWidget, ToolGroupWidget

_THINKING_MIN_DISPLAY_MS = 500

# Collapse consecutive tool runs once they reach this many calls.
# A single tool call is shown inline with its name visible;
# only 2+ consecutive calls get grouped into a collapsible widget.
_TOOL_GROUP_MIN_CALLS = 2


def _is_hidden_system_user_message(content: str) -> bool:
    """Internal system hints are persisted as user messages but not shown in UI."""
    if not content:
        return False
    return content.lstrip().startswith("[SYSTEM]")


class ChatView(QScrollArea):
    """Scrollable chat area that renders TurnEvents into widgets."""

    tool_approval_submitted = Signal(str, str)  # (tool_call_id, "allow"/"deny")
    user_answer_submitted = Signal(str)  # chosen option / typed answer
    orchestra_approval_decided = Signal(str, str)  # (tool_call_id, "approve"/"deny")

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("chat_scroll")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container.setObjectName("chat_container")
        # Prevent the container from requesting more width than the viewport;
        # this is critical for word-wrap to work inside a QScrollArea.
        self._container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)
        self._layout.addStretch()
        self.setWidget(self._container)

        # Track current assistant widget for streaming
        self._current_assistant: AssistantMessageWidget | None = None
        self._message_thinking: _ThinkingBlock | None = None  # For message content thinking
        self._tool_widgets: dict[str, ToolCallWidget] = {}
        self._thinking: ThinkingWidget | None = None
        self._thinking_shown_at: float = 0.0
        self._plan_view: PlanView | None = None

        # Consecutive tool run state (collapsed when threshold is reached)
        self._tool_run_ids: list[str] = []
        self._tool_run_names: list[str] = []
        self._tool_run_widgets: list[ToolCallWidget] = []
        # Active collapsible group for the current run
        self._tool_group: ToolGroupWidget | None = None
        # Map tool_call_id -> group it belongs to (for result routing/status)
        self._group_map: dict[str, ToolGroupWidget] = {}

        # Member timer for scroll-to-bottom — coalesce at 80ms to reduce
        # layout thrashing during rapid streaming
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(80)
        self._scroll_timer.timeout.connect(self._do_scroll)

        # Timer for minimum thinking display duration (500ms)
        self._thinking_hide_timer = QTimer(self)
        self._thinking_hide_timer.setSingleShot(True)
        self._thinking_hide_timer.timeout.connect(self._force_hide_thinking)

        # Batched session restore state
        self._pending_restore: list[Message] = []
        self._restore_chunk_size = 10

        # Paginated restore state — restored histories are rendered as
        # page windows instead of one huge transcript. See
        # _build_restore_units / _build_restore_pages / _render_restore_window.
        self._restore_messages: list[Message] = []
        self._restore_units: list[tuple[int, int]] = []
        self._restore_pages: list[tuple[int, int]] = []
        self._restore_first_page: int = 0
        self._restore_last_page: int = 0
        self._restore_paged: bool = False
        self._restore_rendered: bool = False
        self._restore_page_size_units: int = 40
        self._restore_max_window_pages: int = 5
        self._restore_default_window_pages: int = 1

        # Live-tail safety: once the user/app appends a live message into a
        # paginated restore, history navigation is disabled so a stray click
        # on "Load older/newer/latest" can no longer wipe the live tail by
        # triggering _render_restore_window().  See
        # _ensure_latest_restore_window_for_live_append and the
        # _go_restore_*/_render_restore_window guards.
        self._restore_live_tail_started: bool = False

        # Track currently-rendered history nav frames so refresh_inline_styles
        # can re-apply the theme palette to them after a theme switch.
        self._nav_widgets: list[QFrame] = []

        # Thinking block buffering for proper ordering
        self._think_buffer: str = ""  # Accumulated text while waiting for <think> to close
        self._waiting_think_close: bool = False  # True when we have <think> but not yet

    def add_user_message(self, text: str) -> None:
        self._begin_live_tail_append()
        self._insert_user_message_widget(text)

    def add_error_message(self, text: str) -> None:
        self._begin_live_tail_append()
        self._insert_widget(ErrorMessageWidget(text))
        self._scroll_to_bottom()

    def add_queued_message(self, text: str) -> None:
        self._begin_live_tail_append()
        self._insert_widget(QueuedMessageWidget(text))
        self._scroll_to_bottom()

    def _begin_live_tail_append(self) -> None:
        """Prepare a paginated restore for a live-widget append.

        Order matters here:

        1. Jump the page window back to the final page **with the nav
           strip suppressed** so the new live widget appears beneath
           the latest restored page.  This call happens *before* the
           live-tail flag is set, so the (re-)render still produces
           the visible restored content.
        2. Lock the live tail by setting ``_restore_live_tail_started``.
           From this point on, ``_render_restore_window`` early-returns
           and the ``_go_restore_*`` nav callbacks are no-ops, so a
           stray click can no longer wipe the live tail.
        3. Remove any nav frames that may still be in the layout from
           the previous render.  Live widgets (already inserted before
           this call) are intentionally left untouched — this method
           only touches ``self._nav_widgets``.
        """
        if not self._restore_paged:
            return
        # 1. Jump to latest page WITHOUT nav so the visible restored
        #    content is the latest page but no nav strip is added.
        self._ensure_latest_restore_window_for_live_append(show_nav=False)
        # 2. Lock the live tail — subsequent _render_restore_window
        #    calls become a no-op, and _go_restore_* callbacks no-op.
        self._restore_live_tail_started = True
        # 3. Strip any nav frames left from a previous render so the
        #    UI matches the "no nav" state implied by the live-tail flag.
        self._remove_restore_nav_widgets()

    def _remove_restore_nav_widgets(self) -> None:
        """Remove rendered history nav frames only; never clear live widgets.

        The removal is immediate and thorough:

        * ``hide()`` so the widget vanishes from the viewport in this
          event-loop tick (rather than waiting for ``deleteLater()``).
        * ``removeWidget()`` detaches it from the layout.
        * ``setParent(None)`` detaches it from the widget tree so a
          subsequent ``deleteLater()`` cannot accidentally walk back
          into the live-tail widgets via the parent chain.
        * ``deleteLater()`` schedules the C++ object for deletion.
        * ``self._nav_widgets`` is cleared so ``refresh_inline_styles``
          does not iterate over stale references.
        """
        for frame in list(self._nav_widgets):
            try:
                frame.hide()
                self._layout.removeWidget(frame)
                frame.setParent(None)
                frame.deleteLater()
            except RuntimeError:
                # Widget may already be deleted; ignore.
                pass
        self._nav_widgets = []

    def _insert_user_message_widget(self, text: str) -> None:
        """Insert a UserMessageWidget without touching restore pagination.

        Used by both the live ``add_user_message`` path and the restore
        renderer.  Live callers must run
        ``_ensure_latest_restore_window_for_live_append`` first.
        """
        widget = UserMessageWidget(text)
        self._insert_widget(widget)
        self._current_assistant = None

    def remove_queued_messages(self) -> None:
        """Remove all [queued] message widgets (e.g. on cancel)."""
        for i in reversed(range(self._layout.count())):
            item = self._layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, QueuedMessageWidget):
                self._layout.removeWidget(widget)
                widget.deleteLater()

    def pop_first_queued_message(self) -> None:
        """Remove the first [queued] widget (when it gets submitted)."""
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, QueuedMessageWidget):
                self._layout.removeWidget(widget)
                widget.deleteLater()
                return

    def _show_thinking(self) -> None:
        if self._thinking is not None:
            return
        self._thinking = ThinkingWidget()
        self._thinking_shown_at = time.monotonic()
        self._insert_widget(self._thinking)
        self._scroll_to_bottom()

    def _hide_thinking(self) -> None:
        if self._thinking is None:
            return
        elapsed_ms = (time.monotonic() - self._thinking_shown_at) * 1000
        if elapsed_ms < _THINKING_MIN_DISPLAY_MS:
            remaining = int(_THINKING_MIN_DISPLAY_MS - elapsed_ms)
            self._thinking_hide_timer.start(remaining)
            return
        self._force_hide_thinking()

    def _force_hide_thinking(self) -> None:
        if self._thinking is None:
            return
        self._thinking.stop()
        self._layout.removeWidget(self._thinking)
        self._thinking.deleteLater()
        self._thinking = None

    def _reset_tool_run(self) -> None:
        """End the current consecutive tool run (state only)."""
        self._tool_group = None
        self._tool_run_ids.clear()
        self._tool_run_names.clear()
        self._tool_run_widgets.clear()

    def _register_tool_widget(self, tool_name: str, tool_id: str, widget: ToolCallWidget) -> None:
        """Attach a new tool widget to the current run, collapsing at threshold."""
        self._tool_run_ids.append(tool_id)
        self._tool_run_names.append(tool_name)
        self._tool_run_widgets.append(widget)

        run_len = len(self._tool_run_widgets)

        # Below threshold: show tool calls directly.
        if self._tool_group is None and run_len < _TOOL_GROUP_MIN_CALLS:
            self._insert_widget(widget)
            return

        # Threshold reached: move entire run into a new collapsible group.
        if self._tool_group is None and run_len == _TOOL_GROUP_MIN_CALLS:
            self._tool_group = ToolGroupWidget()
            self._insert_widget(self._tool_group)

            for idx, run_widget in enumerate(self._tool_run_widgets):
                self._layout.removeWidget(run_widget)
                run_widget.hide_preview()

                run_tool_id = self._tool_run_ids[idx]
                run_tool_name = self._tool_run_names[idx]
                self._tool_group.add_widget(run_widget, run_tool_name)
                self._group_map[run_tool_id] = self._tool_group
            return

        # Already collapsed: add new call directly to existing group.
        widget.hide_preview()
        if self._tool_group is not None:
            self._tool_group.add_widget(widget, tool_name)
            self._group_map[tool_id] = self._tool_group

    def handle_event(self, event: TurnEvent) -> None:
        """Process a TurnEvent and update the UI accordingly."""
        # Live turn events must not be appended under an older paged
        # window, and any history nav must be removed before we start
        # inserting live widgets so a stray click cannot wipe the tail.
        self._begin_live_tail_append()
        etype = event.type
        if etype in (TurnEventType.TEXT_DELTA, TurnEventType.TEXT_DONE):
            self._handle_text_event(event)
        elif etype in (
            TurnEventType.TOOL_CALL_START,
            TurnEventType.TOOL_CALL_ARGS_DELTA,
            TurnEventType.TOOL_CALL_DONE,
            TurnEventType.TOOL_RESULT,
            TurnEventType.TOOL_APPROVAL_REQUEST,
        ):
            self._handle_tool_event(event)
        elif etype in (
            TurnEventType.TURN_START,
            TurnEventType.TURN_END,
            TurnEventType.CANCELLED,
        ):
            self._handle_lifecycle_event(event)
        elif etype in (
            TurnEventType.PLAN_GENERATED,
            TurnEventType.PLAN_STEP_START,
            TurnEventType.PLAN_STEP_DONE,
        ):
            self._handle_plan_event(event)
        elif etype in (
            TurnEventType.EXPLORATION_PHASE_CHANGE,
            TurnEventType.EXPLORATION_FINDING,
        ):
            self._handle_exploration_event(event)
        elif etype in (
            TurnEventType.RESEARCH_NOTE_SAVED,
            TurnEventType.RESEARCH_NOTE_REVIEWED,
        ):
            self._handle_research_event(event)
        elif etype in (
            TurnEventType.USER_QUESTION,
            TurnEventType.SAVE_APPROVAL_REQUEST,
        ):
            self._handle_question_event(event)
        elif etype in (
            TurnEventType.SUBAGENT_SPAWNED,
            TurnEventType.SUBAGENT_COMPLETED,
            TurnEventType.SUBAGENT_FAILED,
        ):
            self._handle_subagent_event(event)
        elif etype == TurnEventType.ERROR:
            self._hide_thinking()
            self._reset_tool_run()
            self._insert_widget(ErrorMessageWidget(event.error or "Unknown error"))
            self._scroll_to_bottom()

    def _handle_text_event(self, event: TurnEvent) -> None:
        self._hide_thinking()
        self._reset_tool_run()
        if event.type == TurnEventType.TEXT_DELTA:
            text = event.text

            if self._waiting_think_close:
                # Buffer text until </think> arrives
                self._think_buffer += text
                if "</think>" in text:
                    # Complete — parse accumulated buffer
                    thinking_text, visible_text = _split_thinking(self._think_buffer)
                    self._waiting_think_close = False
                    if thinking_text:
                        if self._message_thinking is None:
                            self._message_thinking = _ThinkingBlock()
                            self._insert_widget(self._message_thinking)
                        self._message_thinking.set_thinking(thinking_text, in_progress=False)
                    if visible_text:
                        if self._current_assistant is None:
                            self._current_assistant = AssistantMessageWidget()
                            self._insert_widget(self._current_assistant)
                        self._current_assistant.append_text(visible_text)
            elif "<think>" in text and "</think>" not in text:
                # Opening <think> without closing — start buffering
                self._waiting_think_close = True
                self._think_buffer = text
                thinking_text, visible_text = _split_thinking(text)
                if thinking_text:
                    if self._message_thinking is None:
                        self._message_thinking = _ThinkingBlock()
                        self._insert_widget(self._message_thinking)
                    self._message_thinking.set_thinking(thinking_text, in_progress=True)
                if visible_text:
                    if self._current_assistant is None:
                        self._current_assistant = AssistantMessageWidget()
                        self._insert_widget(self._current_assistant)
                    self._current_assistant.append_text(visible_text)
            else:
                # Normal text (no thinking, or complete <think>...</think> in one delta)
                thinking_text, visible_text = _split_thinking(text)
                if thinking_text:
                    if self._message_thinking is None:
                        self._message_thinking = _ThinkingBlock()
                        self._insert_widget(self._message_thinking)
                    self._message_thinking.set_thinking(thinking_text, in_progress=False)
                if visible_text:
                    if self._current_assistant is None:
                        self._current_assistant = AssistantMessageWidget()
                        self._insert_widget(self._current_assistant)
                    self._current_assistant.append_text(visible_text)

            self._scroll_to_bottom()
        else:  # TEXT_DONE
            if self._current_assistant is not None:
                # Final render - extract and handle thinking if any
                thinking_text, visible_text = _split_thinking(event.text)

                if thinking_text:
                    # Finalize thinking block
                    if self._message_thinking is None:
                        self._message_thinking = _ThinkingBlock()
                        self._insert_widget(self._message_thinking)
                    self._message_thinking.set_thinking(thinking_text, in_progress=False)

                if visible_text:
                    self._current_assistant.set_text(visible_text)
                elif not thinking_text:
                    # No visible text at all, just render normally
                    self._current_assistant.set_text(event.text)

            self._current_assistant = None
            self._message_thinking = None
            self._think_buffer = ""
            self._waiting_think_close = False

    def _handle_tool_event(self, event: TurnEvent) -> None:
        etype = event.type
        if etype == TurnEventType.TOOL_CALL_START:
            self._hide_thinking()
            tw = ToolCallWidget(event.tool_name, event.tool_call_id)
            self._tool_widgets[event.tool_call_id] = tw
            self._register_tool_widget(event.tool_name, event.tool_call_id, tw)
            self._scroll_to_bottom()
        elif etype == TurnEventType.TOOL_CALL_ARGS_DELTA:
            existing_tw = self._tool_widgets.get(event.tool_call_id)
            if existing_tw is not None:
                existing_tw.append_args_delta(event.tool_args)
        elif etype == TurnEventType.TOOL_CALL_DONE:
            existing_tw = self._tool_widgets.get(event.tool_call_id)
            if existing_tw is not None:
                existing_tw.set_arguments(event.tool_args)
        elif etype == TurnEventType.TOOL_RESULT:
            self._reset_tool_run()
            existing_tw = self._tool_widgets.get(event.tool_call_id)
            if existing_tw is not None:
                existing_tw.set_result(event.tool_result, event.tool_is_error)
            group = self._group_map.get(event.tool_call_id)
            if group:
                group.notify_result(event.tool_is_error)
            self._scroll_to_bottom()
        elif etype == TurnEventType.TOOL_APPROVAL_REQUEST:
            self._hide_thinking()
            self._reset_tool_run()
            widget = ToolApprovalWidget(
                event.tool_call_id,
                event.tool_name,
                event.tool_args,
                event.text,
            )
            widget.approved.connect(self._on_tool_approval)
            self._insert_widget(widget)
            self._scroll_to_bottom()

    def _handle_lifecycle_event(self, event: TurnEvent) -> None:
        etype = event.type
        if etype == TurnEventType.TURN_START:
            self._current_assistant = None
            self._reset_tool_run()
            self._group_map.clear()
            self._show_thinking()
            self._scroll_to_bottom()
        elif etype == TurnEventType.TURN_END:
            self._hide_thinking()
            self._reset_tool_run()
            self._current_assistant = None
        elif etype == TurnEventType.CANCELLED:
            self._hide_thinking()
            self._reset_tool_run()
            self._insert_widget(ErrorMessageWidget("Cancelled by user"))
            self._scroll_to_bottom()

    def _handle_plan_event(self, event: TurnEvent) -> None:
        etype = event.type
        if etype == TurnEventType.PLAN_GENERATED:
            self._hide_thinking()
            self._reset_tool_run()
            self._plan_view = PlanView()
            if event.plan_steps:
                self._plan_view.set_plan(event.plan_steps)

            def _on_plan_approve(pv=self._plan_view):
                pv.set_buttons_visible(False)
                self._on_user_answer("approve")

            def _on_plan_reject(pv=self._plan_view):
                pv.set_buttons_visible(False)
                self._on_user_answer("reject")

            self._plan_view.set_approved_callback(_on_plan_approve)
            self._plan_view.set_rejected_callback(_on_plan_reject)
            self._insert_widget(self._plan_view)
            self._scroll_to_bottom()
        elif etype == TurnEventType.PLAN_STEP_START:
            if self._plan_view:
                self._plan_view.set_step_status(event.plan_step_index, "active")
                self._plan_view.set_buttons_visible(False)
            self._scroll_to_bottom()
        elif etype == TurnEventType.PLAN_STEP_DONE:
            if self._plan_view:
                self._plan_view.set_step_status(event.plan_step_index, "done")
            self._scroll_to_bottom()

    def _handle_exploration_event(self, event: TurnEvent) -> None:
        meta = event.metadata
        if event.type == TurnEventType.EXPLORATION_PHASE_CHANGE:
            self._hide_thinking()
            self._reset_tool_run()
            self._insert_widget(
                ExplorationPhaseWidget(
                    meta.get("from_phase", ""),
                    meta.get("to_phase", ""),
                    event.text,
                )
            )
        else:  # EXPLORATION_FINDING
            self._insert_widget(
                ExplorationFindingWidget(
                    meta.get("category", "general"),
                    event.text,
                    meta.get("address"),
                    meta.get("relevance", "medium"),
                )
            )
        self._scroll_to_bottom()

    def _handle_research_event(self, event: TurnEvent) -> None:
        meta = event.metadata
        if event.type == TurnEventType.RESEARCH_NOTE_SAVED:
            self._hide_thinking()
            self._reset_tool_run()
            self._insert_widget(
                ResearchNoteWidget(
                    title=event.text,
                    genre=meta.get("genre", "general"),
                    path=meta.get("path", ""),
                    preview=meta.get("preview", ""),
                    review_passed=meta.get("review_passed", True),
                )
            )
            self._scroll_to_bottom()
        # RESEARCH_NOTE_REVIEWED — no separate widget, info is in the saved event

    def _handle_subagent_event(self, event: TurnEvent) -> None:
        meta = event.metadata
        if event.type == TurnEventType.SUBAGENT_SPAWNED:
            name = event.text
            agent_type = meta.get("agent_type", "custom")
            self._insert_widget(SubagentEventWidget("spawned", name, f"type: {agent_type}"))
        elif event.type == TurnEventType.SUBAGENT_COMPLETED:
            name = meta.get("name", "")
            turns = meta.get("turn_count", 0)
            elapsed = meta.get("elapsed", 0.0)
            detail = f"{turns} turns, {elapsed:.0f}s"
            self._insert_widget(SubagentEventWidget("completed", name, detail))
        elif event.type == TurnEventType.SUBAGENT_FAILED:
            name = meta.get("name", "")
            error = event.error or "Unknown error"
            self._insert_widget(SubagentEventWidget("failed", name, error))
        self._scroll_to_bottom()

    def _handle_question_event(self, event: TurnEvent) -> None:
        self._hide_thinking()
        self._reset_tool_run()
        is_orchestra = event.metadata.get("orchestra_delegate") if event.metadata else False

        if event.type == TurnEventType.SAVE_APPROVAL_REQUEST:
            options = ["Save All", "Discard All"]
        else:  # USER_QUESTION
            options = event.metadata.get("options", []) if event.metadata else []

        if is_orchestra:
            from .orchestra_approval_dialog import DelegationApprovalWidget

            delegate_spec = (event.metadata or {}).get("delegate_spec", {})
            widget = DelegationApprovalWidget(
                task_name=delegate_spec.get("task", "Unknown Task"),
                instruction=delegate_spec.get("instruction", ""),
                context=delegate_spec.get("context", ""),
                tools=delegate_spec.get("tools", []),
                model=delegate_spec.get("model", ""),
                max_steps=delegate_spec.get("max_steps", 20),
            )
            widget.approved.connect(lambda _, d="approve": self._on_orchestra_approval(event.tool_call_id, d))
            widget.denied.connect(lambda _, d="deny": self._on_orchestra_approval(event.tool_call_id, d))
        else:
            widget = UserQuestionWidget(event.text, options)
            widget.option_selected.connect(self._on_user_answer)

        self._insert_widget(widget)
        self._scroll_to_bottom()

    def _on_orchestra_approval(self, tool_call_id: str, decision: str) -> None:
        """Forward orchestra delegation approval decision to the panel/controller."""
        self.orchestra_approval_decided.emit(tool_call_id, decision)

    def _on_tool_approval(self, tool_call_id: str, decision: str) -> None:
        """Forward tool approval decision to the panel/controller."""
        self.tool_approval_submitted.emit(tool_call_id, decision)

    def _on_user_answer(self, answer: str) -> None:
        """Forward a button-selected answer to the panel/controller."""
        self.user_answer_submitted.emit(answer)

    def restore_from_messages(self, messages: list[Message]) -> None:
        """Replay saved Message objects into the chat view using pagination.

        Only the last page is rendered initially.  Older pages are
        available on demand via the navigation controls emitted into the
        chat; the full message list is retained in memory for the agent
        context.
        """
        # Full reset — clears widgets and pagination state.
        self.clear_chat()
        # A fresh restore re-enables history navigation; the live-tail
        # guard is reset by clear_chat() above, but be explicit.
        self._restore_live_tail_started = False
        self._restore_messages = list(messages)
        self._restore_units = self._build_restore_units(self._restore_messages)
        self._restore_pages = self._build_restore_pages(
            self._restore_units,
            self._restore_page_size_units,
        )

        if not self._restore_pages:
            # Nothing visible to render (e.g. hidden system messages only).
            return

        last_page = len(self._restore_pages) - 1
        self._restore_last_page = last_page
        self._restore_first_page = last_page
        self._restore_paged = True
        self._render_restore_window(scroll_to="bottom")

    def _build_restore_units(self, messages: list[Message]) -> list[tuple[int, int]]:
        """Group messages into render units for paged restore.

        Rules (see plan §2):
        - Hidden persisted system hints (USER messages with ``[SYSTEM]`` prefix)
          are skipped.
        - SYSTEM (or unknown) messages are also skipped here so the
          paginated unit/page counts stay consistent with
          ``_render_restored_messages`` (which never renders them).
        - A normal USER message is one unit.
        - An ASSISTANT message is one unit, extended to include the
          immediately following TOOL message so tool call + result never
          straddle a page boundary.
        - Orphan TOOL messages (no preceding assistant) are included as
          their own unit for safety.
        """
        units: list[tuple[int, int]] = []
        n = len(messages)
        i = 0
        while i < n:
            msg = messages[i]
            if msg.role == Role.USER:
                if _is_hidden_system_user_message(msg.content):
                    i += 1
                    continue
                units.append((i, i + 1))
                i += 1
            elif msg.role == Role.ASSISTANT:
                start = i
                i += 1
                # Absorb the immediately following TOOL message into the
                # same unit so the tool result never lands in a later page
                # than its tool call.
                if i < n and messages[i].role == Role.TOOL:
                    i += 1
                units.append((start, i))
            elif msg.role == Role.TOOL:
                # Orphan tool result (no matching assistant).  Keep it as
                # its own unit so it can be rendered harmlessly.
                units.append((i, i + 1))
                i += 1
            else:
                # SYSTEM (or unknown) — never rendered, so skip here too.
                i += 1
        return units

    def _build_restore_pages(
        self,
        units: list[tuple[int, int]],
        page_size_units: int,
    ) -> list[tuple[int, int]]:
        """Split a list of units into fixed-size page ranges (unit indices)."""
        if not units or page_size_units <= 0:
            return []
        pages: list[tuple[int, int]] = []
        total = len(units)
        for start in range(0, total, page_size_units):
            pages.append((start, min(start + page_size_units, total)))
        return pages

    def _message_range_for_restore_window(self) -> tuple[int, int]:
        """Convert the current page window into a (start, end) message range.

        ``end`` is exclusive, matching list-slicing semantics.
        """
        first = max(0, min(self._restore_first_page, len(self._restore_pages) - 1))
        last = max(first, min(self._restore_last_page, len(self._restore_pages) - 1))
        unit_start = self._restore_pages[first][0]
        unit_end_excl = self._restore_pages[last][1]
        if unit_end_excl <= 0:
            return (0, 0)
        msg_start = self._restore_units[unit_start][0]
        # The last unit's end index (exclusive) is the message slice end.
        msg_end = self._restore_units[unit_end_excl - 1][1]
        return (msg_start, msg_end)

    def _clear_rendered_widgets(self) -> None:
        """Delete currently-rendered widgets without touching pagination state.

        Used when sliding the page window; ``_restore_messages`` /
        ``_restore_pages`` are preserved so the next render can rebuild
        the visible window cheaply.
        """
        self._force_hide_thinking()
        self._thinking_hide_timer.stop()
        self._think_buffer = ""
        self._waiting_think_close = False
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        self._current_assistant = None
        self._message_thinking = None
        self._tool_widgets.clear()
        self._plan_view = None
        self._reset_tool_run()
        self._group_map.clear()

    def _ensure_latest_restore_window_for_live_append(self, show_nav: bool = True) -> None:
        """Jump the page window back to the final page before live appends.

        This guarantees new live messages always appear beneath the
        latest restored page instead of beneath an older one.

        ``show_nav`` controls whether the rendered page includes the
        history nav strip.  The live-tail pre-lock helper
        (``_begin_live_tail_append``) passes ``False`` because the
        live-tail flag is about to suppress nav anyway, and re-emitting
        nav frames only to immediately strip them is wasteful.
        """
        if not self._restore_paged or not self._restore_pages:
            return
        final_page = len(self._restore_pages) - 1
        if self._restore_last_page != final_page or self._restore_first_page != final_page:
            self._restore_first_page = final_page
            self._restore_last_page = final_page
            self._render_restore_window(scroll_to="bottom", show_nav=show_nav)

    def _render_restored_messages(self, messages: list[Message]) -> None:
        """Render a slice of restored messages into the current page window.

        This is the page-bounded equivalent of the old
        ``_restore_next_chunk`` body — it iterates the supplied messages
        once and dispatches by role, but never mutates any pending queue.
        """
        for msg in messages:
            if msg.role == Role.USER:
                if _is_hidden_system_user_message(msg.content):
                    continue
                self._reset_tool_run()
                self._insert_user_message_widget(msg.content)
            elif msg.role == Role.ASSISTANT:
                self._reset_tool_run()
                if msg.content:
                    thinking_text, visible_text = _split_thinking(msg.content)

                    if thinking_text:
                        tb = _ThinkingBlock()
                        tb.set_thinking(thinking_text, in_progress=False)
                        self._insert_widget(tb)

                    w = AssistantMessageWidget()
                    w.set_text(visible_text if visible_text else msg.content)
                    self._insert_widget(w)
                else:
                    w = AssistantMessageWidget()
                    self._insert_widget(w)
                for tc in msg.tool_calls:
                    tw = ToolCallWidget(tc.name, tc.id)
                    try:
                        args_str = json.dumps(tc.arguments, indent=2)
                    except (TypeError, ValueError):
                        args_str = str(tc.arguments)
                    tw.set_arguments(args_str)
                    tw.mark_done()
                    self._tool_widgets[tc.id] = tw
                    self._register_tool_widget(tc.name, tc.id, tw)
            elif msg.role == Role.TOOL:
                self._reset_tool_run()
                for tr in msg.tool_results:
                    existing_tw = self._tool_widgets.get(tr.tool_call_id)
                    if existing_tw is not None:
                        existing_tw.set_result(tr.content, tr.is_error)
                    group = self._group_map.get(tr.tool_call_id)
                    if group:
                        group.notify_result(tr.is_error)
            # SYSTEM / unknown — skip during restore; not part of UI transcript.

    def _make_restore_nav_widget(self, position: str) -> QWidget:
        """Build a small navigation strip for the paged restore view.

        Two of these are emitted per render — one at the top, one at the
        bottom — so the user can jump in either direction regardless of
        scroll position.  Buttons are disabled when no pages exist in
        that direction or when only a single page is present.
        """
        frame = QFrame()
        frame.setObjectName("history_nav")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        older_btn = QPushButton("Load older")
        newer_btn = QPushButton("Load newer")
        latest_btn = QPushButton("Latest")
        for btn in (older_btn, newer_btn, latest_btn):
            btn.setObjectName("history_nav_btn")

        total = len(self._restore_pages)
        first = self._restore_first_page
        last = self._restore_last_page
        has_older = first > 0
        has_newer = last < total - 1
        not_at_latest = last < total - 1

        older_btn.setEnabled(has_older)
        newer_btn.setEnabled(has_newer)
        latest_btn.setEnabled(not_at_latest)

        older_btn.clicked.connect(self._go_restore_older)
        newer_btn.clicked.connect(self._go_restore_newer)
        latest_btn.clicked.connect(self._go_restore_latest)

        # Page summary (e.g. "Showing pages 2-3 of 12").
        # Pages are 1-indexed in the label for readability.
        first_label = first + 1
        last_label = last + 1
        if first == last:
            summary = f"Page {first_label} of {total}"
        else:
            summary = f"Pages {first_label}-{last_label} of {total}"
        label = QLabel(summary)
        label.setObjectName("history_nav_label")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Top widget prioritises "Load older"; bottom prioritises
        # "Latest" / "Load newer".  Both expose all three for symmetry.
        if position == "top":
            order = (older_btn, label, newer_btn, latest_btn)
        else:
            order = (latest_btn, newer_btn, label, older_btn)
        for w in order:
            layout.addWidget(w)
        layout.addStretch(1)

        # Apply theme-aware inline styles so the strip respects the
        # active light/dark palette regardless of which theme the
        # global stylesheet was loaded with.
        self._apply_nav_widget_style(frame, label, older_btn, newer_btn, latest_btn)
        return frame

    def _apply_nav_widget_style(
        self,
        frame: QFrame,
        label: QLabel,
        *buttons: QPushButton,
    ) -> None:
        """Apply the current theme's styles to a history nav strip.

        In the explicit ``"light"`` / ``"dark"`` themes, the per-widget
        stylesheets from the style getters are applied so the nav strip
        matches the rest of the Rikugan palette.

        In the ``"ida"`` (host) theme, the per-widget stylesheets are
        cleared so the IDA wrapper's minimal targeted stylesheet (or
        the host's Qt palette) can control the nav strip.  This
        prevents a stale light/dark inline stylesheet from bleeding
        into the host theme after a theme switch.
        """
        if is_host_theme():
            frame.setStyleSheet("")
            label.setStyleSheet("")
            for btn in buttons:
                btn.setStyleSheet("")
            return
        frame.setStyleSheet(get_history_nav_frame_style())
        label.setStyleSheet(get_history_nav_label_style())
        btn_style = get_history_nav_button_style()
        for btn in buttons:
            btn.setStyleSheet(btn_style)

    def refresh_inline_styles(self) -> None:
        """Re-apply the theme-aware inline styles to history nav widgets.

        Qt's stylesheet cascade is per-widget; widgets that received a
        widget-local stylesheet at construction time do not auto-refresh
        when the parent theme changes.  This method walks the currently
        rendered nav frames and re-issues the same style sheets so the
        strip matches the active palette after a theme switch.

        In the ``"ida"`` (host) theme the per-widget stylesheets are
        cleared instead, so the IDA wrapper's minimal targeted
        stylesheet — or the host's Qt palette — can take over without
        a stale light/dark inline stylesheet leaking through.

        Only direct children whose ``objectName()`` is
        ``"history_nav_label"`` or ``"history_nav_btn"`` receive the
        per-widget stylesheet; unrelated children inside the frame are
        left untouched.  Widgets that have been deleted (e.g. via a
        live append that removed the nav strip) are pruned from
        ``self._nav_widgets`` so the list does not accumulate stale
        ``QFrame`` references.
        """
        host = is_host_theme()
        alive_navs: list[QFrame] = []
        for frame in self._nav_widgets:
            try:
                if host:
                    frame.setStyleSheet("")
                    for child in frame.findChildren(QLabel):
                        if child.objectName() == "history_nav_label":
                            child.setStyleSheet("")
                    for child in frame.findChildren(QPushButton):
                        if child.objectName() == "history_nav_btn":
                            child.setStyleSheet("")
                else:
                    frame.setStyleSheet(get_history_nav_frame_style())
                    btn_style = get_history_nav_button_style()
                    label_style = get_history_nav_label_style()
                    for child in frame.findChildren(QLabel):
                        if child.objectName() == "history_nav_label":
                            child.setStyleSheet(label_style)
                    for child in frame.findChildren(QPushButton):
                        if child.objectName() == "history_nav_btn":
                            child.setStyleSheet(btn_style)
                alive_navs.append(frame)
            except RuntimeError:
                # Widget may have been deleted; drop the stale ref.
                pass
        self._nav_widgets = alive_navs

    def _render_restore_window(
        self,
        scroll_to: str = "bottom",
        show_nav: bool | None = None,
    ) -> None:
        """Render the currently-selected page window.

        Idempotent: clears the layout, then re-inserts the visible
        messages plus top/bottom nav strips.

        Live-tail safety: once ``_restore_live_tail_started`` is set
        (i.e. a live widget has been appended into a paginated
        restore), this method early-returns without touching the
        layout.  The ``_go_restore_*`` callbacks also early-return in
        that state, so a stray click cannot wipe the live tail.

        ``show_nav`` overrides the default nav-strip policy.  When
        ``None`` (the default) the nav strip is shown iff there is
        more than one page.  Pass ``False`` to render the page without
        the nav strip even before the live-tail flag is set (used by
        the live-tail pre-lock helper).
        """
        # Live-tail safety: a render after a live append must not wipe
        # the live widgets.  The early-return is structural — it guards
        # against any future caller that might trigger a re-render
        # (e.g. a stray nav-button click that bypasses the _go_*
        # guards, or a re-entry from a different code path).
        if self._restore_live_tail_started:
            return
        if not self._restore_pages:
            self._clear_rendered_widgets()
            return

        # Clamp window into [0, len(pages)) and cap its size to
        # ``_restore_max_window_pages``.
        total_pages = len(self._restore_pages)
        last = min(self._restore_last_page, total_pages - 1)
        first = min(self._restore_first_page, last)
        # If the window would exceed the cap, shrink from the leading edge.
        if last - first + 1 > self._restore_max_window_pages:
            first = last - self._restore_max_window_pages + 1
        if first < 0:
            first = 0
            last = min(self._restore_max_window_pages - 1, total_pages - 1)
        self._restore_first_page = first
        self._restore_last_page = last

        # Reset the live-tracked nav widgets — _clear_rendered_widgets
        # below will delete them.
        self._nav_widgets = []

        self._clear_rendered_widgets()

        # Resolve the nav-strip policy.  When the caller did not pass
        # one, show the nav iff there is more than one page.
        if show_nav is None:
            show_nav = total_pages > 1

        # Top nav — only show if there's at least one page to navigate to.
        if show_nav:
            top_nav = self._make_restore_nav_widget("top")
            self._nav_widgets.append(top_nav)
            self._insert_widget(top_nav)

        msg_start, msg_end = self._message_range_for_restore_window()
        if msg_end > msg_start:
            self._render_restored_messages(
                self._restore_messages[msg_start:msg_end]
            )

        if show_nav:
            bottom_nav = self._make_restore_nav_widget("bottom")
            self._nav_widgets.append(bottom_nav)
            self._insert_widget(bottom_nav)

        # Reset transient streaming/tool-run state at the end of the
        # render so the chat view is in a clean state for the next
        # live event.  We intentionally do NOT clear ``self._tool_widgets``
        # here: those entries are needed for routing tool results to
        # the rendered tool-call widgets, and the dict is cleaned up
        # when the corresponding widgets are torn down.
        self._current_assistant = None
        self._message_thinking = None
        self._reset_tool_run()

        self._restore_rendered = True

        if scroll_to == "top":
            self.verticalScrollBar().setValue(0)
        elif scroll_to == "force_bottom":
            # Explicit "Latest" actions always want to land on the
            # bottom of the chat, even if the user has scrolled away.
            self._force_scroll_to_bottom()
        else:
            self._scroll_to_bottom()

    def _go_restore_older(self) -> None:
        """Extend the window one page older (sliding cap at 5)."""
        if not self._restore_pages:
            return
        if self._restore_live_tail_started:
            # Live tail safety: a click on the nav button must not
            # re-render the restore window, which would wipe any
            # user/agent widgets that were appended after the restore.
            return
        if self._restore_first_page == 0:
            return
        self._restore_first_page -= 1
        if (
            self._restore_last_page - self._restore_first_page + 1
            > self._restore_max_window_pages
        ):
            self._restore_last_page -= 1
        self._render_restore_window(scroll_to="top")

    def _go_restore_newer(self) -> None:
        """Extend the window one page newer (sliding cap at 5)."""
        if not self._restore_pages:
            return
        if self._restore_live_tail_started:
            return
        last_page = len(self._restore_pages) - 1
        if self._restore_last_page >= last_page:
            return
        self._restore_last_page += 1
        if (
            self._restore_last_page - self._restore_first_page + 1
            > self._restore_max_window_pages
        ):
            self._restore_first_page += 1
        self._render_restore_window(scroll_to="bottom")

    def _go_restore_latest(self) -> None:
        """Jump back to the final page (or the default window at the end)."""
        if not self._restore_pages:
            return
        if self._restore_live_tail_started:
            return
        last_page = len(self._restore_pages) - 1
        window = max(1, min(self._restore_default_window_pages, self._restore_max_window_pages))
        self._restore_last_page = last_page
        self._restore_first_page = max(0, last_page - window + 1)
        # Use force-bottom so the user always lands on the latest page
        # even if they had previously scrolled up.
        self._render_restore_window(scroll_to="force_bottom")

    def _restore_next_chunk(self) -> None:
        """Legacy batched restore — no longer invoked by ``restore_from_messages``.

        Retained as a no-op for backwards compatibility with any
        external callers (e.g. older plugins) that may still trigger it
        via ``QTimer.singleShot`` callbacks scheduled before
        ``clear_chat`` ran.  The early-return at the top of this method
        ensures that, after ``clear_chat`` empties ``_pending_restore``
        and ``_restore_messages``, a late-firing callback cannot
        repopulate the chat.  New code should use
        ``restore_from_messages`` instead.
        """
        # If invoked after a clear, exit immediately.
        if not self._pending_restore or not self._restore_messages:
            return
        chunk_size = min(self._restore_chunk_size, len(self._pending_restore))
        for _ in range(chunk_size):
            if not self._pending_restore:
                break
            msg = self._pending_restore.pop(0)
            if msg.role == Role.USER:
                if _is_hidden_system_user_message(msg.content):
                    continue
                self._reset_tool_run()
                self.add_user_message(msg.content)
            elif msg.role == Role.ASSISTANT:
                self._reset_tool_run()
                if msg.content:
                    thinking_text, visible_text = _split_thinking(msg.content)

                    if thinking_text:
                        tb = _ThinkingBlock()
                        tb.set_thinking(thinking_text, in_progress=False)
                        self._insert_widget(tb)

                    w = AssistantMessageWidget()
                    w.set_text(visible_text if visible_text else msg.content)
                    self._insert_widget(w)
                else:
                    w = AssistantMessageWidget()
                    self._insert_widget(w)
                for tc in msg.tool_calls:
                    tw = ToolCallWidget(tc.name, tc.id)
                    try:
                        args_str = json.dumps(tc.arguments, indent=2)
                    except (TypeError, ValueError):
                        args_str = str(tc.arguments)
                    tw.set_arguments(args_str)
                    tw.mark_done()
                    self._tool_widgets[tc.id] = tw
                    self._register_tool_widget(tc.name, tc.id, tw)
            elif msg.role == Role.TOOL:
                self._reset_tool_run()
                for tr in msg.tool_results:
                    existing_tw = self._tool_widgets.get(tr.tool_call_id)
                    if existing_tw is not None:
                        existing_tw.set_result(tr.content, tr.is_error)
                    group = self._group_map.get(tr.tool_call_id)
                    if group:
                        group.notify_result(tr.is_error)

        if self._pending_restore:
            QTimer.singleShot(0, self._restore_next_chunk)
        else:
            self._current_assistant = None
            self._reset_tool_run()
            self._scroll_to_bottom()

    def clear_chat(self) -> None:
        # Full reset — wipes widgets AND pagination state.
        self._force_hide_thinking()
        self._thinking_hide_timer.stop()
        self._pending_restore.clear()
        self._think_buffer = ""
        self._waiting_think_close = False
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._current_assistant = None
        self._message_thinking = None
        self._tool_widgets.clear()
        self._plan_view = None
        self._reset_tool_run()
        self._group_map.clear()

        # Reset pagination state.
        self._restore_messages = []
        self._restore_units = []
        self._restore_pages = []
        self._restore_first_page = 0
        self._restore_last_page = 0
        self._restore_paged = False
        self._restore_rendered = False
        # Live-tail guard is per-restore, so a fresh restore re-enables
        # history navigation.
        self._restore_live_tail_started = False
        self._nav_widgets = []

    def _insert_widget(self, widget: QWidget) -> None:
        """Insert before the stretch at the end."""
        idx = self._layout.count() - 1
        self._layout.insertWidget(idx, widget)

    def resizeEvent(self, event) -> None:
        """Keep the container width pinned to the viewport width.

        QScrollArea.setWidgetResizable(True) handles this when there is no
        horizontal scrollbar, but QLabel rich-text word-wrap still sometimes
        requests a wider sizeHint.  Explicitly clamping here guarantees text
        wraps to the visible area.
        """
        super().resizeEvent(event)
        if self._container is not None:
            self._container.setFixedWidth(self.viewport().width())

    def _is_near_bottom(self) -> bool:
        """True if the user hasn't scrolled up (within ~60px of bottom)."""
        sb = self.verticalScrollBar()
        return sb.maximum() - sb.value() < 60

    def _scroll_to_bottom(self) -> None:
        if not self._is_near_bottom():
            return
        # Don't restart an already-running timer - Qt coalesces the start() calls
        if self._scroll_timer.isActive():
            return
        self._scroll_timer.start()

    def _force_scroll_to_bottom(self) -> None:
        """Scroll the chat to the bottom regardless of the user's scroll position.

        Used by explicit "Latest" / "Jump to bottom" actions where the
        user has indicated they want to be at the bottom even if they
        had previously scrolled up to read older messages.  Bypasses
        the ``_is_near_bottom`` guard used by passive streaming.
        """
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _do_scroll(self) -> None:
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def shutdown(self) -> None:
        self._scroll_timer.stop()
        self._thinking_hide_timer.stop()
        self._force_hide_thinking()
