"""Tests for MEMORY.md managed-region parser, deterministic render, and locking."""

from __future__ import annotations

from pathlib import Path

import pytest

from rikugan.memory.markdown import (
    ManagedRegionError,
    MemoryProjector,
    parse_memory_document,
    render_memory_document,
)
from rikugan.memory.workspace import MemoryLocator, new_memory_id, new_record_id
from rikugan.memory.workspace_store import WorkspaceStore


class TestParseMemoryDocument:
    def test_empty_document_has_no_managed_region(self) -> None:
        content = "# Memory\n\nSome user notes.\n"
        doc = parse_memory_document(content)

        assert doc.managed == ""
        assert doc.prefix == content
        assert doc.suffix == ""
        assert doc.managed_hash != ""

    def test_well_formed_managed_region(self) -> None:
        content = (
            "# Memory\n\n"
            "<!-- rikugan:managed:start -->\n"
            "## Confirmed Facts\n\n"
            "- [protocol] Uses RC4.\n"
            "<!-- rikugan:managed:end -->\n\n"
            "## User Notes\n\n"
            "Check key schedule.\n"
        )
        doc = parse_memory_document(content)

        assert "Uses RC4" in doc.managed
        assert "Check key schedule" in doc.suffix
        assert "rikugan:managed:start" not in doc.managed

    def test_nested_or_reversed_markers_are_conflicts(self) -> None:
        # Reversed order
        content = "<!-- rikugan:managed:end -->\n<!-- rikugan:managed:start -->\n"
        with pytest.raises(ManagedRegionError):
            parse_memory_document(content)

    def test_missing_end_marker_is_conflict(self) -> None:
        content = "<!-- rikugan:managed:start -->\nSome content\n"
        with pytest.raises(ManagedRegionError):
            parse_memory_document(content)

    def test_missing_start_marker_is_conflict(self) -> None:
        content = "Some content\n<!-- rikugan:managed:end -->\n"
        with pytest.raises(ManagedRegionError):
            parse_memory_document(content)

    def test_double_start_is_conflict(self) -> None:
        content = "<!-- rikugan:managed:start -->\n<!-- rikugan:managed:start -->\n<!-- rikugan:managed:end -->\n"
        with pytest.raises(ManagedRegionError):
            parse_memory_document(content)


class TestRenderMemoryDocument:
    def test_render_preserves_unmanaged_text(self) -> None:
        original = "# Memory\n\n## User Notes\n\nImportant note.\n"
        doc = parse_memory_document(original)
        rendered = render_memory_document(doc, managed_block="## Facts\n\n- fact1\n")

        assert "Important note." in rendered
        assert "fact1" in rendered
        assert rendered.count("<!-- rikugan:managed:start -->") == 1
        assert rendered.count("<!-- rikugan:managed:end -->") == 1

    def test_render_empty_managed_creates_section(self) -> None:
        doc = parse_memory_document("# Memory\n\nUser note.\n")
        rendered = render_memory_document(doc, managed_block="## Facts\n\n- A\n")

        assert "<!-- rikugan:managed:start -->" in rendered
        assert "<!-- rikugan:managed:end -->" in rendered

    def test_render_includes_record_markers(self) -> None:
        """Managed entries carry hidden stable record ID/revision markers."""
        from rikugan.memory.markdown import ManagedEntry

        doc = parse_memory_document("# Memory\n")
        entries = [
            ManagedEntry(
                fact_id="fact-aaa",
                fact_type="protocol",
                title="RC4",
                content="Uses RC4",
                revision=3,
            )
        ]
        rendered = render_memory_document(doc, managed_block="", entries=entries)

        assert "rikugan:record" in rendered
        assert "fact-aaa" in rendered
        assert "rev=3" in rendered


class TestMemoryProjector:
    def test_project_creates_markdown_from_facts(self, tmp_path: Path) -> None:
        memory_id = new_memory_id()
        paths = MemoryLocator(tmp_path).binary(memory_id)
        store = WorkspaceStore.create(paths, owner_memory_id=memory_id)

        fid = new_record_id("fact")
        store.put_fact(fid, "algorithm", "RC4", "Uses RC4 for C2", 0.8, expected_revision=0)

        projector = MemoryProjector()
        projector.project(paths, store)

        content = paths.markdown.read_text(encoding="utf-8")
        assert "Uses RC4 for C2" in content
        assert content.count("<!-- rikugan:managed:start -->") == 1
        assert content.count("<!-- rikugan:managed:end -->") == 1

        state = store.projection_state()
        assert state.projection_dirty is False
        assert state.managed_hash != ""
        store.close()

    def test_project_preserves_unmanaged_edits(self, tmp_path: Path) -> None:
        memory_id = new_memory_id()
        paths = MemoryLocator(tmp_path).binary(memory_id)
        store = WorkspaceStore.create(paths, owner_memory_id=memory_id)

        fid = new_record_id("fact")
        store.put_fact(fid, "algorithm", "RC4", "Uses RC4", 0.8, expected_revision=0)

        # First projection
        projector = MemoryProjector()
        projector.project(paths, store)

        # Add user note to the unmanaged region
        content = paths.markdown.read_text(encoding="utf-8")
        content += "\n## User Notes\n\nCheck key schedule.\n"
        paths.markdown.write_text(content, encoding="utf-8")

        # Re-project
        projector.project(paths, store)

        content = paths.markdown.read_text(encoding="utf-8")
        assert "Check key schedule" in content
        assert "Uses RC4" in content
        store.close()

    def test_project_overwrites_stale_managed_region(self, tmp_path: Path) -> None:
        """Stale managed content in MEMORY.md is always overwritten from SQLite."""
        memory_id = new_memory_id()
        paths = MemoryLocator(tmp_path).binary(memory_id)
        store = WorkspaceStore.create(paths, owner_memory_id=memory_id)

        fid = new_record_id("fact")
        store.put_fact(fid, "algorithm", "RC4", "Uses RC4", 0.8, expected_revision=0)

        projector = MemoryProjector()

        # Write an initial file with stale managed content
        paths.markdown.parent.mkdir(parents=True, exist_ok=True)
        paths.markdown.write_text(
            "# Memory\n\n<!-- rikugan:managed:start -->\n## OLD\n\n- old content\n<!-- rikugan:managed:end -->\n",
            encoding="utf-8",
        )

        projector.project(paths, store)

        content = paths.markdown.read_text(encoding="utf-8")
        assert "old content" not in content
        assert "Uses RC4" in content

        state = store.projection_state()
        assert state.projection_dirty is False
        store.close()

    def test_project_creates_markdown_for_empty_store(self, tmp_path: Path) -> None:
        memory_id = new_memory_id()
        paths = MemoryLocator(tmp_path).binary(memory_id)
        store = WorkspaceStore.create(paths, owner_memory_id=memory_id)

        projector = MemoryProjector()
        projector.project(paths, store)

        content = paths.markdown.read_text(encoding="utf-8")
        assert "# Memory" in content
        store.close()
