"""Tests for the agent loop."""

from __future__ import annotations

import json
import os
import sys
import unittest
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks

install_ida_mocks()

from rikugan.agent.exploration_mode import ExplorationState
from rikugan.agent.loop import AgentLoop, BackgroundAgentRunner
from rikugan.agent.turn import TurnEventType
from rikugan.core.config import RikuganConfig
from rikugan.core.types import (
    Message,
    ModelInfo,
    ProviderCapabilities,
    Role,
    StreamChunk,
    TokenUsage,
    ToolCall,
)
from rikugan.providers.base import LLMProvider
from rikugan.state.session import SessionState
from rikugan.tools.base import ParameterSchema, ToolDefinition
from rikugan.tools.registry import ToolRegistry


class MockProvider(LLMProvider):
    """Mock LLM provider that returns scripted responses."""

    def __init__(self, responses: list[list[StreamChunk]] | None = None):
        super().__init__(api_key="test", model="mock-model")
        self._responses = responses or []
        self._call_count = 0

    @property
    def name(self) -> str:
        return "mock"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def _get_client(self):
        return None

    def _fetch_models_live(self) -> list[ModelInfo]:
        return [ModelInfo(id="mock-model", name="Mock", provider="mock")]

    @staticmethod
    def _builtin_models() -> list[ModelInfo]:
        return [ModelInfo(id="mock-model", name="Mock", provider="mock")]

    def _format_messages(self, messages):
        return messages

    def _normalize_response(self, raw):
        return raw

    def _build_request_kwargs(self, messages, tools, temperature, max_tokens, system):
        return {}

    def _call_api(self, client, kwargs):
        return None

    def _handle_api_error(self, e):
        raise e

    def _stream_chunks(self, client, kwargs, cancel_event=None):
        yield from ()

    def chat(self, messages, tools=None, temperature=0.3, max_tokens=4096, system=""):
        return Message(role=Role.ASSISTANT, content="mock response")

    def chat_stream(
        self,
        messages,
        tools=None,
        temperature=0.3,
        max_tokens=4096,
        system="",
        cancel_event=None,
    ):
        if self._call_count < len(self._responses):
            chunks = self._responses[self._call_count]
            self._call_count += 1
            for chunk in chunks:
                yield chunk
        else:
            yield StreamChunk(text="No more scripted responses.")


def _text_response(text: str) -> list[StreamChunk]:
    """Create a simple text-only response."""
    return [
        StreamChunk(text=text),
        StreamChunk(usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)),
    ]


def _text_response_no_usage(text: str) -> list[StreamChunk]:
    """Create a text response with no usage metadata (compat provider behavior)."""
    return [StreamChunk(text=text)]


def _tool_call_response(tool_name: str, args: dict[str, Any], call_id: str = "call_1") -> list[StreamChunk]:
    """Create a response with a tool call."""
    return [
        StreamChunk(is_tool_call_start=True, tool_call_id=call_id, tool_name=tool_name),
        StreamChunk(tool_args_delta=json.dumps(args), tool_call_id=call_id),
        StreamChunk(is_tool_call_end=True, tool_call_id=call_id, tool_name=tool_name),
        StreamChunk(usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)),
    ]


