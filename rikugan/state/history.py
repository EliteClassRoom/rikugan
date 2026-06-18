"""Session history: persist, list, and restore past sessions.

This is the single persistence layer for all session state.
Includes a versioned session manifest (index file) for fast startup
filtering without opening/parsing every session JSON.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Any

from ..constants import SESSION_SCHEMA_VERSION
from ..core.config import RikuganConfig
from ..core.logging import log_debug, log_warning
from ..core.types import Message
from .session import SessionState

MANIFEST_FILE = "_session_manifest.json"
MANIFEST_SCHEMA_VERSION = 1

#: Fork writes a ``{id}.summary.json`` beside each session with ``messages``
#: as an int count (not a list) for fast listing. MAIN never writes these,
#: but they linger on disk after a user runs the fork, so directory scans
#: must skip them rather than treat them as sessions.
_SUMMARY_SUFFIX = ".summary.json"


def _normalize_db_path(path: str) -> str:
    """Return a stable canonical DB path for session filtering."""
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))
    except OSError:
        return path


class SessionHistory:
    """Manages saved sessions on disk.

    Uses a versioned manifest (JSON index) for fast session listing.
    The manifest is validated against file mtime/size before trusting.
    Falls back to full directory scan for backfill/recovery.
    """

    # Process-local lock serialises manifest read-modify-write operations
    # so concurrent saves in the *same process* (e.g. multiple tabs) cannot
    # silently drop entries.
    _manifest_lock = threading.RLock()

    def __init__(self, config: RikuganConfig):
        self._dir = os.path.join(config.checkpoints_dir, "sessions")
        os.makedirs(self._dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Manifest helpers
    # ------------------------------------------------------------------

    def _manifest_path(self) -> str:
        return os.path.join(self._dir, MANIFEST_FILE)

    def _read_manifest(self) -> dict[str, Any]:
        """Read the session manifest.

        Returns **entries** (``{'entries': {...}, 'version': int,
        'last_full_scan': 0}``) or ``{}`` if missing or corrupt.
        """
        path = self._manifest_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log_debug(f"Session manifest corrupt: {exc}")
            return {}
        if not isinstance(data, dict):
            return {}
        version = data.get("version", 0)
        if version != MANIFEST_SCHEMA_VERSION:
            log_debug(f"Session manifest version mismatch ({version} != {MANIFEST_SCHEMA_VERSION}), rebuilding")
            return {}
        entries = data.get("entries", {})
        if not isinstance(entries, dict):
            return {}
        return data

    def _write_manifest(self, entries: dict[str, dict[str, Any]], last_full_scan: float = 0.0) -> None:
        """Atomically write the session manifest to disk.

        Writes to a temp file and renames to avoid partial/corrupt writes.
        Cleans up the temp file on any write failure.
        """
        path = self._manifest_path()
        data: dict[str, Any] = {
            "version": MANIFEST_SCHEMA_VERSION,
            "entries": entries,
        }
        if last_full_scan > 0:
            data["last_full_scan"] = last_full_scan
        tmp_path = ""
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self._dir, prefix=".manifest_tmp_")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            log_warning(f"Failed to write session manifest: {e}")
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError as cleanup_err:
                    log_warning(f"Failed to clean up temp manifest {tmp_path}: {cleanup_err}")
            raise

    def _build_manifest_entry(self, session: SessionState, description: str = "") -> dict[str, Any]:
        """Build a manifest entry dict for a session.

        Uses ``st_mtime_ns`` (nanosecond precision) for reliable
        validation, falling back to ``int(st_mtime * 1e9)`` on older
        Python where ``st_mtime_ns`` is unavailable.
        """
        db_path = _normalize_db_path(session.idb_path)
        file_path = os.path.join(self._dir, f"{session.id}.json")
        try:
            st = os.stat(file_path)
            file_mtime = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
            file_size = st.st_size
        except OSError:
            file_mtime = 0
            file_size = 0
        return {
            "created_at": session.created_at,
            "provider": session.provider_name,
            "model": session.model_name,
            "idb_path": db_path,
            "db_instance_id": session.db_instance_id,
            "messages": len(session.messages),
            "description": description,
            "file_mtime_ns": file_mtime,
            "file_size": file_size,
        }

    def _update_manifest_entry(self, session: SessionState, description: str = "") -> None:
        """Add or update a manifest entry for *session*.

        Locked internally so concurrent saves in the same process do not
        drop entries.  Failure to update the manifest is non-fatal — the
        session JSON has already been saved and the manifest can be rebuilt
        on next startup.
        """
        try:
            with self._manifest_lock:
                data = self._read_manifest()
                entries = data.get("entries", {})
                last_full_scan = data.get("last_full_scan", 0.0)
                entries[session.id] = self._build_manifest_entry(session, description)
                try:
                    self._write_manifest(entries, last_full_scan=last_full_scan)
                except OSError as write_err:
                    log_warning(f"Failed to update session manifest after saving {session.id}: {write_err}")
        except Exception as e:
            log_warning(f"Failed to update session manifest entry for {session.id}: {e}")

    def _remove_manifest_entry(self, session_id: str) -> None:
        """Remove a manifest entry by session id."""
        with self._manifest_lock:
            data = self._read_manifest()
            entries = data.get("entries", {})
            last_full_scan = data.get("last_full_scan", 0.0)
            if session_id in entries:
                del entries[session_id]
                try:
                    self._write_manifest(entries, last_full_scan=last_full_scan)
                except OSError as write_err:
                    log_warning(f"Failed to write session manifest after removing {session_id}: {write_err}")

    def _validate_manifest_entry(self, session_id: str, entry: dict[str, Any]) -> bool:
        """Check that the session file on disk matches the manifest entry.

        Returns True if the file exists and its mtime_ns/size match.
        Uses ``st_mtime_ns`` for nanosecond precision; falls back to
        ``int(st_mtime * 1e9)``.
        """
        file_path = os.path.join(self._dir, f"{session_id}.json")
        try:
            st = os.stat(file_path)
        except OSError:
            return False
        stored_mtime = entry.get("file_mtime_ns", 0)
        stored_size = entry.get("file_size", 0)
        current_mtime = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        return stored_mtime == current_mtime and stored_size == st.st_size

    def _rebuild_manifest(self) -> dict[str, dict[str, Any]]:
        """Full scan of session JSON files and rebuild the manifest.

        Called on first run (no manifest) or when the manifest is stale/corrupt.
        Writes the manifest under the class-level lock; write failure is
        non-fatal — entries are always returned.
        """
        entries: dict[str, dict[str, Any]] = {}
        try:
            fnames = os.listdir(self._dir)
        except OSError:
            return entries
        for fname in sorted(fnames):
            if not fname.endswith(".json") or fname == MANIFEST_FILE:
                continue
            # Skip fork summary files: their "messages" is an int count, not a
            # list, and their id-slice (fname[:-5]) would yield "{id}.summary".
            if fname.endswith(_SUMMARY_SUFFIX):
                continue
            path = os.path.join(self._dir, fname)
            try:
                with open(path) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                log_debug(f"Skipping corrupt session JSON {fname}: {exc}")
                continue
            sid = data.get("id", fname[:-5])
            try:
                st = os.stat(path)
                file_mtime = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
                file_size = st.st_size
            except OSError:
                file_mtime = 0
                file_size = 0
            entries[sid] = {
                "created_at": data.get("created_at", 0),
                "provider": data.get("provider_name", ""),
                "model": data.get("model_name", ""),
                "idb_path": _normalize_db_path(data.get("idb_path", "")),
                "db_instance_id": data.get("db_instance_id", ""),
                "messages": len(data.get("messages", [])),
                "description": data.get("description", ""),
                "file_mtime_ns": file_mtime,
                "file_size": file_size,
            }
        last_full_scan = time.time()
        with self._manifest_lock:
            try:
                self._write_manifest(entries, last_full_scan=last_full_scan)
            except OSError as write_err:
                log_warning(
                    f"Failed to write rebuilt session manifest: {write_err}. "
                    f"Session listing will still work from directory scan."
                )
        return entries

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save_session(self, session: SessionState, description: str = "") -> str:
        """Save a session atomically and return the file path."""
        path = os.path.join(self._dir, f"{session.id}.json")
        db_path = _normalize_db_path(session.idb_path)
        data = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "id": session.id,
            "created_at": session.created_at,
            "provider_name": session.provider_name,
            "model_name": session.model_name,
            "idb_path": db_path,
            "db_instance_id": session.db_instance_id,
            "current_turn": session.current_turn,
            "metadata": session.metadata,
            "messages": [m.to_dict() for m in session.messages],
        }
        if session.subagent_logs:
            data["subagent_logs"] = {key: [m.to_dict() for m in msgs] for key, msgs in session.subagent_logs.items()}
        if description:
            data["description"] = description
        # Write to temp file first, then atomically rename to final path.
        tmp_path = ""
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self._dir, prefix=".session_tmp_")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            log_warning(f"Failed to save session {session.id}: {e}")
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError as cleanup_err:
                    log_warning(f"Failed to clean up temp session {tmp_path}: {cleanup_err}")
            raise
        # Update manifest.  Failure is non-fatal — the session JSON has
        # already been saved atomically and the manifest can be rebuilt
        # from the directory on next startup.
        try:
            self._update_manifest_entry(session, description=description)
        except Exception as manifest_err:
            log_warning(f"Failed to update session manifest for {session.id}: {manifest_err}")
        return path

    def load_session(self, session_id: str) -> SessionState | None:
        """Load a session by ID. Returns None if not found or corrupt."""
        path = os.path.join(self._dir, f"{session_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log_debug(f"Failed to load session {session_id}: {exc}")
            return None
        session = SessionState(
            id=data["id"],
            created_at=data.get("created_at", 0),
            provider_name=data.get("provider_name", ""),
            model_name=data.get("model_name", ""),
            idb_path=data.get("idb_path", ""),
            db_instance_id=data.get("db_instance_id", ""),
            current_turn=data.get("current_turn", 0),
            metadata=data.get("metadata", {}),
        )
        for md in data.get("messages", []):
            session.messages.append(Message.from_dict(md))
        for key, msg_dicts in data.get("subagent_logs", {}).items():
            session.subagent_logs[key] = [Message.from_dict(md) for md in msg_dicts]
        return session

    def list_sessions(self, idb_path: str = "", db_instance_id: str = "") -> list[dict[str, Any]]:
        """List saved session summaries, filtered by IDB path and instance ID.

        Uses the session manifest for fast filtering when available.
        Falls back to scanning JSON files if the manifest is missing,
        corrupt, or stale.
        """
        normalized_target = _normalize_db_path(idb_path)

        # Try manifest first
        manifest_data = self._read_manifest()
        entries = manifest_data.get("entries", {}) if manifest_data else {}

        if not entries:
            # No manifest or corrupt — rebuild from disk
            entries = self._rebuild_manifest()
            if not entries:
                return []

        # Detect whether there may be JSON files unknown to the manifest
        # (pre-manifest or added outside the normal save path).
        last_full_scan = manifest_data.get("last_full_scan", 0.0)
        need_rebuild = last_full_scan == 0

        if not need_rebuild and last_full_scan > 0:
            # Quick check: if any session JSON file on disk is not in the
            # manifest the listing would silently miss that session.
            try:
                json_ids = {
                    fname[:-5]
                    for fname in os.listdir(self._dir)
                    if fname.endswith(".json") and fname != MANIFEST_FILE and not fname.endswith(_SUMMARY_SUFFIX)
                }
            except OSError as scan_err:
                log_warning(f"Failed to scan sessions directory for manifest validation: {scan_err}")
                json_ids = set()
            if json_ids and not json_ids.issubset(set(entries.keys())):
                need_rebuild = True

        if need_rebuild:
            entries = self._rebuild_manifest()
            if not entries:
                return []

        sessions: list[dict[str, Any]] = []
        manifest_misses = 0
        for sid, entry in entries.items():
            # Filter by instance ID or IDB path
            if db_instance_id:
                if entry.get("db_instance_id", "") != db_instance_id:
                    continue
            elif normalized_target:
                if _normalize_db_path(entry.get("idb_path", "")) != normalized_target:
                    continue
            else:
                if entry.get("idb_path", ""):
                    continue

            # Validate against actual file on disk
            if not self._validate_manifest_entry(sid, entry):
                manifest_misses += 1
                continue

            sessions.append(
                {
                    "id": sid,
                    "created_at": entry.get("created_at", 0),
                    "provider": entry.get("provider", ""),
                    "model": entry.get("model", ""),
                    "idb_path": entry.get("idb_path", ""),
                    "db_instance_id": entry.get("db_instance_id", ""),
                    "messages": entry.get("messages", 0),
                    "description": entry.get("description", ""),
                }
            )

        # If many entries are stale, rebuild once and re-filter
        # in this same call — no recursion.
        if manifest_misses:
            log_debug(f"Manifest had {manifest_misses} stale entries, rebuilding")
            entries = self._rebuild_manifest()
            if not entries:
                return []
            # Re-filter with freshly rebuilt entries
            sessions.clear()
            for sid, entry in entries.items():
                if db_instance_id:
                    if entry.get("db_instance_id", "") != db_instance_id:
                        continue
                elif normalized_target:
                    if _normalize_db_path(entry.get("idb_path", "")) != normalized_target:
                        continue
                else:
                    if entry.get("idb_path", ""):
                        continue
                if not self._validate_manifest_entry(sid, entry):
                    continue
                sessions.append(
                    {
                        "id": sid,
                        "created_at": entry.get("created_at", 0),
                        "provider": entry.get("provider", ""),
                        "model": entry.get("model", ""),
                        "idb_path": entry.get("idb_path", ""),
                        "db_instance_id": entry.get("db_instance_id", ""),
                        "messages": entry.get("messages", 0),
                        "description": entry.get("description", ""),
                    }
                )

        if sessions:
            sessions.sort(key=lambda s: s.get("created_at", 0))
        return sessions

    def get_latest_session(self, idb_path: str = "", db_instance_id: str = "") -> SessionState | None:
        """Load the most recently saved session for this IDB."""
        sessions = self.list_sessions(idb_path=idb_path, db_instance_id=db_instance_id)
        if not sessions:
            return None
        sessions.sort(key=lambda s: s.get("created_at", 0), reverse=True)
        return self.load_session(sessions[0]["id"])

    def delete_session(self, session_id: str) -> bool:
        path = os.path.join(self._dir, f"{session_id}.json")
        if os.path.exists(path):
            os.remove(path)
            self._remove_manifest_entry(session_id)
            return True
        return False
