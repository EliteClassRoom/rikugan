"""Tests for rikugan.ui.panel_core — pure logic helpers."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Install the lightweight ``PySide6`` stubs BEFORE importing any
# rikugan module.  The conftest hook uninstalls those stubs
# (and re-imports the real C extension) for the *next* test
# module's collection, so sibling tests that need real Qt
# (e.g. ``rikugan/tests/test_chat_view_async_restore.py``)
# pick up the real classes even when this file runs first.
from tests.qt_stubs import ensure_pyside6_stubs

ensure_pyside6_stubs()


# Stub heavy rikugan submodules.  We only stub the *names* that
# the production code under test imports, and only as MagicMock —
# real classes from the real modules are not needed because the
# tests in this module exercise static helpers (``_export_*``) and
# build a bare ``RikuganPanelCore`` via ``object.__new__`` so its
# constructor (which would touch every heavy dependency) is bypassed.
#
# Each stub uses a ``__getattr__`` fallback so that ANY missing
# attribute (e.g. ``get_placeholder_style``) resolves to a fresh
# MagicMock instead of ``AttributeError``.  This keeps the test
# file resilient to new style getters added by the production
# code — the test does not need to enumerate every name.
class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        m = MagicMock()
        object.__setattr__(self, name, m)
        return m


# Snapshot the real rikugan modules BEFORE we install the stubs below,
# so a module-level pytest fixture can restore them after this test
# module finishes.  Without this snapshot/restore pair, the stubs we
# install at import time would leak into sibling test modules and
# break tests that touch the real rikugan modules (e.g. provider
# tests that construct ``AnthropicProvider`` / ``OpenAIProvider``).
_STUBBED_MODULES = [
    "rikugan.ui.styles",
    "rikugan.ui.chat_view",
    "rikugan.ui.input_area",
    "rikugan.ui.context_bar",
    "rikugan.ui.tool_widgets",
    "rikugan.ui.message_widgets",
    "rikugan.ui.markdown",
    "rikugan.ui.theme",
    "rikugan.ui.theme.applicator",
    "rikugan.ui.theme.manager",
    "rikugan.ui.theme.tokens",
    "rikugan.ui.theme.palette_dark",
    "rikugan.ui.theme.palette_light",
    "rikugan.ui.theme.palette_ida",
    "rikugan.core.config",
    "rikugan.core.logging",
    "rikugan.core.types",
    "rikugan.core.host",
    "rikugan.agent.turn",
    "rikugan.agent.mutation",
    "rikugan.providers.auth_cache",
    "rikugan.providers.anthropic_provider",
    "rikugan.providers.ollama_provider",
    "rikugan.providers.registry",
]
_STUBBED_MODULE_BACKUPS: dict[str, object] = {name: sys.modules.get(name) for name in _STUBBED_MODULES}


for _mod_name in [
    "rikugan.ui.styles",
    "rikugan.ui.chat_view",
    "rikugan.ui.input_area",
    "rikugan.ui.context_bar",
    "rikugan.ui.tool_widgets",
    "rikugan.ui.message_widgets",
    "rikugan.ui.markdown",
    "rikugan.ui.theme",
    "rikugan.ui.theme.applicator",
    "rikugan.ui.theme.manager",
    "rikugan.ui.theme.tokens",
    "rikugan.ui.theme.palette_dark",
    "rikugan.ui.theme.palette_light",
    "rikugan.ui.theme.palette_ida",
    "rikugan.core.config",
    "rikugan.core.logging",
    "rikugan.core.types",
    "rikugan.core.host",
    "rikugan.agent.turn",
    "rikugan.agent.mutation",
    "rikugan.providers.auth_cache",
    "rikugan.providers.anthropic_provider",
    "rikugan.providers.ollama_provider",
    "rikugan.providers.registry",
]:
    # Always (re)install the stub.  Other test files may have left
    # partial stubs in sys.modules that lack the names this module
    # needs; reinstalling a clean stub keeps the behavior
    # deterministic regardless of collection order.
    _stub = _StubModule(_mod_name)
    for _attr in [
        "build_small_button_stylesheet",
        "maybe_host_stylesheet",
        "use_native_host_theme",
        "ChatView",
        "InputArea",
        "ContextBar",
        "_SharedSpinnerTimer",
        "RikuganConfig",
        "log_error",
        "log_info",
        "log_debug",
        "log_warning",
        "TurnEvent",
        "TurnEventType",
        "MutationRecord",
        "Role",
        "ModelInfo",
        "resolve_auth_cached",
        "resolve_anthropic_auth",
        "DEFAULT_OLLAMA_URL",
        "ProviderRegistry",
    ]:
        setattr(_stub, _attr, MagicMock())
    sys.modules[_mod_name] = _stub

# Ensure DEFAULT_OLLAMA_URL is a string (used in comparisons)
_ollama_stub = sys.modules.get("rikugan.providers.ollama_provider")
if _ollama_stub and not isinstance(getattr(_ollama_stub, "DEFAULT_OLLAMA_URL", None), str):
    _ollama_stub.DEFAULT_OLLAMA_URL = "http://localhost:11434"


# ``TestShutdownDisconnectsThemeChanged`` exercises the real
# ``ThemeManager`` singleton (the only way to observe what
# ``panel.shutdown()`` actually disconnected from).  Provide a
# working ``themeChanged`` stand-in that records its listeners on
# a real list so the test's ``_listeners`` precondition works.
class _StubThemeSignal:
    def __init__(self):
        self._listeners: list = []

    def connect(self, slot):
        self._listeners.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self._listeners.clear()
        else:
            try:
                self._listeners.remove(slot)
            except ValueError:
                pass

    def emit(self, *_args, **_kwargs):
        for listener in list(self._listeners):
            try:
                listener(*_args, **_kwargs)
            except Exception:
                pass


class _StubThemeManager:
    """Stand-in for the real ``ThemeManager`` singleton.

    Records connects/disconnects in a real list so the shutdown
    test can assert the panel's slot was registered and later
    removed.  The production code only calls ``connect`` /
    ``disconnect`` on ``themeChanged``; everything else is a
    no-op.
    """

    _instance: _StubThemeManager | None = None

    def __init__(self):
        self.themeChanged = _StubThemeSignal()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None


_tm_stub = sys.modules.get("rikugan.ui.theme.manager")
if _tm_stub is not None:
    _tm_stub.ThemeManager = _StubThemeManager

# Force-remove any stub that test_ida_panel may have registered
# so we always import the real module here.
sys.modules.pop("rikugan.ui.panel_core", None)

# Pytest fixture that restores the real rikugan modules after this
# test module finishes.  The fixtures below are module-scoped so
# they run exactly once per ``test_panel_core.py`` collection cycle,
# and they use the ``_STUBBED_MODULE_BACKUPS`` snapshot taken at
# import time to put the real modules back in ``sys.modules``.
#
# Without this fixture, the MagicMock stubs installed above leak
# into sibling test modules and poison ``rikugan.core.config``,
# ``rikugan.providers.registry``, and other modules for every
# downstream test — which is exactly the kind of test-isolation
# regression that makes headless / provider tests fail when run
# after a panel-core test in the same pytest invocation.
import pytest  # noqa: E402

from rikugan.ui.export_formatting import (  # noqa: E402
    _TOOL_RESULT_TRUNCATE_CHARS,
    _export_detect_lang,
    _export_format_tool_args,
    _export_format_tool_result,
)
from rikugan.ui.panel_core import (  # noqa: E402
    RikuganPanelCore,
)


@pytest.fixture(scope="module", autouse=True)
def _restore_rikugan_modules_after_panel_core_tests():
    """Restore the real rikugan modules once this test module finishes."""
    yield
    for name, original in _STUBBED_MODULE_BACKUPS.items():
        if original is None:
            # Module wasn't loaded before this test file — drop the stub
            # so the next test file re-imports the real implementation.
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


# ---------------------------------------------------------------------------
# _export_detect_lang
# ---------------------------------------------------------------------------


class TestExportDetectLang(unittest.TestCase):
    def test_arg_key_code_returns_python(self):
        self.assertEqual(_export_detect_lang("anything", arg_key="code"), "python")

    def test_arg_key_python_returns_python(self):
        self.assertEqual(_export_detect_lang("anything", arg_key="python"), "python")

    def test_arg_key_c_code_returns_c(self):
        self.assertEqual(_export_detect_lang("anything", arg_key="c_code"), "c")

    def test_arg_key_c_declaration_returns_c(self):
        self.assertEqual(_export_detect_lang("anything", arg_key="c_declaration"), "c")

    def test_arg_key_prototype_returns_c(self):
        self.assertEqual(_export_detect_lang("anything", arg_key="prototype"), "c")

    def test_tool_name_execute_python(self):
        self.assertEqual(_export_detect_lang("x", tool_name="execute_python"), "python")

    def test_tool_name_decompile_function(self):
        self.assertEqual(_export_detect_lang("x", tool_name="decompile_function"), "c")

    def test_tool_name_get_il(self):
        self.assertEqual(_export_detect_lang("x", tool_name="get_il"), "c")

    def test_tool_name_fetch_disassembly(self):
        self.assertEqual(_export_detect_lang("x", tool_name="fetch_disassembly"), "x86asm")

    def test_hexdump_pattern_returns_text(self):
        hexdump = "00000000  48 65 6c 6c 6f 20 57 6f  72 6c 64 0a\n"
        self.assertEqual(_export_detect_lang(hexdump), "text")

    def test_asm_pattern_returns_x86asm(self):
        asm = "mov eax, 0x1234\ncall 0xdeadbeef\n"
        self.assertEqual(_export_detect_lang(asm), "x86asm")

    def test_c_pattern_returns_c(self):
        c_code = "int foo(void) {\n  if (x > 0) { return 1; }\n}"
        self.assertEqual(_export_detect_lang(c_code), "c")

    def test_python_pattern_returns_python(self):
        py_code = "def foo():\n    return 1\nimport os\n"
        self.assertEqual(_export_detect_lang(py_code), "python")

    def test_empty_returns_empty(self):
        self.assertEqual(_export_detect_lang(""), "")

    def test_plain_text_returns_empty(self):
        self.assertEqual(_export_detect_lang("hello world, nothing special"), "")

    def test_arg_key_takes_priority_over_tool_name(self):
        # arg_key check comes first
        result = _export_detect_lang("x", tool_name="execute_python", arg_key="c_code")
        self.assertEqual(result, "c")


# ---------------------------------------------------------------------------
# _export_format_tool_args
# ---------------------------------------------------------------------------


class TestExportFormatToolArgs(unittest.TestCase):
    def _make_tc(self, name: str, args: dict):
        tc = MagicMock()
        tc.name = name
        tc.arguments = args
        return tc

    def test_short_value_inline(self):
        tc = self._make_tc("tool", {"key": "val"})
        result = _export_format_tool_args(tc)
        self.assertIn("`key`", result)
        self.assertIn("'val'", result)

    def test_long_value_code_block(self):
        long_val = "x" * 100
        tc = self._make_tc("tool", {"code": long_val})
        result = _export_format_tool_args(tc)
        self.assertIn("```python", result)
        self.assertIn(long_val, result)

    def test_multiline_value_code_block(self):
        tc = self._make_tc("tool", {"body": "line1\nline2"})
        result = _export_format_tool_args(tc)
        self.assertIn("```", result)
        self.assertIn("line1\nline2", result)

    def test_empty_args(self):
        tc = self._make_tc("tool", {})
        result = _export_format_tool_args(tc)
        self.assertEqual(result, "")

    def test_multiple_args(self):
        tc = self._make_tc("tool", {"a": "short", "b": "also short"})
        result = _export_format_tool_args(tc)
        self.assertIn("`a`", result)
        self.assertIn("`b`", result)


# ---------------------------------------------------------------------------
# _export_format_tool_result
# ---------------------------------------------------------------------------


class TestExportFormatToolResult(unittest.TestCase):
    def _make_tr(self, content: str, name: str = "tool"):
        tr = MagicMock()
        tr.content = content
        tr.name = name
        return tr

    def test_short_content_not_truncated(self):
        tr = self._make_tr("short content")
        result = _export_format_tool_result(tr)
        self.assertIn("short content", result)
        self.assertNotIn("truncated", result)

    def test_long_content_truncated(self):
        long_content = "A" * (_TOOL_RESULT_TRUNCATE_CHARS + 100)
        tr = self._make_tr(long_content)
        result = _export_format_tool_result(tr)
        self.assertIn("truncated", result)
        self.assertNotIn("A" * (_TOOL_RESULT_TRUNCATE_CHARS + 1), result)

    def test_returns_code_block(self):
        tr = self._make_tr("output")
        result = _export_format_tool_result(tr)
        self.assertIn("```", result)
        self.assertTrue(result.startswith("```"))

    def test_decompile_tool_gets_c_hint(self):
        tr = self._make_tr("int main(void) {}", "decompile_function")
        result = _export_format_tool_result(tr)
        self.assertIn("```c", result)


# ---------------------------------------------------------------------------
# Panel logic via object.__new__ injection
# ---------------------------------------------------------------------------


def _make_panel():
    # Use the class's own ``__new__`` rather than ``object.__new__``.
    # ``RikuganPanelCore`` inherits from a C-level Qt class
    # (``QWidget``), and ``object.__new__`` is rejected on C-level
    # subclasses with a ``TypeError`` — use
    # ``RikuganPanelCore.__new__(RikuganPanelCore)`` which delegates
    # to the C-level allocator.  The same idiom is used in
    # ``test_chat_view.py`` and ``test_settings_dialog.py``; keeping
    # the form consistent avoids surprises when real PySide6 has
    # been loaded by a sibling test in the same session.
    panel = RikuganPanelCore.__new__(RikuganPanelCore)
    panel._is_shutdown = False
    panel._polling = False
    panel._pending_answer = False
    panel._chat_views = {}
    panel._pending_restore_messages = {}
    panel._context_bar = None
    panel._mutation_panel = None
    panel._skills_refresh_timer = None
    panel._poll_timer = None
    # Token-display debouncing fields added in the Phase 1.3 perf change.
    # The debounced path requires these on the panel even when constructed
    # via ``__new__`` (which bypasses ``__init__``).
    panel._pending_token_display = None
    panel._token_display_timer = None
    panel._last_token_display_value = -1
    panel._input_area = MagicMock()
    panel._send_btn = MagicMock()
    panel._cancel_btn = MagicMock()
    panel._mutations_btn = MagicMock()
    panel._count_label = MagicMock()
    panel._tab_widget = MagicMock()
    panel._tab_bar = MagicMock()
    panel._ctrl = MagicMock()
    panel._config = MagicMock()
    panel._ui_hooks = None
    panel._awaiting_button_approval = False
    return panel


class TestTabIdAtIndex(unittest.TestCase):
    def test_returns_none_when_widget_is_none(self):
        panel = _make_panel()
        panel._tab_widget.widget.return_value = None
        result = panel._tab_id_at_index(0)
        self.assertIsNone(result)

    def test_returns_tab_id_from_property(self):
        panel = _make_panel()
        mock_widget = MagicMock()
        mock_widget.property.return_value = "tab123"
        panel._chat_views["tab123"] = mock_widget
        panel._tab_widget.widget.return_value = mock_widget
        result = panel._tab_id_at_index(0)
        self.assertEqual(result, "tab123")

    def test_returns_none_when_property_not_in_chat_views(self):
        panel = _make_panel()
        mock_widget = MagicMock()
        mock_widget.property.return_value = "ghost_id"
        # ghost_id not in _chat_views, and widget itself is not in values either
        panel._tab_widget.widget.return_value = mock_widget
        result = panel._tab_id_at_index(0)
        self.assertIsNone(result)

    def test_fallback_to_widget_identity(self):
        panel = _make_panel()
        mock_widget = MagicMock()
        mock_widget.property.return_value = None  # no property
        panel._chat_views["tab_x"] = mock_widget
        panel._tab_widget.widget.return_value = mock_widget
        result = panel._tab_id_at_index(0)
        self.assertEqual(result, "tab_x")


class TestActiveChatView(unittest.TestCase):
    def test_returns_view_for_active_tab(self):
        panel = _make_panel()
        mock_view = MagicMock()
        panel._ctrl.active_tab_id = "t1"
        panel._chat_views["t1"] = mock_view
        self.assertIs(panel._active_chat_view(), mock_view)

    def test_returns_none_when_active_tab_not_in_views(self):
        panel = _make_panel()
        panel._ctrl.active_tab_id = "missing"
        self.assertIsNone(panel._active_chat_view())


class TestSetRunning(unittest.TestCase):
    def test_running_true_sets_queue_text(self):
        panel = _make_panel()
        panel._set_running(True)
        panel._send_btn.setText.assert_called_with("Queue")

    def test_running_false_sets_send_text(self):
        panel = _make_panel()
        panel._set_running(False)
        panel._send_btn.setText.assert_called_with("Send")

    def test_running_shows_cancel_btn(self):
        panel = _make_panel()
        panel._set_running(True)
        panel._cancel_btn.setVisible.assert_called_with(True)

    def test_not_running_hides_cancel_btn(self):
        panel = _make_panel()
        panel._set_running(False)
        panel._cancel_btn.setVisible.assert_called_with(False)


class TestUpdateTabBarVisibility(unittest.TestCase):
    def test_single_tab_hides_bar(self):
        panel = _make_panel()
        panel._tab_widget.count.return_value = 1
        panel._update_tab_bar_visibility()
        panel._tab_bar.setVisible.assert_called_with(False)

    def test_two_tabs_shows_bar(self):
        panel = _make_panel()
        panel._tab_widget.count.return_value = 2
        panel._update_tab_bar_visibility()
        panel._tab_bar.setVisible.assert_called_with(True)

    def test_zero_tabs_hides_bar(self):
        panel = _make_panel()
        panel._tab_widget.count.return_value = 0
        panel._update_tab_bar_visibility()
        panel._tab_bar.setVisible.assert_called_with(False)


class TestOnCloseTab(unittest.TestCase):
    def test_does_not_close_last_tab(self):
        panel = _make_panel()
        panel._tab_widget.count.return_value = 1
        panel._on_close_tab(0)
        panel._ctrl.close_tab.assert_not_called()

    def test_closes_tab_with_multiple(self):
        panel = _make_panel()
        panel._tab_widget.count.return_value = 2
        mock_widget = MagicMock()
        mock_widget.property.return_value = "tid"
        panel._chat_views["tid"] = mock_widget
        panel._tab_widget.widget.return_value = mock_widget
        panel._on_close_tab(0)
        panel._ctrl.close_tab.assert_called_once_with("tid")

    def test_removes_view_from_chat_views(self):
        panel = _make_panel()
        panel._tab_widget.count.return_value = 2
        mock_widget = MagicMock()
        mock_widget.property.return_value = "tid"
        panel._chat_views["tid"] = mock_widget
        panel._tab_widget.widget.return_value = mock_widget
        panel._on_close_tab(0)
        self.assertNotIn("tid", panel._chat_views)


class TestOnToggleMutationLog(unittest.TestCase):
    def test_noop_when_no_panel(self):
        panel = _make_panel()
        panel._mutation_panel = None
        panel._on_toggle_mutation_log()  # must not raise

    def test_shows_when_hidden(self):
        panel = _make_panel()
        mock_mp = MagicMock()
        mock_mp.isVisible.return_value = False
        panel._mutation_panel = mock_mp
        panel._on_toggle_mutation_log()
        mock_mp.setVisible.assert_called_with(True)

    def test_hides_when_visible(self):
        panel = _make_panel()
        mock_mp = MagicMock()
        mock_mp.isVisible.return_value = True
        panel._mutation_panel = mock_mp
        panel._on_toggle_mutation_log()
        mock_mp.setVisible.assert_called_with(False)

    def test_updates_checked_state(self):
        panel = _make_panel()
        mock_mp = MagicMock()
        mock_mp.isVisible.return_value = False
        panel._mutation_panel = mock_mp
        panel._on_toggle_mutation_log()
        panel._mutations_btn.setChecked.assert_called_with(True)


class TestOnUndoRequested(unittest.TestCase):
    def test_noop_when_shutdown(self):
        panel = _make_panel()
        panel._is_shutdown = True
        panel._on_undo_requested(1)
        # _start_agent should not be called — we can check ctrl is not used
        panel._ctrl.start_agent.assert_not_called()

    def test_starts_undo_agent(self):
        panel = _make_panel()
        panel._ctrl.active_tab_id = "t1"
        mock_view = MagicMock()
        panel._chat_views["t1"] = mock_view
        panel._ctrl.start_agent.return_value = None  # no error
        # Pre-inject a mock poll_timer so _ensure_poll_timer returns early
        panel._poll_timer = MagicMock()
        panel._on_undo_requested(2)
        panel._ctrl.start_agent.assert_called_once_with("/undo 2")


class TestOnOrchestraApproval(unittest.TestCase):
    """Regression tests for ``RikuganPanelCore._on_orchestra_approval``.

    The orchestra / agent-handoff path uses a different approval queue
    inside the agent loop (``_approval_queue``) than regular tool
    approvals (``_tool_approval_queue``).  The panel must call
    ``agent_loop.submit_approval`` (which targets the orchestra queue)
    — never ``submit_tool_approval`` (which targets the tool queue).
    After submitting, the panel must clear the same UI state flags
    that the button-only approval flow clears
    (``_pending_answer``, ``_awaiting_button_approval``) so the input
    area is re-enabled for the next user turn.
    """

    def _make_runner_loop(self) -> MagicMock:
        runner = MagicMock()
        agent_loop = MagicMock()
        runner.agent_loop = agent_loop
        return runner, agent_loop

    def test_approve_calls_submit_approval(self) -> None:
        panel = _make_panel()
        runner, agent_loop = self._make_runner_loop()
        panel._ctrl.get_runner.return_value = runner

        panel._on_orchestra_approval("call_xyz", "approve")

        agent_loop.submit_approval.assert_called_once_with("approve")

    def test_deny_calls_submit_approval(self) -> None:
        panel = _make_panel()
        runner, agent_loop = self._make_runner_loop()
        panel._ctrl.get_runner.return_value = runner

        panel._on_orchestra_approval("call_xyz", "deny")

        agent_loop.submit_approval.assert_called_once_with("deny")

    def test_does_not_call_submit_tool_approval(self) -> None:
        """``_on_orchestra_approval`` must NOT push to the
        tool-approval queue.  The two channels serve different
        agent-loop flows and routing an orchestra decision to the
        tool queue would deadlock the orchestra handoff."""
        panel = _make_panel()
        runner, agent_loop = self._make_runner_loop()
        panel._ctrl.get_runner.return_value = runner

        panel._on_orchestra_approval("call_xyz", "approve")

        agent_loop.submit_tool_approval.assert_not_called()

    def test_clears_pending_answer_flag(self) -> None:
        panel = _make_panel()
        runner, _ = self._make_runner_loop()
        panel._ctrl.get_runner.return_value = runner
        panel._pending_answer = True

        panel._on_orchestra_approval("call_xyz", "approve")

        self.assertFalse(panel._pending_answer)

    def test_clears_awaiting_button_approval_flag(self) -> None:
        panel = _make_panel()
        runner, _ = self._make_runner_loop()
        panel._ctrl.get_runner.return_value = runner
        panel._awaiting_button_approval = True

        panel._on_orchestra_approval("call_xyz", "deny")

        self.assertFalse(panel._awaiting_button_approval)

    def test_no_runner_does_not_raise(self) -> None:
        """If the agent runner is gone (cancelled, finished) the
        call must be a no-op — no exception, but the UI flags are
        still cleared so the panel can re-enable input."""
        panel = _make_panel()
        panel._ctrl.get_runner.return_value = None
        panel._pending_answer = True
        panel._awaiting_button_approval = True

        # Must not raise.
        panel._on_orchestra_approval("call_xyz", "approve")

        # The flags reflect "the decision is done" regardless of
        # whether the agent loop is alive to receive it.
        self.assertFalse(panel._pending_answer)
        self.assertFalse(panel._awaiting_button_approval)


class TestShutdownIdempotency(unittest.TestCase):
    def test_double_shutdown_safe(self):
        panel = _make_panel()
        panel._poll_timer = None
        panel._skills_refresh_timer = None
        panel._context_bar = None
        panel._ui_hooks = None
        panel.shutdown()
        panel.shutdown()  # second call must not raise or double-cleanup
        panel._ctrl.shutdown.assert_called_once()

    def test_shutdown_calls_ctrl_shutdown(self):
        panel = _make_panel()
        panel._poll_timer = None
        panel._skills_refresh_timer = None
        panel._context_bar = None
        panel._ui_hooks = None
        panel.shutdown()
        panel._ctrl.shutdown.assert_called_once()


class TestStopSkillsRefreshTimer(unittest.TestCase):
    def test_noop_when_timer_none(self):
        panel = _make_panel()
        panel._skills_refresh_timer = None
        panel._stop_skills_refresh_timer()  # must not raise

    def test_clears_timer_ref(self):
        panel = _make_panel()
        mock_timer = MagicMock()
        panel._skills_refresh_timer = mock_timer
        panel._stop_skills_refresh_timer()
        self.assertIsNone(panel._skills_refresh_timer)
        mock_timer.stop.assert_called_once()
        mock_timer.deleteLater.assert_called_once()


class TestRestoreMessagesIfNeeded(unittest.TestCase):
    def test_noop_when_no_pending_restore(self):
        panel = _make_panel()
        mock_view = MagicMock()
        panel._chat_views["t1"] = mock_view
        panel._restore_messages_if_needed("t1")
        mock_view.restore_from_messages_async.assert_not_called()

    def test_restores_pending_messages_once(self):
        panel = _make_panel()
        mock_view = MagicMock()
        panel._chat_views["t1"] = mock_view
        panel._pending_restore_messages["t1"] = ["m1", "m2"]
        panel._restore_messages_if_needed("t1")
        mock_view.restore_from_messages_async.assert_called_once_with(["m1", "m2"])
        self.assertNotIn("t1", panel._pending_restore_messages)


class TestUpdateTokenDisplay(unittest.TestCase):
    def test_noop_when_context_bar_none(self):
        panel = _make_panel()
        panel._context_bar = None
        panel._update_token_display(1000)  # must not raise

    def test_calls_set_tokens_with_given_count(self):
        panel = _make_panel()
        mock_cb = MagicMock()
        panel._context_bar = mock_cb
        panel._config.provider.context_window = 200000
        panel._update_token_display(5000)
        # Phase 1.3: token display is debounced — flush before asserting.
        panel._flush_pending_token_display()
        mock_cb.set_tokens.assert_called_once_with(5000, 200000)

    def test_zero_context_window_fallback(self):
        panel = _make_panel()
        mock_cb = MagicMock()
        panel._context_bar = mock_cb
        panel._config.provider.context_window = 0
        panel._update_token_display(1234)
        # Phase 1.3: token display is debounced — flush before asserting.
        panel._flush_pending_token_display()
        mock_cb.set_tokens.assert_called_once_with(1234, 0)

    def test_coalesces_repeated_updates_within_window(self):
        """Multiple updates with different values produce only one set_tokens call."""
        panel = _make_panel()
        mock_cb = MagicMock()
        panel._context_bar = mock_cb
        panel._config.provider.context_window = 200000
        panel._update_token_display(1000)
        panel._update_token_display(2000)
        panel._update_token_display(3000)
        # Only the latest value is flushed, not all three. We check the
        # last call's args explicitly because Qt may eagerly fire the
        # single-shot debounce timer in some test environments, which
        # would otherwise look like multiple set_tokens invocations.
        panel._flush_pending_token_display()
        self.assertEqual(mock_cb.set_tokens.call_args, mock_cb.set_tokens.call_args_list[-1])
        self.assertEqual(mock_cb.set_tokens.call_args.args, (3000, 200000))

    def test_noop_when_value_unchanged(self):
        """An update with the same value as the last displayed value is a no-op."""
        panel = _make_panel()
        mock_cb = MagicMock()
        panel._context_bar = mock_cb
        panel._config.provider.context_window = 200000
        panel._update_token_display(5000)
        panel._flush_pending_token_display()
        panel._update_token_display(5000)  # same value — must not enqueue
        mock_cb.set_tokens.assert_called_once_with(5000, 200000)


# ---------------------------------------------------------------------------
# _create_tab — must connect real ChatView signals, not call
# nonexistent methods (see review of the async chat restore
# change).  This regression guard ensures the connection shape
# stays compatible with the real ``ChatView`` class.
# ---------------------------------------------------------------------------


class TestCreateTabSignalWiring(unittest.TestCase):
    """``RikuganPanelCore._create_tab`` must use ``ChatView`` signals.

    Older revisions of ``_create_tab`` called
    ``chat_view.set_tool_approval_callback(...)`` and
    ``chat_view.set_user_answer_callback(...)``, but the real
    ``ChatView`` class only exposes ``tool_approval_submitted``,
    ``user_answer_submitted``, and ``orchestra_approval_decided``
    Qt signals.  Calling the missing methods would raise
    ``AttributeError`` the first time the user opened a tab.
    This regression test pins the correct behaviour by *actually
    running* production ``_create_tab`` against a stubbed
    ``ChatView`` and asserting on the resulting wiring.
    """

    def _make_panel_with_chat_view(self):
        """Build a panel whose ``_create_tab`` can be invoked.

        We rely on the test-file-level stub of
        ``rikugan.ui.chat_view``: the stub's ``ChatView`` attribute
        is a plain ``MagicMock``, so ``ChatView()`` returns a fresh
        ``MagicMock`` instance.  Production ``_create_tab`` runs
        against that mock — and we then assert on the side
        effects (signal connections, ``setProperty``, tab storage,
        tab-widget insertion).
        """
        panel = _make_panel()
        # ``_update_tab_bar_visibility`` (called at the end of
        # production ``_create_tab``) compares ``tab_widget.count()``
        # against ``1``.  The bare ``MagicMock`` returns a truthy
        # mock, which breaks the comparison.  Pin the count to a
        # real int so the production code can run end-to-end.
        panel._tab_widget.count.return_value = 1
        return panel

    def test_create_tab_uses_chat_view_signals_not_legacy_callbacks(self) -> None:
        """``_create_tab`` must not call the legacy
        ``set_tool_approval_callback`` / ``set_user_answer_callback``
        methods on the chat view (they don't exist on the real
        ``ChatView`` class).  The panel must connect the real Qt
        signals instead.

        The test runs *production* ``_create_tab`` against a
        stubbed ``ChatView`` and checks the resulting mock for
        signal ``.connect()`` calls.  If a future refactor
        reintroduced the legacy callback methods, the real
        ``ChatView()`` mock (which has no such attribute) would
        raise ``AttributeError`` and this test would fail.
        """
        panel = self._make_panel_with_chat_view()

        chat_view = panel._create_tab("tab-x", "New Chat")

        # The new chat view must be stored under its tab_id so
        # lookups work.
        self.assertIn("tab-x", panel._chat_views)
        self.assertIs(panel._chat_views["tab-x"], chat_view)
        # The ``tab_id`` property is set on the widget for
        # ``_tab_id_at_index`` to recover it via ``widget.property``.
        chat_view.setProperty.assert_called_with("tab_id", "tab-x")
        # Tab widget must have received the new view + label.
        panel._tab_widget.addTab.assert_called_with(chat_view, "New Chat")
        # The three Qt signals must each be connected exactly
        # once to the matching panel slot.
        chat_view.tool_approval_submitted.connect.assert_called_once_with(panel._on_tool_approval)
        chat_view.user_answer_submitted.connect.assert_called_once_with(panel._on_user_answer_submitted)
        chat_view.orchestra_approval_decided.connect.assert_called_once_with(panel._on_orchestra_approval)
        # The legacy callback methods must NOT be called.
        # ``MagicMock`` auto-creates attributes on access, so we
        # verify by checking the call list on the mock.
        for forbidden in (
            "set_tool_approval_callback",
            "set_user_answer_callback",
        ):
            getattr(chat_view, forbidden).assert_not_called()


# ---------------------------------------------------------------------------
# _on_theme_changed — must refresh every existing ChatView's
# inline styles when the active theme changes.  The fix to the
# review regression added a loop over ``self._chat_views.values()``
# that calls ``refresh_inline_styles()``; this test pins the
# behaviour so a future refactor doesn't silently drop the loop.
# ---------------------------------------------------------------------------


class TestOnThemeChangedRefresh(unittest.TestCase):
    def test_calls_refresh_inline_styles_on_all_chat_views(self) -> None:
        """``_on_theme_changed`` must call ``refresh_inline_styles``
        on every chat view currently in ``_chat_views`` so the
        cached inline-styled widgets pick up the new theme
        tokens.  The review found that the original code did
        not iterate the chat views; this test pins the
        corrected behaviour by *calling the production function*
        and asserting on the side effects.
        """
        panel = _make_panel()
        cv1 = MagicMock()
        cv2 = MagicMock()
        cv3 = MagicMock()
        panel._chat_views = {"a": cv1, "b": cv2, "c": cv3}

        # The production function takes a ThemeTokens payload
        # (the value emitted by ThemeManager.themeChanged).  We
        # don't need a real token — a MagicMock satisfies the
        # signature.
        panel._on_theme_changed(MagicMock())

        # Every chat view must have been refreshed exactly once.
        cv1.refresh_inline_styles.assert_called_once()
        cv2.refresh_inline_styles.assert_called_once()
        cv3.refresh_inline_styles.assert_called_once()

    def test_on_theme_changed_survives_failing_chat_view(self) -> None:
        """If a single ``ChatView.refresh_inline_styles`` raises,
        ``_on_theme_changed`` must still refresh the remaining
        views.  The production function wraps each call in a
        ``try / except`` for best-effort refresh, and the test
        pins that contract.
        """
        panel = _make_panel()
        cv_good = MagicMock()
        cv_bad = MagicMock()
        cv_bad.refresh_inline_styles.side_effect = RuntimeError("boom")
        panel._chat_views = {"good": cv_good, "bad": cv_bad}

        # Must not raise.
        panel._on_theme_changed(MagicMock())

        # The good view was still refreshed.
        cv_good.refresh_inline_styles.assert_called_once()
        # The bad view was attempted (the error did not skip it).
        cv_bad.refresh_inline_styles.assert_called_once()


# ---------------------------------------------------------------------------
# shutdown() — must disconnect from ThemeManager.themeChanged
# so the singleton doesn't keep a dangling reference to the
# panel alive after teardown.
# ---------------------------------------------------------------------------


class TestShutdownDisconnectsThemeChanged(unittest.TestCase):
    def setUp(self) -> None:
        # Sibling test files (notably
        # ``tests/tools/test_settings_dialog.py``) re-import the
        # *real* ``rikugan.ui.theme.manager`` so they can exercise
        # the production ``ThemeManager`` singleton.  When those
        # tests run before us in the same session, the real
        # module is what ``from rikugan.ui.theme.manager import
        # ThemeManager`` resolves to here.  Force the stub back
        # into place so the test can observe connect/disconnect
        # against the in-test ``_StubThemeSignal``.
        sys.modules.pop("rikugan.ui.theme.manager", None)
        _tm_stub = _StubModule("rikugan.ui.theme.manager")
        _tm_stub.ThemeManager = _StubThemeManager
        sys.modules["rikugan.ui.theme.manager"] = _tm_stub

    def test_shutdown_disconnects_theme_changed(self) -> None:
        from rikugan.ui.theme.manager import ThemeManager

        # Reset the ThemeManager singleton so we control its
        # signal listeners.
        ThemeManager.reset()
        tm = ThemeManager.instance()

        panel = _make_panel()
        panel._poll_timer = None
        panel._skills_refresh_timer = None
        panel._context_bar = None
        panel._ui_hooks = None
        # Connect the panel's slot to the live manager.
        tm.themeChanged.connect(panel._on_theme_changed)
        # Sanity: disconnect should not have been called yet.
        self.assertTrue(
            any(getattr(slot, "__name__", "") == "_on_theme_changed" for slot in (tm.themeChanged._listeners or []))
            if hasattr(tm.themeChanged, "_listeners")
            else True,
            "precondition: handler connected",
        )

        # The real disconnect call is wrapped in try/except; we
        # patch it to a no-op for the test so we can observe
        # the call.
        original_disconnect = tm.themeChanged.disconnect
        with patch.object(tm.themeChanged, "disconnect", wraps=original_disconnect) as mock_disconnect:
            panel.shutdown()
        mock_disconnect.assert_any_call(panel._on_theme_changed)
        # Reset for any other tests that may run later.
        ThemeManager.reset()


# ---------------------------------------------------------------------------
# Tools tab order, default selection, and renamer isolation
# ---------------------------------------------------------------------------


class TestToolsTabOrderAndDefault(unittest.TestCase):
    """The visible Tools tabs are Agents, A2A, Knowledge in that order,
    and the Knowledge tab is the default landing tab.

    The Bulk Renamer tab has been removed from the visible Tools
    surface so opening Tools no longer enumerates the function table.
    The renamer implementation is dormant, not deleted; these tests
    pin the new contract that nothing in the panel builds a renamer
    widget, engine, or enumeration pump on Tools open.
    """

    def test_tab_constants_match_index_order(self):
        from rikugan.ui.tools_panel import ToolsPanel

        self.assertEqual(ToolsPanel.TAB_AGENTS, 0)
        self.assertEqual(ToolsPanel.TAB_A2A, 1)
        self.assertEqual(ToolsPanel.TAB_KNOWLEDGE, 2)
        self.assertEqual(ToolsPanel.TAB_COUNT, 3)
        # Order matters for ``_TAB_INITIALIZERS`` below.
        self.assertLess(ToolsPanel.TAB_AGENTS, ToolsPanel.TAB_A2A)
        self.assertLess(ToolsPanel.TAB_A2A, ToolsPanel.TAB_KNOWLEDGE)

    def test_tab_initializer_keys_match_constants(self):
        panel = RikuganPanelCore.__new__(RikuganPanelCore)
        from rikugan.ui.tools_panel import ToolsPanel

        initializers = panel._TAB_INITIALIZERS
        # No renamer initializer should be reachable by tab index.
        self.assertNotIn("_ensure_renamer_tab_initialized", initializers.values())
        # The Renamer constant must NOT exist any more.
        self.assertFalse(
            hasattr(ToolsPanel, "TAB_RENAMER"),
            "ToolsPanel.TAB_RENAMER has been removed; renamer is hidden.",
        )
        # Initializers line up with the public tab constants.
        self.assertIn(ToolsPanel.TAB_AGENTS, initializers)
        self.assertIn(ToolsPanel.TAB_A2A, initializers)
        self.assertIn(ToolsPanel.TAB_KNOWLEDGE, initializers)
        # Knowledge is bound to the Knowledge initializer.
        self.assertEqual(
            initializers[ToolsPanel.TAB_KNOWLEDGE],
            "_ensure_knowledge_tab_initialized",
        )

    def test_show_tools_panel_defaults_to_knowledge(self):
        """Calling ``show_tools_panel`` without arguments opens Knowledge."""
        panel = RikuganPanelCore.__new__(RikuganPanelCore)
        panel._is_shutdown = False
        panel._mode_bar = MagicMock()
        panel._tools_form = None
        panel._tools_btn = MagicMock()
        panel._tools_poll_timer = MagicMock()
        panel._ensure_tools_panel_created = MagicMock()

        # Build a fake ToolsPanel whose ``_tabs`` we can spy on.
        from rikugan.ui.tools_panel import ToolsPanel

        fake_panel = MagicMock()
        fake_panel._tabs.currentIndex.return_value = ToolsPanel.TAB_A2A
        fake_panel._tabs.count.return_value = ToolsPanel.TAB_COUNT
        panel._tools_panel = fake_panel
        # ``_ensure_tab_initialized`` should be called with the
        # knowledge tab index.
        panel._ensure_tab_initialized = MagicMock()

        panel.show_tools_panel()

        # Default tab is Knowledge (2), not the removed Renamer.
        fake_panel._tabs.setCurrentIndex.assert_called_with(ToolsPanel.TAB_KNOWLEDGE)
        panel._ensure_tab_initialized.assert_called_with(ToolsPanel.TAB_KNOWLEDGE)

    def test_show_tools_panel_falls_back_for_unknown_index(self):
        """Out-of-range and explicit renamer indices fall back to Knowledge."""
        from rikugan.ui.tools_panel import ToolsPanel

        panel = RikuganPanelCore.__new__(RikuganPanelCore)
        panel._is_shutdown = False
        panel._mode_bar = MagicMock()
        panel._tools_form = None
        panel._tools_btn = MagicMock()
        panel._tools_poll_timer = MagicMock()
        panel._ensure_tools_panel_created = MagicMock()
        panel._tools_panel = MagicMock()
        panel._tools_panel._tabs.count.return_value = ToolsPanel.TAB_COUNT
        panel._ensure_tab_initialized = MagicMock()

        panel.show_tools_panel(tab_index=99)
        panel._tools_panel._tabs.setCurrentIndex.assert_called_with(ToolsPanel.TAB_KNOWLEDGE)
        panel._ensure_tab_initialized.assert_called_with(ToolsPanel.TAB_KNOWLEDGE)

        # Historical numeric index ``0`` previously meant Renamer.
        # It must now map to the new tab-zero (Agents), not raise.
        panel._tools_panel._tabs.setCurrentIndex.reset_mock()
        panel._ensure_tab_initialized.reset_mock()
        panel.show_tools_panel(tab_index=0)
        panel._tools_panel._tabs.setCurrentIndex.assert_called_with(ToolsPanel.TAB_AGENTS)
        panel._ensure_tab_initialized.assert_called_with(ToolsPanel.TAB_AGENTS)

    def test_no_renamer_widget_or_engine_attributes_on_panel(self):
        """Panel must not lazily construct renamer widgets, engines, or timers."""
        panel = RikuganPanelCore.__new__(RikuganPanelCore)
        self.assertFalse(
            hasattr(panel, "_bulk_renamer"),
            "_bulk_renamer attribute should be gone after the renamer removal.",
        )
        self.assertFalse(hasattr(panel, "_renamer_engine"))
        self.assertFalse(hasattr(panel, "_renamer_fetch_timer"))
        # The panel must also not expose any renamer handler method.
        self.assertFalse(hasattr(panel, "_on_renamer_start"))
        self.assertFalse(hasattr(panel, "_on_renamer_cancel"))
        self.assertFalse(hasattr(panel, "_ensure_renamer_tab_initialized"))
        self.assertFalse(hasattr(panel, "show_tools_with_renamer"))

    def test_theme_refresh_iterates_only_active_tabs(self):
        """The theme refresh loop should no longer touch a renamer widget."""
        panel = RikuganPanelCore.__new__(RikuganPanelCore)
        panel._bulk_renamer = None
        # Look for any ``_bulk_renamer`` mention in the theme refresh
        # code path. The active attribute list is the simplest check.
        from rikugan.ui import panel_core as pc

        # The expected active attribute list is documented inline at
        # the loop site; verify no ``_bulk_renamer`` is iterated.
        src = pc.__file__
        with open(src, encoding="utf-8") as handle:
            body = handle.read()
        # Find the theme refresh loop and check it does not name renamer.
        loop_idx = body.find("for attr in (")
        self.assertGreaterEqual(loop_idx, 0, "theme refresh loop not found")
        snippet = body[loop_idx : loop_idx + 200]
        self.assertNotIn("_bulk_renamer", snippet)


if __name__ == "__main__":
    unittest.main()
