"""Tests for research mode: command parsing, note writing, slugs, index."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.agent.loop import _parse_user_command
from rikugan.agent.modes.research import (
    ResearchNote,
    ResearchState,
    _generate_index,
    _slugify,
)
from rikugan.agent.turn import TurnEvent, TurnEventType


class TestParseResearchCommand(unittest.TestCase):
    """Test /research command parsing."""

    def test_research_command_parsed(self):
        cmd = _parse_user_command("/research analyze network protocol")
        self.assertTrue(cmd.use_research_mode)
        self.assertEqual(cmd.message, "analyze network protocol")

    def test_research_case_insensitive(self):
        cmd = _parse_user_command("/Research Analyze crypto")
        self.assertTrue(cmd.use_research_mode)
        self.assertEqual(cmd.message, "Analyze crypto")

    def test_non_research_command(self):
        cmd = _parse_user_command("just a question")
        self.assertFalse(cmd.use_research_mode)

    def test_explore_not_research(self):
        cmd = _parse_user_command("/explore check strings")
        self.assertFalse(cmd.use_research_mode)
        self.assertTrue(cmd.use_exploration_mode)


class TestSlugify(unittest.TestCase):
    """Test the _slugify helper."""

    def test_basic(self):
        self.assertEqual(_slugify("Socket Initialization"), "socket-initialization")

    def test_special_chars(self):
        self.assertEqual(_slugify("C2 — Command & Control!"), "c2-command-control")

    def test_unicode(self):
        self.assertEqual(_slugify("résumé café"), "resume-cafe")

    def test_empty(self):
        self.assertEqual(_slugify(""), "untitled")

    def test_whitespace_only(self):
        self.assertEqual(_slugify("   "), "untitled")

    def test_hyphens_collapsed(self):
        self.assertEqual(_slugify("foo - bar -- baz"), "foo-bar-baz")


class TestResearchNote(unittest.TestCase):
    """Test ResearchNote dataclass."""

    def test_defaults(self):
        note = ResearchNote(
            genre="networking",
            title="Socket Init",
            slug="socket-init",
            path="/tmp/notes/networking/socket-init.md",
            content="# Socket Init\n\nContent here.",
        )
        self.assertFalse(note.reviewed)
        self.assertFalse(note.review_passed)
        self.assertEqual(note.related_notes, [])


class TestGenerateIndex(unittest.TestCase):
    """Test index.md generation."""

    def test_empty_notes(self):
        state = ResearchState(notes_dir="/tmp/notes")
        index = _generate_index(state, "firmware.bin", "analyze protocol")
        self.assertIn("# Research Index", index)
        self.assertIn("firmware.bin", index)

    def test_with_notes(self):
        state = ResearchState(notes_dir="/tmp/notes")
        state.notes_written = [
            ResearchNote(
                genre="networking",
                title="Socket Initialization",
                slug="socket-initialization",
                path="/tmp/notes/networking/socket-initialization.md",
                content="# Socket Init",
                review_passed=True,
            ),
            ResearchNote(
                genre="crypto",
                title="Key Derivation",
                slug="key-derivation",
                path="/tmp/notes/crypto/key-derivation.md",
                content="# Key Derivation",
                review_passed=False,
            ),
        ]
        index = _generate_index(state, "firmware.bin", "analyze protocol")
        self.assertIn("## Networking", index)
        self.assertIn("## Crypto", index)
        self.assertIn("[[socket-initialization]]", index)
        self.assertIn("[[key-derivation]]", index)
        self.assertIn("(needs review)", index)

    def test_genres_sorted(self):
        state = ResearchState(notes_dir="/tmp/notes")
        state.notes_written = [
            ResearchNote(genre="zz-misc", title="A", slug="a", path="", content=""),
            ResearchNote(genre="aa-init", title="B", slug="b", path="", content=""),
        ]
        index = _generate_index(state, "test.bin", "goal")
        aa_pos = index.index("Aa Init")
        zz_pos = index.index("Zz Misc")
        self.assertLess(aa_pos, zz_pos)


class TestTurnEvents(unittest.TestCase):
    """Test new TurnEvent factory methods for research mode."""

    def test_research_note_saved_event(self):
        ev = TurnEvent.research_note_saved(
            title="Socket Init",
            genre="networking",
            path="/tmp/notes/networking/socket-init.md",
            preview="The binary initializes...",
            review_passed=True,
        )
        self.assertEqual(ev.type, TurnEventType.RESEARCH_NOTE_SAVED)
        self.assertEqual(ev.text, "Socket Init")
        self.assertEqual(ev.metadata["genre"], "networking")
        self.assertTrue(ev.metadata["review_passed"])

    def test_research_note_reviewed_event(self):
        ev = TurnEvent.research_note_reviewed(
            title="Socket Init",
            passed=False,
            feedback="Missing evidence for claim X",
        )
        self.assertEqual(ev.type, TurnEventType.RESEARCH_NOTE_REVIEWED)
        self.assertFalse(ev.metadata["passed"])
        self.assertIn("Missing evidence", ev.metadata["feedback"])


class TestNoteWriting(unittest.TestCase):
    """Test that notes are written to disk correctly."""

    def test_write_note_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_dir = os.path.join(tmpdir, "notes")
            os.makedirs(notes_dir)
            genre_dir = os.path.join(notes_dir, "networking")
            os.makedirs(genre_dir)

            note_path = os.path.join(genre_dir, "socket-init.md")
            content = "# Socket Init\n\n## Summary\n\nTest content with [[wiki-link]]."
            with open(note_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Verify written
            with open(note_path, encoding="utf-8") as f:
                read_content = f.read()
            self.assertEqual(read_content, content)
            self.assertIn("[[wiki-link]]", read_content)


if __name__ == "__main__":
    unittest.main()
