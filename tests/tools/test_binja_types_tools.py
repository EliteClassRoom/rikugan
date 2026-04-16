"""Tests for _extract_types_dict and _build_struct_decl in binja/tools/types_tools."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.binja.tools.types_tools import _extract_types_dict, _build_struct_decl


class TestExtractTypesDict(unittest.TestCase):
    def test_returns_none_for_none(self):
        assert _extract_types_dict(None) is None

    def test_returns_none_for_unrecognised(self):
        assert _extract_types_dict(42) is None
        assert _extract_types_dict("string") is None
        assert _extract_types_dict([]) is None

    def test_legacy_tuple_with_dict(self):
        sentinel = object()
        result = _extract_types_dict(({"Foo": sentinel}, [], []))
        assert result == {"Foo": sentinel}

    def test_legacy_tuple_first_not_dict(self):
        # Tuple but first element isn't a dict — unrecognised
        assert _extract_types_dict(([], [], [])) is None

    def test_empty_tuple(self):
        assert _extract_types_dict(()) is None

    def test_types_attr_dict(self):
        sentinel = object()
        class FakeResult:
            types = {"Bar": sentinel}
        assert _extract_types_dict(FakeResult()) == {"Bar": sentinel}

    def test_types_attr_list_of_pairs(self):
        sentinel = object()
        class FakeResult:
            types = [("Baz", sentinel)]
        result = _extract_types_dict(FakeResult())
        assert result == {"Baz": sentinel}

    def test_types_attr_list_of_objects(self):
        sentinel = object()
        class FakeTypeInfo:
            name = "Qux"
            type = sentinel
        class FakeResult:
            types = [FakeTypeInfo()]
        result = _extract_types_dict(FakeResult())
        assert result == {"Qux": sentinel}

    def test_types_attr_empty_list(self):
        class FakeResult:
            types = []
        assert _extract_types_dict(FakeResult()) == {}

    def test_types_attr_none_skipped(self):
        class FakeResult:
            types = None
        assert _extract_types_dict(FakeResult()) is None

    def test_qualified_name_stringified(self):
        class QName:
            def __str__(self):
                return "MyStruct"
        sentinel = object()
        class FakeResult:
            types = [(QName(), sentinel)]
        result = _extract_types_dict(FakeResult())
        assert "MyStruct" in result
        assert result["MyStruct"] is sentinel


class TestBuildStructDecl(unittest.TestCase):
    def test_simple_struct(self):
        fields = [
            {"name": "a", "type": "uint32_t", "offset": 0, "size": 4},
            {"name": "b", "type": "uint32_t", "offset": 4, "size": 4},
        ]
        decl = _build_struct_decl("Foo", fields)
        assert "struct Foo {" in decl
        assert "uint32_t a;" in decl
        assert "uint32_t b;" in decl
        assert decl.strip().endswith("};")

    def test_padding_inserted_for_gaps(self):
        fields = [
            {"name": "a", "type": "uint8_t", "offset": 0, "size": 1},
            {"name": "b", "type": "uint32_t", "offset": 4, "size": 4},
        ]
        decl = _build_struct_decl("Bar", fields)
        assert "_pad_1" in decl  # padding between offset 1 and 4

    def test_no_fields_produces_empty_struct(self):
        decl = _build_struct_decl("Empty", [])
        assert "struct Empty {" in decl
        assert "};" in decl


if __name__ == "__main__":
    unittest.main()
