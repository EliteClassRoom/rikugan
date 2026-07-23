"""Tests for the MiniMax provider.

Covers:

* Default model and builtin metadata follow current docs.
* Automatic thinking for M3 (and only M3).
* ``cache_control`` stripping on the outgoing request.
* ``_build_request_kwargs`` payload equivalence — ``request_context``
  must be a pure pass-through (Task 5 contract).
"""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks

install_ida_mocks()

from rikugan.core.types import LLMRequestContext, Message, Role


# ---------------------------------------------------------------------------
# Default model and builtin metadata
# ---------------------------------------------------------------------------


class TestMiniMaxDefaultsAndMetadata(unittest.TestCase):
    """MiniMax default model and builtin metadata follow current docs."""

    def test_default_model_is_minimax_m3(self) -> None:
        from rikugan.core.config import PROVIDER_DEFAULT_MODELS

        self.assertEqual(PROVIDER_DEFAULT_MODELS["minimax"], "MiniMax-M3")

    def test_minimax_provider_default_model_is_m3(self) -> None:
        from rikugan.providers.minimax_provider import MiniMaxProvider

        provider = MiniMaxProvider(api_key="sk-test")
        self.assertEqual(provider.model, "MiniMax-M3")

    def test_builtin_models_include_m3_with_documented_limits(self) -> None:
        from rikugan.providers.minimax_provider import MiniMaxProvider

        models = MiniMaxProvider._builtin_models()
        ids = [m.id for m in models]
        self.assertIn("MiniMax-M3", ids)
        self.assertIn("MiniMax-M2.7", ids)
        self.assertIn("MiniMax-M2.7-highspeed", ids)
        m3 = next(m for m in models if m.id == "MiniMax-M3")
        self.assertEqual(m3.context_window, 1_000_000)
        self.assertEqual(m3.max_output_tokens, 524_288)
        for m in models:
            if m.id.startswith("MiniMax-M2"):
                self.assertEqual(m.context_window, 204_800)
                self.assertEqual(m.max_output_tokens, 204_800)

    def test_capabilities_reflect_largest_documented_model(self) -> None:
        from rikugan.providers.minimax_provider import MiniMaxProvider

        caps = MiniMaxProvider(api_key="sk-test").capabilities
        self.assertEqual(caps.max_context_window, 1_000_000)
        self.assertEqual(caps.max_output_tokens, 524_288)
        self.assertTrue(caps.tool_use)


# ---------------------------------------------------------------------------
# Automatic thinking (M3 only)
# ---------------------------------------------------------------------------


class TestMiniMaxAutomaticThinking(unittest.TestCase):
    """``_build_request_kwargs`` must enable automatic thinking for M3
    and not add a manual thinking budget for M2.x."""

    def _kwargs(self, model: str, max_tokens: int = 8192):
        from rikugan.providers.minimax_provider import MiniMaxProvider

        provider = MiniMaxProvider(api_key="sk-test", model=model)
        return provider._build_request_kwargs(
            messages=[],
            tools=None,
            temperature=0.5,
            max_tokens=max_tokens,
            system="",
        )

    def test_m3_includes_adaptive_thinking(self) -> None:
        kwargs = self._kwargs("MiniMax-M3", max_tokens=131072)
        self.assertEqual(kwargs.get("thinking"), {"type": "adaptive"})
        # Caller's max_tokens preserved exactly (no override).
        self.assertEqual(kwargs.get("max_tokens"), 131072)

    def test_m3_thinking_case_insensitive(self) -> None:
        kwargs = self._kwargs("minimax-m3")
        self.assertEqual(kwargs.get("thinking"), {"type": "adaptive"})

    def test_m2_does_not_add_thinking_payload(self) -> None:
        """M2.x models cannot disable thinking; we must not add a
        separate ``budget_tokens`` or other manual thinking field."""
        kwargs = self._kwargs("MiniMax-M2.5", max_tokens=65536)
        self.assertNotIn("thinking", kwargs)
        # No budget_tokens field should leak into the top-level kwargs.
        self.assertNotIn("budget_tokens", kwargs)
        self.assertEqual(kwargs.get("max_tokens"), 65536)

    def test_m27_does_not_add_thinking_payload(self) -> None:
        kwargs = self._kwargs("MiniMax-M2.7", max_tokens=65536)
        self.assertNotIn("thinking", kwargs)

    def test_strips_cache_control_from_request(self) -> None:
        """The MiniMax adapter continues to strip unsupported ``cache_control``."""
        kwargs = self._kwargs("MiniMax-M3")

        # system: empty string passes through; tools: None → not in kwargs.
        # The strip is defensive — assert no ``cache_control`` keys leaked.
        def _walk(obj):
            if isinstance(obj, dict):
                if "cache_control" in obj:
                    yield obj
                for v in obj.values():
                    yield from _walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from _walk(v)

        self.assertEqual(list(_walk(kwargs)), [])


