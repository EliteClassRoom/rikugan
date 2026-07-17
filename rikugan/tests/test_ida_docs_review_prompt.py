"""Tests for the IDAPython docs fetch URL guidance.

The Sphinx docs site behind ``python.docs.hex-rays.com`` returns
``403 Forbidden`` for deep-link HTML pages
(``/<module>/<func>.html``) — the response is rejected by the site's
bot protection.  Module index pages and raw RST source files
(``/_sources/<module>/index.rst.txt``) return ``200 OK``.

The bundled ``ida-scripting`` skill and the
``IDA_DOCS_REVIEWER_PROMPT`` must steer the agent to the URL pattern
that actually works.  A test failure here is the primary regression
guard against the prompt sending the LLM into a 403 loop.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from rikugan.agent.agents.ida_docs_reviewer import IDA_DOCS_REVIEWER_PROMPT

# ---------------------------------------------------------------------------
# Reviewer prompt
# ---------------------------------------------------------------------------


class TestReviewerPromptUrlGuidance(unittest.TestCase):
    """The reviewer system prompt must point to URLs that return 200 OK."""

    def test_prompt_recommends_rst_source_format(self):
        # /_sources/<module>/index.rst.txt is the only pattern that
        # returns full module reference AND survives CDN bot protection.
        self.assertIn(
            "/_sources/",
            IDA_DOCS_REVIEWER_PROMPT,
            "Reviewer prompt must recommend the Sphinx raw RST source format (/_sources/<module>/index.rst.txt).",
        )

    def test_prompt_recommends_source_with_module_template(self):
        # The reviewer must understand the <module> slot in the RST URL.
        # The post-error prompt uses the generic <module> template rather
        # than a concrete module example.
        self.assertIn(
            "_sources/<module>/index.rst.txt",
            IDA_DOCS_REVIEWER_PROMPT,
            "Reviewer prompt must show the RST source URL with a <module> slot.",
        )

    def test_prompt_warns_about_html_403(self):
        # If the reviewer follows the broken HTML pattern, every deep
        # link fetch returns 403 and burns a turn.  Pre-empt it.
        self.assertIn(
            "403",
            IDA_DOCS_REVIEWER_PROMPT,
            "Reviewer prompt must warn that HTML deep-link pages return 403 Forbidden (bot-protected).",
        )

    def test_prompt_demotes_html_pages_below_rst_source(self):
        # The /<module>/<func>.html pattern should be clearly marked
        # as unreliable, not as the primary online source.
        # We accept the legacy pattern being present ONLY if the prompt
        # also explicitly warns against it.
        prompt = IDA_DOCS_REVIEWER_PROMPT
        self.assertIn("DO NOT fetch HTML", prompt)

    def test_prompt_lists_html_pattern_danger_zone(self):
        # The exact broken pattern must be shown so the LLM recognizes
        # it as something to avoid.
        self.assertIn(
            "ida_<module>/<func>.html",
            IDA_DOCS_REVIEWER_PROMPT,
            "Reviewer prompt must show the failing HTML pattern so the LLM can recognize and skip it.",
        )

    def test_prompt_has_documentation_sources_section(self):
        # Sanity: the existing structure is preserved.
        self.assertIn("Documentation sources", IDA_DOCS_REVIEWER_PROMPT)
        self.assertIn("ida-scripting", IDA_DOCS_REVIEWER_PROMPT.lower())


# ---------------------------------------------------------------------------
# Bundled skill URL guidance
# ---------------------------------------------------------------------------


class TestIdaScriptingSkillUrlGuidance(unittest.TestCase):
    """The bundled ``ida-scripting`` SKILL.md teaches the same lesson.

    Otherwise, any agent that consults the skill (not just the docs
    reviewer) will retry the broken HTML pattern.
    """

    SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "builtins" / "ida-scripting" / "SKILL.md"

    def setUp(self):
        self.body = self.SKILL_PATH.read_text(encoding="utf-8")

    def test_skill_recommends_rst_source_format(self):
        self.assertIn(
            "/_sources/",
            self.body,
            "ida-scripting SKILL.md must recommend the Sphinx raw RST "
            "source format (/_sources/<module>/index.rst.txt).",
        )

    def test_skill_warns_about_html_403(self):
        self.assertIn(
            "403",
            self.body,
            "ida-scripting SKILL.md must warn that HTML deep-link pages return 403 Forbidden (bot-protected).",
        )

    def test_skill_when_to_fetch_more_section_present(self):
        self.assertIn("## When to fetch more", self.body)


if __name__ == "__main__":
    unittest.main()
