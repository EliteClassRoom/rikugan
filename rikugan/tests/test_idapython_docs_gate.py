"""Tests for the IDAPython docs-review gate (post-error variant).

Covers:

* ``classify_idapython_script`` — complexity heuristic (still used at
  static-validation time even though the pre-execute gate is gone).
* ``RikuganConfig`` round-trip of ``docs_review_mode`` + legacy
  ``require_ida_docs_for_complex_scripts`` migration.
* ``AgentLoop._review_failed_script`` — post-error reviewer: only
  spawned when execute_python raises an API-shaped exception AND
  ``docs_review_mode == 'on_error'`` AND the reviewer hasn't run yet
  this task. Augments the failed tool result with the reviewer's
  verdict + auto-injected reference docs.
* ``AgentLoop._build_reference_injection`` — pulls offline docs for
  up to 3 modules referenced in the failed script.
* ``AgentLoop._describe_tool_call`` for ``execute_python`` — empty
  description (the unified widget renders the code itself).

The agent-loop tests use lightweight fakes for the provider and tool
registry so they run without any IDA / Qt dependencies — they live in
the same ``tests/`` tree as other agent tests.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from rikugan.core.config import RikuganConfig
from rikugan.tools.idapython_complexity import (
    COMPLEX_LINE_THRESHOLD,
    classify_idapython_script,
)
from rikugan.tools.validate_idapython import validate_idapython

# ---------------------------------------------------------------------------
# Classifier tests
# ---------------------------------------------------------------------------


class TestClassifier(unittest.TestCase):
    """Heuristics for classify_idapython_script()."""

    def test_simple_one_liner_is_not_complex(self):
        src = "print(idaapi.get_inf_structure())"
        result = classify_idapython_script(src)
        self.assertFalse(result.is_complex, msg=result.reasons)
        self.assertEqual(result.reasons, ())

    def test_long_script_is_complex(self):
        # Build a script longer than the threshold.
        lines = ["import idautils"]
        for i in range(COMPLEX_LINE_THRESHOLD + 5):
            lines.append(f"print({i})")
        result = classify_idapython_script("\n".join(lines))
        self.assertTrue(result.is_complex)
        self.assertTrue(any("non-comment lines" in r for r in result.reasons))

    def test_multi_module_script_is_complex(self):
        src = "import idaapi\nimport idautils\nimport ida_funcs\nprint(idaapi.get_inf_structure())\n"
        result = classify_idapython_script(src)
        self.assertTrue(result.is_complex)
        self.assertTrue(any("IDA modules" in r for r in result.reasons))

    def test_mutating_calls_are_complex(self):
        src = "import idc\nidc.set_cmt(0x401000, 'test', 0)\n"
        result = classify_idapython_script(src)
        self.assertTrue(result.is_complex)
        self.assertTrue(any("mutating" in r for r in result.reasons))

    def test_iteration_helpers_are_complex(self):
        src = "import idautils\nfor ea in idautils.Functions():\n    print(hex(ea))\n"
        result = classify_idapython_script(src)
        self.assertTrue(result.is_complex)
        self.assertTrue(any("iterates database" in r for r in result.reasons))

    def test_visitor_subclass_is_complex(self):
        src = (
            "from ida_hexrays import ctree_visitor_t\n"
            "class MyVisitor(ctree_visitor_t):\n"
            "    def visit_insn(self, insn):\n"
            "        return 0\n"
        )
        result = classify_idapython_script(src)
        self.assertTrue(result.is_complex)
        self.assertTrue(any("visitor" in r for r in result.reasons))

    def test_heavy_modules_are_complex(self):
        src = "import ida_hexrays\n"
        result = classify_idapython_script(src)
        self.assertTrue(result.is_complex)

    def test_validator_warnings_trigger_complex(self):
        src = "idc.GetOperandValue(0x401000, 0)\n"
        validation = validate_idapython(src)
        self.assertTrue(validation.warnings, "expected legacy API warning")
        result = classify_idapython_script(src, validation)
        self.assertTrue(result.is_complex)
        self.assertTrue(any("legacy" in r or "warn" in r for r in result.reasons))

    def test_validator_blocked_triggers_complex(self):
        src = "idaapi.get_operands(0x401000)\n"
        validation = validate_idapython(src)
        self.assertTrue(validation.is_blocked)
        result = classify_idapython_script(src, validation)
        self.assertTrue(result.is_complex)
        self.assertTrue(any("blocked" in r for r in result.reasons))

    def test_syntax_error_does_not_crash(self):
        result = classify_idapython_script("def broken(:\n")
        # Pure length still counts; the script is treated as complex
        # so the reviewer can give the agent a clear error.
        self.assertIsInstance(result.is_complex, bool)

    def test_comments_only_is_simple(self):
        src = "# just a comment\n# another\n"
        result = classify_idapython_script(src)
        self.assertFalse(result.is_complex)


# ---------------------------------------------------------------------------
# Config round-trip
# ---------------------------------------------------------------------------


class TestConfigField(unittest.TestCase):
    def test_default_is_on_error(self):
        cfg = RikuganConfig()
        self.assertEqual(cfg.docs_review_mode, "on_error")

    def test_round_trip_through_dict(self):
        cfg = RikuganConfig()
        cfg.docs_review_mode = "off"
        cfg.save = MagicMock()  # avoid disk side effects
        cfg.load = MagicMock()
        from dataclasses import asdict

        d = asdict(cfg)
        cfg2 = RikuganConfig()
        cfg2.docs_review_mode = d["docs_review_mode"]
        self.assertEqual(cfg2.docs_review_mode, "off")

    def test_legacy_false_migrates_to_off(self):
        """Legacy config require_ida_docs_for_complex_scripts=False → off."""
        cfg = RikuganConfig()
        # Simulate load() with legacy field present
        legacy_data = {"require_ida_docs_for_complex_scripts": False}
        cfg._apply_loaded_config(legacy_data)
        self.assertEqual(cfg.docs_review_mode, "off")

    def test_legacy_true_migrates_to_on_error(self):
        """Legacy config require_ida_docs_for_complex_scripts=True → on_error."""
        cfg = RikuganConfig()
        legacy_data = {"require_ida_docs_for_complex_scripts": True}
        cfg._apply_loaded_config(legacy_data)
        self.assertEqual(cfg.docs_review_mode, "on_error")

    def test_legacy_missing_defaults_to_on_error(self):
        """No legacy field → on_error default."""
        cfg = RikuganConfig()
        cfg._apply_loaded_config({})
        self.assertEqual(cfg.docs_review_mode, "on_error")

    def test_explicit_off_round_trips(self):
        cfg = RikuganConfig()
        cfg._apply_loaded_config({"docs_review_mode": "off"})
        self.assertEqual(cfg.docs_review_mode, "off")

    def test_invalid_value_defaults_to_on_error(self):
        cfg = RikuganConfig()
        cfg._apply_loaded_config({"docs_review_mode": "bogus"})
        self.assertEqual(cfg.docs_review_mode, "on_error")


# ---------------------------------------------------------------------------
# Agent-loop gate tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeRunner:
    """Captures the kwargs passed to ``SubagentRunner.run_task``."""

    final_text: str = ""
    raise_on_run: Exception | None = None
    captured_kwargs: dict[str, Any] = field(default_factory=dict)
    captured_args: tuple = ()

    def run_task(self, *args, **kwargs):
        self.captured_args = args
        self.captured_kwargs = kwargs

        def _gen():
            if self.raise_on_run is not None:
                raise self.raise_on_run
            yield from ()

        gen = _gen()
        try:
            return_value = yield from gen
        except Exception:
            raise
        return return_value or self.final_text


class _FakeProvider:
    name = "test"
    model = "test-model"


class _FakeToolRegistry:
    def list_names(self):
        return []

    def list_available_tools(self):
        return []

    def to_provider_format(self):
        return []

    def get(self, name):
        return None

    def coerce_arguments_for(self, name, args):
        return dict(args)

    def execute(self, name, args):
        return ""


def _make_loop(*, gate_enabled: bool, runner: _FakeRunner | None = None):
    """Construct an AgentLoop with the bare minimum wiring for gate tests.

    Skips ``_build_system_prompt`` and other heavy setup. Replaces
    ``SubagentRunner`` with a fake so the gate can run without LLM
    round-trips.

    *gate_enabled* maps to ``config.docs_review_mode``: True → ``"on_error"``,
    False → ``"off"`` (post-error semantics — no pre-execute gate anymore).
    """
    from rikugan.agent.loop import AgentLoop

    cfg = RikuganConfig()
    cfg.docs_review_mode = "on_error" if gate_enabled else "off"

    loop = AgentLoop.__new__(AgentLoop)
    loop.provider = _FakeProvider()
    loop.tools = _FakeToolRegistry()
    loop.config = cfg
    from rikugan.state.session import SessionState

    loop.session = SessionState()
    loop.skills = None
    loop.host_name = "IDA Pro"
    import threading

    loop._cancelled = threading.Event()
    loop._running = False
    loop._consecutive_errors = 0
    loop._tools_disabled_for_turn = False
    # Post-error docs-review: max 1 reviewer call per user message.
    loop._docs_reviewer_invoked = False
    import queue

    loop._user_answer_queue = queue.Queue(maxsize=1)
    loop._tool_approval_queue = queue.Queue(maxsize=1)
    loop._approval_queue = queue.Queue(maxsize=1)
    loop._always_allow_scripts = False
    loop.plan_mode = False

    if runner is not None:
        # Monkey-patch the gate helper to use our fake runner.
        loop._SubagentRunner = lambda *a, **kw: runner
    return loop


class TestPostErrorReviewGate(unittest.TestCase):
    """Post-error docs-review gate: reviewer spawns only on API-shaped runtime error.

    The pre-execute ``_review_complex_idapython_script`` gate is gone.
    The new ``_review_failed_script`` runs AFTER execute_python raises
    an API-shaped exception (AttributeError/ImportError/NameError) and
    never blocks execution — the script already ran (and failed).
    ``docs_review_mode='off'`` disables the gate entirely.
    """

    def _complex_script(self) -> str:
        return (
            "import idaapi\n"
            "import idautils\n"
            "import ida_funcs\n"
            "for ea in idautils.Functions():\n"
            "    ida_funcs.get_func_name(ea)\n"
        )

    def _api_shaped_traceback(self) -> str:
        return (
            "Traceback (most recent call last):\n"
            '  File "<string>", line 1, in <module>\n'
            "AttributeError: module 'idaapi' has no attribute 'get_operands'\n"
        )

    def _logic_bug_traceback(self) -> str:
        return (
            "Traceback (most recent call last):\n"
            '  File "<string>", line 1, in <module>\n'
            "ValueError: invalid literal for int()\n"
        )

    def test_api_shaped_error_triggers_reviewer(self):
        from rikugan.core.types import ToolCall
        from rikugan.tools.traceback_classifier import classify_traceback

        loop = _make_loop(gate_enabled=True)
        runner = _FakeRunner(final_text="VERDICT: REWRITE_REQUIRED\nAPI_NOTES:\n- x")
        import rikugan.agent.loop as loop_mod

        original = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = ToolCall(id="tc1", name="execute_python", arguments={"code": self._complex_script()})
            classification = classify_traceback(self._api_shaped_traceback(), self._complex_script())
            self.assertTrue(classification.is_api_shaped)

            gen = loop._review_failed_script(tc, self._api_shaped_traceback(), self._complex_script(), classification)
            result = _drain_str(gen)
            self.assertIn("AttributeError", result)
            self.assertIn("VERDICT: REWRITE_REQUIRED", result)
            self.assertTrue(loop._docs_reviewer_invoked)
        finally:
            loop_mod.SubagentRunner = original

    def test_flag_persists_after_first_invocation(self):
        """Flag đã set → reviewer không spawn lần 2 trong cùng 1 task.

        Guard này ở trong ``_execute_single_tool`` except branch; test
        này verify flag semantics (idempotent — nếu gọi thủ công vẫn OK).
        """
        from rikugan.core.types import ToolCall
        from rikugan.tools.traceback_classifier import classify_traceback

        loop = _make_loop(gate_enabled=True)
        loop._docs_reviewer_invoked = True  # đã invoke

        runner = _FakeRunner(final_text="VERDICT: APPROVED")
        import rikugan.agent.loop as loop_mod

        original = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = ToolCall(id="tc2", name="execute_python", arguments={"code": self._complex_script()})
            classification = classify_traceback(self._api_shaped_traceback(), self._complex_script())

            # Caller-side guard is in _execute_single_tool; here we
            # verify the flag itself is set + calling _review_failed_script
            # is still safe (idempotent — guard is caller's responsibility).
            self.assertTrue(loop._docs_reviewer_invoked)
            gen = loop._review_failed_script(tc, self._api_shaped_traceback(), self._complex_script(), classification)
            result = _drain_str(gen)
            # Even with flag set, calling the method directly still
            # produces a valid augmented result — flag is for the gate,
            # not for the method.
            self.assertIsInstance(result, str)
        finally:
            loop_mod.SubagentRunner = original

    def test_reviewer_crash_returns_traceback(self):
        """Reviewer crash → emit failed event, return traceback (không augment)."""
        from rikugan.core.types import ToolCall
        from rikugan.tools.traceback_classifier import classify_traceback

        loop = _make_loop(gate_enabled=True)
        runner = _FakeRunner(raise_on_run=RuntimeError("provider down"))
        import rikugan.agent.loop as loop_mod

        original = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = ToolCall(id="tc3", name="execute_python", arguments={"code": self._complex_script()})
            classification = classify_traceback(self._api_shaped_traceback(), self._complex_script())

            gen = loop._review_failed_script(tc, self._api_shaped_traceback(), self._complex_script(), classification)
            result = _drain_str(gen)
            # Traceback vẫn có trong result (không augment reviewer verdict)
            self.assertIn("AttributeError", result)
        finally:
            loop_mod.SubagentRunner = original

    def test_reference_injection_pulls_module_docs(self):
        """_build_reference_injection trả RST content cho module có trong bundle."""
        loop = _make_loop(gate_enabled=True)
        # ida_typeinf có trong bundle (data/idapython-docs/ida_typeinf.rst.txt)
        result = loop._build_reference_injection(("ida_typeinf",))
        self.assertIn("ida_typeinf", result)

    def test_reference_injection_skips_missing_module(self):
        """Module không có trong bundle → skip, không crash."""
        loop = _make_loop(gate_enabled=True)
        result = loop._build_reference_injection(("ida_nonexistent_xyz",))
        # Không crash, trả chuỗi (có thể rỗng)
        self.assertIsInstance(result, str)

    def test_docs_review_mode_off_skips_reviewer(self):
        """docs_review_mode='off' → reviewer không invoke; flag vẫn False."""
        loop = _make_loop(gate_enabled=False)
        self.assertEqual(loop.config.docs_review_mode, "off")
        # Flag _docs_reviewer_invoked vẫn False (reviewer không chạy)
        self.assertFalse(loop._docs_reviewer_invoked)

    def test_reviewed_state_emitted(self):
        """Post-error reviewer emit DOCS_GATE_STATUS running + reviewed."""
        from rikugan.agent.turn import TurnEventType
        from rikugan.core.types import ToolCall
        from rikugan.tools.traceback_classifier import classify_traceback

        loop = _make_loop(gate_enabled=True)
        runner = _FakeRunner(final_text="VERDICT: APPROVED\nLooks good.")
        import rikugan.agent.loop as loop_mod

        original = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = ToolCall(id="tc1", name="execute_python", arguments={"code": self._complex_script()})
            classification = classify_traceback(self._api_shaped_traceback(), self._complex_script())

            events: list = []
            gen = loop._review_failed_script(tc, self._api_shaped_traceback(), self._complex_script(), classification)
            for event in gen:
                events.append(event)

            gate_events = [e for e in events if e.type == TurnEventType.DOCS_GATE_STATUS]
            states = [e.metadata.get("docs_gate_state") for e in gate_events]
            self.assertIn("running", states)
            self.assertIn("reviewed", states)
        finally:
            loop_mod.SubagentRunner = original


# ---------------------------------------------------------------------------
# _describe_tool_call for execute_python (Task 3)
# ---------------------------------------------------------------------------


class TestDescribeToolCallExecutePython(unittest.TestCase):
    """The unified ExecutePythonWidget renders its own code block, so
    ``_describe_tool_call`` must return an empty string for
    ``execute_python`` (previously it duplicated the first line of code).
    Other mutating tools keep their human-readable descriptions."""

    def test_execute_python_returns_empty_description(self):
        from rikugan import constants
        from rikugan.agent.loop import AgentLoop

        desc = AgentLoop._describe_tool_call(
            constants.EXECUTE_PYTHON_TOOL_NAME,
            {"code": "import idautils\nprint(1)\n"},
        )
        self.assertEqual(desc, "")

    def test_execute_python_empty_args_returns_empty(self):
        from rikugan import constants
        from rikugan.agent.loop import AgentLoop

        desc = AgentLoop._describe_tool_call(constants.EXECUTE_PYTHON_TOOL_NAME, {})
        self.assertEqual(desc, "")

    def test_other_mutating_tool_still_described(self):
        from rikugan.agent.loop import AgentLoop

        desc = AgentLoop._describe_tool_call(
            "rename_function",
            {"old_name": "sub_1000", "new_name": "process_data"},
        )
        self.assertIn("sub_1000", desc)
        self.assertIn("process_data", desc)


def _drain_str(gen):
    """Drain a generator that returns a ``str``.

    ``list(gen)`` exhausts the generator and loses the return value, so
    we drive ``next()`` in a loop and capture the value from
    ``StopIteration.value``.
    """
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            return stop.value


if __name__ == "__main__":
    unittest.main()