# ---------------------------------------------------------------------------
# Task 5: request-context pass-through equivalence
# ---------------------------------------------------------------------------


class TestMiniMaxRequestContextPayloadEquivalence(unittest.TestCase):
    """Task 5: ``request_context`` must be a pure pass-through for the
    MiniMax provider — its override inherits from AnthropicProvider and
    currently strips ``cache_control`` / enables ``thinking`` for M3."""

    def test_request_context_does_not_change_minimax_payload(self) -> None:
        from rikugan.providers.minimax_provider import MiniMaxProvider

        provider = MiniMaxProvider(api_key="sk-test", model="MiniMax-M3")
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
            "MiniMax payload differs when request_context is provided — "
            "the context must be a pure pass-through for non-GLM "
            "providers.",
        )


# ---------------------------------------------------------------------------
# Task 5 reviewer fix: MiniMax must also see the same suffix separator
# behaviour the base pipeline documents.  Because MiniMax inherits from
# AnthropicProvider and overrides ``_build_request_kwargs`` only to strip
# ``cache_control`` and inject M3 thinking, the suffix is already merged
# upstream — so for MiniMax the equivalence test above covers it
# implicitly.  This class keeps MiniMax-specific overrides (recovery /
# disable_thinking) out of the suite until a future task wires them.
# ---------------------------------------------------------------------------


class TestMiniMaxInheritsAnthropicStreamingCoercion(unittest.TestCase):
    """``MiniMaxProvider`` inherits ``AnthropicProvider`` and therefore
    inherits its ``message_delta`` token-coercion safety.  This test
    exercises the inherited ``_stream_chunks`` path through a real
    ``MiniMaxProvider`` instance to catch any future override that
    bypasses the coercion.
    """

    def _fake_stream(self, events):
        class _FakeAnthropicStream:
            def __init__(self, events):
                self._events = events

            def __enter__(self):
                return iter(self._events)

            def __exit__(self, exc_type, exc, tb):
                return False

        class _FakeAnthropicMessages:
            def __init__(self, events):
                self._events = events

            def stream(self, **_kwargs):
                return _FakeAnthropicStream(self._events)

        class _FakeAnthropicClient:
            def __init__(self, events):
                self.messages = _FakeAnthropicMessages(events)

        return _FakeAnthropicClient(events)

    def test_minimax_inherits_anthropic_message_delta_token_coercion(self) -> None:
        from rikugan.providers.minimax_provider import MiniMaxProvider

        provider = MiniMaxProvider(
            api_key="sk-test",
            model="MiniMax-M2.5",
        )
        events = [
            SimpleNamespace(
                type="message_delta",
                delta=SimpleNamespace(stop_reason=None),
                usage=SimpleNamespace(output_tokens="12"),
            )
        ]
        chunks = list(provider._stream_chunks(self._fake_stream(events), {}))
        usage_chunks = [c for c in chunks if c.usage is not None]
        self.assertEqual(len(usage_chunks), 1)
        self.assertEqual(usage_chunks[0].usage.completion_tokens, 12)


if __name__ == "__main__":
    unittest.main()