class TestAgentLoop(unittest.TestCase):
    def _make_loop(self, provider: MockProvider, tools: ToolRegistry | None = None) -> AgentLoop:
        config = RikuganConfig()
        config.auto_context = False  # Skip IDA API calls
        session = SessionState(provider_name="mock", model_name="mock-model")
        return AgentLoop(
            provider=provider,
            tool_registry=tools or ToolRegistry(),
            config=config,
            session=session,
        )

    def test_simple_text_response(self):
        provider = MockProvider(responses=[_text_response("Hello!")])
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]
        self.assertIn(TurnEventType.TURN_START, types)
        self.assertIn(TurnEventType.TEXT_DELTA, types)
        self.assertIn(TurnEventType.TEXT_DONE, types)
        self.assertIn(TurnEventType.TURN_END, types)

        text_done = next(e for e in events if e.type == TurnEventType.TEXT_DONE)
        self.assertEqual(text_done.text, "Hello!")

    def test_session_records_messages(self):
        provider = MockProvider(responses=[_text_response("Hi there")])
        config = RikuganConfig()
        config.auto_context = False
        session = SessionState()
        loop = AgentLoop(provider, ToolRegistry(), config, session)

        list(loop.run("Hello"))
        self.assertEqual(len(session.messages), 2)
        self.assertEqual(session.messages[0].role, Role.USER)
        self.assertEqual(session.messages[0].content, "Hello")
        self.assertEqual(session.messages[1].role, Role.ASSISTANT)
        self.assertEqual(session.messages[1].content, "Hi there")

    def test_tool_call_and_result(self):
        # Set up a tool
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="echo_tool",
                description="Echo the input",
                parameters=[ParameterSchema(name="text", type="string", description="Text to echo", required=True)],
                handler=lambda text: f"Echo: {text}",
                category="test",
            )
        )

        # Turn 1: tool call, Turn 2: text response
        provider = MockProvider(
            responses=[
                _tool_call_response("echo_tool", {"text": "hello"}, call_id="call_1"),
                _text_response("The echo returned hello"),
            ]
        )
        loop = self._make_loop(provider, tools=registry)

        events = list(loop.run("Echo hello"))
        types = [e.type for e in events]
        self.assertIn(TurnEventType.TOOL_CALL_START, types)
        self.assertIn(TurnEventType.TOOL_CALL_DONE, types)
        self.assertIn(TurnEventType.TOOL_RESULT, types)

        tool_result = next(e for e in events if e.type == TurnEventType.TOOL_RESULT)
        # TurnEvent now carries the sanitized (wrapped) result, not the raw string.
        self.assertIn("Echo: hello", tool_result.tool_result)
        self.assertFalse(tool_result.tool_is_error)

    def test_tool_error(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="failing_tool",
                description="Always fails",
                parameters=[],
                handler=lambda: (_ for _ in ()).throw(ValueError("bad input")),
                category="test",
            )
        )

        provider = MockProvider(
            responses=[
                _tool_call_response("failing_tool", {}, call_id="call_1"),
                _text_response("Tool failed"),
            ]
        )
        loop = self._make_loop(provider, tools=registry)

        events = list(loop.run("Run failing tool"))
        tool_result = next(e for e in events if e.type == TurnEventType.TOOL_RESULT)
        self.assertTrue(tool_result.tool_is_error)

    def test_cancellation_mid_tool_loop(self):
        """Cancel during a multi-turn tool loop."""
        registry = ToolRegistry()

        def cancel_handler():
            # Cancel during tool execution
            loop.cancel()
            return "done"

        registry.register(
            ToolDefinition(
                name="cancel_trigger",
                description="Triggers cancel",
                parameters=[],
                handler=cancel_handler,
                category="test",
            )
        )

        provider = MockProvider(
            responses=[
                _tool_call_response("cancel_trigger", {}, call_id="call_1"),
                _text_response("Should not reach"),
            ]
        )
        loop = self._make_loop(provider, tools=registry)

        events = list(loop.run("Trigger cancel"))
        types = [e.type for e in events]
        self.assertIn(TurnEventType.CANCELLED, types)
        # Should not reach the second response
        self.assertNotIn(TurnEventType.TEXT_DONE, types)

    def test_is_running_flag(self):
        provider = MockProvider(responses=[_text_response("Done")])
        loop = self._make_loop(provider)
        self.assertFalse(loop.is_running)

        list(loop.run("Hi"))  # consume generator
        self.assertFalse(loop.is_running)

    def test_usage_tracked(self):
        provider = MockProvider(responses=[_text_response("Hi")])
        config = RikuganConfig()
        config.auto_context = False
        session = SessionState()
        loop = AgentLoop(provider, ToolRegistry(), config, session)

        events = list(loop.run("Hello"))
        usage_events = [e for e in events if e.type == TurnEventType.USAGE_UPDATE]
        self.assertTrue(len(usage_events) > 0)
        # Session should accumulate usage; prompt tokens dominate a single text response
        self.assertGreater(session.total_usage.total_tokens, 0)
        self.assertGreater(session.total_usage.prompt_tokens, 0)
        self.assertLess(session.total_usage.completion_tokens, session.total_usage.prompt_tokens)
        # Session total should match the final usage event
        last_usage = usage_events[-1].usage
        self.assertEqual(session.total_usage.total_tokens, last_usage.total_tokens)

    def test_usage_fallback_when_provider_omits_usage(self):
        provider = MockProvider(responses=[_text_response_no_usage("Hi")])
        config = RikuganConfig()
        config.auto_context = False
        session = SessionState()
        loop = AgentLoop(provider, ToolRegistry(), config, session)

        events = list(loop.run("Hello"))
        usage_events = [e for e in events if e.type == TurnEventType.USAGE_UPDATE]

        # Local estimation should still drive token/context tracking.
        self.assertGreater(len(usage_events), 0)
        self.assertGreater(session.last_prompt_tokens, 0)
        self.assertGreater(session.total_usage.total_tokens, 0)

    def test_truncated_output_finish_reason_length_warns_user(self):
        """When finish_reason='length' (output cut by max_tokens), the loop
        MUST surface a warning so the user knows the response is incomplete.

        Without this, the chat appears to end normally mid-sentence — the
        original "chat bị ngắt đột ngột" symptom. The provider already
        streams the partial text via TEXT_DELTA; the loop must additionally
        emit an ERROR event describing the truncation.
        """
        chunks = [
            StreamChunk(text="The answer is partially"),
            StreamChunk(finish_reason="length"),
        ]
        provider = MockProvider(responses=[chunks])
        loop = self._make_loop(provider)

        events = list(loop.run("Tell me"))
        types = [e.type for e in events]

        # Text still streams through so the partial answer is visible.
        self.assertIn(TurnEventType.TEXT_DELTA, types)
        # A warning event must be emitted — currently NONE exists, so this
        # assertion fails until the loop handles finish_reason.
        self.assertIn(TurnEventType.ERROR, types)
        warn = next(e for e in events if e.type == TurnEventType.ERROR)
        self.assertIn("length", (warn.error or "").lower())

    def test_normal_stop_finish_reason_emits_no_warning(self):
        """finish_reason='stop' is a deliberate, complete response — the loop
        must NOT emit a spurious ERROR warning (false positives would train the
        user to ignore real truncation warnings)."""
        chunks = [
            StreamChunk(text="All done."),
            StreamChunk(finish_reason="stop"),
        ]
        provider = MockProvider(responses=[chunks])
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]
        self.assertNotIn(TurnEventType.ERROR, types)

    def test_finish_reason_tool_calls_emits_no_warning(self):
        """finish_reason='tool_calls' ends a turn that hands control to tools —
        not a truncation, so no warning."""
        chunks = [
            StreamChunk(text="Let me check."),
            StreamChunk(finish_reason="tool_calls"),
        ]
        provider = MockProvider(responses=[chunks])
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]
        self.assertNotIn(TurnEventType.ERROR, types)

    def test_missing_finish_reason_emits_no_warning(self):
        """Some OpenAI-compatible proxies never send a finish_reason. The loop
        must not warn on a missing value (None) — otherwise every response from
        such proxies would show a spurious warning."""
        chunks = [StreamChunk(text="No finish reason here.")]
        provider = MockProvider(responses=[chunks])
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]
        self.assertNotIn(TurnEventType.ERROR, types)

    def test_anthropic_max_tokens_stop_reason_warns_user(self):
        """Anthropic's stop_reason uses 'max_tokens' instead of OpenAI's
        'length'. The normalization must map it to the same truncation warning
        so Anthropic users also see why the response was cut."""
        chunks = [
            StreamChunk(text="Partial answer"),
            StreamChunk(finish_reason="max_tokens"),
        ]
        provider = MockProvider(responses=[chunks])
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]
        self.assertIn(TurnEventType.ERROR, types)
        warn = next(e for e in events if e.type == TurnEventType.ERROR)
        self.assertIn("length", (warn.error or "").lower())

    def test_anthropic_end_turn_emits_no_warning(self):
        """Anthropic's normal completion stop_reason is 'end_turn' — must be
        treated like OpenAI's 'stop' (no warning)."""
        chunks = [
            StreamChunk(text="Complete answer"),
            StreamChunk(finish_reason="end_turn"),
        ]
        provider = MockProvider(responses=[chunks])
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]
        self.assertNotIn(TurnEventType.ERROR, types)

    def test_anthropic_tool_use_stop_reason_emits_no_warning(self):
        """Anthropic's stop_reason 'tool_use' means the model wants to invoke
        a tool — this is a deliberate, complete turn (tool execution follows),
        NOT a truncation.  Must not be treated as an unknown/unexpected reason.

        Regression: ``tool_use`` was missing from the deliberate-completion
        set, so Anthropic streams raised a spurious
        '⚠️ The response ended unexpectedly (finish_reason=tool_use)' warning
        on every tool-calling turn.
        """
        chunks = [
            StreamChunk(text="Let me check."),
            StreamChunk(finish_reason="tool_use"),
        ]
        provider = MockProvider(responses=[chunks])
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]
        self.assertNotIn(TurnEventType.ERROR, types)

    def test_content_filter_finish_reason_warns_user(self):
        """finish_reason='content_filter' means the provider suppressed output;
        the user must be told why the response is empty/odd."""
        chunks = [
            StreamChunk(text=""),
            StreamChunk(finish_reason="content_filter"),
        ]
        provider = MockProvider(responses=[chunks])
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]
        self.assertIn(TurnEventType.ERROR, types)
        warn = next(e for e in events if e.type == TurnEventType.ERROR)
        self.assertIn("content_filter", (warn.error or "").lower())

    def test_broken_stream_after_partial_text_persists_assistant_message(self):
        """When the SSE stream breaks mid-generation (after partial text),
        the loop MUST:

        1. emit the partial TEXT_DELTA / TEXT_DONE so the user keeps what
           was already streamed,
        2. emit an ERROR event explaining the failure,
        3. persist the assistant message into the session so "continue"
           works and history is not silently dropped.

        Without this, a network drop mid-stream loses everything the user
        already saw — the "chat bị ngắt đột ngột" symptom where text
        disappears and history has a gap.
        """
        from rikugan.core.errors import ProviderError

        class BrokenStreamProvider(MockProvider):
            """Provider whose chat_stream yields partial text then raises a
            non-retryable ProviderError, simulating an SSE stream that drops
            mid-generation (e.g. httpx.RemoteProtocolError classified as a
            generic, non-retryable ProviderError by _handle_api_error)."""

            def chat_stream(self, messages, tools=None, temperature=0.3, max_tokens=4096, system="", cancel_event=None):
                yield StreamChunk(text="Partial answer that the user already ")
                yield StreamChunk(text="saw stream by.")
                raise ProviderError(
                    "Connection reset mid-stream",
                    provider="mock",
                    retryable=False,
                )

        provider = BrokenStreamProvider()
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]

        # Partial text still visible.
        self.assertIn(TurnEventType.TEXT_DELTA, types)
        self.assertIn(TurnEventType.TEXT_DONE, types)
        # User is told why it stopped.
        self.assertIn(TurnEventType.ERROR, types)
        # Assistant message persisted with the partial text (not dropped).
        assistant_msgs = [m for m in loop.session.messages if m.role == Role.ASSISTANT]
        self.assertEqual(len(assistant_msgs), 1)
        self.assertIn("Partial answer", assistant_msgs[0].content)

    def test_broken_stream_before_any_output_still_raises_to_retry_layer(self):
        """If the stream fails BEFORE any chunk was streamed, there is no
        partial output to preserve — the error must propagate up so the
        retry layer in _stream_llm_turn can handle it as before.  Catching
        it here would silently turn every cold-connection failure into a
        no-op turn."""
        from rikugan.core.errors import ProviderError

        class ColdFailProvider(MockProvider):
            def chat_stream(self, messages, tools=None, temperature=0.3, max_tokens=4096, system="", cancel_event=None):
                raise ProviderError("Connection refused", provider="mock", retryable=False)

        provider = ColdFailProvider()
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]

        # No partial output → error surfaces as an ERROR event (from run()'s
        # top-level try/except), no TEXT_DONE, and crucially NO assistant
        # message persisted.
        self.assertIn(TurnEventType.ERROR, types)
        self.assertNotIn(TurnEventType.TEXT_DONE, types)
        assistant_msgs = [m for m in loop.session.messages if m.role == Role.ASSISTANT]
        self.assertEqual(len(assistant_msgs), 0)

    def test_cancellation_during_stream_propagates_as_cancelled_event(self):
        """A cancellation raised mid-stream must NOT be swallowed as a
        'partial output' warning — it must become a CANCELLED event so the
        UI's cancellation UX works.  This guards the CancellationError
        re-raise branch in the new try/except."""
        from rikugan.core.errors import CancellationError

        class CancelMidStreamProvider(MockProvider):
            def chat_stream(self, messages, tools=None, temperature=0.3, max_tokens=4096, system="", cancel_event=None):
                yield StreamChunk(text="Streaming")
                raise CancellationError("Cancelled mid-stream")

        provider = CancelMidStreamProvider()
        loop = self._make_loop(provider)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]

        self.assertIn(TurnEventType.CANCELLED, types)
        # The partial-warning path must not have fired.
        self.assertNotIn(TurnEventType.ERROR, types)

    def test_broken_stream_with_partial_tool_call_keeps_completed_calls(self):
        """If the stream breaks after some tool calls completed (is_tool_call_end
        seen) but before the turn finished, completed tool calls are preserved
        and executed; an incomplete tool call (only start, no end) is dropped."""
        from rikugan.core.errors import ProviderError

        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="echo",
                description="echo",
                parameters=[ParameterSchema(name="text", type="string", description="t", required=True)],
                handler=lambda text: f"Echo: {text}",
                category="test",
            )
        )

        class MixedStreamProvider(MockProvider):
            def chat_stream(self, messages, tools=None, temperature=0.3, max_tokens=4096, system="", cancel_event=None):
                # Completed tool call
                yield StreamChunk(is_tool_call_start=True, tool_call_id="c1", tool_name="echo")
                yield StreamChunk(tool_args_delta='{"text": "hi"}', tool_call_id="c1")
                yield StreamChunk(is_tool_call_end=True, tool_call_id="c1", tool_name="echo")
                # Then the stream breaks
                raise ProviderError("dropped", provider="mock", retryable=False)

        provider = MixedStreamProvider()
        loop = self._make_loop(provider, tools=registry)

        events = list(loop.run("Hi"))
        types = [e.type for e in events]

        # Completed tool call result is still emitted and the break is warned.
        self.assertIn(TurnEventType.TOOL_RESULT, types)
        self.assertIn(TurnEventType.ERROR, types)

    def test_execute_python_requires_approval_even_in_explore_only(self):
        provider = MockProvider()
        loop = self._make_loop(provider)
        loop._exploration_state = ExplorationState(explore_only=True)  # /explore context

        tc = ToolCall(
            id="call_approval_test",
            name="execute_python",
            arguments={"code": "print('hi')"},
        )

        gate = loop._wait_for_approval(tc)
        event = next(gate)
        self.assertEqual(event.type, TurnEventType.TOOL_APPROVAL_REQUEST)
        self.assertEqual(event.tool_name, "execute_python")

        loop.submit_tool_approval("allow")
        with self.assertRaises(StopIteration) as done:
            next(gate)
        self.assertTrue(done.exception.value)


