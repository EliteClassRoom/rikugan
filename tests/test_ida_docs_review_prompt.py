"""Unit tests for the IDA docs reviewer prompt.

Task 10 of 13 (offline docs tool).  These tests pin the reviewer
prompt so that ``lookup_idapython_doc`` is the preferred doc source
and ``web_fetch`` is demoted to a fallback only.
"""

from __future__ import annotations

import unittest


class TestReviewerPromptPrefersTool(unittest.TestCase):
    def test_prompt_mentions_lookup_idapython_doc(self):
        from rikugan.agent.agents.ida_docs_reviewer import IDA_DOCS_REVIEWER_PROMPT

        self.assertIn("lookup_idapython_doc", IDA_DOCS_REVIEWER_PROMPT)

    def test_prompt_demotes_web_fetch_to_fallback(self):
        from rikugan.agent.agents.ida_docs_reviewer import (
            build_ida_docs_reviewer_addendum,
        )

        prompt = build_ida_docs_reviewer_addendum()
        tool_idx = prompt.find("lookup_idapython_doc")
        self.assertGreater(tool_idx, -1, "lookup_idapython_doc not in prompt")
        # The first web_fetch occurrence after the tool entry should exist
        # (tool first → fallback later).
        web_fetch_idx = prompt.find("web_fetch", tool_idx) if tool_idx >= 0 else -1
        self.assertGreater(web_fetch_idx, -1, "web_fetch not in prompt after the tool")
        # Tool appears strictly before its fallback statement
        self.assertLess(tool_idx, web_fetch_idx)

    def test_prompt_explains_fallback_reason(self):
        from rikugan.agent.agents.ida_docs_reviewer import IDA_DOCS_REVIEWER_PROMPT

        # The fallback should mention "not in bundle" or similar
        lowered = IDA_DOCS_REVIEWER_PROMPT.lower()
        self.assertTrue(
            "not in bundle" in lowered or "fall back" in lowered,
            "Prompt should explain when to fall back to web_fetch",
        )


if __name__ == "__main__":
    unittest.main()
