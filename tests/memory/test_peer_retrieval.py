"""Tests for PeerMemoryRetriever: eligibility, caps, read-only peer opens."""

from __future__ import annotations

from pathlib import Path

from rikugan.memory.case_repository import CaseRepository
from rikugan.memory.case_schema import CaseRelationType
from rikugan.memory.peer_retrieval import PeerMemoryRetriever
from rikugan.memory.registry import MemoryRegistry
from rikugan.memory.repository import SQLiteKnowledgeRepository
from rikugan.memory.schema import KnowledgeMemory
from rikugan.memory.workspace import MemoryLocator, new_record_id
from rikugan.memory.workspace_store import WorkspaceStore


def _setup(tmp_path: Path) -> tuple[CaseRepository, MemoryRegistry, MemoryLocator, str, str, str]:
    """Create registry + case + 2 binary members with facts."""
    locator = MemoryLocator(tmp_path / "memory")
    registry = MemoryRegistry(locator.registry_database())
    registry.initialize()
    cases = CaseRepository(registry, locator)

    # Create binary A with facts
    mid_a = registry.create_workspace("binary", "loader.exe").memory_id
    paths_a = locator.binary(mid_a)
    store_a = WorkspaceStore.create(paths_a, owner_memory_id=mid_a)
    repo_a = SQLiteKnowledgeRepository(store_a, owner_memory_id=mid_a)
    repo_a.upsert_memory(
        KnowledgeMemory(
            id=new_record_id("fact"),
            binary_id=mid_a,
            type="algorithm",
            title="RC4",
            content="Uses RC4 for C2",
            confidence=0.8,
        )
    )
    store_a.close()

    # Create binary B with facts
    mid_b = registry.create_workspace("binary", "payload.dll").memory_id
    paths_b = locator.binary(mid_b)
    store_b = WorkspaceStore.create(paths_b, owner_memory_id=mid_b)
    repo_b = SQLiteKnowledgeRepository(store_b, owner_memory_id=mid_b)
    repo_b.upsert_memory(
        KnowledgeMemory(
            id=new_record_id("fact"),
            binary_id=mid_b,
            type="protocol",
            title="HTTP",
            content="Uses HTTP transport",
            confidence=0.7,
        )
    )
    store_b.close()

    case = cases.create_case("Campaign")
    cases.add_member(case.case_id, mid_a, expected_case_revision=case.revision)
    current = cases.get_case(case.case_id)
    cases.add_member(case.case_id, mid_b, expected_case_revision=current.revision)

    return cases, registry, locator, case.case_id, mid_a, mid_b


class TestPeerRetrieval:
    def test_eligible_peer_with_strong_relation(self, tmp_path: Path) -> None:
        cases, _, locator, case_id, mid_a, mid_b = _setup(tmp_path)
        cases.put_case_relation(case_id, mid_a, CaseRelationType.COMMUNICATES_WITH, mid_b, confidence=0.9)

        retriever = PeerMemoryRetriever(cases, locator)
        pack = retriever.retrieve(case_id, active_memory_id=mid_a)

        assert len(pack.peers) == 1
        assert pack.peers[0].memory_id == mid_b
        assert len(pack.records) > 0

    def test_ineligible_peer_low_confidence(self, tmp_path: Path) -> None:
        cases, _, locator, case_id, mid_a, mid_b = _setup(tmp_path)
        cases.put_case_relation(case_id, mid_a, CaseRelationType.COMMUNICATES_WITH, mid_b, confidence=0.5)

        retriever = PeerMemoryRetriever(cases, locator)
        pack = retriever.retrieve(case_id, active_memory_id=mid_a)

        assert len(pack.peers) == 0
        assert len(pack.records) == 0

    def test_shares_artifact_eligible(self, tmp_path: Path) -> None:
        cases, _, locator, case_id, mid_a, mid_b = _setup(tmp_path)
        cases.put_case_relation(
            case_id,
            mid_a,
            CaseRelationType.SHARES_ARTIFACT_WITH,
            mid_b,
            confidence=0.3,
            artifact_ref="hash:abc",
        )

        retriever = PeerMemoryRetriever(cases, locator)
        pack = retriever.retrieve(case_id, active_memory_id=mid_a)

        # Artifact match makes it eligible despite low confidence
        assert len(pack.peers) == 1

    def test_no_relations_no_peers(self, tmp_path: Path) -> None:
        cases, _, locator, case_id, mid_a, _ = _setup(tmp_path)

        retriever = PeerMemoryRetriever(cases, locator)
        pack = retriever.retrieve(case_id, active_memory_id=mid_a)

        assert len(pack.peers) == 0

    def test_max_peers_capped(self, tmp_path: Path) -> None:
        """At most 3 peers returned regardless of eligible count."""
        cases, registry, locator, case_id, mid_a, _ = _setup(tmp_path)

        # Add 4 more peers with relations
        for i in range(4):
            extra = registry.create_workspace("binary", f"extra{i}.exe").memory_id
            paths = locator.binary(extra)
            store = WorkspaceStore.create(paths, owner_memory_id=extra)
            store.close()
            current = cases.get_case(case_id)
            cases.add_member(case_id, extra, expected_case_revision=current.revision)
            cases.put_case_relation(
                case_id,
                mid_a,
                CaseRelationType.SAME_FAMILY_AS,
                extra,
                confidence=0.9,
            )

        retriever = PeerMemoryRetriever(cases, locator)
        pack = retriever.retrieve(case_id, active_memory_id=mid_a)

        assert len(pack.peers) <= 3

    def test_query_filters_results(self, tmp_path: Path) -> None:
        cases, _, locator, case_id, mid_a, mid_b = _setup(tmp_path)
        cases.put_case_relation(case_id, mid_a, CaseRelationType.COMMUNICATES_WITH, mid_b, confidence=0.9)

        retriever = PeerMemoryRetriever(cases, locator)
        # Query that matches nothing
        pack = retriever.retrieve(case_id, active_memory_id=mid_a, query="nonexistent_xyz")
        assert len(pack.records) == 0

        # Query that matches fact content
        pack2 = retriever.retrieve(case_id, active_memory_id=mid_a, query="HTTP")
        assert len(pack2.records) > 0
