"""Tests for provider types and registry."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks

install_ida_mocks()

# Defensive: drop any ``_StubModule`` entries a sibling test file
# (e.g. ``tests/tools/test_panel_core.py``) left in ``sys.modules``
# before we import the real rikugan modules.  Without this purge
# the provider tests would see a ``MagicMock`` registry and fail
# with ``AttributeError: __name__`` on ``assertRaises``.
from tests import purge_rikugan_stubs

purge_rikugan_stubs()

from rikugan.core.errors import ProviderError
from rikugan.core.types import Message, Role, StreamChunk, TokenUsage, ToolCall, ToolResult
from rikugan.providers.registry import ProviderRegistry


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

    def test_dependency_warnings_returns_list(self):
        """dependency_warnings() exists and returns a list (regression: the
        method was missing on MAIN, causing panel_core to log
        'ProviderRegistry' object has no attribute 'dependency_warnings')."""
        reg = ProviderRegistry()
        warnings = reg.dependency_warnings()
        self.assertIsInstance(warnings, list)
        # Each warning is a human-readable string (no internal objects leaked).
        for w in warnings:
            self.assertIsInstance(w, str)



class TestProviderDefaultSync(unittest.TestCase):
    """Ensure PROVIDER_DEFAULT_MODELS stays in sync with provider constructors."""

    def test_anthropic_default_matches_constructor(self):
        from rikugan.core.config import PROVIDER_DEFAULT_MODELS
        from rikugan.providers.anthropic_provider import AnthropicProvider

        p = AnthropicProvider.__new__(AnthropicProvider)
        p.model = ""  # __init__ not called
        default = AnthropicProvider.__init__.__defaults__
        if default:
            # First positional after self is api_key="", api_base="", model=...
            constructor_model = default[2]  # model is 3rd default (api_key, api_base, model)
            self.assertEqual(PROVIDER_DEFAULT_MODELS["anthropic"], constructor_model)

    def test_openai_default_matches_constructor(self):
        from rikugan.core.config import PROVIDER_DEFAULT_MODELS
        from rikugan.providers.openai_provider import OpenAIProvider

        p = OpenAIProvider.__new__(OpenAIProvider)
        default = OpenAIProvider.__init__.__defaults__
        if default:
            constructor_model = default[2]  # model is 3rd default (api_key, api_base, model)
            self.assertEqual(PROVIDER_DEFAULT_MODELS["openai"], constructor_model)

    def test_gemini_default_matches_constructor(self):
        from rikugan.core.config import PROVIDER_DEFAULT_MODELS
        from rikugan.providers.gemini_provider import GeminiProvider

        p = GeminiProvider.__new__(GeminiProvider)
        default = GeminiProvider.__init__.__defaults__
        if default:
            constructor_model = default[1]  # model is 2nd default (api_key, model)
            self.assertEqual(PROVIDER_DEFAULT_MODELS["gemini"], constructor_model)

    def test_minimax_default_matches_constructor(self):
        from rikugan.core.config import PROVIDER_DEFAULT_MODELS
        from rikugan.providers.minimax_provider import MiniMaxProvider

        p = MiniMaxProvider.__new__(MiniMaxProvider)
        default = MiniMaxProvider.__init__.__defaults__
        if default:
            constructor_model = default[2]  # model is 3rd default (api_key, api_base, model)
            self.assertEqual(PROVIDER_DEFAULT_MODELS["minimax"], constructor_model)


class TestAuthenticationGuidance(unittest.TestCase):
    """Verify AuthenticationError includes provider-specific guidance."""

    def test_anthropic_guidance(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError(provider="anthropic")
        msg = str(err)
        self.assertIn("ANTHROPIC_API_KEY", msg)
        self.assertIn("claude setup-token", msg)

    def test_openai_guidance(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError(provider="openai")
        msg = str(err)
        self.assertIn("OPENAI_API_KEY", msg)

    def test_gemini_guidance(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError(provider="gemini")
        msg = str(err)
        self.assertIn("GOOGLE_API_KEY", msg)
        self.assertIn("GEMINI_API_KEY", msg)

    def test_minimax_guidance(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError(provider="minimax")
        msg = str(err)
        self.assertIn("MINIMAX_API_KEY", msg)

    def test_ollama_guidance(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError(provider="ollama")
        msg = str(err)
        self.assertIn("does not require an API key", msg)
        self.assertIn("OLLAMA_BASE_URL", msg)

    def test_openai_compat_guidance(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError(provider="openai_compat")
        msg = str(err)
        self.assertIn("API key", msg)
        self.assertIn("base URL", msg)

    def test_unknown_provider_generic_guidance(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError(provider="unknown_provider_xyz")
        msg = str(err)
        self.assertIn("environment variable", msg)
        self.assertIn("Rikugan settings", msg)

    def test_explicit_guidance_overrides_provider(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError(
            provider="openai",
            guidance="Custom instructions here.",
        )
        msg = str(err)
        self.assertIn("Custom instructions here.", msg)

    def test_no_provider_default_message(self):
        from rikugan.core.errors import AuthenticationError

        err = AuthenticationError()
        msg = str(err)
        self.assertEqual(msg, "Invalid or missing API key")


if __name__ == "__main__":
    unittest.main()
