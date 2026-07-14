"""Tests for session binding round-trip with binary_memory_id/active_case_id."""

from __future__ import annotations

from pathlib import Path

from rikugan.core.config import RikuganConfig
from rikugan.state.history import SessionHistory
from rikugan.state.session import SessionState


def test_session_and_manifest_round_trip_memory_binding(tmp_path: Path) -> None:
    config = RikuganConfig()
    config._config_dir = str(tmp_path)
    session = SessionState(
        id="bound-session",
        idb_path="C:/samples/a.i64",
        db_instance_id="uuid-a",
        binary_memory_id="mem-" + "a" * 32,
        active_case_id="case-" + "b" * 32,
    )
    history = SessionHistory(config)
    history.save_session(session)
    loaded = history.load_session(session.id)

    assert loaded is not None
    assert loaded.binary_memory_id == session.binary_memory_id
    assert loaded.active_case_id == session.active_case_id


def test_list_sessions_filters_by_binary_memory_id(tmp_path: Path) -> None:
    config = RikuganConfig()
    config._config_dir = str(tmp_path)
    history = SessionHistory(config)

    mid = "mem-" + "c" * 32
    session_a = SessionState(
        id="session-a",
        idb_path="C:/samples/a.i64",
        binary_memory_id=mid,
    )
    session_b = SessionState(
        id="session-b",
        idb_path="C:/samples/b.i64",
        binary_memory_id="mem-" + "d" * 32,
    )
    history.save_session(session_a)
    history.save_session(session_b)

    results = history.list_sessions(binary_memory_id=mid)
    ids = [r["id"] for r in results]
    assert "session-a" in ids
    assert "session-b" not in ids


def test_v1_session_loads_with_empty_memory_fields(tmp_path: Path) -> None:
    """Old session JSON without memory fields loads with empty defaults."""
    import json

    config = RikuganConfig()
    config._config_dir = str(tmp_path)
    history = SessionHistory(config)

    # Write a v1-style session JSON without binary_memory_id/active_case_id
    session_dir = tmp_path / "checkpoints" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    legacy_data = {
        "schema_version": 1,
        "id": "legacy-session",
        "created_at": 1000.0,
        "provider_name": "anthropic",
        "model_name": "claude",
        "idb_path": "C:/samples/old.i64",
        "db_instance_id": "old-uuid",
        "current_turn": 0,
        "metadata": {},
        "messages": [],
    }
    (session_dir / "legacy-session.json").write_text(json.dumps(legacy_data), encoding="utf-8")

    loaded = history.load_session("legacy-session")
    assert loaded is not None
    assert loaded.binary_memory_id == ""
    assert loaded.active_case_id == ""
    assert loaded.idb_path == "C:/samples/old.i64"
