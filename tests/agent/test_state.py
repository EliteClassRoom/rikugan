"""Tests for state management: session and history."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.core.types import Message, Role, TokenUsage, ToolCall, ToolResult
from rikugan.state.session import SessionState
from rikugan.state.history import SessionHistory
from rikugan.core.config import RikuganConfig


class TestSessionState(unittest.TestCase):
    def test_default_session(self):
        s = SessionState(provider_name="anthropic", model_name="claude")
        self.assertEqual(s.provider_name, "anthropic")
        self.assertEqual(s.model_name, "claude")
        self.assertEqual(len(s.messages), 0)
        self.assertFalse(s.is_running)
        self.assertEqual(s.current_turn, 0)

    def test_add_message(self):
        s = SessionState()
        msg = Message(role=Role.USER, content="hello")
        s.add_message(msg)
        self.assertEqual(len(s.messages), 1)
        self.assertEqual(s.messages[0].content, "hello")

    def test_add_message_with_usage(self):
        s = SessionState()
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        msg = Message(role=Role.ASSISTANT, content="hi", token_usage=usage)
        s.add_message(msg)
        self.assertEqual(s.total_usage.prompt_tokens, 10)
        self.assertEqual(s.total_usage.completion_tokens, 20)
        self.assertEqual(s.total_usage.total_tokens, 30)

    def test_usage_accumulates(self):
        s = SessionState()
        for i in range(3):
            usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            s.add_message(Message(role=Role.ASSISTANT, content=f"msg{i}", token_usage=usage))
        self.assertEqual(s.total_usage.total_tokens, 45)

    def test_clear(self):
        s = SessionState()
        s.add_message(Message(role=Role.USER, content="test"))
        s.current_turn = 5
        s.is_running = True
        s.clear()
        self.assertEqual(len(s.messages), 0)
        self.assertEqual(s.current_turn, 0)
        self.assertFalse(s.is_running)
        self.assertEqual(s.total_usage.total_tokens, 0)

    def test_get_messages_for_provider(self):
        s = SessionState()
        s.add_message(Message(role=Role.USER, content="a"))
        s.add_message(Message(role=Role.ASSISTANT, content="b"))
        msgs = s.get_messages_for_provider()
        self.assertEqual(len(msgs), 2)
        # Returns a copy, not the internal list
        msgs.append(Message(role=Role.USER, content="c"))
        self.assertEqual(len(s.messages), 2)

    def test_message_count(self):
        s = SessionState()
        self.assertEqual(s.message_count(), 0)
        s.add_message(Message(role=Role.USER, content="test"))
        self.assertEqual(s.message_count(), 1)


class TestMessageSerialization(unittest.TestCase):
    """Test Message.to_dict / from_dict round-trip (previously via conversation.py)."""

    def test_roundtrip(self):
        messages = [
            Message(role=Role.USER, content="hello", id="id1", timestamp=1.0),
            Message(role=Role.ASSISTANT, content="hi", id="id2", timestamp=2.0),
        ]
        data = json.dumps([m.to_dict() for m in messages])
        restored = [Message.from_dict(d) for d in json.loads(data)]
        self.assertEqual(len(restored), 2)
        self.assertEqual(restored[0].role, Role.USER)
        self.assertEqual(restored[0].content, "hello")
        self.assertEqual(restored[1].role, Role.ASSISTANT)

    def test_tool_calls(self):
        tc = ToolCall(id="tc1", name="decompile_function", arguments={"address": "0x401000"})
        msg = Message(role=Role.ASSISTANT, content="", tool_calls=[tc], id="id1", timestamp=1.0)
        data = json.dumps([msg.to_dict()])
        restored = [Message.from_dict(d) for d in json.loads(data)]
        self.assertEqual(len(restored[0].tool_calls), 1)
        self.assertEqual(restored[0].tool_calls[0].name, "decompile_function")

    def test_tool_results(self):
        tr = ToolResult(tool_call_id="tc1", name="decompile_function", content="int main() {}", is_error=False)
        msg = Message(role=Role.TOOL, tool_results=[tr], id="id1", timestamp=1.0)
        data = json.dumps([msg.to_dict()])
        restored = [Message.from_dict(d) for d in json.loads(data)]
        self.assertEqual(restored[0].tool_results[0].content, "int main() {}")
        self.assertFalse(restored[0].tool_results[0].is_error)


class TestSessionHistory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = RikuganConfig(_config_dir=self.tmpdir)

    def test_save_and_load_session(self):
        history = SessionHistory(self.config)
        session = SessionState(id="test123", provider_name="anthropic", model_name="claude")
        session.add_message(Message(role=Role.USER, content="hello"))
        session.add_message(Message(role=Role.ASSISTANT, content="hi"))

        path = history.save_session(session)
        self.assertTrue(os.path.exists(path))

        loaded = history.load_session("test123")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, "test123")
        self.assertEqual(loaded.provider_name, "anthropic")
        self.assertEqual(len(loaded.messages), 2)

    def test_load_nonexistent(self):
        history = SessionHistory(self.config)
        self.assertIsNone(history.load_session("nonexistent"))

    def test_list_sessions(self):
        history = SessionHistory(self.config)
        for i in range(3):
            s = SessionState(id=f"sess{i}", provider_name="anthropic", model_name="claude")
            s.add_message(Message(role=Role.USER, content=f"msg{i}"))
            history.save_session(s)

        sessions = history.list_sessions()
        self.assertEqual(len(sessions), 3)
        ids = {s["id"] for s in sessions}
        self.assertEqual(ids, {"sess0", "sess1", "sess2"})

    def test_get_latest_session(self):
        history = SessionHistory(self.config)
        s1 = SessionState(id="old", created_at=1000.0)
        s1.add_message(Message(role=Role.USER, content="old"))
        history.save_session(s1)

        s2 = SessionState(id="new", created_at=2000.0)
        s2.add_message(Message(role=Role.USER, content="new"))
        history.save_session(s2)

        latest = history.get_latest_session()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.id, "new")

    def test_get_latest_empty(self):
        history = SessionHistory(self.config)
        self.assertIsNone(history.get_latest_session())

    def test_delete_session(self):
        history = SessionHistory(self.config)
        s = SessionState(id="todelete")
        s.add_message(Message(role=Role.USER, content="test"))
        history.save_session(s)
        self.assertTrue(history.delete_session("todelete"))
        self.assertIsNone(history.load_session("todelete"))

    def test_delete_nonexistent(self):
        history = SessionHistory(self.config)
        self.assertFalse(history.delete_session("nonexistent"))


if __name__ == "__main__":
    unittest.main()