class TestBackgroundAgentRunner(unittest.TestCase):
    def test_run_in_background(self):
        provider = MockProvider(responses=[_text_response("Background response")])
        config = RikuganConfig()
        config.auto_context = False
        session = SessionState()
        loop = AgentLoop(provider, ToolRegistry(), config, session)
        runner = BackgroundAgentRunner(loop)

        runner.start("Hello from background")

        events = []
        while True:
            event = runner.get_event(timeout=2.0)
            if event is None:
                break
            events.append(event)

        types = [e.type for e in events]
        self.assertIn(TurnEventType.TEXT_DONE, types)
        text_done = next(e for e in events if e.type == TurnEventType.TEXT_DONE)
        self.assertEqual(text_done.text, "Background response")


class TestSkillInvocation(unittest.TestCase):
    def test_skill_rewrite(self):
        """Test that /slug messages get rewritten with skill body."""
        import tempfile

        from rikugan.skills.registry import SkillRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, "test-skill")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: Test Skill\ndescription: A test\n---\nYou are a test skill.\n")

            registry = SkillRegistry(tmpdir)
            registry.discover()

            provider = MockProvider(responses=[_text_response("Skill response")])
            config = RikuganConfig()
            config.auto_context = False
            session = SessionState()
            loop = AgentLoop(provider, ToolRegistry(), config, session, skill_registry=registry)

            list(loop.run("/test-skill do something"))

            # The user message in session should contain the skill body
            user_msg = session.messages[0]
            self.assertIn("[Skill: Test Skill]", user_msg.content)
            self.assertIn("You are a test skill.", user_msg.content)
            self.assertIn("do something", user_msg.content)


