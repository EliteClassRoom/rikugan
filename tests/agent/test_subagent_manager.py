"""Tests for rikugan.agent.subagent_manager registry logic (no thread/LLM)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks

install_ida_mocks()

from rikugan.agent.subagent_manager import (
    SubagentInfo,
    SubagentManager,
    SubagentStatus,
)
from rikugan.core.config import RikuganConfig
from rikugan.providers.base import LLMProvider, ModelInfo, ProviderCapabilities
from rikugan.tools.registry import ToolRegistry


class _StubProvider(LLMProvider):
    """Minimal provider stub for SubagentManager unit tests."""

    def __init__(self) -> None:
        super().__init__(api_key="test", model="stub-model")

    @property
    def name(self) -> str:
        return "stub"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def _get_client(self):  # pragma: no cover - never called in these tests
        return None

    def _fetch_models_live(self):  # pragma: no cover
        return [ModelInfo(id="stub-model", name="Stub", provider="stub")]

    @staticmethod
    def _builtin_models():  # pragma: no cover
        return [ModelInfo(id="stub-model", name="Stub", provider="stub")]

    def _format_messages(self, messages):  # pragma: no cover
        return messages

    def _normalize_response(self, raw):  # pragma: no cover
        return raw

    def _build_request_kwargs(self, messages, tools, **kwargs):  # pragma: no cover
        return {}

    def _call_api(self, client, kwargs):  # pragma: no cover
        return {}

    def _handle_api_error(self, e):  # pragma: no cover
        raise e

    def _stream_chunks(self, client, kwargs):  # pragma: no cover
        return iter([])


def _make_manager() -> SubagentManager:
    return SubagentManager(
        provider=_StubProvider(),
        tool_registry=ToolRegistry(),
        config=RikuganConfig(),
        host_name="test",
    )


# ---------------------------------------------------------------------------
# SubagentStatus enum
# ---------------------------------------------------------------------------


class TestSubagentStatus(unittest.TestCase):
    def test_string_inheritance(self) -> None:
        assert SubagentStatus.PENDING == "pending"
        assert SubagentStatus.RUNNING == "running"
        assert SubagentStatus.COMPLETED == "completed"
        assert SubagentStatus.FAILED == "failed"
        assert SubagentStatus.CANCELLED == "cancelled"

    def test_all_statuses(self) -> None:
        assert {s.value for s in SubagentStatus} == {
            "pending",
            "running",
            "completed",
            "failed",
            "cancelled",
        }


# ---------------------------------------------------------------------------
# SubagentInfo dataclass
# ---------------------------------------------------------------------------


class TestSubagentInfo(unittest.TestCase):
    def test_defaults(self) -> None:
        info = SubagentInfo(
            id="abc",
            name="worker",
            task="do thing",
            agent_type="custom",
            status=SubagentStatus.PENDING,
            created_at=0.0,
        )
        assert info.completed_at is None
        assert info.parent_id is None
        assert info.children == []
        assert info.summary == ""
        assert info.turn_count == 0
        assert info.token_usage is None
        assert info.perks == []
        assert info.category == ""


# ---------------------------------------------------------------------------
# SubagentManager registry methods
# ---------------------------------------------------------------------------


class TestRegister(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = _make_manager()

    def test_register_returns_unique_id(self) -> None:
        id1 = self.mgr.register(name="w1", task="t1")
        id2 = self.mgr.register(name="w2", task="t2")
        assert id1 != id2
        assert len(id1) == 12  # uuid hex prefix

    def test_register_starts_pending(self) -> None:
        agent_id = self.mgr.register(name="w1", task="t1")
        info = self.mgr.get(agent_id)
        assert info is not None
        assert info.status == SubagentStatus.PENDING
        assert info.name == "w1"
        assert info.task == "t1"
        assert info.agent_type == "custom"

    def test_register_emits_event(self) -> None:
        self.mgr.register(name="w1", task="t1")
        event = self.mgr.poll_event()
        assert event is not None
        assert event.type.value == "subagent_spawned"

    def test_register_with_parent_links_children(self) -> None:
        parent_id = self.mgr.register(name="parent", task="t")
        child_id = self.mgr.register(name="child", task="t", parent_id=parent_id)
        parent = self.mgr.get(parent_id)
        assert parent is not None
        assert child_id in parent.children

    def test_register_with_unknown_parent_does_not_crash(self) -> None:
        """If parent_id is unknown we should still register the child."""
        child_id = self.mgr.register(name="orphan", task="t", parent_id="nonexistent")
        assert self.mgr.get(child_id) is not None
        # Orphan has no parent link but is still listed
        assert self.mgr.tree() == []

    def test_register_stores_perks_and_category(self) -> None:
        agent_id = self.mgr.register(
            name="bulk_renamer",
            task="rename 100 functions",
            agent_type="custom",
            perks=["read_only", "fast"],
            category="bulk_rename",
        )
        info = self.mgr.get(agent_id)
        assert info is not None
        assert info.perks == ["read_only", "fast"]
        assert info.category == "bulk_rename"


class TestGetAndList(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = _make_manager()

    def test_get_unknown_returns_none(self) -> None:
        assert self.mgr.get("nonexistent") is None

    def test_list_all_empty(self) -> None:
        assert self.mgr.list_all() == []

    def test_list_all_returns_all(self) -> None:
        ids = [self.mgr.register(name=f"w{i}", task="t") for i in range(3)]
        all_infos = self.mgr.list_all()
        assert {i.id for i in all_infos} == set(ids)

    def test_tree_filters_to_roots(self) -> None:
        parent = self.mgr.register(name="parent", task="t")
        self.mgr.register(name="child1", task="t", parent_id=parent)
        self.mgr.register(name="child2", task="t", parent_id=parent)
        self.mgr.register(name="orphan", task="t")

        roots = self.mgr.tree()
        root_ids = {r.id for r in roots}
        assert parent in root_ids
        assert len(roots) == 2  # parent + orphan


class TestCounters(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = _make_manager()

    def test_counts_when_empty(self) -> None:
        assert self.mgr.running_count() == 0
        assert self.mgr.completed_count() == 0

    def test_running_count(self) -> None:
        a = self.mgr.register(name="a", task="t")
        b = self.mgr.register(name="b", task="t")
        self.mgr.get(a).status = SubagentStatus.RUNNING
        self.mgr.get(b).status = SubagentStatus.COMPLETED
        assert self.mgr.running_count() == 1
        assert self.mgr.completed_count() == 1

    def test_counts_ignore_other_statuses(self) -> None:
        a = self.mgr.register(name="a", task="t")
        self.mgr.get(a).status = SubagentStatus.FAILED
        assert self.mgr.running_count() == 0
        assert self.mgr.completed_count() == 0


class TestCancel(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = _make_manager()

    def test_cancel_pending(self) -> None:
        agent_id = self.mgr.register(name="a", task="t")
        self.mgr.cancel(agent_id)
        info = self.mgr.get(agent_id)
        assert info.status == SubagentStatus.CANCELLED
        assert info.completed_at is not None

    def test_cancel_running(self) -> None:
        agent_id = self.mgr.register(name="a", task="t")
        self.mgr.get(agent_id).status = SubagentStatus.RUNNING
        self.mgr.cancel(agent_id)
        assert self.mgr.get(agent_id).status == SubagentStatus.CANCELLED

    def test_cancel_completed_is_noop_on_status(self) -> None:
        """Once completed, cancellation must not change the status."""
        agent_id = self.mgr.register(name="a", task="t")
        self.mgr.get(agent_id).status = SubagentStatus.COMPLETED
        self.mgr.cancel(agent_id)
        assert self.mgr.get(agent_id).status == SubagentStatus.COMPLETED

    def test_cancel_emits_failure_event(self) -> None:
        agent_id = self.mgr.register(name="a", task="t")
        # Drain spawn event
        self.mgr.poll_event()
        self.mgr.cancel(agent_id)
        event = self.mgr.poll_event()
        assert event is not None
        # Failure event for the cancellation
        assert "cancel" in event.type.value.lower() or "fail" in event.type.value.lower()

    def test_cancel_unknown_id_is_safe(self) -> None:
        """Cancelling an agent that doesn't exist must not raise."""
        self.mgr.cancel("nonexistent")  # no exception


