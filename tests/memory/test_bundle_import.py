"""Tests for bundle importer: round-trip export→import, idempotency, remap."""

from __future__ import annotations

from pathlib import Path

from rikugan.memory.bundle_export import export_workspace
from rikugan.memory.bundle_import import import_workspace_bundle
from rikugan.memory.repository import SQLiteKnowledgeRepository
from rikugan.memory.schema import KnowledgeEntity, KnowledgeMemory
from rikugan.memory.workspace import MemoryLocator, new_memory_id, new_record_id
from rikugan.memory.workspace_store import WorkspaceStore


def _seed_and_export(tmp_path: Path) -> Path:
    """Create a workspace with facts, export it, return bundle path."""
    memory_id = new_memory_id()
    locator = MemoryLocator(tmp_path / "memory")
    paths = locator.binary(memory_id)
    store = WorkspaceStore.create(paths, owner_memory_id=memory_id)
    repo = SQLiteKnowledgeRepository(store, owner_memory_id=memory_id)
    repo.upsert_memory(
        KnowledgeMemory(
            id=new_record_id("fact"),
            binary_id=memory_id,
            type="algorithm",
            title="RC4",
            content="Uses RC4",
            confidence=0.8,
        )
    )
    repo.upsert_entity(
        KnowledgeEntity(
            id=new_record_id("entity"),
            binary_id=memory_id,
            type="function",
            name="main",
            address="0x401000",
        )
    )
    bundle_path = tmp_path / "bundle.zip"
    export_workspace(paths, repo, bundle_path)
    store.close()
    return bundle_path


class TestBundleImport:
    def test_import_round_trip(self, tmp_path: Path) -> None:
        bundle = _seed_and_export(tmp_path)

        # Create a fresh target workspace
        target_mid = new_memory_id()
        locator = MemoryLocator(tmp_path / "memory2")
        target_paths = locator.binary(target_mid)
        target_store = WorkspaceStore.create(target_paths, owner_memory_id=target_mid)
        target_repo = SQLiteKnowledgeRepository(target_store, owner_memory_id=target_mid)

        result = import_workspace_bundle(bundle, target_repo)
        assert result.imported_count > 0

        # Verify facts were imported
        facts = target_repo.list_memories()
        assert len(facts) >= 1
        assert any("RC4" in f.content for f in facts)

        # Verify entities
        entities = target_repo.list_entities()
        assert len(entities) >= 1
        target_store.close()

    def test_import_is_idempotent(self, tmp_path: Path) -> None:
        """Rerunning same bundle produces the same import ID."""
        bundle = _seed_and_export(tmp_path)

        target_mid = new_memory_id()
        locator = MemoryLocator(tmp_path / "memory3")
        target_paths = locator.binary(target_mid)
        target_store = WorkspaceStore.create(target_paths, owner_memory_id=target_mid)
        target_repo = SQLiteKnowledgeRepository(target_store, owner_memory_id=target_mid)

        r1 = import_workspace_bundle(bundle, target_repo)
        r2 = import_workspace_bundle(bundle, target_repo)
        assert r1.import_id == r2.import_id
        target_store.close()

    def test_import_preserves_provenance(self, tmp_path: Path) -> None:
        """Imported records have new target memory_id, not origin."""
        bundle = _seed_and_export(tmp_path)

        target_mid = new_memory_id()
        locator = MemoryLocator(tmp_path / "memory4")
        target_paths = locator.binary(target_mid)
        target_store = WorkspaceStore.create(target_paths, owner_memory_id=target_mid)
        target_repo = SQLiteKnowledgeRepository(target_store, owner_memory_id=target_mid)

        import_workspace_bundle(bundle, target_repo)
        facts = target_repo.list_memories()
        for f in facts:
            assert f.binary_id == target_mid
        target_store.close()
