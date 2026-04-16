"""Tests for OpenAI provider: message formatting, normalization, error handling."""

from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.core.types import Message, Role, ToolCall, ToolResult


def _make_provider():
    from rikugan.providers.openai_provider import OpenAIProvider
    return OpenAIProvider(api_key="test-key", model="gpt-test")


class TestOpenAIFormatMessages(unittest.TestCase):
    def test_user_message(self):
        p = _make_provider()
        msgs = [Message(role=Role.USER, content="Hello")]
        result = p._format_messages(msgs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "user")

    def test_system_message_included(self):
        """OpenAI keeps system messages in the message array."""
        p = _make_provider()
        msgs = [
            Message(role=Role.SYSTEM, content="You are a helper"),
            Message(role=Role.USER, content="Hi"),
        ]
        result = p._format_messages(msgs)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["role"], "system")

    def test_assistant_with_tool_calls(self):
        p = _make_provider()
        msgs = [Message(
            role=Role.ASSISTANT,
            content="Checking",
            tool_calls=[ToolCall(id="tc_1", name="get_info", arguments={"x": 1})],
        )]
        result = p._format_messages(msgs)
        self.assertEqual(result[0]["role"], "assistant")
        self.assertEqual(result[0]["content"], "Checking")
        self.assertEqual(len(result[0]["tool_calls"]), 1)
        tc = result[0]["tool_calls"][0]
        self.assertEqual(tc["id"], "tc_1")
        self.assertEqual(tc["type"], "function")
        self.assertEqual(tc["function"]["name"], "get_info")
        self.assertEqual(json.loads(tc["function"]["arguments"]), {"x": 1})

    def test_tool_results_use_tool_role(self):
        """OpenAI keeps tool results as 'tool' role messages."""
        p = _make_provider()
        msgs = [Message(
            role=Role.TOOL,
            tool_results=[
                ToolResult(tool_call_id="tc_1", name="get_info", content="result"),
            ],
        )]
        result = p._format_messages(msgs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "tool")
        self.assertEqual(result[0]["tool_call_id"], "tc_1")
        self.assertEqual(result[0]["content"], "result")


class TestOpenAINormalizeResponse(unittest.TestCase):
    def test_text_response(self):
        p = _make_provider()
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="Hello", tool_calls=None),
            )],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        msg = p._normalize_response(response)
        self.assertEqual(msg.content, "Hello")
        self.assertEqual(msg.tool_calls, [])
        self.assertEqual(msg.token_usage.total_tokens, 15)

    def test_tool_call_response(self):
        p = _make_provider()
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[SimpleNamespace(
                        id="tc_1",
                        function=SimpleNamespace(
                            name="test_tool",
                            arguments='{"key": "val"}',
                        ),
                    )],
                ),
            )],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        )
        msg = p._normalize_response(response)
        self.assertEqual(msg.content, "")
        self.assertEqual(len(msg.tool_calls), 1)
        self.assertEqual(msg.tool_calls[0].name, "test_tool")
        self.assertEqual(msg.tool_calls[0].arguments, {"key": "val"})

    def test_no_usage(self):
        p = _make_provider()
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="OK", tool_calls=None),
            )],
            usage=None,
        )
        msg = p._normalize_response(response)
        self.assertEqual(msg.token_usage.total_tokens, 0)


class TestOpenAIHandleApiError(unittest.TestCase):
    def test_generic_error_raises_provider_error(self):
        from rikugan.core.errors import ProviderError
        p = _make_provider()
        with self.assertRaises(ProviderError):
            p._handle_api_error(RuntimeError("something broke"))

    def test_context_length_string(self):
        from rikugan.core.errors import ProviderError
        p = _make_provider()
        with self.assertRaises(ProviderError):
            p._handle_api_error(RuntimeError("maximum context length exceeded"))


if __name__ == "__main__":
    unittest.main()