class TestUpdateExternal(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = _make_manager()

    def test_update_changes_status_and_records_completion(self) -> None:
        agent_id = self.mgr.register(name="a", task="t")
        self.mgr.update_external(
            agent_id, SubagentStatus.COMPLETED, summary="done", turn_count=3
        )
        info = self.mgr.get(agent_id)
        assert info.status == SubagentStatus.COMPLETED
        assert info.summary == "done"
        assert info.turn_count == 3
        assert info.completed_at is not None

    def test_update_to_failed(self) -> None:
        agent_id = self.mgr.register(name="a", task="t")
        self.mgr.update_external(agent_id, SubagentStatus.FAILED, summary="oops")
        assert self.mgr.get(agent_id).status == SubagentStatus.FAILED

    def test_update_unknown_id_is_safe(self) -> None:
        """No exception if we update an agent that was never registered."""
        self.mgr.update_external("nope", SubagentStatus.COMPLETED)


class TestPollEvent(unittest.TestCase):
    def test_poll_empty_returns_none(self) -> None:
        mgr = _make_manager()
        assert mgr.poll_event() is None

    def test_poll_returns_event_after_register(self) -> None:
        mgr = _make_manager()
        mgr.register(name="a", task="t")
        event = mgr.poll_event()
        assert event is not None
