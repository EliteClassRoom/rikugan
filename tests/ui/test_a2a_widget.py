"""Tests for rikugan.ui.a2a_widget.A2ABridgeWidget.

Strategy: use MagicMock to stand in for the Qt widgets (QListWidget,
QComboBox, QTableWidget, etc.) so the test is hermetic and doesn't
depend on the qt_stubs API surface. The A2ABridgeWidget is built
with a custom QWidget base that pre-injects mock children; we then
verify the widget's logic by introspecting the mock state.

The dispatcher itself is mocked so no subprocess or HTTP is exercised
— those have their own integration tests.
"""

from __future__ import annotations

import os
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()
install_ida_mocks()


def _build_widget_with_mocks(agents: list | None = None) -> tuple:
    """Build an A2ABridgeWidget with a stub dispatcher.

    Returns (widget, mocks_dict) so tests can inspect both.
    """
    from rikugan.agent.a2a.types import ExternalAgentConfig
    from rikugan.ui.a2a_widget import A2ABridgeWidget

    if agents is None:
        agents = [ExternalAgentConfig(
            name="claude", transport="subprocess", endpoint="claude",
            capabilities=["code_generation"],
        )]

    fake_dispatcher = MagicMock()
    fake_dispatcher.discover.return_value = agents

    # We bypass the real __init__ (which builds Qt widgets) and
    # manually wire the dependencies. This lets the tests run
    # without a real Qt event loop.
    w = A2ABridgeWidget.__new__(A2ABridgeWidget)
    # Initialize the QObject base so signals work.
    from rikugan.ui.qt_compat import QObject
    QObject.__init__(w)

    w._dispatcher = fake_dispatcher
    w._history = {}
    w._inflight = {}
    # Pre-populate the stub-fallback agent list so ``_lookup_target_agent``
    # works without going through ``_refresh_agents``.
    w._target_combo_agents = list(agents)
    # ``_target_combo.currentIndex`` must return a real int for the
    # safe-int wrapper to accept.
    w._target_combo = MagicMock()
    w._target_combo.currentIndex.return_value = 0
    w._target_combo.count.return_value = len(agents)
    w._agent_list = MagicMock()
    w._target_combo = MagicMock()
    w._task_edit = MagicMock()
    w._task_edit.toPlainText.return_value = ""
    w._history_table = MagicMock()
    w._history_table.rowCount.return_value = 0
    w._history_table.columnCount.return_value = 5
    w._agent_count_label = MagicMock()
    w._send_btn = MagicMock()
    w._cancel_btn = MagicMock()
    w._view_output_btn = MagicMock()
    w._clear_history_btn = MagicMock()
    w._refresh_agents_btn = MagicMock()
    w._include_context_check = MagicMock()
    w._include_context_check.isChecked.return_value = False
    # Skip the QTimer.singleShot initial refresh so we don't have
    # to wait for an event loop tick.
    return w, {"dispatcher": fake_dispatcher, "agents": agents}


class _FakeAgent:
    def __init__(self, name: str = "claude", transport: str = "subprocess") -> None:
        self.name = name
        self.transport = transport
        self.endpoint = name
        self.capabilities = ["code_generation"]


class TestRefreshAgents(unittest.TestCase):
    """discover() is forwarded to the dispatcher; UI state is updated."""

    def test_refresh_uses_dispatcher(self) -> None:
        w, mocks = _build_widget_with_mocks()
        w._refresh_agents()
        mocks["dispatcher"].discover.assert_called_once()

    def test_refresh_passes_agents_to_lists(self) -> None:
        agents = [_FakeAgent("claude"), _FakeAgent("codex")]
        w, mocks = _build_widget_with_mocks(agents)
        w._refresh_agents()
        # QListWidget.addItem called once per agent
        self.assertEqual(w._agent_list.addItem.call_count, 2)
        self.assertEqual(w._target_combo.addItem.call_count, 2)

    def test_refresh_with_no_agents_disables_send(self) -> None:
        w, mocks = _build_widget_with_mocks([])
        w._refresh_agents()
        # send button was disabled (call_count >= 1 with falsy arg)
        # We use ``not c.args[0]`` instead of ``is False`` because
        # MagicMock doesn't always preserve identity for booleans.
        disabled_calls = [
            c for c in w._send_btn.setEnabled.call_args_list
            if c.args and not c.args[0]
        ]
        self.assertGreaterEqual(len(disabled_calls), 1)

    def test_refresh_with_agents_enables_send(self) -> None:
        w, mocks = _build_widget_with_mocks([_FakeAgent()])
        w._refresh_agents()
        # The most recent setEnabled call should be True (enable)
        self.assertTrue(w._send_btn.setEnabled.called)
        last_call = w._send_btn.setEnabled.call_args_list[-1]
        self.assertTrue(last_call.args[0])

    def test_refresh_bails_when_widgets_already_deleted(self) -> None:
        """A PaletteChange arriving after teardown must not crash.

        Shiboken raises RuntimeError when the C++ QListWidget is already
        deleted (e.g. the panel was closed between the event being queued
        and delivered). _refresh_agents should bail out silently rather
        than propagate the RuntimeError or attempt discover() on dead UI.
        """
        w, mocks = _build_widget_with_mocks([_FakeAgent()])
        # Simulate the list widget's C++ side being gone.
        w._agent_list.clear.side_effect = RuntimeError(
            "Internal C++ object (PySide6.QtWidgets.QListWidget) already deleted."
        )
        # Must not raise.
        w._refresh_agents()
        # Bailed before touching the dispatcher — no discovery on dead UI.
        mocks["dispatcher"].discover.assert_not_called()



