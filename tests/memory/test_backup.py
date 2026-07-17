"""Tests for SQLite backup: coherent snapshot, restore, integrity."""

from __future__ import annotations

from pathlib import Path

import pytest

from rikugan.memory.backup import create_backup, list_backups, restore_from_backup
from rikugan.memory.workspace import MemoryLocator, WorkspacePaths, new_memory_id, new_record_id
from rikugan.memory.workspace_store import WorkspaceStore


def _create_workspace(tmp_path: Path) -> tuple[WorkspaceStore, WorkspacePaths, str]:
    mid = new_memory_id()
    locator = MemoryLocator(tmp_path / "memory")
    paths = locator.binary(mid)
    store = WorkspaceStore.create(paths, owner_memory_id=mid)
    store.put_fact(new_record_id("fact"), "test", "T", "Hello backup", 0.8, expected_revision=0)
    return store, paths, mid


class TestBackup:
    def test_create_backup_preserves_data(self, tmp_path: Path) -> None:
        store, paths, mid = _create_workspace(tmp_path)
        backup_dir = tmp_path / "backups"

        result = create_backup(paths, mid, backup_dir)
        assert result.backup_path.exists()
        assert result.db_size > 0
        assert len(result.manifest_hash) == 64

        # Verify backup contains the fact
        import sqlite3

        conn = sqlite3.connect(str(result.backup_path))
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) AS c FROM facts").fetchone()["c"]
        assert count == 1
        conn.close()
        store.close()

    def test_list_backups_sorted_newest_first(self, tmp_path: Path) -> None:
        _store, paths, mid = _create_workspace(tmp_path)
        backup_dir = tmp_path / "backups"

        import time

        create_backup(paths, mid, backup_dir)
        time.sleep(1.2)  # ensure distinct timestamps
        create_backup(paths, mid, backup_dir)

        backups = list_backups(backup_dir)
        assert len(backups) == 2
        # Newest first
        assert backups[0].stat().st_mtime >= backups[1].stat().st_mtime

    def test_list_backups_empty(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "no_backups"
        assert list_backups(backup_dir) == []

    def test_restore_from_backup(self, tmp_path: Path) -> None:
        store, paths, mid = _create_workspace(tmp_path)
        backup_dir = tmp_path / "backups"
        result = create_backup(paths, mid, backup_dir)
        store.close()

        # Restore into a new workspace
        new_mid = new_memory_id()
        new_locator = MemoryLocator(tmp_path / "restored")
        new_paths = new_locator.binary(new_mid)
        restored = restore_from_backup(result.backup_path, new_paths, new_mid)

        # Verify restored data
        facts = restored.list_facts()
        assert len(facts) == 1
        assert "Hello backup" in facts[0].content
        restored.close()

    def test_backup_missing_db_raises(self, tmp_path: Path) -> None:
        mid = new_memory_id()
        locator = MemoryLocator(tmp_path / "memory")
        paths = locator.binary(mid)
        with pytest.raises(FileNotFoundError):
            create_backup(paths, mid, tmp_path / "backups")
