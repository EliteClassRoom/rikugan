"""Immutable shared contracts for Chat History On-Demand.

This module is deliberately Qt-free and persistence-internal-free so the
history worker (background thread), ``SessionControllerBase``, and the
``HistoryPanel`` widget can all exchange typed, immutable values without
importing each other. It is the only place the DTO/status shapes live; any
consumer that re-declares them will drift from the wire format.

Frozen dataclasses enforce immutability because history results cross a
thread boundary (Python worker -> ``queue.Queue`` -> Qt main thread) and a
mutated DTO would be a race condition that is silent until the UI renders
stale data. See ``docs/superpowers/specs/2026-07-16-chat-history-on-demand-design.md``
sections 6.2, 8, and 10.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rikugan.state.session import SessionState


@dataclass(frozen=True)
class SessionHistoryEntry:
    """Display-only metadata row for one persisted session.

    The UI list never receives loose manifest dictionaries. ``updated_at`` is
    derived from the session file mtime; ``message_count`` is the raw
    message-array length recorded at last save/rebuild and may exceed the
    rendered count if ``load_session`` later skips a corrupt message.
    """

    session_id: str
    title: str
    created_at: float
    updated_at: float
    provider: str
    model: str
    message_count: int


@dataclass(frozen=True)
class HistoryScope:
    """Immutable snapshot of "which IDB, at which generation" a request targets.

    Captured on the Qt main thread before any background I/O so the worker
    never reads live controller fields while an IDB switch may be mutating
    them. ``generation`` lets the main thread discard a result produced for a
    stale scope after an IDB change or shutdown.
    """

    idb_path: str
    db_instance_id: str
    generation: int


class HistoryRequestStatus(str, Enum):
    """Outcome of a list or load request.

    String values are stable wire identifiers surfaced to the UI; they must
    not be renamed without coordinating every consumer (worker, controller,
    panel error states).
    """

    LISTED = "listed"
    LOADED = "loaded"
    NOT_FOUND = "not_found"
    WRONG_IDB = "wrong_idb"
    EMPTY = "empty"
    SAVE_FLUSH_TIMEOUT = "save_flush_timeout"
    FAILED = "failed"


class HistoryAttachStatus(str, Enum):
    """Outcome of attaching a loaded session on the Qt main thread."""

    OPENED = "opened"
    ALREADY_OPEN = "already_open"
    STALE_SCOPE = "stale_scope"


@dataclass(frozen=True)
class HistoryListResult:
    """Typed terminal result of a background history-list request.

    The worker always enqueues exactly one ``HistoryListResult`` per
    request — success or failure. Exceptions are never used for
    cross-thread control flow (spec §8.1, §11.4, §13). ``scope`` is
    echoed so the Qt-main-thread drain can reject a stale generation
    before touching the widget.

    ``entries`` is empty on every non-success status so the UI cannot
    render a partially-stale list after a save-flush timeout or an
    unexpected exception.
    """

    status: HistoryRequestStatus
    scope: HistoryScope
    entries: tuple[SessionHistoryEntry, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class HistoryLoadResult:
    """Typed result of a background ``load_history_session`` request.

    The worker always emits exactly one terminal result (success or failure);
    exceptions are never used for cross-thread control flow. ``scope`` is
    echoed back so the main-thread drain can reject stale generations before
    touching ``_sessions`` or Qt.
    """

    status: HistoryRequestStatus
    scope: HistoryScope
    session: SessionState | None = None
    error: str = ""


@dataclass(frozen=True)
class HistoryAttachResult:
    """Typed result of ``attach_history_session`` (Qt main thread only)."""

    status: HistoryAttachStatus
    tab_id: str = ""
    session: SessionState | None = None