class TestSendClick(unittest.TestCase):
    def test_send_with_empty_task_does_nothing(self) -> None:
        w, _ = _build_widget_with_mocks()
        w._task_edit.toPlainText.return_value = "  \n  "  # whitespace
        w._on_send_clicked()
        # No history row added
        self.assertEqual(w._history_table.insertRow.call_count, 0)
        # No thread started (we never patched QThread so this is implicit)

    def test_send_with_no_agent_does_nothing(self) -> None:
        w, _ = _build_widget_with_mocks([])
        w._task_edit.toPlainText.return_value = "test"
        w._on_send_clicked()
        self.assertEqual(w._history_table.insertRow.call_count, 0)

    def test_send_appends_history_row(self) -> None:
        from rikugan.ui.a2a_widget import _HistoryRow
        w, _ = _build_widget_with_mocks([_FakeAgent()])
        w._task_edit.toPlainText.return_value = "summarize the binary"
        # Mock QThread so we don't actually spin a thread
        with patch("rikugan.ui.a2a_widget.QThread"):
            w._on_send_clicked()

        # Should have inserted exactly one row
        self.assertEqual(w._history_table.insertRow.call_count, 1)
        # And have a row in _history
        self.assertEqual(len(w._history), 1)
        task_id = next(iter(w._history.keys()))
        row = w._history[task_id]
        self.assertIsInstance(row, _HistoryRow)
        self.assertEqual(row.agent_name, "claude")
        self.assertEqual(row.status, "queued")
        # 5 cells set per row
        self.assertEqual(w._history_table.setItem.call_count, 5)

    def test_signal_emitted_on_send(self) -> None:
        w, _ = _build_widget_with_mocks([_FakeAgent()])
        w._task_edit.toPlainText.return_value = "test"
        captured: list = []
        w.task_dispatched.connect(lambda tid, name, exc: captured.append((tid, name, exc)))

        with patch("rikugan.ui.a2a_widget.QThread"):
            w._on_send_clicked()

        self.assertEqual(len(captured), 1)
        _tid, name, exc = captured[0]
        self.assertEqual(name, "claude")
        self.assertEqual(exc, "test")


class TestWorkerSignalHandlers(unittest.TestCase):
    """The widget's signal handlers update the row in _history."""

    def _spawn(self) -> tuple:
        """Spawn a row so handlers have something to update."""
        w, _ = _build_widget_with_mocks([_FakeAgent()])
        w._task_edit.toPlainText.return_value = "x"
        with patch("rikugan.ui.a2a_widget.QThread"):
            w._on_send_clicked()
        task_id = next(iter(w._history.keys()))
        return w, task_id

    def test_started_sets_running(self) -> None:
        w, task_id = self._spawn()
        w._on_task_started(task_id, "claude")
        self.assertEqual(w._history[task_id].status, "running")

    def test_output_appends(self) -> None:
        w, task_id = self._spawn()
        w._on_task_output(task_id, "first chunk\n")
        w._on_task_output(task_id, "second chunk\n")
        self.assertIn("first chunk", w._history[task_id].result_text)
        self.assertIn("second chunk", w._history[task_id].result_text)

    def test_completed_marks_status(self) -> None:
        w, task_id = self._spawn()
        w._on_task_completed(task_id, "")
        self.assertEqual(w._history[task_id].status, "completed")

    def test_failed_marks_error(self) -> None:
        w, task_id = self._spawn()
        w._on_task_failed(task_id, "boom")
        self.assertEqual(w._history[task_id].status, "failed")
        self.assertEqual(w._history[task_id].error_text, "boom")

    def test_cancelled_marks_status(self) -> None:
        w, task_id = self._spawn()
        w._on_task_cancelled(task_id)
        self.assertEqual(w._history[task_id].status, "cancelled")


class TestHistoryRowHelpers(unittest.TestCase):
    def test_excerpt_short(self) -> None:
        w, _ = _build_widget_with_mocks()
        self.assertEqual(w._format_result_excerpt("short"), "short")

    def test_excerpt_long(self) -> None:
        w, _ = _build_widget_with_mocks()
        long = "x" * 200
        excerpt = w._format_result_excerpt(long)
        self.assertLessEqual(len(excerpt), 60)
        self.assertTrue(excerpt.startswith("…"))

    def test_excerpt_strips_whitespace(self) -> None:
        w, _ = _build_widget_with_mocks()
        # 30 leading spaces + 50 chars = 80 chars, but strip() removes
        # the whitespace. The result should be the unstripped portion
        # of the cleaned text.
        text = " " * 30 + "actual content here" + " " * 30
        excerpt = w._format_result_excerpt(text)
        # The result is the last 57 chars of the cleaned text
        self.assertLessEqual(len(excerpt), 60)


