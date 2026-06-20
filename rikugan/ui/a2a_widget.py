"""A2ABridgeWidget — Qt UI for delegating tasks to external agents.

Mirrors the design in AGENTS.md: a 3-pane widget (Available Agents,
Delegate Task form, Task History table) that lets the user browse
auto-discovered + user-configured agents, send a task, and review
the streamed output. The widget is hosted in the existing
``RikuganPanelCore`` and runs alongside the chat tabs.

Threading: every delegation runs in its own ``QThread`` (one thread
per task, not a shared pool) so a long-running subprocess call
doesn't block the UI. The thread yields events via Qt signals;
the widget's main thread connects those to UI updates. Cancellation
is done by a ``threading.Event`` that the worker polls between
subprocess stdout lines (subprocess transport) or A2A status
checks (a2a transport).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..agent.a2a import A2ADispatcher
from ..agent.turn import TurnEventType
from .qt_compat import (
    QCheckBox,
    QComboBox,
    QEvent,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QObject,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
)

# ---------------------------------------------------------------------------
# Background worker — runs the dispatcher in a separate thread
# ---------------------------------------------------------------------------


class _A2AWorker(QObject):
    """QObject worker that drives an A2ADispatcher.run_task iteration.

    Lives in a worker QThread. Emits Qt signals (one per dispatcher
    event) so the main thread can update widgets safely without
    cross-thread Qt access.

    Why one worker per task (not a shared pool): the dispatcher
    cooperates with the caller's event loop via ``yield from``, so
    a single ``run_task`` IS a coroutine. Running multiple in one
    thread would interleave events and complicate the UI mapping
    back to rows. One thread per task is simpler at the cost of a
    few extra threads (most users won't fire 5+ concurrent
    delegations).
    """

    # signal: task_id, agent_name
    started = Signal(str, str)
    # signal: task_id, text
    output_received = Signal(str, str)
    # signal: task_id, result_text
    completed = Signal(str, str)
    # signal: task_id, error_message
    failed = Signal(str, str)
    # signal: task_id
    cancelled = Signal(str)

    def __init__(
        self,
        dispatcher: A2ADispatcher,
        agent_name: str,
        task: str,
        include_context: str,
        cancel_event: Any,  # threading.Event
        task_id: str,
    ) -> None:
        super().__init__()
        self._dispatcher = dispatcher
        self._agent_name = agent_name
        self._task = task
        self._include_context = include_context
        self._cancel_event = cancel_event
        self._task_id = task_id

    def run(self) -> None:
        """Drive the dispatcher's generator. Emits signals as we go."""
        self.started.emit(self._task_id, self._agent_name)
        try:
            for event in self._dispatcher.run_task(
                self._agent_name,
                self._task,
                cancel_event=self._cancel_event,
                include_context=self._include_context,
            ):
                if event.type == TurnEventType.TEXT_DELTA:
                    self.output_received.emit(self._task_id, event.text or "")
                elif event.type == TurnEventType.ERROR:
                    self.failed.emit(self._task_id, event.error or "External agent error")
                    return
        except Exception as e:
            self.failed.emit(self._task_id, f"Worker exception: {e}")
            return

        # The dispatcher's run_task returns the aggregated result as
        # the generator's return value. We don't have a direct hook
        # to retrieve it, so we rely on the worker to keep a copy
        # via the started/output/completed signal stream. To keep
        # the contract simple, the widget reads the final text from
        # the last output_received emission.
        self.completed.emit(self._task_id, "")


# ---------------------------------------------------------------------------
# History row model — kept as a dict, not a dataclass, to avoid
# thread-safety concerns with Qt row reads from the main thread.
# ---------------------------------------------------------------------------


class _HistoryRow:
    """Lightweight record for one delegation row in the history table."""

    __slots__ = (
        "agent_name",
        "error_text",
        "result_text",
        "started_at",
        "status",
        "task_excerpt",
        "task_id",
    )

    def __init__(
        self,
        task_id: str,
        agent_name: str,
        task_excerpt: str,
    ) -> None:
        self.task_id = task_id
        self.agent_name = agent_name
        self.task_excerpt = task_excerpt
        self.status = "queued"
        self.started_at = time.time()
        self.result_text = ""
        self.error_text = ""


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------


