"""Tests for SQLiteKnowledgeRepository adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from rikugan.memory.repository import SQLiteKnowledgeRepository
from rikugan.memory.schema import (
    KnowledgeEntity,
    KnowledgeMemory,
    KnowledgeObservation,
    KnowledgeRelation,
)
from rikugan.memory.workspace import MemoryLocator, new_memory_id, new_record_id
from rikugan.memory.workspace_store import WorkspaceStore


def _create_repo(tmp_path: Path) -> tuple[SQLiteKnowledgeRepository, str]:
    memory_id = new_memory_id()
    paths = MemoryLocator(tmp_path).binary(memory_id)
    store = WorkspaceStore.create(paths, owner_memory_id=memory_id)
    repo = SQLiteKnowledgeRepository(store, owner_memory_id=memory_id)
    return repo, memory_id


class TestMemoryParity:
    def test_upsert_and_list_memory(self, tmp_path: Path) -> None:
        repo, mid = _create_repo(tmp_path)
        memory = KnowledgeMemory(
            id=new_record_id("fact"),
            binary_id=mid,
            type="fact",
            title="RC4",
            content="Uses RC4 for C2",
            confidence=0.8,
        )
        repo.upsert_memory(memory)
        assert repo.list_memories() == [memory]

    def test_upsert_memory_owner_check(self, tmp_path: Path) -> None:
        repo, _mid = _create_repo(tmp_path)
        memory = KnowledgeMemory(
            id=new_record_id("fact"),
            binary_id="wrong",
            type="fact",
            title="Bad",
            content="x",
        )
        with pytest.raises(ValueError, match="owner"):
            repo.upsert_memory(memory)


class TestEntityParity:
    def test_upsert_and_list_entities(self, tmp_path: Path) -> None:
        repo, mid = _create_repo(tmp_path)
        entity = KnowledgeEntity(
            id=new_record_id("entity"),
            binary_id=mid,
            type="function",
            name="main",
            address="0x401000",
        )
        repo.upsert_entity(entity)
        result = repo.list_entities()
        assert len(result) == 1
        assert result[0].name == "main"
        assert result[0].address == "0x401000"


class TestRelationParity:
    def test_upsert_and_list_relations(self, tmp_path: Path) -> None:
        repo, mid = _create_repo(tmp_path)
        eid1 = new_record_id("entity")
        eid2 = new_record_id("entity")
        e1 = KnowledgeEntity(id=eid1, binary_id=mid, type="function", name="a")
        e2 = KnowledgeEntity(id=eid2, binary_id=mid, type="function", name="b")
        repo.upsert_entity(e1)
        repo.upsert_entity(e2)
        relation = KnowledgeRelation(
            id=new_record_id("relation"),
            binary_id=mid,
            src=eid1,
            predicate="calls",
            dst=eid2,
            confidence=0.9,
        )
        repo.upsert_relation(relation)
        result = repo.list_relations()
        assert len(result) == 1
        assert result[0].predicate == "calls"
        assert result[0].src == eid1
        assert result[0].dst == eid2


class TestObservationParity:
    def test_append_and_count_observations(self, tmp_path: Path) -> None:
        repo, mid = _create_repo(tmp_path)
        obs = KnowledgeObservation(
            id=new_record_id("observation"),
            binary_id=mid,
            ts="2025-01-01T00:00:00",
            kind="save_memory",
            payload={"category": "algorithm"},
        )
        repo.append_observation(obs)
        assert repo.count_observations() == 1


class TestRepositoryProtocol:
    def test_implements_protocol(self, tmp_path: Path) -> None:
        repo, _ = _create_repo(tmp_path)
        assert hasattr(repo, "list_memories")
        assert hasattr(repo, "upsert_memory")
        assert hasattr(repo, "list_entities")
        assert hasattr(repo, "list_relations")
        assert hasattr(repo, "count_observations")
        assert hasattr(repo, "append_observation")
