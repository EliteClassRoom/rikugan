"""Tests for rikugan.binja.tools.common helper functions.

All tested functions are pure or accept duck-typed objects, so no BN install needed.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Minimal stubs so the module-level host imports don't break
# ---------------------------------------------------------------------------

def _stub_mod(name: str, **kw) -> types.ModuleType:
    m = types.ModuleType(name)
    m.__dict__.update(kw)
    return m


# binaryninja stub — just needs to be importable
sys.modules.setdefault("binaryninja", _stub_mod("binaryninja"))

from rikugan.binja.tools.compat import call_compat, parse_addr_like  # noqa: E402
from rikugan.binja.tools.fn_utils import (  # noqa: E402
    get_function_end, get_function_name, iter_function_instruction_addresses,
)
from rikugan.binja.tools.sym_utils import (  # noqa: E402
    is_export_symbol, is_import_symbol, symbol_name, symbol_type_name,
)
from rikugan.binja.tools.disasm_utils import render_tokens  # noqa: E402


# ---------------------------------------------------------------------------
# parse_addr_like
# ---------------------------------------------------------------------------

class TestParseAddrLike(unittest.TestCase):
    def test_int_passthrough(self):
        self.assertEqual(parse_addr_like(0x1000), 0x1000)

    def test_hex_string(self):
        self.assertEqual(parse_addr_like("0x1000"), 0x1000)

    def test_decimal_string(self):
        self.assertEqual(parse_addr_like("4096"), 4096)

    def test_zero(self):
        self.assertEqual(parse_addr_like(0), 0)


# ---------------------------------------------------------------------------
# call_compat
# ---------------------------------------------------------------------------

class TestCallCompat(unittest.TestCase):
    def test_calls_first_matching_method(self):
        obj = MagicMock()
        obj.get_function_at.return_value = "result"
        result = call_compat(obj, "get_function_at", "get_func", addr=0x1000)
        self.assertEqual(result, "result")

    def test_falls_back_to_second_method(self):
        # Use a real object with only the second method defined
        class Obj:
            def fallback(self):
                return "fallback_result"
        result = call_compat(Obj(), "nonexistent", "fallback")
        self.assertEqual(result, "fallback_result")

    def test_returns_default_when_no_method(self):
        obj = object()
        result = call_compat(obj, "missing_method", default="sentinel")
        self.assertEqual(result, "sentinel")

    def test_default_is_none(self):
        result = call_compat(object(), "nonexistent")
        self.assertIsNone(result)

    def test_skips_non_callable_attr(self):
        class Obj:
            noncall = 42  # not callable
            def real(self):
                return "real"
        result = call_compat(Obj(), "noncall", "real")
        self.assertEqual(result, "real")


# ---------------------------------------------------------------------------
# get_function_name
# ---------------------------------------------------------------------------

class TestGetFunctionName(unittest.TestCase):
    def test_name_attribute(self):
        func = MagicMock()
        func.name = "my_function"
        self.assertEqual(get_function_name(func), "my_function")

    def test_symbol_full_name_fallback(self):
        func = MagicMock()
        func.name = None
        func.symbol.full_name = "ns::my_function"
        self.assertEqual(get_function_name(func), "ns::my_function")

    def test_sub_address_fallback(self):
        func = MagicMock()
        func.name = None
        func.symbol = None
        func.start = 0x1234
        self.assertEqual(get_function_name(func), "sub_1234")

    def test_empty_name_uses_symbol(self):
        func = MagicMock()
        func.name = ""
        func.symbol.full_name = "fallback_name"
        self.assertEqual(get_function_name(func), "fallback_name")


# ---------------------------------------------------------------------------
# get_function_end
# ---------------------------------------------------------------------------

class TestGetFunctionEnd(unittest.TestCase):
    def test_highest_address_attribute(self):
        func = MagicMock()
        func.highest_address = 0x2000
        func.start = 0x1000
        func.basic_blocks = []
        self.assertEqual(get_function_end(func), 0x2000)

    def test_end_attribute_fallback(self):
        func = MagicMock(spec=["end", "start", "basic_blocks"])
        func.end = 0x1500
        func.start = 0x1000
        func.basic_blocks = []
        result = get_function_end(func)
        self.assertEqual(result, 0x1500)

    def test_returns_start_when_no_end_info(self):
        func = MagicMock(spec=["start", "basic_blocks"])
        func.start = 0x1000
        func.basic_blocks = []
        result = get_function_end(func)
        self.assertEqual(result, 0x1000)


# ---------------------------------------------------------------------------
# render_tokens
# ---------------------------------------------------------------------------

class TestRenderTokens(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(render_tokens([]), "")

    def test_tokens_with_text_attr(self):
        t1 = MagicMock()
        t1.text = "MOV"
        t2 = MagicMock()
        t2.text = " "
        t3 = MagicMock()
        t3.text = "R0, R1"
        self.assertEqual(render_tokens([t1, t2, t3]), "MOV R0, R1")

    def test_tokens_without_text_attr(self):
        result = render_tokens(["hello", " ", "world"])
        self.assertEqual(result, "hello world")

    def test_strips_outer_whitespace(self):
        t = MagicMock()
        t.text = "  padded  "
        self.assertEqual(render_tokens([t]), "padded")


# ---------------------------------------------------------------------------
# symbol_name
# ---------------------------------------------------------------------------

class TestSymbolName(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(symbol_name(None), "")

    def test_full_name(self):
        sym = MagicMock()
        sym.full_name = "std::vector"
        self.assertEqual(symbol_name(sym), "std::vector")

    def test_short_name_fallback(self):
        sym = MagicMock()
        sym.full_name = None
        sym.short_name = "vector"
        self.assertEqual(symbol_name(sym), "vector")

    def test_name_fallback(self):
        sym = MagicMock()
        sym.full_name = None
        sym.short_name = None
        sym.name = "plain"
        self.assertEqual(symbol_name(sym), "plain")

    def test_all_none_returns_empty(self):
        sym = MagicMock()
        sym.full_name = None
        sym.short_name = None
        sym.name = None
        self.assertEqual(symbol_name(sym), "")


# ---------------------------------------------------------------------------
# symbol_type_name
# ---------------------------------------------------------------------------

class TestSymbolTypeName(unittest.TestCase):
    def test_no_type_returns_empty(self):
        sym = MagicMock()
        sym.type = None
        self.assertEqual(symbol_type_name(sym), "")

    def test_type_with_name(self):
        sym = MagicMock()
        sym.type.name = "FunctionSymbol"
        self.assertEqual(symbol_type_name(sym), "FunctionSymbol")

    def test_type_str_fallback(self):
        sym = MagicMock()
        sym.type.name = None
        sym.type.__str__ = lambda self: "TypeRepr"
        self.assertEqual(symbol_type_name(sym), "TypeRepr")


# ---------------------------------------------------------------------------
# is_import_symbol / is_export_symbol
# ---------------------------------------------------------------------------

class TestSymbolKind(unittest.TestCase):
    def test_import_symbol(self):
        sym = MagicMock()
        sym.type.name = "ImportedFunctionSymbol"
        self.assertTrue(is_import_symbol(sym))

    def test_non_import_symbol(self):
        sym = MagicMock()
        sym.type.name = "FunctionSymbol"
        self.assertFalse(is_import_symbol(sym))

    def test_export_symbol(self):
        sym = MagicMock()
        sym.type.name = "ExportedFunctionSymbol"
        self.assertTrue(is_export_symbol(sym))

    def test_non_export_symbol(self):
        sym = MagicMock()
        sym.type.name = "FunctionSymbol"
        self.assertFalse(is_export_symbol(sym))


# ---------------------------------------------------------------------------
# iter_function_instruction_addresses
# ---------------------------------------------------------------------------

class TestIterFunctionInstructionAddresses(unittest.TestCase):
    def _make_bb(self, start: int, end: int) -> MagicMock:
        bb = MagicMock(spec=["start", "end"])
        bb.start = start
        bb.end = end
        return bb

    def test_empty_basic_blocks(self):
        func = MagicMock()
        func.basic_blocks = []
        self.assertEqual(list(iter_function_instruction_addresses(func)), [])

    def test_single_block(self):
        func = MagicMock()
        func.view = None
        func.basic_blocks = [self._make_bb(0x1000, 0x1004)]
        result = list(iter_function_instruction_addresses(func))
        self.assertIn(0x1000, result)

    def test_max_instructions_respected(self):
        func = MagicMock()
        func.view = None
        func.basic_blocks = [self._make_bb(0x1000, 0x1000 + 1000)]
        result = list(iter_function_instruction_addresses(func, max_instructions=5))
        self.assertLessEqual(len(result), 5)


if __name__ == "__main__":
    unittest.main()
