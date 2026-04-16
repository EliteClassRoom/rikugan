"""Tests for the tool framework."""

from __future__ import annotations

import sys
import os
import unittest

# Install mocks before importing Rikugan modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.tools.base import tool
from rikugan.tools.registry import ToolRegistry
from rikugan.core.errors import ToolNotFoundError


class TestToolDecorator(unittest.TestCase):
    def test_basic_tool_registration(self):
        @tool(name="test_tool", description="A test tool")
        def my_tool(x: int, y: str = "hello") -> str:
            return f"{x}-{y}"

        defn = my_tool._tool_definition
        self.assertEqual(defn.name, "test_tool")
        self.assertEqual(defn.description, "A test tool")
        self.assertEqual(len(defn.parameters), 2)

        # x is required
        self.assertEqual(defn.parameters[0].name, "x")
        self.assertEqual(defn.parameters[0].type, "integer")
        self.assertTrue(defn.parameters[0].required)

        # y has default
        self.assertEqual(defn.parameters[1].name, "y")
        self.assertEqual(defn.parameters[1].type, "string")
        self.assertFalse(defn.parameters[1].required)

    def test_tool_json_schema(self):
        @tool()
        def another_tool(name: str, count: int = 5) -> str:
            """Do something."""
            return "ok"

        schema = another_tool._tool_definition.to_json_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("name", schema["properties"])
        self.assertIn("count", schema["properties"])
        self.assertIn("name", schema["required"])
        self.assertNotIn("count", schema["required"])

    def test_tool_provider_format(self):
        @tool(name="my_func", description="My function")
        def my_func(a: str) -> str:
            return a

        fmt = my_func._tool_definition.to_provider_format()
        self.assertEqual(fmt["type"], "function")
        self.assertEqual(fmt["function"]["name"], "my_func")

    def test_tool_execution_wraps_errors(self):
        @tool(name="failing_tool")
        def failing_tool() -> str:
            """Fails."""
            raise ValueError("boom")

        from rikugan.core.errors import ToolError
        with self.assertRaises(ToolError):
            failing_tool()


class TestToolRegistry(unittest.TestCase):
    def test_register_and_execute(self):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> str:
            """Add two numbers."""
            return str(a + b)

        registry.register_function(add)
        result = registry.execute("add", {"a": 3, "b": 4})
        self.assertEqual(result, "7")

    def test_unknown_tool(self):
        registry = ToolRegistry()
        with self.assertRaises(ToolNotFoundError):
            registry.execute("nonexistent", {})

    def test_list_tools(self):
        registry = ToolRegistry()

        @tool(name="t1")
        def t1() -> str:
            """Tool 1."""
            return "1"

        @tool(name="t2")
        def t2() -> str:
            """Tool 2."""
            return "2"

        registry.register_function(t1)
        registry.register_function(t2)
        self.assertEqual(set(registry.list_names()), {"t1", "t2"})


class TestBuiltinTools(unittest.TestCase):
    """Test that built-in tools are loadable (using mocks)."""

    def test_navigation_tools(self):
        from rikugan.ida.tools.navigation import get_cursor_position
        result = get_cursor_position()
        self.assertTrue(result.startswith("0x"))

    def test_database_tools_loadable(self):
        from rikugan.ida.tools import database
        self.assertTrue(hasattr(database, "get_binary_info"))


if __name__ == "__main__":
    unittest.main()
