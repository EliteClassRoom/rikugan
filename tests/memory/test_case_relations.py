"""Tests for case relations: creation, listing, membership enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from rikugan.memory.case_repository import CaseRepository
from rikugan.memory.case_schema import (
    CaseRelationType,
)
from rikugan.memory.registry import MemoryRegistry
from rikugan.memory.workspace import MemoryLocator


def _setup(tmp_path: Path) -> tuple[CaseRepository, MemoryRegistry, str, str]:
    """Create registry + case + two member binaries."""
    locator = MemoryLocator(tmp_path / "memory")
    registry = MemoryRegistry(locator.registry_database())
    registry.initialize()
    cases = CaseRepository(registry, locator)
    binary_a = registry.create_workspace("binary", "loader.exe")
    binary_b = registry.create_workspace("binary", "payload.dll")
    case = cases.create_case("Malware Campaign")
    cases.add_member(case.case_id, binary_a.memory_id, expected_case_revision=case.revision)
    current = cases.get_case(case.case_id)
    cases.add_member(case.case_id, binary_b.memory_id, expected_case_revision=current.revision)
    return cases, registry, binary_a.memory_id, binary_b.memory_id


class TestCaseRelations:
    def test_put_directed_relation(self, tmp_path: Path) -> None:
        cases, _, mid_a, mid_b = _setup(tmp_path)
        case = cases.list_cases()[0]

        rel = cases.put_case_relation(
            case.case_id,
            mid_a,
            CaseRelationType.EMBEDS_OR_LOADS,
            mid_b,
            confidence=0.9,
        )
        assert rel.predicate is CaseRelationType.EMBEDS_OR_LOADS
        assert rel.subject_memory_id == mid_a
        assert rel.object_memory_id == mid_b

    def test_put_symmetric_relation_canonicalized(self, tmp_path: Path) -> None:
        cases, _, mid_a, mid_b = _setup(tmp_path)
        case = cases.list_cases()[0]

        # Pass in reverse order — symmetric predicates sort endpoints
        rel = cases.put_case_relation(
            case.case_id,
            mid_b,
            CaseRelationType.COMMUNICATES_WITH,
            mid_a,
            confidence=0.8,
        )
        # Endpoints are canonicalized (sorted) regardless of input order
        assert {rel.subject_memory_id, rel.object_memory_id} == {mid_a, mid_b}

    def test_self_relation_rejected(self, tmp_path: Path) -> None:
        cases, _, mid_a, _ = _setup(tmp_path)
        case = cases.list_cases()[0]
        with pytest.raises(ValueError, match="self"):
            cases.put_case_relation(
                case.case_id,
                mid_a,
                CaseRelationType.COMMUNICATES_WITH,
                mid_a,
            )

    def test_shares_artifact_requires_ref(self, tmp_path: Path) -> None:
        cases, _, mid_a, mid_b = _setup(tmp_path)
        case = cases.list_cases()[0]
        with pytest.raises(ValueError, match="artifact"):
            cases.put_case_relation(
                case.case_id,
                mid_a,
                CaseRelationType.SHARES_ARTIFACT_WITH,
                mid_b,
            )

    def test_shares_artifact_succeeds_with_ref(self, tmp_path: Path) -> None:
        cases, _, mid_a, mid_b = _setup(tmp_path)
        case = cases.list_cases()[0]
        rel = cases.put_case_relation(
            case.case_id,
            mid_a,
            CaseRelationType.SHARES_ARTIFACT_WITH,
            mid_b,
            artifact_ref="hash:abc123",
        )
        assert rel.artifact_ref == "hash:abc123"

    def test_list_relations(self, tmp_path: Path) -> None:
        cases, _, mid_a, mid_b = _setup(tmp_path)
        case = cases.list_cases()[0]
        cases.put_case_relation(
            case.case_id,
            mid_a,
            CaseRelationType.DERIVED_FROM,
            mid_b,
            confidence=0.7,
        )
        cases.put_case_relation(
            case.case_id,
            mid_a,
            CaseRelationType.COMMUNICATES_WITH,
            mid_b,
            confidence=0.6,
        )
        rels = cases.list_case_relations(case.case_id)
        assert len(rels) == 2

    def test_nonmember_endpoint_rejected(self, tmp_path: Path) -> None:
        cases, registry, mid_a, _ = _setup(tmp_path)
        case = cases.list_cases()[0]
        outsider = registry.create_workspace("binary", "unrelated.exe")
        with pytest.raises(ValueError, match="member"):
            cases.put_case_relation(
                case.case_id,
                mid_a,
                CaseRelationType.COMMUNICATES_WITH,
                outsider.memory_id,
            )
