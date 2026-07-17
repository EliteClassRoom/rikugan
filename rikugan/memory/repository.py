"""SQLite knowledge repository adapter.

Bridges the existing :class:`KnowledgeMemory` / :class:`KnowledgeEntity` /
:class:`KnowledgeRelation` / :class:`KnowledgeObservation` dataclasses
from :mod:`rikugan.memory.schema` to the :class:`WorkspaceStore` SQLite
backend.

This adapter is the read/write interface consumed by retrieval, context,
and service layers. It preserves the current dataclass shapes so existing
retrieval and sanitize code works unchanged during the cutover.
"""

from __future__ import annotations

import json
from typing import Protocol

from .schema import (
    KnowledgeEntity,
    KnowledgeMemory,
    KnowledgeObservation,
    KnowledgeRelation,
)
from .workspace_store import WorkspaceStore


class KnowledgeRepository(Protocol):
    """Read/write interface for workspace knowledge records."""

    owner_memory_id: str

    def list_memories(self) -> list[KnowledgeMemory]: ...

    def list_entities(self) -> list[KnowledgeEntity]: ...

    def list_relations(self) -> list[KnowledgeRelation]: ...

    def count_observations(self) -> int: ...

    def upsert_memory(self, value: KnowledgeMemory) -> None: ...

    def upsert_entity(self, value: KnowledgeEntity) -> None: ...

    def upsert_relation(self, value: KnowledgeRelation) -> None: ...

    def append_observation(self, value: KnowledgeObservation) -> None: ...


def _validate_owner(record_owner: str, expected: str) -> None:
    """Raise ValueError if *record_owner* does not match *expected*."""
    if record_owner != expected:
        raise ValueError(f"owner_memory_id mismatch: record has {record_owner!r}, workspace has {expected!r}")


class SQLiteKnowledgeRepository:
    """Adapter that maps knowledge dataclasses onto WorkspaceStore tables."""

    def __init__(self, store: WorkspaceStore, *, owner_memory_id: str) -> None:
        self._store = store
        self.owner_memory_id = owner_memory_id

    # ------------------------------------------------------------------
    # Memories → facts
    # ------------------------------------------------------------------

    def upsert_memory(self, value: KnowledgeMemory) -> None:
        """Insert or update a memory as a fact record."""
        _validate_owner(value.binary_id, self.owner_memory_id)
        # Determine the current revision (0 for new, current for update)
        existing = self._store.get_fact(value.id)
        expected_revision = existing.revision if existing else 0
        self._store.put_fact(
            value.id,
            value.type,
            value.title,
            value.content,
            value.confidence,
            expected_revision=expected_revision,
        )

    def list_memories(self) -> list[KnowledgeMemory]:
        """List all current memories."""
        facts = self._store.list_facts()
        return [
            KnowledgeMemory(
                id=f.fact_id,
                binary_id=self.owner_memory_id,
                type=f.fact_type,
                title=f.title,
                content=f.content,
                confidence=f.confidence,
            )
            for f in facts
        ]

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    def upsert_entity(self, value: KnowledgeEntity) -> None:
        """Insert or update an entity."""
        _validate_owner(value.binary_id, self.owner_memory_id)
        existing = self._store.get_entity(value.id)
        metadata = {
            "display_name": value.display_name,
            "address": value.address,
            "tags": value.tags,
        }
        if existing:
            # Merge with existing metadata
            metadata = {**existing.metadata, **metadata}
        self._store.put_entity(
            value.id,
            value.type,
            value.name,
            metadata,
        )

    def list_entities(self) -> list[KnowledgeEntity]:
        """List all current entities."""
        # WorkspaceStore doesn't have list_entities yet — use raw query
        rows = self._store._conn.execute("SELECT * FROM entities ORDER BY created_at").fetchall()
        return [
            KnowledgeEntity(
                id=row["entity_id"],
                binary_id=self.owner_memory_id,
                type=row["entity_type"],
                name=row["name"],
                display_name=json.loads(row["metadata"]).get("display_name", ""),
                address=json.loads(row["metadata"]).get("address", ""),
                tags=json.loads(row["metadata"]).get("tags", []),
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Relations
    # ------------------------------------------------------------------

    def upsert_relation(self, value: KnowledgeRelation) -> None:
        """Insert or update a relation."""
        _validate_owner(value.binary_id, self.owner_memory_id)
        self._store.put_relation(
            value.id,
            value.src,
            value.predicate,
            value.dst,
            value.confidence,
        )

    def list_relations(self) -> list[KnowledgeRelation]:
        """List all current relations."""
        rels = self._store.list_relations()
        return [
            KnowledgeRelation(
                id=r.relation_id,
                binary_id=self.owner_memory_id,
                src=r.subject_id,
                predicate=r.predicate,
                dst=r.object_id,
                confidence=r.confidence,
            )
            for r in rels
        ]

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def append_observation(self, value: KnowledgeObservation) -> None:
        """Append an immutable observation."""
        _validate_owner(value.binary_id, self.owner_memory_id)
        self._store.append_observation(
            value.id,
            value.kind,
            json.dumps(value.payload, ensure_ascii=False, sort_keys=True),
        )

    def count_observations(self) -> int:
        """Count all observations."""
        return self._store.count_observations()

    # ------------------------------------------------------------------
    # Convenience: allocate-and-append
    # ------------------------------------------------------------------

    def upsert_memory_fact(
        self,
        category: str,
        fact: str,
        source: str,
    ) -> KnowledgeMemory:
        """Allocate or update one fact and append an observation atomically.

        Creates a new fact ID (or updates the latest fact of the same
        category if one exists), then appends an observation recording the
        source. Returns the resulting :class:`KnowledgeMemory`.
        """
        from .workspace import new_record_id

        # Find an existing fact with the same category to update
        existing = None
        for mem in self.list_memories():
            if mem.type == category:
                existing = mem
                break

        if existing is not None:
            # Update existing fact with new content
            current = self._store.get_fact(existing.id)
            expected_rev = current.revision if current else 0
            self._store.put_fact(
                existing.id,
                category,
                existing.title,
                fact,
                0.7,
                expected_revision=expected_rev,
            )
            result = KnowledgeMemory(
                id=existing.id,
                binary_id=self.owner_memory_id,
                type=category,
                title=existing.title,
                content=fact,
                confidence=0.7,
            )
        else:
            fid = new_record_id("fact")
            self._store.put_fact(fid, category, category, fact, 0.7, expected_revision=0)
            result = KnowledgeMemory(
                id=fid,
                binary_id=self.owner_memory_id,
                type=category,
                title=category,
                content=fact,
                confidence=0.7,
            )

        # Append observation
        oid = new_record_id("observation")
        self._store.append_observation(
            oid,
            source,
            json.dumps({"category": category}, ensure_ascii=False, sort_keys=True),
        )
        return result
