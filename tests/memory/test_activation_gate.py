"""Tests for central memory activation gate.

Verifies that the feature flag controls the full pipeline: when enabled,
the controller wires BinaryMemoryService into the loop; when disabled
(default), the legacy path is untouched.
"""

from __future__ import annotations

from pathlib import Path

from rikugan.agent.loop import AgentLoop
from rikugan.core.config import RikuganConfig
from rikugan.memory.manager import MemoryWorkspaceManager
from rikugan.memory.workspace import FilesystemIdentity, IdentityRequest


class TestActivationGate:
    def test_default_config_is_disabled(self) -> None:
        config = RikuganConfig()
        assert config.memory_workspaces_enabled is False

    def test_enabled_flag_round_trips_through_save_load(self, tmp_path: Path) -> None:
        config = RikuganConfig()
        config._config_dir = str(tmp_path)
        config.memory_workspaces_enabled = True
        config.save()

        loaded = RikuganConfig()
        loaded._config_dir = str(tmp_path)
        loaded.load()

        assert loaded.memory_workspaces_enabled is True

    def test_invalid_type_does_not_enable(self, tmp_path: Path) -> None:
        """A string "true" in JSON does not flip the feature on."""
        import json

        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"memory_workspaces_enabled": "true"}),
            encoding="utf-8",
        )

        config = RikuganConfig()
        config._config_dir = str(tmp_path)
        config.load()

        assert config.memory_workspaces_enabled is False

    def test_enabled_manager_initializes_registry(self, tmp_path: Path) -> None:
        config = RikuganConfig()
        config._config_dir = str(tmp_path)
        config.memory_workspaces_enabled = True
        MemoryWorkspaceManager(config)

        assert (tmp_path / "memory" / "registry.db").exists()

    def test_full_enabled_flow_wires_service_into_loop(self, tmp_path: Path) -> None:
        """End-to-end: enabled config → bind → service available."""
        from unittest.mock import MagicMock

        from rikugan.memory.authority import MemoryAuthorityIssuer
        from rikugan.memory.markdown import MemoryProjector
        from rikugan.memory.repository import SQLiteKnowledgeRepository
        from rikugan.memory.service import BinaryMemoryService
        from rikugan.memory.workspace_store import WorkspaceStore

        config = RikuganConfig()
        config._config_dir = str(tmp_path)
        config.memory_workspaces_enabled = True

        from rikugan.state.session import SessionState

        session = SessionState(idb_path=str(tmp_path / "test.i64"), db_instance_id="uuid-1")
        provider = MagicMock()
        tools = MagicMock()

        loop = AgentLoop(provider, tools, config, session)
        assert loop.memory_service is None  # Before wiring

        # Simulate controller wiring (same logic as _wire_central_memory)
        manager = MemoryWorkspaceManager(config)

        fs = FilesystemIdentity("vol", "1")
        request = IdentityRequest(
            source_kind="idb",
            idb_path=str(tmp_path / "test.i64"),
            db_instance_id="uuid-1",
            display_name="test.i64",
            filesystem_identity=fs,
        )
        result = manager.bind(request)
        assert result.binding is not None
        assert result.binding.state == "active"

        paths = manager.require_persistent_paths()
        store = WorkspaceStore.create(paths, owner_memory_id=result.binding.memory_id)
        repo = SQLiteKnowledgeRepository(store, owner_memory_id=result.binding.memory_id)
        issuer = MemoryAuthorityIssuer()

        context = manager.run_context()
        service = BinaryMemoryService(
            context=context,
            paths=paths,
            repository=repo,
            store=store,
            projector=MemoryProjector(),
            authority_issuer=issuer,
        )
        loop.memory_service = service
        loop._memory_authority = issuer.issue(context)

        assert loop.memory_service is not None
        assert loop._memory_authority is not None
