"""Tests for provider types and registry."""

from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.core.types import Message, Role, ToolCall, ToolResult, TokenUsage, StreamChunk
from rikugan.providers.registry import ProviderRegistry
from rikugan.core.errors import ProviderError


class TestMessageTypes(unittest.TestCase):
    def test_message_serialization(self):
        msg = Message(
            role=Role.ASSISTANT,
            content="Hello",
            tool_calls=[
                ToolCall(id="call_123", name="test", arguments={"x": 1}),
            ],
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        d = msg.to_dict()
        self.assertEqual(d["role"], "assistant")
        self.assertEqual(d["content"], "Hello")
        self.assertEqual(len(d["tool_calls"]), 1)
        self.assertEqual(d["tool_calls"][0]["name"], "test")

    def test_message_roundtrip(self):
        original = Message(
            role=Role.USER,
            content="Test message",
        )
        d = original.to_dict()
        restored = Message.from_dict(d)
        self.assertEqual(restored.role, Role.USER)
        self.assertEqual(restored.content, "Test message")

    def test_tool_result_serialization(self):
        msg = Message(
            role=Role.TOOL,
            tool_results=[
                ToolResult(tool_call_id="call_123", name="test", content="result"),
            ],
        )
        d = msg.to_dict()
        self.assertEqual(len(d["tool_results"]), 1)
        self.assertEqual(d["tool_results"][0]["content"], "result")


class TestStreamChunk(unittest.TestCase):
    def test_text_chunk(self):
        chunk = StreamChunk(text="hello")
        self.assertEqual(chunk.text, "hello")
        self.assertFalse(chunk.is_tool_call_start)

    def test_tool_call_chunk(self):
        chunk = StreamChunk(
            tool_call_id="call_1",
            tool_name="test_tool",
            is_tool_call_start=True,
        )
        self.assertTrue(chunk.is_tool_call_start)
        self.assertEqual(chunk.tool_name, "test_tool")


class TestProviderRegistry(unittest.TestCase):
    def test_list_providers(self):
        reg = ProviderRegistry()
        providers = reg.list_providers()
        self.assertIn("anthropic", providers)
        self.assertIn("openai", providers)
        self.assertIn("gemini", providers)
        self.assertIn("ollama", providers)

    def test_unknown_provider(self):
        reg = ProviderRegistry()
        with self.assertRaises(ProviderError):
            reg.create("nonexistent")


if __name__ == "__main__":
    unittest.main()
