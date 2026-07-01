"""Tests for provider streaming (chat_stream) paths.

These tests exercise the complex streaming state machines in each provider
using mock stream objects, without requiring the actual SDK packages.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks

install_ida_mocks()

from rikugan.core.types import Message, Role


class TestAnthropicStreaming(unittest.TestCase):
    """Test AnthropicProvider.chat_stream with mock Anthropic stream events."""

    def _make_provider(self):
        from rikugan.providers.anthropic_provider import AnthropicProvider

        p = AnthropicProvider(api_key="test-key", model="claude-test")
        return p

    def _mock_stream_events(self, events):
        """Create a mock context manager that yields events."""
        stream_mock = MagicMock()
        stream_mock.__iter__ = MagicMock(return_value=iter(events))
        stream_mock.__enter__ = MagicMock(return_value=stream_mock)
        stream_mock.__exit__ = MagicMock(return_value=False)
        return stream_mock

    def test_text_only_stream(self):
        """Stream with text-only content blocks."""
        events = [
            SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="text", text="")),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="Hello ")),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="world")),
            SimpleNamespace(type="content_block_stop"),
            SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="end_turn")),
        ]

        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = self._mock_stream_events(events)
        p._client = mock_client

        chunks = list(p.chat_stream([Message(role=Role.USER, content="Hi")]))

        texts = [c.text for c in chunks if c.text]
        self.assertEqual(texts, ["Hello ", "world"])
        finish = [c for c in chunks if c.finish_reason]
        self.assertEqual(len(finish), 1)
        self.assertEqual(finish[0].finish_reason, "end_turn")

    def test_tool_call_stream(self):
        """Stream with a tool_use content block."""
        events = [
            SimpleNamespace(
                type="content_block_start", content_block=SimpleNamespace(type="tool_use", id="tc_1", name="get_info")
            ),
            SimpleNamespace(
                type="content_block_delta", delta=SimpleNamespace(type="input_json_delta", partial_json='{"key":')
            ),
            SimpleNamespace(
                type="content_block_delta", delta=SimpleNamespace(type="input_json_delta", partial_json='"val"}')
            ),
            SimpleNamespace(type="content_block_stop"),
        ]

        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = self._mock_stream_events(events)
        p._client = mock_client

        chunks = list(p.chat_stream([Message(role=Role.USER, content="Use tool")]))

        starts = [c for c in chunks if c.is_tool_call_start]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0].tool_call_id, "tc_1")
        self.assertEqual(starts[0].tool_name, "get_info")

        args_deltas = [c.tool_args_delta for c in chunks if c.tool_args_delta and not c.is_tool_call_end]
        self.assertEqual(args_deltas, ['{"key":', '"val"}'])

        ends = [c for c in chunks if c.is_tool_call_end]
        self.assertEqual(len(ends), 1)

    def test_message_start_usage(self):
        """Stream emits usage from message_start event."""
        events = [
            SimpleNamespace(type="message_start", message=SimpleNamespace(usage=SimpleNamespace(input_tokens=42))),
            SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="text", text="")),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="OK")),
            SimpleNamespace(type="content_block_stop"),
        ]

        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = self._mock_stream_events(events)
        p._client = mock_client

        chunks = list(p.chat_stream([Message(role=Role.USER, content="Hi")]))
        usage_chunks = [c for c in chunks if c.usage is not None]
        self.assertEqual(len(usage_chunks), 1)
        self.assertEqual(usage_chunks[0].usage.prompt_tokens, 42)


class TestOpenAIStreaming(unittest.TestCase):
    """Test OpenAIProvider.chat_stream with mock OpenAI stream chunks."""

    def _make_provider(self):
        from rikugan.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key="test-key", model="gpt-test")

    def test_text_only_stream(self):
        """Stream with text-only deltas."""
        stream_chunks = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="Hello ", tool_calls=None),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="world", tool_calls=None),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=None, tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            ),
        ]

        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter(stream_chunks)
        p._client = mock_client

        chunks = list(p.chat_stream([Message(role=Role.USER, content="Hi")]))

        texts = [c.text for c in chunks if c.text]
        self.assertEqual(texts, ["Hello ", "world"])
        finish = [c for c in chunks if c.finish_reason]
        self.assertEqual(len(finish), 1)
        self.assertEqual(finish[0].finish_reason, "stop")

    def test_tool_call_stream(self):
        """Stream with tool call deltas."""
        stream_chunks = [
            # First chunk: tool call start
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="tc_1",
                                    function=SimpleNamespace(name="get_info", arguments=""),
                                )
                            ],
                        ),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            # Second chunk: tool args
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(name=None, arguments='{"x": 1}'),
                                )
                            ],
                        ),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            # Third chunk: finish
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=None, tool_calls=None),
                        finish_reason="tool_calls",
                    )
                ],
                usage=None,
            ),
        ]

        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter(stream_chunks)
        p._client = mock_client

        chunks = list(p.chat_stream([Message(role=Role.USER, content="Use tool")]))

        starts = [c for c in chunks if c.is_tool_call_start]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0].tool_call_id, "tc_1")
        self.assertEqual(starts[0].tool_name, "get_info")

        ends = [c for c in chunks if c.is_tool_call_end]
        self.assertEqual(len(ends), 1)

    def test_usage_chunk(self):
        """Stream reports usage in final chunk."""
        stream_chunks = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="OK", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
            ),
        ]

        p = self._make_provider()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter(stream_chunks)
        p._client = mock_client

        chunks = list(p.chat_stream([Message(role=Role.USER, content="Hi")]))
        usage_chunks = [c for c in chunks if c.usage is not None]
        self.assertEqual(len(usage_chunks), 1)
        self.assertEqual(usage_chunks[0].usage.total_tokens, 15)


# ---------------------------------------------------------------------------
# Cancellation: verify chat_stream honors a cancel_event by force-closing the
# underlying HTTP stream. Without this, user-clicks-Stop during a long model
# response has no effect until the next SSE chunk arrives (could be minutes).
# ---------------------------------------------------------------------------


class _BlockingAnthropicStream:
    """Fake Anthropic stream that yields one chunk then blocks on iteration.

    Simulates a real SDK stream waiting on HTTP recv() for the next SSE event.
    The ``close()`` method unblocks iteration (real SDKs do this on socket
    close, raising ``httpx.RemoteProtocolError`` inside the consumer).
    """

    def __init__(self) -> None:
        self.close_called = threading.Event()
        self.iter_started = threading.Event()

    def __iter__(self):
        self.iter_started.set()
        yield SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="text", text=""),
        )
        yield SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="hi"),
        )
        # Block until close() is called (or test times out)
        if not self.close_called.wait(timeout=5.0):
            raise RuntimeError("test bug: stream close() never called")
        # Real SDK raises on closed connection
        raise RuntimeError("stream closed by client")

    def close(self) -> None:
        self.close_called.set()

    def __enter__(self) -> _BlockingAnthropicStream:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.close()
        return False


class TestAnthropicCancelDuringStream(unittest.TestCase):
    """User clicks Stop while model is mid-stream. Verify close() is called."""

    def test_cancel_event_closes_stream_promptly(self) -> None:
        from rikugan.providers.anthropic_provider import AnthropicProvider

        p = AnthropicProvider(api_key="test-key", model="claude-test")
        blocking = _BlockingAnthropicStream()

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = blocking
        p._client = mock_client

        cancel = threading.Event()
        cancel.set()  # simulate Stop already clicked before we start consuming

        start = time.monotonic()
        consumer_exc: list = []

        def consume() -> None:
            try:
                # The provider must accept ``cancel_event`` (new API surface).
                list(
                    p.chat_stream(
                        [Message(role=Role.USER, content="hi")],
                        cancel_event=cancel,
                    )
                )
            except Exception as e:
                consumer_exc.append(e)

        t = threading.Thread(target=consume, daemon=True)
        t.start()
        t.join(timeout=1.0)
        elapsed = time.monotonic() - start

        self.assertFalse(
            t.is_alive(),
            f"consumer thread did not exit within 1s (elapsed={elapsed:.2f}s) "
            f"— cancel_event did not interrupt the streaming read",
        )
        self.assertTrue(
            blocking.close_called.is_set(),
            "stream.close() was never called — watchdog never fired",
        )


class _BlockingOpenAIStream:
    """Fake OpenAI stream: yields one chunk then blocks; close() unblocks."""

    def __init__(self) -> None:
        self.close_called = threading.Event()

    def __iter__(self):
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="hi", tool_calls=None),
                    finish_reason=None,
                )
            ],
            usage=None,
        )
        if not self.close_called.wait(timeout=5.0):
            raise RuntimeError("test bug: stream never closed")
        raise RuntimeError("stream closed by client")

    def close(self) -> None:
        self.close_called.set()


class TestOpenAICancelDuringStream(unittest.TestCase):
    """User clicks Stop while OpenAI model is mid-stream."""

    def test_cancel_event_closes_stream_promptly(self) -> None:
        from rikugan.providers.openai_provider import OpenAIProvider

        p = OpenAIProvider(api_key="test-key", model="gpt-test")
        blocking = _BlockingOpenAIStream()

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = blocking
        p._client = mock_client

        cancel = threading.Event()
        cancel.set()

        start = time.monotonic()

        def consume() -> None:
            try:
                list(
                    p.chat_stream(
                        [Message(role=Role.USER, content="hi")],
                        cancel_event=cancel,
                    )
                )
            except Exception:
                pass

        t = threading.Thread(target=consume, daemon=True)
        t.start()
        t.join(timeout=1.0)
        elapsed = time.monotonic() - start

        self.assertFalse(
            t.is_alive(),
            f"OpenAI consumer thread did not exit within 1s (elapsed={elapsed:.2f}s)",
        )
        self.assertTrue(
            blocking.close_called.is_set(),
            "OpenAI stream.close() was never called",
        )


if __name__ == "__main__":
    unittest.main()