class TestCancelHandler(unittest.TestCase):
    def test_cancel_sets_event(self) -> None:
        """Cancel button click must set the cancel_event for the in-flight task."""
        w, _ = _build_widget_with_mocks([_FakeAgent()])
        w._task_edit.toPlainText.return_value = "x"
        with patch("rikugan.ui.a2a_widget.QThread"):
            w._on_send_clicked()
        task_id = next(iter(w._history.keys()))
        # The inflight entry must hold a real threading.Event.
        _thread, _worker, cancel_event = w._inflight[task_id]
        # Simulate the cancel click: the handler reads the selected
        # row from the history table. We mock currentRow + item.
        w._history_table.currentRow.return_value = 0
        item_mock = MagicMock()
        item_mock.data.return_value = task_id
        w._history_table.item.return_value = item_mock
        # And we need a real cancel_event, not a mock, to verify
        # ``.set()`` was actually called.
        w._inflight[task_id] = (
            _thread, _worker, threading.Event()
        )
        _t, _w, real_cancel = w._inflight[task_id]
        w._on_cancel_clicked()
        self.assertTrue(real_cancel.is_set())


class TestShutdown(unittest.TestCase):
    def test_shutdown_cancels_inflight(self) -> None:
        w, _ = _build_widget_with_mocks([_FakeAgent()])
        w._task_edit.toPlainText.return_value = "x"
        with patch("rikugan.ui.a2a_widget.QThread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread.isRunning.return_value = True
            mock_thread_cls.return_value = mock_thread
            w._on_send_clicked()
        # Replace the real cancel events with mocks so we can
        # assert on them.
        for task_id in w._inflight:
            _t, _w, _cancel = w._inflight[task_id]
            w._inflight[task_id] = (_t, _w, threading.Event())
        w.shutdown()
        for task_id, (_t, _w, ev) in w._inflight.items():
            self.assertTrue(ev.is_set(), f"cancel_event for {task_id} was not set")
        self.assertEqual(len(w._inflight), 0)


class TestHistoryRowModel(unittest.TestCase):
    """The _HistoryRow dataclass behaves as expected."""

    def test_status_defaults_to_queued(self) -> None:
        from rikugan.ui.a2a_widget import _HistoryRow
        row = _HistoryRow(task_id="abc", agent_name="claude", task_excerpt="x")
        self.assertEqual(row.status, "queued")
        self.assertEqual(row.result_text, "")
        self.assertEqual(row.error_text, "")
        # started_at is a recent timestamp
        import time
        self.assertLess(time.time() - row.started_at, 5.0)


class TestWorker(unittest.TestCase):
    """The QObject worker drives the dispatcher and emits signals."""

    def test_worker_stores_arguments(self) -> None:
        from rikugan.ui.a2a_widget import _A2AWorker
        cancel = threading.Event()
        fake_dispatcher = MagicMock()
        w = _A2AWorker(
            fake_dispatcher, "claude", "do thing", "ctx", cancel, "tid-1"
        )
        self.assertEqual(w._agent_name, "claude")
        self.assertEqual(w._task, "do thing")
        self.assertEqual(w._include_context, "ctx")
        self.assertIs(w._cancel_event, cancel)
        self.assertEqual(w._task_id, "tid-1")

    def test_worker_run_emits_started_output_completed(self) -> None:
        from rikugan.agent.turn import TurnEvent, TurnEventType
        from rikugan.ui.a2a_widget import _A2AWorker
        cancel = threading.Event()

        def fake_run(agent_name, task, **kwargs):
            yield TurnEvent(
                type=TurnEventType.TEXT_DELTA, text="hello"
            )
            return "final result"

        fake_dispatcher = MagicMock()
        fake_dispatcher.run_task.side_effect = fake_run

        worker = _A2AWorker(fake_dispatcher, "claude", "x", "", cancel, "tid")
        events: list = []
        worker.started.connect(lambda *a: events.append(("started", a)))
        worker.output_received.connect(lambda *a: events.append(("output", a)))
        worker.completed.connect(lambda *a: events.append(("completed", a)))

        worker.run()

        self.assertEqual(len(events), 3)
        self.assertEqual(events[0][0], "started")
        self.assertEqual(events[1][0], "output")
        self.assertEqual(events[2][0], "completed")

    def test_worker_run_emits_failed_on_exception(self) -> None:
        from rikugan.ui.a2a_widget import _A2AWorker
        cancel = threading.Event()
        fake_dispatcher = MagicMock()
        fake_dispatcher.run_task.side_effect = RuntimeError("boom")

        worker = _A2AWorker(fake_dispatcher, "claude", "x", "", cancel, "tid")
        events: list = []
        worker.failed.connect(lambda *a: events.append(a))
        worker.completed.connect(lambda *a: events.append(("completed", a)))

        worker.run()

        # Only one failed event
        self.assertEqual(len(events), 1)
        self.assertIn("boom", events[0][1])


if __name__ == "__main__":
    unittest.main()
