"""SQLite backup: coherent snapshot via Connection.backup() API.

Creates an offline copy of a workspace database using SQLite's native
backup mechanism, which produces a consistent point-in-time snapshot
even while the database is in use.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .workspace import WorkspacePaths
from .workspace_store import WorkspaceStore


@dataclass(frozen=True)
class BackupResult:
    """Result of a backup operation."""

    backup_path: Path
    manifest_hash: str
    db_size: int


def create_backup(
    paths: WorkspacePaths,
    owner_memory_id: str,
    backup_dir: Path,
) -> BackupResult:
    """Create a SQLite backup of a workspace database.

    Uses ``sqlite3.Connection.backup()`` for a coherent snapshot that
    does not require exclusive access to the source database.

    Parameters
    ----------
    paths:
        Workspace filesystem paths.
    owner_memory_id:
        Owner workspace ID (for validation).
    backup_dir:
        Directory to write the backup into.

    Returns the backup file path and manifest hash.
    """
    if not paths.database.exists():
        raise FileNotFoundError(f"workspace database not found: {paths.database}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    backup_name = f"memory_{owner_memory_id[:12]}_{timestamp}.db"
    backup_path = backup_dir / backup_name

    # Open source read-only and backup into destination
    source = sqlite3.connect(str(paths.database), uri=True)
    dest = sqlite3.connect(str(backup_path))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()

    # Compute hash for manifest
    data = backup_path.read_bytes()
    manifest_hash = hashlib.sha256(data).hexdigest()

    return BackupResult(
        backup_path=backup_path,
        manifest_hash=manifest_hash,
        db_size=len(data),
    )


def list_backups(backup_dir: Path) -> list[Path]:
    """List all backup files in a directory, sorted newest first."""
    if not backup_dir.exists():
        return []
    backups = sorted(
        backup_dir.glob("memory_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups


def restore_from_backup(
    backup_path: Path,
    target_paths: WorkspacePaths,
    owner_memory_id: str,
) -> WorkspaceStore:
    """Restore a workspace database from a backup file.

    Creates a new workspace at *target_paths* and copies all data from
    the backup. The caller is responsible for validating the restored
    data matches expectations.

    Returns the opened WorkspaceStore.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"backup not found: {backup_path}")

    # Validate backup is a readable SQLite database
    test_conn = sqlite3.connect(str(backup_path))
    try:
        test_conn.execute("SELECT COUNT(*) FROM workspace_meta")
    except sqlite3.OperationalError:
        test_conn.close()
        raise ValueError(f"backup is not a valid workspace database: {backup_path}") from None
    finally:
        test_conn.close()

    # Create target workspace and copy data
    target_store = WorkspaceStore.create(target_paths, owner_memory_id=owner_memory_id)
    target_store.close()

    # Overwrite with backup contents via SQLite backup API
    source = sqlite3.connect(str(backup_path))
    dest = sqlite3.connect(str(target_paths.database))
    try:
        source.backup(dest)
        # Update owner to match the new target
        dest.execute(
            "UPDATE workspace_meta SET value = ? WHERE key = 'owner_memory_id'",
            (owner_memory_id,),
        )
        dest.commit()
    finally:
        dest.close()
        source.close()

    return WorkspaceStore.open(target_paths, owner_memory_id=owner_memory_id)