class A2ABridgeWidget(QWidget):
    """3-pane Qt widget: agents, delegate form, task history.

    Signals:
        task_dispatched: emitted when a new delegation starts.
            Args: task_id (str), agent_name (str), task_excerpt (str)
    """

    task_dispatched = Signal(str, str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("a2a_bridge_widget")

        # One dispatcher shared across this widget's lifetime. The
        # registry is cached on first ``discover()`` so the agents
        # list only does the heavy work once.
        self._dispatcher = A2ADispatcher()

        # task_id → _HistoryRow (only main thread reads/writes)
        self._history: dict[str, _HistoryRow] = {}

        # task_id → (QThread, _A2AWorker, threading.Event). We hold
        # a strong reference to the thread so it isn't GC'd mid-run.
        # ``cancel_event`` is the worker's cancel flag.
        self._inflight: dict[str, tuple[QThread, _A2AWorker, Any]] = {}

        # Top-level layout
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        root.addWidget(self._build_agents_pane(), stretch=1)
        root.addWidget(self._build_delegate_pane(), stretch=2)
        root.addWidget(self._build_history_pane(), stretch=3)

        # Initial population: discover agents now so the list is
        # populated before the user clicks anything.
        QTimer.singleShot(0, self._refresh_agents)

    # -- Pane builders -------------------------------------------------------

    def _build_agents_pane(self) -> QGroupBox:
        """Top: list of discovered external agents + refresh button."""
        box = QGroupBox("Available Agents")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._agent_list = QListWidget()
        self._agent_list.setAlternatingRowColors(True)
        # ``QListWidget`` is a subclass of ``QAbstractItemView``; we
        # reference the enum via the base class because the qt_stubs
        # attach ``SelectionMode`` there (consistent with agent_tree.py
        # and bulk_renamer.py).
        self._agent_list.setSelectionMode(
            __import__(
                "rikugan.ui.qt_compat", fromlist=["QAbstractItemView"]
            ).QAbstractItemView.SelectionMode.SingleSelection
        )
        _safe_connect(self._agent_list, "itemDoubleClicked", self._on_agent_double_clicked)
        layout.addWidget(self._agent_list, 1)

        bar = QHBoxLayout()
        self._refresh_agents_btn = QPushButton("Refresh")
        self._refresh_agents_btn.setToolTip("Re-scan PATH for claude / codex and reload orchestra.toml")
        _safe_connect(self._refresh_agents_btn, "clicked", self._refresh_agents)
        bar.addWidget(self._refresh_agents_btn)
        self._agent_count_label = QLabel("0 agents")
        # Right-align the count label so it pushes against the
        # right edge of the agents pane. The qt_stubs' QLabel doesn't
        # expose ``alignment()`` as a getter, so we set it directly
        # with the Qt.AlignRight flag (0x0080).
        self._agent_count_label.setAlignment(0x0080)
        bar.addWidget(self._agent_count_label, 1)
        layout.addLayout(bar)
        return box

    def _build_delegate_pane(self) -> QGroupBox:
        """Middle: target agent selector + task text + context toggle + send."""
        box = QGroupBox("Delegate Task")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Agent picker
        agent_row = QHBoxLayout()
        agent_row.addWidget(QLabel("Target:"))
        self._target_combo = QComboBox()
        # ``setSizePolicy`` isn't in the qt_stubs; use _safe_call to
        # skip in test environments.
        _safe_call(
            self._target_combo,
            "setSizePolicy",
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        agent_row.addWidget(self._target_combo, 1)
        layout.addLayout(agent_row)

        # Task text
        self._task_edit = QPlainTextEdit()
        self._task_edit.setPlaceholderText(
            "Describe what the external agent should do. Be specific — the external agent has no Rikugan tool access."
        )
        self._task_edit.setMinimumHeight(80)
        layout.addWidget(self._task_edit, 1)

        # Options
        opt_row = QHBoxLayout()
        self._include_context_check = QCheckBox("Include current binary context")
        # Disabled: the widget used to forward a "not implemented"
        # placeholder string instead of real binary context, which
        # silently misled users (the external agent answered with no
        # context). Leave the control visible-but-off with an honest
        # tooltip until the dispatcher path that injects real context
        # is wired in. See C5 / Phase 2.
        self._include_context_check.setEnabled(False)
        self._include_context_check.setChecked(False)
        self._include_context_check.setToolTip(
            "Not available yet — binary-context injection for external agents "
            "is planned for a future release. Describe the relevant context in "
            "the task text for now."
        )
        opt_row.addWidget(self._include_context_check)
        opt_row.addStretch(1)
        self._send_btn = QPushButton("Send Task")
        self._send_btn.setDefault(True)
        _safe_connect(self._send_btn, "clicked", self._on_send_clicked)
        opt_row.addWidget(self._send_btn)
        layout.addLayout(opt_row)
        return box

    def _build_history_pane(self) -> QGroupBox:
        """Bottom: history of past + in-flight delegations."""
        box = QGroupBox("Task History")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._history_table = QTableWidget(0, 5)
        self._history_table.setHorizontalHeaderLabels(["Time", "Agent", "Task", "Status", "Result"])
        # Same QAbstractItemView-via-base-class trick for the
        # ``SelectionBehavior`` and ``EditTrigger`` enums. The qt_stubs
        # only attach them to the base class.
        _abstract = __import__("rikugan.ui.qt_compat", fromlist=["QAbstractItemView"]).QAbstractItemView
        self._history_table.setSelectionBehavior(_abstract.SelectionBehavior.SelectRows)
        self._history_table.setEditTriggers(_abstract.EditTrigger.NoEditTriggers)
        self._history_table.verticalHeader().setVisible(False)
        # Stretch the Result column so long outputs are readable.
        header = self._history_table.horizontalHeader()
        # Use _safe_call because QHeaderView.ResizeMode is not in the
        # qt_stubs. In real Qt this sets the column to ResizeToContents
        # (0) or Stretch (1).
        for col in range(5):
            mode = 1 if col in (2, 4) else 0  # Stretch for Task/Result
            _safe_call(header, "setSectionResizeMode", col, mode)
        layout.addWidget(self._history_table, 1)

        bar = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel Selected")
        self._cancel_btn.setEnabled(False)
        _safe_connect(self._cancel_btn, "clicked", self._on_cancel_clicked)
        bar.addWidget(self._cancel_btn)
        self._view_output_btn = QPushButton("View Output")
        self._view_output_btn.setEnabled(False)
        _safe_connect(self._view_output_btn, "clicked", self._on_view_output_clicked)
        bar.addWidget(self._view_output_btn)
        bar.addStretch(1)
        self._clear_history_btn = QPushButton("Clear")
        _safe_connect(self._clear_history_btn, "clicked", self._on_clear_history_clicked)
        bar.addWidget(self._clear_history_btn)
        layout.addLayout(bar)
        return box

    # -- Agent list management -----------------------------------------------

    def _refresh_agents(self) -> None:
        """Re-run discovery and rebuild the agent list widgets.

        Bail out silently if the underlying Qt widgets were already deleted
        (e.g. a PaletteChange arriving after the panel was torn down) —
        Shiboken raises ``RuntimeError`` on access to a deleted C++ object.
        """
        try:
            self._agent_list.clear()
            self._target_combo.clear()
        except RuntimeError:
            return
        agents = self._dispatcher.discover()
        for agent in agents:
            label = f"{agent.name}  ({agent.transport})"
            list_item = QListWidgetItem(label)
            list_item.setData(0x0100, agent)  # Qt.UserRole — store the config
            self._agent_list.addItem(list_item)
            # ``addItem(label, userData=agent)`` is the Qt 5+ form.
            # The qt_stubs only support the no-kwarg form, so use
            # the positional variant and ``setData`` to attach the
            # agent config to the item afterward.
            try:
                self._target_combo.addItem(label, agent)
            except TypeError:
                self._target_combo.addItem(label)
                # Attach the agent to the last-added item via
                # Qt.UserRole. The combo's ``itemData(i)`` won't
                # return it under this fallback — use
                # ``_target_combo_agents[i]`` for lookup. (See
                # _lookup_target_agent.)
                if not hasattr(self, "_target_combo_agents"):
                    self._target_combo_agents = []
                self._target_combo_agents.append(agent)

        count = len(agents)
        self._agent_count_label.setText(f"{count} agent{'s' if count != 1 else ''}")
        self._send_btn.setEnabled(count > 0)

    def _on_agent_double_clicked(self, item: QListWidgetItem) -> None:
        """Double-click selects the same agent in the delegate combo."""
        agent = item.data(0x0100)
        if agent is None:
            return
        for i in range(self._target_combo.count()):
            if self._lookup_target_agent(i) is agent:
                self._target_combo.setCurrentIndex(i)
                return

    def _lookup_target_agent(self, index: int | None = None) -> Any:
        """Return the ExternalAgentConfig for the selected (or given) combo row.

        Tries the Qt-native ``currentData``/``itemData`` first
        (real Qt path). Falls back to ``_target_combo_agents`` if
        the qt_stubs don't support userData on QComboBox.addItem.
        Returns ``None`` for an empty combo.
        """
        # First try the stub-fallback list which we maintain
        # ourselves. This works in BOTH real Qt and stubbed env
        # because we populate it in _refresh_agents as a safety net.
        agents = getattr(self, "_target_combo_agents", [])
        if agents:
            if index is not None:
                if 0 <= index < len(agents):
                    return agents[index]
                return None
            # Selected index
            i = self._safe_int(self._target_combo.currentIndex(), default=0)
            if 0 <= i < len(agents):
                return agents[i]
            return None
        # No fallback list — try real Qt
        count = self._safe_int(getattr(self._target_combo, "count", lambda: 0)(), default=-1)
        if count <= 0:
            return None
        i = index if index is not None else self._safe_int(self._target_combo.currentIndex(), default=0)
        if i < 0 or i >= count:
            return None
        try:
            return self._target_combo.itemData(i)
        except (TypeError, AttributeError):
            return None

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Coerce a value to int, falling back if it's a MagicMock or non-int."""
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return default

    # -- Send / cancel handlers ---------------------------------------------

    def _on_send_clicked(self) -> None:
        """Spawn a worker thread for the selected agent + task."""
        agent = self._lookup_target_agent()
        task_text = self._task_edit.toPlainText().strip()
        if agent is None:
            return
        if not task_text:
            self._task_edit.setFocus()
            return

        # Binary-context inclusion is disabled in the UI (checkbox is
        # off + unclickable) until the dispatcher path that injects
        # real context is wired in. Forwarding the checkbox state here
        # would previously send a misleading "not implemented"
        # placeholder to the external agent; we send no prefix until
        # the feature ships.
        context_prefix = ""

        task_id = uuid.uuid4().hex[:12]
        row = _HistoryRow(
            task_id=task_id,
            agent_name=agent.name,
            task_excerpt=task_text[:60] + ("…" if len(task_text) > 60 else ""),
        )
        self._history[task_id] = row
        self._append_history_row(row)

        # Build cancel event + thread + worker.
        import threading

        cancel_event = threading.Event()
        worker = _A2AWorker(
            self._dispatcher,
            agent.name,
            task_text,
            context_prefix,
            cancel_event,
            task_id,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        worker.started.connect(self._on_task_started)
        worker.output_received.connect(self._on_task_output)
        worker.completed.connect(self._on_task_completed)
        worker.failed.connect(self._on_task_failed)
        worker.cancelled.connect(self._on_task_cancelled)

        # Cleanup when the thread finishes. We use a single-shot
        # connection on ``thread.finished`` so we don't leak refs
        # — when the thread quits, both the worker and the cancel
        # event can be released.
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._inflight[task_id] = (thread, worker, cancel_event)
        thread.start()

        self.task_dispatched.emit(task_id, agent.name, row.task_excerpt)

    def _on_cancel_clicked(self) -> None:
        """Cancel the currently selected in-flight task."""
        row_idx = self._history_table.currentRow()
        if row_idx < 0:
            return
        task_id_item = self._history_table.item(row_idx, 0)
        if task_id_item is None:
            return
        # We stashed the task_id in the first cell's ToolTip rather
        # than the visible Time text. See ``_append_history_row``.
        task_id = task_id_item.data(0x0101)  # Qt.UserRole + 1
        inflight = self._inflight.get(task_id)
        if inflight is None:
            return
        _thread, _worker, cancel_event = inflight
        cancel_event.set()

    def _on_view_output_clicked(self) -> None:
        """Open a read-only dialog with the selected row's full output."""
        row_idx = self._history_table.currentRow()
        if row_idx < 0:
            return
        task_id = self._history_table.item(row_idx, 0).data(0x0101)
        row = self._history.get(task_id)
        if row is None:
            return
        # Try the rich dialog first; fall back to a plain message
        # box. ``_OutputDialog`` lives in message_widgets and is the
        # same widget the chat view uses for tool results, so output
        # formatting is consistent across the app.
        try:
            from .message_widgets import _OutputDialog  # local import to avoid cycle

            dlg = _OutputDialog(row.agent_name, row.task_excerpt, row.result_text, self)
            dlg.exec()
            return
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QMessageBox  # type: ignore[import-not-found]

            box = QMessageBox(self)
            box.setWindowTitle(f"{row.agent_name} — output")
            box.setText(row.result_text or row.error_text or "(no output)")
            box.exec()
        except Exception:
            pass

    def _on_clear_history_clicked(self) -> None:
        """Drop completed/failed rows from the table. In-flight rows stay."""
        for task_id in list(self._history.keys()):
            if task_id not in self._inflight:
                del self._history[task_id]
        self._rebuild_history_table()

    # -- Worker signal handlers (main thread) --------------------------------

    def _on_task_started(self, task_id: str, agent_name: str) -> None:
        row = self._history.get(task_id)
        if row is None:
            return
        row.status = "running"
        self._update_row_status(row)

    def _on_task_output(self, task_id: str, text: str) -> None:
        """Append a chunk of output to the row's result text + result column."""
        row = self._history.get(task_id)
        if row is None:
            return
        row.result_text += text
        # Update only the result column to avoid scroll jumping.
        row_idx = self._find_row_index(task_id)
        if row_idx >= 0:
            self._history_table.item(row_idx, 4).setText(self._format_result_excerpt(row.result_text))

    def _on_task_completed(self, task_id: str, _result_text: str) -> None:
        """Task finished successfully."""
        row = self._history.get(task_id)
        if row is None:
            return
        row.status = "completed"
        self._update_row_status(row)
        # The cancel button must be re-evaluated — the task is no
        # longer cancellable.
        self._refresh_button_states()

    def _on_task_failed(self, task_id: str, error: str) -> None:
        row = self._history.get(task_id)
        if row is None:
            return
        row.status = "failed"
        row.error_text = error
        row.result_text = error
        self._update_row_status(row)
        self._refresh_button_states()

    def _on_task_cancelled(self, task_id: str) -> None:
        row = self._history.get(task_id)
        if row is None:
            return
        row.status = "cancelled"
        self._update_row_status(row)
        self._refresh_button_states()

    def _on_thread_finished(self) -> None:
        """Called when any inflight thread quits. Cleans up refs.

        QThread.finished doesn't carry the task_id, so we walk the
        inflight map and drop any threads that aren't running. A
        small leak: if a thread was already removed from ``_inflight``
        we miss it. The leak is bounded by the test's lifetime —
        Python refcount reclaims it as soon as the worker is GC'd.
        """
        for task_id in list(self._inflight.keys()):
            thread, _worker, _cancel = self._inflight[task_id]
            if not thread.isRunning():
                del self._inflight[task_id]

    # -- Table helpers -------------------------------------------------------

    def _append_history_row(self, row: _HistoryRow) -> None:
        """Insert a new row at the bottom. Stash task_id in cell 0's UserRole+1."""
        self._history_table.insertRow(self._history_table.rowCount())
        row_idx = self._history_table.rowCount() - 1
        # Time column shows wall clock + stashes task_id in Qt.UserRole+1
        # so cancel / view handlers can find the row.
        time_item = QTableWidgetItem(time.strftime("%H:%M:%S", time.localtime(row.started_at)))
        time_item.setData(0x0101, row.task_id)  # Qt.UserRole + 1
        self._history_table.setItem(row_idx, 0, time_item)
        self._history_table.setItem(row_idx, 1, QTableWidgetItem(row.agent_name))
        self._history_table.setItem(row_idx, 2, QTableWidgetItem(row.task_excerpt))
        self._history_table.setItem(row_idx, 3, QTableWidgetItem(row.status))
        self._history_table.setItem(row_idx, 4, QTableWidgetItem(""))

    def _update_row_status(self, row: _HistoryRow) -> None:
        row_idx = self._find_row_index(row.task_id)
        if row_idx < 0:
            return
        status_item = self._history_table.item(row_idx, 3)
        status_item.setText(row.status)
        # Light status coloring: green/grey/red. Wrapped in try/except
        # so the stub environment (which doesn't have QColor) doesn't
        # break the test.
        try:
            from PySide6.QtGui import QColor  # type: ignore[import-not-found]

            if row.status == "completed":
                status_item.setForeground(QColor("#3fb950"))
            elif row.status == "failed":
                status_item.setForeground(QColor("#f85149"))
            elif row.status == "cancelled":
                status_item.setForeground(QColor("#d29922"))
            else:
                status_item.setForeground(QColor("#8b949e"))
        except Exception:
            pass

    def _find_row_index(self, task_id: str) -> int:
        # ``rowCount`` may return a MagicMock in tests; coerce to int
        # and clamp at 0 to avoid TypeError on ``range()``.
        n = self._safe_int(self._history_table.rowCount(), default=0)
        for i in range(n):
            item = self._history_table.item(i, 0)
            if item is not None and item.data(0x0101) == task_id:
                return i
        return -1

    def _format_result_excerpt(self, text: str) -> str:
        """Last 60 chars of the result text for the table cell."""
        text = text.strip()
        if len(text) <= 60:
            return text
        return "…" + text[-57:]

    def _rebuild_history_table(self) -> None:
        """Clear the table and re-add all rows from ``_history``."""
        self._history_table.setRowCount(0)
        for row in self._history.values():
            self._append_history_row(row)

    def _refresh_button_states(self) -> None:
        """Enable cancel only if there's an in-flight task selected."""
        row_idx = self._safe_int(self._history_table.currentRow(), default=-1)
        if row_idx < 0:
            self._cancel_btn.setEnabled(False)
            self._view_output_btn.setEnabled(False)
            return
        task_id = self._history_table.item(row_idx, 0).data(0x0101)
        in_flight = task_id in self._inflight
        self._cancel_btn.setEnabled(in_flight)
        self._view_output_btn.setEnabled(task_id in self._history)

    def changeEvent(self, event: QEvent) -> None:
        """Re-render agent list when the host theme flips — keeps colours consistent."""
        if event.type() == QEvent.Type.PaletteChange:
            self._refresh_agents()
        super().changeEvent(event)

    # -- Cleanup ------------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel all in-flight tasks and wait briefly for threads to exit."""
        for _task_id, (_thread, _worker, cancel_event) in self._inflight.items():
            cancel_event.set()
        for task_id, (thread, _worker, _cancel) in list(self._inflight.items()):
            thread.quit()
            thread.wait(2000)  # 2s grace
            del self._inflight[task_id]


__all__ = ["A2ABridgeWidget"]


def _safe_connect(signal_owner: Any, signal_name: str, slot: Any) -> bool:
    """Connect a Qt signal if it exists; silently no-op otherwise.

    The qt_stubs used in unit tests do not implement Qt signals
    (no ``itemDoubleClicked`` on QListWidget, no ``valueChanged`` on
    QSpinBox, etc.). Wrapping every ``.connect`` in a try/except
    would clutter the widget; this helper keeps the call sites clean
    while letting the widget still build in stubbed environments.
    Returns True if the connection was made, False if the signal
    was missing.
    """
    try:
        signal = getattr(signal_owner, signal_name)
    except AttributeError:
        return False
    try:
        signal.connect(slot)
        return True
    except Exception:
        return False


def _safe_call(obj: Any, method_name: str, *args: Any, **kwargs: Any) -> bool:
    """Call a Qt method if it exists; silently no-op otherwise.

    The qt_stubs only implement a subset of the real Qt API
    (e.g. ``QComboBox.setSizePolicy`` is missing). Calling these
    methods on a stub raises ``AttributeError``. This helper
    lets the widget degrade gracefully when the method isn't
    available in the test environment.
    """
    try:
        method = getattr(obj, method_name)
    except AttributeError:
        return False
    try:
        method(*args, **kwargs)
        return True
    except Exception:
        return False
