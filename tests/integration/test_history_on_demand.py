"""End-to-end behavioral regression for Chat History On-Demand (Task 11).

This integration test stitches together the real persistence layer
(``SessionHistory``), the real controller history APIs
(``capture_history_scope`` / ``list_history_sessions`` /
``load_history_session`` / ``attach_history_session`` /
``find_tab_for_session``), and the real ``RikuganPanelCore`` history
coordinator (``_start_history_list_request`` / ``_history_list_worker`` /
``_drain_history_results`` / ``_on_history_open_requested`` /
``_apply_history_loaded`` / ``on_database_changed`` / ``_invalidate_history``)
to verify the spec section 14.5 behavioral outline.

The panel is built via ``RikuganPanelCore.__new__`` so ``__init__`` (which
would touch every heavy IDA / Qt dependency) is bypassed. The
history-coordinator fields are seeded manually, mirroring the
``_make_history_panel`` idiom in ``tests/tools/test_panel_core.py``. The
controller is a REAL ``IdaSessionController`` backed by a temp config /
session directory so ``SessionHistory`` actually writes JSON, builds a
manifest, and validates current-IDB matching.

Per the brief, this test must NOT depend on ``install_ida_mocks`` ordering
nor on the process-wide IDA-flag state cached in ``rikugan.core.host``.
Each IDB path is assigned a deterministic 32-hex ``db_instance_id`` via a
module-local map; ``host.set_database_instance_id`` /
``host.get_database_instance_id`` are monkey-patched so the controller's
``_ensure_db_instance_id`` returns the same stable id for the same IDB
across controller instances. This mirrors what IDA's persistent netnode
provides in production.

Behavioral outline (brief Step 1):

    persist 2 IDB-A sessions + 1 IDB-B session
    panel_a = make_panel(idb_a)
    assert panel_a.tab_count() == 1
    assert panel_a.active_session.messages == []
    panel_a.open_history()
    assert panel_a.visible_history_ids() == {a1.id, a2.id}
    panel_a.open_history_session(a1.id)
    assert panel_a.tab_count() == 2
    panel_a.open_history_session(a1.id)
    assert panel_a.tab_count() == 2  # focus, no duplicate
    panel_a.on_database_changed(idb_b)
    assert panel_a.tab_count() == 1
    assert panel_a.active_session.messages == []
    panel_a.open_history()
    assert panel_a.visible_history_ids() == {b1.id}
    panel_restart = make_panel(idb_b)
    assert panel_restart.tab_count() == 1
    assert panel_restart.active_session.messages == []

Deterministic queue drains and direct slot calls are used in place of
sleeps -- no ``time.sleep`` appears anywhere in the file.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path + IDA mocks: install BEFORE importing anything from rikugan so
# ``rikugan.core.host`` caches the IDA path (HOST_IDA) and our patched
# netnode-backed database-instance helpers are used.
# ---------------------------------------------------------------------------
_TESTS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _TESTS_ROOT)

from tests.mocks.ida_mock import install_ida_mocks  # noqa: E402

install_ida_mocks()

# Defensive: drop any ``_StubModule`` entries a sibling test file
# (e.g. ``tests/tools/test_panel_core.py``) left in ``sys.modules``
# before we import the real rikugan modules. Without this purge, the
# integration test would see ``MagicMock`` instances for
# ``rikugan.core.types.Message`` etc. when collected after a panel-core
# test in the same pytest invocation. Same pattern as
# ``tests/providers/test_providers.py``.
from tests import purge_rikugan_stubs  # noqa: E402

purge_rikugan_stubs()

# Install PySide6 stubs before importing panel_core (which imports Qt).
from tests.qt_stubs import ensure_pyside6_stubs  # noqa: E402

ensure_pyside6_stubs()

# ---------------------------------------------------------------------------
# Stub heavy rikugan submodules so ``panel_core`` can be imported without
# the real provider/agent/theme stack. Same idiom as
# ``tests/tools/test_panel_core.py``: a per-module ``MagicMock`` fallback
# keeps the stub resilient to new style getters.
# ---------------------------------------------------------------------------
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
    "rikugan.core.logging",
    "rikugan.agent.turn",
    "rikugan.agent.mutation",
    "rikugan.providers.auth_cache",
    "rikugan.providers.anthropic_provider",
    "rikugan.providers.ollama_provider",
    "rikugan.providers.registry",
]

_STUBBED_MODULE_BACKUPS: dict[str, object] = {name: sys.modules.get(name) for name in _STUBBED_MODULES}


class _StubModule(types.ModuleType):
    """Module whose every attribute resolves to a fresh ``MagicMock``."""

    def __getattr__(self, name):
        m = MagicMock()
        object.__setattr__(self, name, m)
        return m


for _mod_name in _STUBBED_MODULES:
    _stub = _StubModule(_mod_name)
    for _attr in [
        "build_small_button_stylesheet",
        "maybe_host_stylesheet",
        "use_native_host_theme",
        "ChatView",
        "InputArea",
        "ContextBar",
        "_SharedSpinnerTimer",
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

# ``DEFAULT_OLLAMA_URL`` must be a real string for comparisons.
_ollama_stub = sys.modules.get("rikugan.providers.ollama_provider")
if _ollama_stub and not isinstance(getattr(_ollama_stub, "DEFAULT_OLLAMA_URL", None), str):
    _ollama_stub.DEFAULT_OLLAMA_URL = "http://localhost:11434"


# Theme-manager stub so panel shutdown can disconnect from a real signal.
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

# Force-remove any prior stub for panel_core so we import cleanly here.
sys.modules.pop("rikugan.ui.panel_core", None)

import pytest  # noqa: E402

from rikugan.core.config import RikuganConfig  # noqa: E402
from rikugan.core.types import Message, Role  # noqa: E402
from rikugan.ida.ui.session_controller import IdaSessionController  # noqa: E402
from rikugan.state.history import SessionHistory  # noqa: E402
from rikugan.ui.panel_core import RikuganPanelCore  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_rikugan_modules_after_integration_tests():
    """Restore the real rikugan modules once this test module finishes."""
    yield
    for name, original in _STUBBED_MODULE_BACKUPS.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


# ---------------------------------------------------------------------------
# Stable IDB-instance identity for the test run.
#
# Production reads/writes ``db_instance_id`` through an IDA netnode so the
# same IDB yields the same id across ``IdaSessionController`` instances.
# ``tests/mocks/ida_mock.py`` already provides a ``_PersistentNetnode`` that
# achieves this when the mock is installed before ``rikugan.core.host`` is
# imported. However, collection-order pollution (another test module
# importing ``rikugan.core.host`` before us with ``is_ida() == False``) can
# disable the persistent path. Rather than depend on collection order, we
# install a stable path -> id map and monkey-patch the host helpers.
# ---------------------------------------------------------------------------
_IDB_INSTANCE_MAP: dict[str, str] = {}


def _stable_instance_for(idb_path: str) -> str:
    """Return a deterministic 32-hex id for ``idb_path`` (assigned lazily).

    Uses uuid5 (deterministic, no hashseed) so the same idb_path yields
    the same 32-hex lowercase id across test runs and across processes.
    """
    import uuid

    normalized = os.path.normcase(os.path.realpath(idb_path))
    if normalized not in _IDB_INSTANCE_MAP:
        # uuid5 is deterministic across runs (unlike Python's hash()).
        # The result is a 32-char lowercase hex string, matching what
        # ``rikugan.core.host.set_database_instance_id`` writes to the
        # netnode and what ``_canonical_instance_id`` expects.
        _IDB_INSTANCE_MAP[normalized] = uuid.uuid5(uuid.NAMESPACE_URL, f"rikugan-test://{normalized}").hex
    return _IDB_INSTANCE_MAP[normalized]


# Rebind the host helpers used by the controller. The controller module
# does ``from ..core.host import get_database_instance_id`` at import
# time, which binds the FUNCTION OBJECT (not a deferred lookup) into its
# own namespace. So patching only ``rikugan.core.host.X`` has no effect:
# the controller keeps the original reference. We must rebind BOTH the
# host module attributes AND the controller module's bound imports.
import rikugan.core.host as _host  # noqa: E402
import rikugan.ui.session_controller_base as _scb  # noqa: E402

_CURRENT_IDB_PATH = {"path": ""}


def _patched_get_database_instance_id() -> str:
    path = _CURRENT_IDB_PATH["path"]
    if not path:
        return ""
    return _stable_instance_for(path)


def _patched_set_database_instance_id(_instance_id: str) -> bool:
    # The controller always passes a freshly-derived id for the current
    # path. We accept it and treat the mapping as idempotent so the id
    # never drifts within a test run.
    return True


_host.get_database_instance_id = _patched_get_database_instance_id
_host.set_database_instance_id = _patched_set_database_instance_id
# CRITICAL: rebind the controller's already-imported references too.
_scb.get_database_instance_id = _patched_get_database_instance_id
_scb.set_database_instance_id = _patched_set_database_instance_id


# ---------------------------------------------------------------------------
# Minimal tracking QTabWidget stub. Production calls ``addTab`` /
# ``removeTab`` / ``setCurrentIndex`` / ``indexOf`` / ``widget`` / ``count``.
# We track inserted widgets on a list so ``tab_count()`` reflects reality.
# ---------------------------------------------------------------------------
class _FakeTabWidget:
    def __init__(self):
        self._tabs: list = []
        self._current = -1

    def addTab(self, widget, label):
        self._tabs.append(widget)
        self._current = len(self._tabs) - 1
        return self._current

    def removeTab(self, index):
        if 0 <= index < len(self._tabs):
            del self._tabs[index]
            if self._current >= len(self._tabs):
                self._current = len(self._tabs) - 1

    def setCurrentIndex(self, index):
        self._current = index

    def currentIndex(self):
        return self._current

    def count(self):
        return len(self._tabs)

    def widget(self, index):
        if 0 <= index < len(self._tabs):
            return self._tabs[index]
        return None

    def indexOf(self, widget):
        try:
            return self._tabs.index(widget)
        except ValueError:
            return -1


class _FakeSignal:
    def __init__(self):
        self._slots: list = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self._slots.clear()
        elif slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *_args, **_kwargs):
        for slot in list(self._slots):
            slot(*_args, **_kwargs)


class _FakeChatView:
    """Minimal stand-in for ``ChatView``.

    ``_create_tab`` connects Qt signals on the view; we expose
    ``setProperty`` for the ``tab_id`` lookup and no-op ``shutdown`` /
    ``restore_from_messages_async`` so the panel can tear us down without
    crashing.
    """

    def __init__(self):
        self._props: dict[str, object] = {}
        # Attributes accessed via ``chat_view.tool_approval_submitted.connect``
        # etc. -- fake Qt signals.
        self.tool_approval_submitted = _FakeSignal()
        self.user_answer_submitted = _FakeSignal()
        self.orchestra_approval_decided = _FakeSignal()

    def setProperty(self, name, value):
        self._props[name] = value

    def property(self, name):
        return self._props.get(name)

    def shutdown(self):
        pass

    def restore_from_messages_async(self, _messages):
        pass

    def deleteLater(self):
        pass


# Replace the stubbed ``ChatView`` import on the stub module with our fake
# so ``_create_tab`` constructs instances of ``_FakeChatView``.
_chat_view_stub = sys.modules.get("rikugan.ui.chat_view")
if _chat_view_stub is not None:
    _chat_view_stub.ChatView = _FakeChatView


# ---------------------------------------------------------------------------
# Recording HistoryPanel -- records the calls PanelCore makes on the
# HistoryPanel. Mirrors the subset of the ``HistoryPanel`` public API
# exercised by PanelCore (``set_entries`` / ``set_loading`` / ``set_error``
# / ``clear`` / ``visible_session_ids`` / ``isVisible``).
# ---------------------------------------------------------------------------
class _RecordingHistoryPanel:
    def __init__(self):
        self.entries: list = []
        self.loading_calls = 0
        self.error_calls: list[tuple[str, bool]] = []
        self.cleared = 0
        self._visible = False

    def setVisible(self, visible):
        self._visible = bool(visible)

    def isVisible(self):
        return self._visible

    def set_entries(self, entries):
        self.entries = list(entries)

    def set_loading(self):
        self.loading_calls += 1

    def set_error(self, message, retry_visible=True):
        self.error_calls.append((message, bool(retry_visible)))

    def clear(self):
        self.cleared += 1
        self.entries = []

    def visible_session_ids(self):
        return [e.session_id for e in self.entries]

    def shutdown(self):
        pass


def _build_panel(ctrl: IdaSessionController) -> RikuganPanelCore:
    """Construct a real ``RikuganPanelCore`` instance via ``__new__``.

    Bypasses ``__init__`` (which would touch every IDA / provider / Qt
    dependency) and seeds the history-coordinator fields the brief lists
    so the panel's history code paths can be exercised deterministically.
    """
    panel = RikuganPanelCore.__new__(RikuganPanelCore)
    panel._is_shutdown = False
    panel._polling = False
    panel._pending_answer = False
    panel._chat_views: dict[str, object] = {}
    panel._pending_restore_messages: dict[str, list] = {}
    panel._context_bar = None
    panel._mutation_panel = MagicMock()
    panel._skills_refresh_timer = None
    panel._poll_timer = None
    panel._pending_token_display = None
    panel._token_display_timer = None
    panel._last_token_display_value = -1
    panel._input_area = MagicMock()
    panel._send_btn = MagicMock()
    panel._cancel_btn = MagicMock()
    panel._mutations_btn = MagicMock()
    panel._history_btn = MagicMock()
    panel._count_label = MagicMock()
    panel._tab_bar = MagicMock()
    panel._ui_hooks = None
    panel._awaiting_button_approval = False
    # The real controller. Tests that need to read live controller state
    # (``active_session`` / ``tab_count``) do so through this object.
    panel._ctrl = ctrl
    panel._config = ctrl.config
    # Tracking tab widget so ``tab_count()`` reflects real ``addTab`` /
    # ``removeTab`` calls made by the panel's history slots.
    panel._tab_widget = _FakeTabWidget()
    # History coordinator fields (Task 8/9/10 -- spec section 8.1, 11.4).
    panel._history_panel = _RecordingHistoryPanel()
    panel._history_generation = 0
    panel._history_executor = None
    import queue

    panel._history_result_queue = queue.Queue(maxsize=2)
    panel._history_poll_timer = None
    panel._history_pending = False
    panel._history_closing = threading.Event()
    panel._history_retry_load_session_id = None
    panel._history_last_load_session_id = None
    # Initial tab: panel construction always creates exactly one empty
    # ``New Chat`` tab in production (``_build_ui``); replicate that here
    # so ``tab_count() == 1`` from the start.
    panel._create_tab(ctrl.active_tab_id, "New Chat")
    return panel


class _HistoryOnDemandFacade:
    """High-level facade that maps the brief's behavioral outline onto
    real panel slot calls.

    Each method is a thin wrapper over the production panel slot so the
    integration test asserts behavior through the same code paths IDA's
    UI would trigger. No ``time.sleep`` -- workers are drained
    deterministically via ``_drain_history_results`` after the worker
    future resolves.
    """

    def __init__(self, panel: RikuganPanelCore):
        self._panel = panel

    # --- assertions helpers --------------------------------------------
    def tab_count(self) -> int:
        return self._panel._tab_widget.count()

    @property
    def active_session(self):
        return self._panel._ctrl.session

    def visible_history_ids(self) -> set[str]:
        return set(self._panel._history_panel.visible_session_ids())

    # --- behavioral actions --------------------------------------------
    def open_history(self) -> None:
        """Toggle the History button ON, then submit a list request.

        Production path: ``_on_history_btn_toggled(True)`` leads to
        ``_show_right_panel("history")`` + ``_start_history_list_request``.
        Here we go straight to ``_start_history_list_request`` after
        marking the panel visible so the drain's visibility check keeps
        the timer alive; the result is drained synchronously.
        """
        self._panel._history_panel.setVisible(True)
        self._panel._start_history_list_request()
        # Wait for the single-worker executor to finish the list job so
        # the typed result is in the queue. The executor is a
        # ``ThreadPoolExecutor(max_workers=1)``; ``shutdown(wait=True)``
        # blocks until the worker enqueues and exits, with no timeout
        # because the worker has no external dependency beyond
        # ``SessionHistory`` (which reads a local temp directory).
        executor = self._panel._history_executor
        if executor is not None:
            executor.shutdown(wait=True)
            # Re-create the executor so a subsequent open_history /
            # open_history_session can submit again. In production the
            # panel reuses the executor until ``_invalidate_history``
            # drops it; here we mirror that lazily-fresh behavior.
            from concurrent.futures import ThreadPoolExecutor

            self._panel._history_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="rikugan-history",
            )
        self._panel._drain_history_results()

    def open_history_session(self, session_id: str) -> None:
        """Click a row: pre-dedupe, load worker, drain, apply attach."""
        self._panel._on_history_open_requested(session_id)
        executor = self._panel._history_executor
        if executor is not None:
            executor.shutdown(wait=True)
            from concurrent.futures import ThreadPoolExecutor

            self._panel._history_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="rikugan-history",
            )
        self._panel._drain_history_results()

    def on_database_changed(self, new_path: str) -> None:
        # Sync the stable-instance map cell BEFORE the controller reset
        # so ``_ensure_db_instance_id`` reads the new id.
        _CURRENT_IDB_PATH["path"] = new_path
        self._panel.on_database_changed(new_path)

    def shutdown(self) -> None:
        self._panel._is_shutdown = True
        try:
            self._panel._invalidate_history(clear_panel=False)
        except Exception:
            pass


def _persist_session(
    cfg: RikuganConfig,
    *,
    idb_path: str,
    db_instance_id: str,
    user_content: str,
    assistant_content: str = "ok",
) -> str:
    """Persist one non-empty session for ``idb_path`` via ``SessionHistory``.

    Returns the persisted ``SessionState.id`` so the test can reference it
    by its manifest identity (not its in-memory tab id).
    """
    from rikugan.state.session import SessionState

    session = SessionState(
        idb_path=idb_path,
        db_instance_id=db_instance_id,
    )
    session.add_message(Message(role=Role.USER, content=user_content))
    session.add_message(Message(role=Role.ASSISTANT, content=assistant_content))
    SessionHistory(cfg).save_session(session)
    SessionHistory.flush_saves()
    return session.id


# ---------------------------------------------------------------------------
# The behavioral regression scenario (spec section 14.5).
# ---------------------------------------------------------------------------
class TestHistoryOnDemandIntegration(unittest.TestCase):
    """Spec section 14.5 behavioral outline as one deterministic scenario."""

    def setUp(self):
        # Fresh IDB-instance map so each test is hermetic.
        _IDB_INSTANCE_MAP.clear()
        # Fresh controller-backed temp config dir for real persistence.
        self._tmp_root = tempfile.mkdtemp(prefix="rikugan-int-")
        self.cfg = RikuganConfig()
        self.cfg._config_dir = self._tmp_root

        # IDB-A / IDB-B paths inside the same temp tree.
        self.idb_a = os.path.join(self._tmp_root, "a.i64")
        self.idb_b = os.path.join(self._tmp_root, "b.i64")
        # Stable ids for each IDB, matching what the patched host helpers
        # would yield for those paths.
        _CURRENT_IDB_PATH["path"] = self.idb_a
        self.idb_a_instance = _stable_instance_for(self.idb_a)
        self.idb_b_instance = _stable_instance_for(self.idb_b)

        # Persist two non-empty IDB-A sessions + one IDB-B session BEFORE
        # constructing any panel/controller. This mirrors "prior sessions
        # exist on disk" -- the brief's starting state.
        self.a1_id = _persist_session(
            self.cfg,
            idb_path=self.idb_a,
            db_instance_id=self.idb_a_instance,
            user_content="Analyze parser",
            assistant_content="parser ok",
        )
        self.a2_id = _persist_session(
            self.cfg,
            idb_path=self.idb_a,
            db_instance_id=self.idb_a_instance,
            user_content="Triage imports",
            assistant_content="imports ok",
        )
        self.b1_id = _persist_session(
            self.cfg,
            idb_path=self.idb_b,
            db_instance_id=self.idb_b_instance,
            user_content="Identify crypto",
            assistant_content="crypto ok",
        )

        # The controller uses ``_config_dir`` to find the sessions dir.
        # The patched host helpers resolve the live db_instance_id from
        # ``_CURRENT_IDB_PATH`` so the controller sees the same stable
        # ids we persisted with.
        _CURRENT_IDB_PATH["path"] = self.idb_a
        self.ctrl = IdaSessionController(self.cfg)
        self.panel = _build_panel(self.ctrl)
        self.facade = _HistoryOnDemandFacade(self.panel)

    def tearDown(self):
        try:
            self.facade.shutdown()
        finally:
            SessionHistory.flush_saves()
            self.ctrl.shutdown()
            shutil.rmtree(self._tmp_root, ignore_errors=True)

    def test_startup_one_empty_new_chat(self):
        """Spec 7.1: opening Rikugan shows exactly one empty New Chat."""
        self.assertEqual(self.facade.tab_count(), 1)
        self.assertEqual(self.facade.active_session.messages, [])

    def test_history_lists_only_current_idb(self):
        """Spec 8.3: History lists only sessions for the current IDB."""
        self.facade.open_history()
        self.assertEqual(
            self.facade.visible_history_ids(),
            {self.a1_id, self.a2_id},
        )

    def test_open_creates_one_tab_then_focus_no_duplicate(self):
        """Spec 10.2: open creates one tab; selecting again focuses it."""
        self.assertEqual(self.facade.tab_count(), 1)
        self.facade.open_history()
        self.facade.open_history_session(self.a1_id)
        self.assertEqual(self.facade.tab_count(), 2)
        # Selecting the SAME persisted id again must focus the existing
        # tab, not open a duplicate (pre- or post-load dedupe).
        self.facade.open_history_session(self.a1_id)
        self.assertEqual(self.facade.tab_count(), 2)

    def test_idb_switch_resets_one_empty_new_chat(self):
        """Spec 7.2: switching IDBs leaves exactly one empty New Chat
        for the new IDB. The previous IDB's chats remain on disk.
        """
        self.facade.on_database_changed(self.idb_b)
        self.assertEqual(self.facade.tab_count(), 1)
        self.assertEqual(self.facade.active_session.messages, [])
        self.facade.open_history()
        self.assertEqual(
            self.facade.visible_history_ids(),
            {self.b1_id},
        )

    def test_restart_again_starts_one_empty_new_chat(self):
        """Spec 14.5 step 11: restarting the panel again starts with
        one empty tab. The previous IDB's chats are still on disk.
        """
        # First switch to IDB-B so the restart scenario mirrors the
        # brief outline (panel_restart = make_panel(idb_b)).
        self.facade.on_database_changed(self.idb_b)
        # Simulate a panel restart: tear down the current panel and
        # construct a fresh one for IDB-B.
        self.facade.shutdown()
        SessionHistory.flush_saves()
        self.ctrl.shutdown()

        _CURRENT_IDB_PATH["path"] = self.idb_b
        ctrl2 = IdaSessionController(self.cfg)
        try:
            panel2 = _build_panel(ctrl2)
            facade2 = _HistoryOnDemandFacade(panel2)
            self.assertEqual(facade2.tab_count(), 1)
            self.assertEqual(facade2.active_session.messages, [])
            facade2.shutdown()
        finally:
            SessionHistory.flush_saves()
            ctrl2.shutdown()

    def test_full_scenario_in_one_flow(self):
        """The complete behavioral outline from the brief, executed in
        sequence against one panel/controller pair.

        Asserts every step the brief lists, in order, so a regression in
        any of the sub-behaviors fails at the specific assertion that
        detected it.
        """
        # Step 1: startup exactly one empty New Chat.
        self.assertEqual(self.facade.tab_count(), 1)
        self.assertEqual(self.facade.active_session.messages, [])

        # Step 2: open History -- only IDB-A entries appear.
        self.facade.open_history()
        self.assertEqual(
            self.facade.visible_history_ids(),
            {self.a1_id, self.a2_id},
        )

        # Step 3: open a1 -> one additional tab.
        self.facade.open_history_session(self.a1_id)
        self.assertEqual(self.facade.tab_count(), 2)

        # Step 4: open a1 again -> focus, no duplicate.
        self.facade.open_history_session(self.a1_id)
        self.assertEqual(self.facade.tab_count(), 2)

        # Step 5: switch to IDB-B -> exactly one empty New Chat.
        self.facade.on_database_changed(self.idb_b)
        self.assertEqual(self.facade.tab_count(), 1)
        self.assertEqual(self.facade.active_session.messages, [])

        # Step 6: open History -- only IDB-B's entry appears.
        self.facade.open_history()
        self.assertEqual(self.facade.visible_history_ids(), {self.b1_id})

        # Step 7: restart panel for IDB-B -> again exactly one empty tab.
        self.facade.shutdown()
        SessionHistory.flush_saves()
        self.ctrl.shutdown()
        _CURRENT_IDB_PATH["path"] = self.idb_b
        ctrl2 = IdaSessionController(self.cfg)
        try:
            panel2 = _build_panel(ctrl2)
            facade2 = _HistoryOnDemandFacade(panel2)
            self.assertEqual(facade2.tab_count(), 1)
            self.assertEqual(facade2.active_session.messages, [])
            facade2.shutdown()
        finally:
            SessionHistory.flush_saves()
            ctrl2.shutdown()


if __name__ == "__main__":
    unittest.main()
