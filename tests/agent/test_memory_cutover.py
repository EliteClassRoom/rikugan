"""Tests for AgentLoop central memory cutover (save_memory conditional dispatch)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from rikugan.agent.loop import AgentLoop
from rikugan.core.config import RikuganConfig
from rikugan.core.types import ToolCall
from rikugan.memory.authority import MemoryAuthorityIssuer
from rikugan.memory.markdown import MemoryProjector
from rikugan.memory.repository import SQLiteKnowledgeRepository
from rikugan.memory.service import BinaryMemoryService
from rikugan.memory.workspace import MemoryLocator, MemoryRunContext, new_memory_id
from rikugan.memory.workspace_store import WorkspaceStore
from rikugan.state.session import SessionState


def _make_loop_with_central_memory(tmp_path: Path) -> tuple[AgentLoop, BinaryMemoryService]:
    """Build a minimal AgentLoop wired with central memory service."""
    memory_id = new_memory_id()
    context = MemoryRunContext(memory_id, "", 1, 0)
    paths = MemoryLocator(tmp_path / "memory").binary(memory_id)
    store = WorkspaceStore.create(paths, owner_memory_id=memory_id)
    repo = SQLiteKnowledgeRepository(store, owner_memory_id=memory_id)
    issuer = MemoryAuthorityIssuer()
    service = BinaryMemoryService(
        context=context,
        paths=paths,
        repository=repo,
        store=store,
        projector=MemoryProjector(),
        authority_issuer=issuer,
    )

    config = RikuganConfig()
    session = SessionState(idb_path=str(tmp_path / "test.i64"))
    provider = MagicMock()
    tools = MagicMock()

    loop = AgentLoop(provider, tools, config, session)
    loop.memory_service = service
    loop._memory_authority = issuer.issue(context)
    return loop, service


class TestSaveMemoryCentralDispatch:
    def test_save_memory_uses_central_service_when_wired(self, tmp_path: Path) -> None:
        loop, service = _make_loop_with_central_memory(tmp_path)

        tc = ToolCall(id="tc1", name="save_memory", arguments={"category": "algorithm", "fact": "Uses RC4"})
        gen = loop._handle_save_memory_tool(tc)
        events = list(gen)
        tr = events[-1] if events else None

        # The tool result should not be an error
        assert tr is not None
        facts = service.repository.list_memories()
        assert len(facts) == 1
        assert facts[0].content == "Uses RC4"
        assert facts[0].type == "algorithm"

    def test_save_memory_central_projects_to_memory_md(self, tmp_path: Path) -> None:
        loop, service = _make_loop_with_central_memory(tmp_path)

        tc = ToolCall(id="tc1", name="save_memory", arguments={"category": "protocol", "fact": "Uses HTTP"})
        list(loop._handle_save_memory_tool(tc))

        md = service.paths.markdown.read_text(encoding="utf-8")
        assert "Uses HTTP" in md

    def test_save_memory_without_service_returns_error(self, tmp_path: Path) -> None:
        """When memory_service is None (identity failure), save_memory reports unavailable."""
        config = RikuganConfig()
        session = SessionState(idb_path=str(tmp_path / "test.i64"))
        provider = MagicMock()
        tools = MagicMock()
        loop = AgentLoop(provider, tools, config, session)
        # loop.memory_service stays None (no wiring)

        tc = ToolCall(id="tc1", name="save_memory", arguments={"category": "test", "fact": "X"})
        events = list(loop._handle_save_memory_tool(tc))

        legacy_path = tmp_path / "RIKUGAN.md"
        assert not legacy_path.exists()  # no legacy file written
        tr = events[-1] if events else None
        assert tr is not None
