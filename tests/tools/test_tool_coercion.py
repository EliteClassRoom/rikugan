"""Tests for tool argument coercion in ToolRegistry."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.tools.base import ParameterSchema, ToolDefinition
from rikugan.tools.registry import ToolRegistry


def _make_defn(params: list[ParameterSchema]) -> ToolDefinition:
    """Helper to create a ToolDefinition with given params."""
    return ToolDefinition(
        name="test_tool",
        description="test",
        parameters=params,
        handler=lambda **kw: str(kw),
    )


class TestCoerceArguments(unittest.TestCase):
    """Tests for ToolRegistry._coerce_arguments()."""

    def test_string_to_int(self):
        defn = _make_defn([ParameterSchema(name="count", type="integer")])
        result = ToolRegistry._coerce_arguments(defn, {"count": "30"})
        self.assertEqual(result["count"], 30)
        self.assertIsInstance(result["count"], int)

    def test_float_string_to_int(self):
        defn = _make_defn([ParameterSchema(name="count", type="integer")])
        result = ToolRegistry._coerce_arguments(defn, {"count": "30.0"})
        self.assertEqual(result["count"], 30)

    def test_bool_true_to_int(self):
        """bool is a subclass of int — should be coerced to plain int."""
        defn = _make_defn([ParameterSchema(name="count", type="integer")])
        result = ToolRegistry._coerce_arguments(defn, {"count": True})
        self.assertEqual(result["count"], 1)
        # Verify it's a plain int, not a bool
        self.assertIs(type(result["count"]), int)

    def test_bool_false_to_int(self):
        defn = _make_defn([ParameterSchema(name="count", type="integer")])
        result = ToolRegistry._coerce_arguments(defn, {"count": False})
        self.assertEqual(result["count"], 0)
        self.assertIs(type(result["count"]), int)

    def test_int_zero_to_bool_false(self):
        """Integer 0 should coerce to False for boolean params."""
        defn = _make_defn([ParameterSchema(name="flag", type="boolean")])
        result = ToolRegistry._coerce_arguments(defn, {"flag": 0})
        self.assertFalse(result["flag"])
        self.assertIsInstance(result["flag"], bool)

    def test_int_one_to_bool_true(self):
        """Integer 1 should coerce to True for boolean params."""
        defn = _make_defn([ParameterSchema(name="flag", type="boolean")])
        result = ToolRegistry._coerce_arguments(defn, {"flag": 1})
        self.assertTrue(result["flag"])
        self.assertIsInstance(result["flag"], bool)

    def test_string_true_to_bool(self):
        defn = _make_defn([ParameterSchema(name="flag", type="boolean")])
        result = ToolRegistry._coerce_arguments(defn, {"flag": "true"})
        self.assertTrue(result["flag"])

    def test_string_false_to_bool(self):
        defn = _make_defn([ParameterSchema(name="flag", type="boolean")])
        result = ToolRegistry._coerce_arguments(defn, {"flag": "false"})
        self.assertFalse(result["flag"])

    def test_string_yes_to_bool(self):
        defn = _make_defn([ParameterSchema(name="flag", type="boolean")])
        result = ToolRegistry._coerce_arguments(defn, {"flag": "yes"})
        self.assertTrue(result["flag"])

    def test_int_to_string(self):
        defn = _make_defn([ParameterSchema(name="name", type="string")])
        result = ToolRegistry._coerce_arguments(defn, {"name": 42})
        self.assertEqual(result["name"], "42")

    def test_string_to_number(self):
        defn = _make_defn([ParameterSchema(name="ratio", type="number")])
        result = ToolRegistry._coerce_arguments(defn, {"ratio": "3.14"})
        self.assertAlmostEqual(result["ratio"], 3.14)

    def test_native_types_unchanged(self):
        """Values already matching their schema type should pass through."""
        defn = _make_defn([
            ParameterSchema(name="count", type="integer"),
            ParameterSchema(name="flag", type="boolean"),
            ParameterSchema(name="name", type="string"),
        ])
        result = ToolRegistry._coerce_arguments(defn, {
            "count": 42, "flag": True, "name": "hello",
        })
        self.assertEqual(result["count"], 42)
        self.assertTrue(result["flag"])
        self.assertEqual(result["name"], "hello")

    def test_unknown_param_ignored(self):
        defn = _make_defn([ParameterSchema(name="count", type="integer")])
        result = ToolRegistry._coerce_arguments(defn, {"count": 5, "extra": "ignored"})
        self.assertEqual(result["count"], 5)
        self.assertEqual(result["extra"], "ignored")

    def test_empty_arguments(self):
        defn = _make_defn([ParameterSchema(name="x", type="integer")])
        result = ToolRegistry._coerce_arguments(defn, {})
        self.assertEqual(result, {})

    def test_invalid_value_passes_through(self):
        """Unparseable values should pass through for the handler to reject."""
        defn = _make_defn([ParameterSchema(name="count", type="integer")])
        result = ToolRegistry._coerce_arguments(defn, {"count": "not_a_number"})
        self.assertEqual(result["count"], "not_a_number")


if __name__ == "__main__":
    unittest.main()
