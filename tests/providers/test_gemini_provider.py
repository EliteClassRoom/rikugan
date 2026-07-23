"""Tests for Gemini provider: error handling, format history, builtin models."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks

install_ida_mocks()

from rikugan.core.types import LLMRequestContext, Message, Role


def _make_provider():
    from rikugan.providers.gemini_provider import GeminiProvider

    return GeminiProvider(api_key="test-key", model="gemini-test")


class TestGeminiHandleApiError(unittest.TestCase):
    def test_generic_error_raises_provider_error(self):
        from rikugan.core.errors import ProviderError

        p = _make_provider()
        with self.assertRaises(ProviderError):
            p._handle_api_error(RuntimeError("something broke"))

    def test_auth_error_from_string_matching(self):
        from rikugan.core.errors import AuthenticationError

        p = _make_provider()
        with self.assertRaises(AuthenticationError):
            p._handle_api_error(RuntimeError("Invalid API key provided"))

    def test_rate_limit_from_string_matching(self):
        from rikugan.core.errors import RateLimitError

        p = _make_provider()
        with self.assertRaises(RateLimitError):
            p._handle_api_error(RuntimeError("Rate limit exceeded, 429"))

    def test_context_length_from_string(self):
        from rikugan.core.errors import ContextLengthError

        p = _make_provider()
        with self.assertRaises(ContextLengthError):
            p._handle_api_error(RuntimeError("token limit exceeded"))

    def test_permission_denied_from_string(self):
        from rikugan.core.errors import AuthenticationError

        p = _make_provider()
        with self.assertRaises(AuthenticationError):
            p._handle_api_error(RuntimeError("permission denied"))


class TestGeminiFormatHistory(unittest.TestCase):
    """Test GeminiProvider._format_history (basic path without genai SDK)."""

    def test_builtin_models(self):
        from rikugan.providers.gemini_provider import GeminiProvider

        models = GeminiProvider._builtin_models()
        self.assertTrue(len(models) > 0)
        for m in models:
            self.assertEqual(m.provider, "gemini")
            self.assertTrue(m.context_window > 0)


class TestGeminiCapabilities(unittest.TestCase):
    def test_capabilities(self):
        p = _make_provider()
        caps = p.capabilities
        self.assertTrue(caps.streaming)
        self.assertTrue(caps.tool_use)


# ---------------------------------------------------------------------------
# Task 5: payload equivalence.
# ---------------------------------------------------------------------------


class TestGeminiRequestContextPayloadEquivalence(unittest.TestCase):
    def test_request_context_does_not_change_gemini_payload(self) -> None:
        import importlib

        provider = _make_provider()
        # The google-genai SDK is optional; load types only if available.
        # Without types the Gemini build path cannot construct a real
        # ``GenerateContentConfig`` payload, so we skip the assertion
        # rather than fabricating a fake module.
        try:
            provider._types = importlib.import_module("google.genai.types")
        except ImportError:
            self.skipTest("google-genai SDK not installed")

        messages = [Message(role=Role.USER, content="hello")]
        baseline = provider._build_request_kwargs(messages, None, 0.3, 4096, "system")
        contextual = provider._build_request_kwargs(
            messages,
            None,
            0.3,
            4096,
            "system",
            request_context=LLMRequestContext(recovery=True),
        )

        self.assertEqual(
            contextual,
            baseline,
            "Gemini payload differs when request_context is provided — "
            "the context must be a pure pass-through for non-GLM "
            "providers.",
        )


if __name__ == "__main__":
    unittest.main()
