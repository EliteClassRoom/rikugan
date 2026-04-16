"""Tests for Gemini provider: error handling, format history, builtin models."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()


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


if __name__ == "__main__":
    unittest.main()
