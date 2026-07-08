"""Tests for the system prompt builder."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks

install_ida_mocks()

from rikugan.agent.system_prompt import _BASE_PROMPT, build_system_prompt


class TestBuildSystemPrompt(unittest.TestCase):
    def test_base_prompt_only(self):
        prompt = build_system_prompt()
        self.assertIn("Rikugan", prompt)
        self.assertIn("reverse engineering", prompt)

    def test_with_binary_info(self):
        prompt = build_system_prompt(binary_info="PE32+ x86_64, 256 functions")
        self.assertIn("Current Binary", prompt)
        self.assertIn("PE32+ x86_64", prompt)

    def test_with_current_position(self):
        prompt = build_system_prompt(
            current_address="0x401000",
            current_function="main",
        )
        self.assertIn("Current Position", prompt)
        self.assertIn("0x401000", prompt)
        self.assertIn("main", prompt)

    def test_address_without_function(self):
        prompt = build_system_prompt(current_address="0x401000")
        self.assertIn("0x401000", prompt)
        # Function name should not appear since it's None
        self.assertNotIn("Function:", prompt)

    def test_with_tool_names(self):
        tools = ["decompile_function", "list_imports", "rename_function"]
        prompt = build_system_prompt(tool_names=tools)
        self.assertIn("Available Tools", prompt)
        self.assertIn("decompile_function", prompt)
        self.assertIn("list_imports", prompt)

    def test_with_skill_summary(self):
        summary = "- /malware-analysis: Windows PE malware analysis"
        prompt = build_system_prompt(skill_summary=summary)
        self.assertIn("Skills", prompt)
        self.assertIn("/malware-analysis", prompt)

    def test_with_extra_context(self):
        prompt = build_system_prompt(extra_context="Custom instruction")
        self.assertIn("Additional Context", prompt)
        self.assertIn("Custom instruction", prompt)

    def test_all_parameters(self):
        prompt = build_system_prompt(
            binary_info="ELF x86_64",
            current_function="sub_401000",
            current_address="0x401000",
            extra_context="Focus on crypto functions",
            tool_names=["decompile_function"],
            skill_summary="/vuln-audit: security audit",
        )
        self.assertIn("Current Binary", prompt)
        self.assertIn("Current Position", prompt)
        self.assertIn("Available Tools", prompt)
        self.assertIn("Skills", prompt)
        self.assertIn("Additional Context", prompt)

    def test_none_parameters_excluded(self):
        prompt = build_system_prompt()
        self.assertNotIn("Current Binary", prompt)
        self.assertNotIn("Current Position", prompt)
        self.assertNotIn("Available Tools", prompt)
        self.assertNotIn("Skills", prompt)
        self.assertNotIn("Additional Context", prompt)

    def test_base_prompt_contains_tool_usage_guidance(self):
        self.assertIn("execute_python", _BASE_PROMPT)
        self.assertIn("LAST RESORT", _BASE_PROMPT)

    def test_base_prompt_contains_discipline_section(self):
        self.assertIn("Discipline", _BASE_PROMPT)
        self.assertIn("Do exactly what was asked", _BASE_PROMPT)


class TestBasePromptContent(unittest.TestCase):
    """Verify the base prompt has essential sections."""

    def test_has_capabilities_section(self):
        self.assertIn("## Capabilities", _BASE_PROMPT)

    def test_has_safety_section(self):
        self.assertIn("## Safety", _BASE_PROMPT)

    def test_has_renaming_section(self):
        self.assertIn("## Renaming", _BASE_PROMPT)

    def test_has_analysis_section(self):
        self.assertIn("## Analysis Approach", _BASE_PROMPT)

    def test_renaming_section_covers_all_object_types(self):
        """Baseline RENAMING_SECTION must cover all 6 IDA object types."""
        from rikugan.agent.prompts.base import RENAMING_SECTION

        self.assertIn("PascalCase", RENAMING_SECTION)  # functions
        self.assertIn("snake_case", RENAMING_SECTION)  # variables
        self.assertIn("g_", RENAMING_SECTION)  # globals
        self.assertIn("Enum", RENAMING_SECTION)  # enums
        self.assertIn("Typedef", RENAMING_SECTION)  # typedefs

    def test_renaming_section_references_naming_convention_skill(self):
        """Baseline must point to the naming-convention skill for edge cases."""
        from rikugan.agent.prompts.base import RENAMING_SECTION

        self.assertIn("naming-convention", RENAMING_SECTION)

    def test_base_prompt_recommends_lookup_idapython_doc(self):
        """Main agent prompt must tell agent to use lookup_idapython_doc for API verification,
        and explicitly forbid raw os.path access to the data dir (which bypasses path-traversal protection).
        Regression guard for the agent-bypass-via-os.path issue observed in the wild.
        """
        self.assertIn("lookup_idapython_doc", _BASE_PROMPT)
        # Must mention both how to do it (call the tool) and what NOT to do
        self.assertIn("lookup_idapython_doc(module=", _BASE_PROMPT)
        self.assertIn("Do NOT read those", _BASE_PROMPT)
        # And must call out the specific failure mode
        self.assertIn("os.path.open", _BASE_PROMPT)
        self.assertIn("path-traversal protection", _BASE_PROMPT)

    def test_renaming_section_does_not_reference_ghost_tool(self):
        """Regression: rename_multi_variables is a ghost tool — must NOT be
        referenced as if it exists. See spec self-review round 2."""
        from rikugan.agent.prompts.base import RENAMING_SECTION

        # The phrase 'Use rename_multi_variables when available' must be gone.
        self.assertNotIn("Use rename_multi_variables", RENAMING_SECTION)


if __name__ == "__main__":
    unittest.main()