class TestProfileEnforcement(unittest.TestCase):
    """Test that analysis profiles are enforced in the agent loop."""

    def _make_loop_with_profile(
        self,
        profile_name: str,
        provider: MockProvider,
        tools: ToolRegistry = None,
        custom_profiles: dict = None,
    ) -> AgentLoop:
        config = RikuganConfig()
        config.auto_context = False
        config.active_profile = profile_name
        if custom_profiles:
            config.custom_profiles = custom_profiles
        session = SessionState(provider_name="mock", model_name="mock-model")
        return AgentLoop(
            provider=provider,
            tool_registry=tools or ToolRegistry(),
            config=config,
            session=session,
        )

    def test_private_profile_skips_binary_info(self):
        """Private profile should not call get_binary_info."""
        config = RikuganConfig()
        config.auto_context = True  # Enable auto-context
        config.active_profile = "private"

        registry = ToolRegistry()
        calls = []

        def track_binary_info():
            calls.append("get_binary_info")
            return "Binary: test.exe"

        registry.register(
            ToolDefinition(
                name="get_binary_info",
                description="Get binary info",
                parameters=[],
                handler=track_binary_info,
                category="context",
            )
        )

        provider = MockProvider(responses=[_text_response("Done")])
        session = SessionState(provider_name="mock", model_name="mock-model")
        loop = AgentLoop(provider, registry, config, session)

        list(loop.run("Hi"))
        # get_binary_info should NOT have been called because private profile hides metadata
        self.assertEqual(calls, [])

    def test_ioc_stripping_in_tool_results(self):
        """ioc_filters should strip hashes/IPs from tool results."""
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="test_tool",
                description="Returns IOC data",
                parameters=[],
                handler=lambda: "Hash: d41d8cd98f00b204e9800998ecf8427e, IP: 10.0.0.1",
                category="test",
            )
        )

        # Use private profile which has all ioc_filters enabled
        config = RikuganConfig()
        config.auto_context = False
        config.active_profile = "private"
        session = SessionState(provider_name="mock", model_name="mock-model")

        provider = MockProvider(
            responses=[
                _tool_call_response("test_tool", {}, call_id="call_ioc"),
                _text_response("Done"),
            ]
        )
        loop = AgentLoop(provider, registry, config, session)

        events = list(loop.run("Run test"))
        tool_result_event = next(
            (e for e in events if e.type == TurnEventType.TOOL_RESULT),
            None,
        )
        self.assertIsNotNone(tool_result_event)
        # IOCs should be redacted
        self.assertIn("[HASH_REDACTED]", tool_result_event.tool_result)
        self.assertIn("[IP_REDACTED]", tool_result_event.tool_result)

    def test_denied_tools_filtered_from_schema(self):
        """Denied tools should not appear in the tools schema."""
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="allowed_tool",
                description="Allowed",
                parameters=[],
                handler=lambda: "ok",
                category="test",
            )
        )
        registry.register(
            ToolDefinition(
                name="denied_tool",
                description="Denied",
                parameters=[],
                handler=lambda: "ok",
                category="test",
            )
        )

        custom_profiles = {
            "restricted": {
                "name": "restricted",
                "denied_tools": ["denied_tool"],
            }
        }

        provider = MockProvider(responses=[_text_response("Done")])
        loop = self._make_loop_with_profile(
            "restricted",
            provider,
            tools=registry,
            custom_profiles=custom_profiles,
        )

        schema = loop._build_tools_schema(None, False)
        tool_names = [t.get("function", {}).get("name") for t in schema]
        self.assertIn("allowed_tool", tool_names)
        self.assertNotIn("denied_tool", tool_names)

    def test_granular_ioc_filter_only_selected(self):
        """Only selected IOC categories should be redacted."""
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="test_tool",
                description="Returns mixed IOCs",
                parameters=[],
                handler=lambda: "Hash: d41d8cd98f00b204e9800998ecf8427e, IP: 10.0.0.1, url: http://evil.com/bad",
                category="test",
            )
        )

        # Custom profile with only hashes enabled
        custom_profiles = {
            "hash-only": {
                "name": "hash-only",
                "ioc_filters": {"hashes": True, "ipv4": False, "urls": False},
            }
        }
        config = RikuganConfig()
        config.auto_context = False
        config.active_profile = "hash-only"
        config.custom_profiles = custom_profiles
        session = SessionState(provider_name="mock", model_name="mock-model")

        provider = MockProvider(
            responses=[
                _tool_call_response("test_tool", {}, call_id="call_granular"),
                _text_response("Done"),
            ]
        )
        loop = AgentLoop(provider, registry, config, session)

        events = list(loop.run("Run test"))
        tool_result_event = next(
            (e for e in events if e.type == TurnEventType.TOOL_RESULT),
            None,
        )
        self.assertIsNotNone(tool_result_event)
        self.assertIn("[HASH_REDACTED]", tool_result_event.tool_result)
        # IP and URL should NOT be redacted
        self.assertIn("10.0.0.1", tool_result_event.tool_result)
        self.assertIn("http://evil.com/bad", tool_result_event.tool_result)

    def test_custom_filter_rule_in_tool_result(self):
        """Custom filter rules should be applied to tool results."""
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="test_tool",
                description="Returns sensitive data",
                parameters=[],
                handler=lambda: "hostname: DESKTOP-VICTIM, key: sk-abcdef1234567890",
                category="test",
            )
        )

        custom_profiles = {
            "custom-rules": {
                "name": "custom-rules",
                "ioc_filters": {},
                "custom_filter_rules": [
                    {"name": "host", "pattern": "DESKTOP-VICTIM", "is_regex": False, "replacement": "[HOST]"},
                    {"name": "key", "pattern": r"sk-[a-zA-Z0-9]+", "is_regex": True, "replacement": "[KEY]"},
                ],
            }
        }
        config = RikuganConfig()
        config.auto_context = False
        config.active_profile = "custom-rules"
        config.custom_profiles = custom_profiles
        session = SessionState(provider_name="mock", model_name="mock-model")

        provider = MockProvider(
            responses=[
                _tool_call_response("test_tool", {}, call_id="call_custom"),
                _text_response("Done"),
            ]
        )
        loop = AgentLoop(provider, registry, config, session)

        events = list(loop.run("Run test"))
        tool_result_event = next(
            (e for e in events if e.type == TurnEventType.TOOL_RESULT),
            None,
        )
        self.assertIsNotNone(tool_result_event)
        self.assertIn("[HOST]", tool_result_event.tool_result)
        self.assertIn("[KEY]", tool_result_event.tool_result)
        self.assertNotIn("DESKTOP-VICTIM", tool_result_event.tool_result)

    def test_default_profile_no_filtering(self):
        """Default profile should not strip IOCs or hide metadata."""
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="test_tool",
                description="Returns data",
                parameters=[],
                handler=lambda: "Hash: d41d8cd98f00b204e9800998ecf8427e",
                category="test",
            )
        )

        config = RikuganConfig()
        config.auto_context = False
        config.active_profile = "default"
        session = SessionState(provider_name="mock", model_name="mock-model")

        provider = MockProvider(
            responses=[
                _tool_call_response("test_tool", {}, call_id="call_def"),
                _text_response("Done"),
            ]
        )
        loop = AgentLoop(provider, registry, config, session)

        events = list(loop.run("Run test"))
        tool_result_event = next(
            (e for e in events if e.type == TurnEventType.TOOL_RESULT),
            None,
        )
        self.assertIsNotNone(tool_result_event)
        # Default profile does NOT strip IOCs
        self.assertNotIn("[HASH_REDACTED]", tool_result_event.tool_result)

    def test_denied_tool_blocked_at_execution(self):
        """Denied tools should be blocked at execution time, not just schema filtering."""
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="list_functions",
                description="Lists functions",
                parameters=[],
                handler=lambda: "func1\nfunc2\nfunc3",
                category="functions",
            )
        )

        custom_profiles = {
            "restricted": {
                "name": "restricted",
                "denied_tools": ["list_functions"],
            }
        }

        # LLM tries to call the denied tool anyway
        provider = MockProvider(
            responses=[
                _tool_call_response("list_functions", {}, call_id="call_denied"),
                _text_response("Done"),
            ]
        )
        loop = self._make_loop_with_profile(
            "restricted",
            provider,
            tools=registry,
            custom_profiles=custom_profiles,
        )

        events = list(loop.run("list functions"))
        tool_result_event = next(
            (e for e in events if e.type == TurnEventType.TOOL_RESULT),
            None,
        )
        self.assertIsNotNone(tool_result_event)
        # Tool should be blocked with an error, not executed
        self.assertIn("denied by the active profile", tool_result_event.tool_result)
        self.assertNotIn("func1", tool_result_event.tool_result)


if __name__ == "__main__":
    unittest.main()
