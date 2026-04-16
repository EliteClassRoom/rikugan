"""Tests for the skills system."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.skills.loader import (
    _parse_frontmatter,
    _split_frontmatter,
    discover_skills,
)
from rikugan.skills.registry import SkillRegistry


class TestFrontmatterParser(unittest.TestCase):
    def test_simple_key_value(self):
        text = "name: My Skill\ndescription: Does something"
        result = _parse_frontmatter(text)
        self.assertEqual(result["name"], "My Skill")
        self.assertEqual(result["description"], "Does something")

    def test_inline_list(self):
        text = "tags: [vuln, audit, security]"
        result = _parse_frontmatter(text)
        self.assertEqual(result["tags"], ["vuln", "audit", "security"])

    def test_block_list(self):
        text = "allowed_tools:\n  - decompile_function\n  - get_xrefs\n  - rename_function"
        result = _parse_frontmatter(text)
        self.assertEqual(result["allowed_tools"], [
            "decompile_function", "get_xrefs", "rename_function",
        ])

    def test_quoted_values(self):
        text = 'name: "My Quoted Skill"\nversion: "1.0"'
        result = _parse_frontmatter(text)
        self.assertEqual(result["name"], "My Quoted Skill")
        self.assertEqual(result["version"], "1.0")

    def test_empty_value(self):
        text = "name: Test\nempty_key:"
        result = _parse_frontmatter(text)
        self.assertEqual(result["empty_key"], "")

    def test_comments_ignored(self):
        text = "# This is a comment\nname: Test"
        result = _parse_frontmatter(text)
        self.assertEqual(result["name"], "Test")
        self.assertNotIn("#", result)


class TestSplitFrontmatter(unittest.TestCase):
    def test_with_frontmatter(self):
        text = "---\nname: Test\n---\nBody content here"
        fm, body = _split_frontmatter(text)
        self.assertIn("name: Test", fm)
        self.assertEqual(body.strip(), "Body content here")

    def test_without_frontmatter(self):
        text = "Just a body with no frontmatter"
        fm, body = _split_frontmatter(text)
        self.assertEqual(fm, "")
        self.assertEqual(body, text)

    def test_empty_body(self):
        text = "---\nname: Test\n---\n"
        fm, body = _split_frontmatter(text)
        self.assertIn("name: Test", fm)


class TestDiscoverSkills(unittest.TestCase):
    def test_discover_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a skill
            skill_dir = os.path.join(tmpdir, "vuln-audit")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: Vulnerability Audit\ndescription: Find security bugs\ntags: [security]\n---\nYou are a security auditor.\nAnalyze the function for vulnerabilities.\n")

            skills = discover_skills(tmpdir)
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "Vulnerability Audit")
            self.assertEqual(skills[0].slug, "vuln-audit")
            self.assertEqual(skills[0].description, "Find security bugs")
            self.assertEqual(skills[0].tags, ["security"])
            self.assertIn("security auditor", skills[0].body)

    def test_missing_directory(self):
        skills = discover_skills("/nonexistent/path")
        self.assertEqual(skills, [])

    def test_skip_invalid_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Directory without SKILL.md
            os.makedirs(os.path.join(tmpdir, "no-skill"))
            # Regular file (not directory)
            with open(os.path.join(tmpdir, "file.txt"), "w") as f:
                f.write("not a skill")

            skills = discover_skills(tmpdir)
            self.assertEqual(len(skills), 0)


class TestSkillRegistry(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create two skills
        for slug, name, desc in [
            ("vuln-audit", "Vulnerability Audit", "Find security bugs"),
            ("rename-all", "Bulk Rename", "Rename everything in a function"),
        ]:
            skill_dir = os.path.join(self.tmpdir, slug)
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write(f"---\nname: {name}\ndescription: {desc}\n---\nBody for {slug}\n")

    def test_discover_and_list(self):
        reg = SkillRegistry(self.tmpdir)
        count = reg.discover()
        # Built-in skills + 2 user skills (vuln-audit overrides the built-in)
        self.assertGreaterEqual(count, 2)
        self.assertIn("vuln-audit", reg.list_slugs())
        self.assertIn("rename-all", reg.list_slugs())

    def test_get_skill(self):
        reg = SkillRegistry(self.tmpdir)
        reg.discover()
        skill = reg.get("vuln-audit")
        self.assertIsNotNone(skill)
        # User skill overrides the built-in one with the same slug
        self.assertEqual(skill.name, "Vulnerability Audit")
        self.assertIn("Body for vuln-audit", skill.body)

    def test_get_missing(self):
        reg = SkillRegistry(self.tmpdir)
        reg.discover()
        self.assertIsNone(reg.get("nonexistent"))

    def test_summary_for_prompt(self):
        reg = SkillRegistry(self.tmpdir)
        reg.discover()
        summary = reg.get_summary_for_prompt()
        self.assertIn("/vuln-audit", summary)
        self.assertIn("/rename-all", summary)
        self.assertIn("Find security bugs", summary)

    def test_empty_registry_summary(self):
        # A fresh registry with no discover() call has no skills
        reg = SkillRegistry("/nonexistent")
        self.assertIsNone(reg.get_summary_for_prompt())

    def test_resolve_skill_invocation(self):
        reg = SkillRegistry(self.tmpdir)
        reg.discover()

        skill, remaining = reg.resolve_skill_invocation("/vuln-audit check this function")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.slug, "vuln-audit")
        self.assertEqual(remaining, "check this function")

    def test_resolve_no_match(self):
        reg = SkillRegistry(self.tmpdir)
        reg.discover()

        skill, remaining = reg.resolve_skill_invocation("just a normal message")
        self.assertIsNone(skill)
        self.assertEqual(remaining, "just a normal message")

    def test_resolve_unknown_slug(self):
        reg = SkillRegistry(self.tmpdir)
        reg.discover()

        skill, remaining = reg.resolve_skill_invocation("/unknown-skill do something")
        self.assertIsNone(skill)
        self.assertEqual(remaining, "/unknown-skill do something")


if __name__ == "__main__":
    unittest.main()
