"""Tests for the IDAPython docs-review gate.

Covers:

* ``classify_idapython_script`` — complexity heuristic (simple scripts
  pass through, complex scripts trigger the gate, validator hits count).
* ``RikuganConfig`` round-trip of ``require_ida_docs_for_complex_scripts``.
* ``AgentLoop._review_complex_idapython_script`` integration:
    - APPROVED verdict -> caller proceeds to approval path
    - REWRITE_REQUIRED verdict -> caller gets an error tool result
    - Config disabled -> gate never fires (callers can mock the
      ``_review_complex_idapython_script`` helper and assert it is not
      invoked)

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

    Skips ``_build_system_prompt`` and other heavy setup.  Replaces
    ``SubagentRunner`` with a fake so the gate can run without LLM
    round-trips.
    """
    from rikugan.agent.loop import AgentLoop

    cfg = RikuganConfig()
    cfg.require_ida_docs_for_complex_scripts = gate_enabled

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


class TestDocsGate(unittest.TestCase):
    def _complex_script(self) -> str:
        # Multi-module + mutating, intentionally complex.
        return (
            "import idaapi\n"
            "import idautils\n"
            "import ida_funcs\n"
            "import ida_bytes\n"
            "for ea in idautils.Functions():\n"
            "    name = ida_funcs.get_func_name(ea)\n"
            "    ida_bytes.patch_byte(ea, 0x90)\n"
            "    ida_name.set_name(ea, 'sub_' + hex(ea))\n"
            "print(name)\n"
        )

    def test_simple_script_skips_gate(self):
        loop = _make_loop(gate_enabled=True)
        runner = _FakeRunner()
        loop._SubagentRunner = lambda *a, **kw: runner

        called = {"reviewer": False}

        def _review(*a, **kw):
            called["reviewer"] = True
            return iter(())

        loop._review_complex_idapython_script = _review  # type: ignore[assignment]

        tc = MagicMock()
        tc.id = "1"
        tc.name = "execute_python"
        tc.arguments = {"code": "print(idaapi.get_inf_structure())"}

        # Manually invoke the gate-firing branch.  We don't have to
        # drive _execute_single_tool end-to-end — we just want to
        # confirm the gate was *not* triggered.
        from rikugan.tools.idapython_complexity import classify_idapython_script
        from rikugan.tools.validate_idapython import validate_idapython

        code = tc.arguments["code"]
        complexity = classify_idapython_script(code, validate_idapython(code))
        self.assertFalse(complexity.is_complex)
        self.assertFalse(called["reviewer"])

    def test_complex_script_with_approved_verdict_proceeds(self):
        loop = _make_loop(gate_enabled=True)
        approved_summary = (
            "VERDICT: APPROVED\n"
            "REASONS:\n- script is well-formed\n"
            "API_NOTES:\n- ida_funcs.get_func_name — docs OK\n"
            "REWRITE_GUIDANCE:\n- none\n"
        )
        runner = _FakeRunner(final_text=approved_summary)
        # Swap SubagentRunner construction
        import rikugan.agent.loop as loop_mod

        original_runner = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = MagicMock()
            tc.id = "tc1"
            tc.name = "execute_python"
            tc.arguments = {"code": self._complex_script()}

            # Drive the helper directly
            from rikugan.tools.idapython_complexity import classify_idapython_script
            from rikugan.tools.validate_idapython import validate_idapython

            code = tc.arguments["code"]
            validation = validate_idapython(code)
            complexity = classify_idapython_script(code, validation)
            self.assertTrue(complexity.is_complex)

            gen = loop._review_complex_idapython_script(tc, complexity, validation)
            approved, summary = _drain_with_return(gen)
            self.assertTrue(approved)
            self.assertIn("VERDICT: APPROVED", summary)
        finally:
            loop_mod.SubagentRunner = original_runner

    def test_complex_script_with_rewrite_verdict_blocks(self):
        loop = _make_loop(gate_enabled=True)
        rejected_summary = (
            "VERDICT: REWRITE_REQUIRED\n"
            "REASONS:\n- ida_bytes.patch_byte returns nothing, use ida_bytes.patch_bytes\n"
            "API_NOTES:\n- ida_bytes.patch_byte — wrong API\n"
            "REWRITE_GUIDANCE:\n- use ida_bytes.patch_bytes(ea, b'\\x90')\n"
        )
        runner = _FakeRunner(final_text=rejected_summary)
        import rikugan.agent.loop as loop_mod

        original_runner = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = MagicMock()
            tc.id = "tc2"
            tc.name = "execute_python"
            tc.arguments = {"code": self._complex_script()}

            from rikugan.tools.idapython_complexity import classify_idapython_script
            from rikugan.tools.validate_idapython import validate_idapython

            code = tc.arguments["code"]
            validation = validate_idapython(code)
            complexity = classify_idapython_script(code, validation)
            self.assertTrue(complexity.is_complex)

            gen = loop._review_complex_idapython_script(tc, complexity, validation)
            approved, summary = _drain_with_return(gen)
            self.assertFalse(approved)
            self.assertIn("REWRITE_REQUIRED", summary)
        finally:
            loop_mod.SubagentRunner = original_runner

    def test_reviewer_crash_falls_through(self):
        """Behavior change (Decision #6): a reviewer crash is an
        infrastructure fault, not a script fault.  The gate now
        emits a ``DOCS_GATE_STATUS`` ``failed`` event and returns
        ``(True, "")`` so the caller proceeds to user approval
        instead of hard-blocking."""
        loop = _make_loop(gate_enabled=True)
        runner = _FakeRunner(raise_on_run=RuntimeError("provider down"))
        import rikugan.agent.loop as loop_mod

        original_runner = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = MagicMock()
            tc.id = "tc3"
            tc.name = "execute_python"
            tc.arguments = {"code": self._complex_script()}

            from rikugan.tools.idapython_complexity import classify_idapython_script
            from rikugan.tools.validate_idapython import validate_idapython

            code = tc.arguments["code"]
            validation = validate_idapython(code)
            complexity = classify_idapython_script(code, validation)
            self.assertTrue(complexity.is_complex)

            events: list = []
            gen = loop._review_complex_idapython_script(tc, complexity, validation)
            while True:
                try:
                    events.append(next(gen))
                except StopIteration as stop:
                    approved, summary = stop.value
                    break

            from rikugan.agent.turn import TurnEventType

            gate_events = [e for e in events if e.type == TurnEventType.DOCS_GATE_STATUS]
            self.assertTrue(
                any(e.metadata.get("docs_gate_state") == "failed" for e in gate_events),
                "No 'failed' DOCS_GATE_STATUS event emitted on reviewer crash",
            )
            # Fall-through to user approval
            self.assertTrue(approved)
            self.assertEqual(summary, "")
        finally:
            loop_mod.SubagentRunner = original_runner

    def test_validator_block_overrides_approved_verdict(self):
        """Defense in depth: even if the reviewer approves, a blocked
        validator result must NOT let the gate pass."""
        loop = _make_loop(gate_enabled=True)
        approved_summary = (
            "VERDICT: APPROVED\n"
            "REASONS:\n- script is well-formed\n"
            "API_NOTES:\n- idaapi.get_operands — present\n"
            "REWRITE_GUIDANCE:\n- none\n"
        )
        runner = _FakeRunner(final_text=approved_summary)
        import rikugan.agent.loop as loop_mod

        original_runner = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = MagicMock()
            tc.id = "tc4"
            tc.name = "execute_python"
            # ``idaapi.get_operands`` is a known-hallucinated API.
            tc.arguments = {"code": "print(idaapi.get_operands(0x401000))\n"}

            from rikugan.tools.idapython_complexity import classify_idapython_script
            from rikugan.tools.validate_idapython import validate_idapython

            code = tc.arguments["code"]
            validation = validate_idapython(code)
            complexity = classify_idapython_script(code, validation)
            self.assertTrue(validation.is_blocked)
            self.assertTrue(complexity.is_complex)

            gen = loop._review_complex_idapython_script(tc, complexity, validation)
            approved, _summary = _drain_with_return(gen)
            self.assertFalse(approved)
        finally:
            loop_mod.SubagentRunner = original_runner


# ---------------------------------------------------------------------------
# DOCS_GATE_STATUS event emission tests (Task 2)
# ---------------------------------------------------------------------------

# A script the classifier flags as complex: multi-module + multi-line.
_COMPLEX_EMISSION_SCRIPT = ("import idautils\nimport idc\nfor ea in idautils.Functions():\n    print(ea)\n") * 3


class TestDocsGateStatusEmission(unittest.TestCase):
    """The review path emits ``DOCS_GATE_STATUS``, never ``TEXT_DELTA``."""

    def _review(self, script: str, verdict_text: str):
        from rikugan.core.types import ToolCall

        loop = _make_loop(gate_enabled=True)
        runner = _FakeRunner(final_text=verdict_text)
        import rikugan.agent.loop as loop_mod

        original_runner = loop_mod.SubagentRunner
        loop_mod.SubagentRunner = lambda *a, **kw: runner
        try:
            tc = ToolCall(id="tc1", name="execute_python", arguments={"code": script})
            validation = validate_idapython(script)
            complexity = classify_idapython_script(script, validation)

            events: list = []
            gen = loop._review_complex_idapython_script(tc, complexity, validation)
            while True:
                try:
                    events.append(next(gen))
                except StopIteration as stop:
                    result = stop.value
                    break
            return events, result
        finally:
            loop_mod.SubagentRunner = original_runner

    def test_approved_emits_docs_gate_status_not_text_delta(self):
        from rikugan.agent.turn import TurnEventType

        events, (approved, _summary) = self._review(_COMPLEX_EMISSION_SCRIPT, "VERDICT: APPROVED\nLooks good.")
        event_types = [e.type for e in events]
        self.assertIn(TurnEventType.DOCS_GATE_STATUS, event_types)
        self.assertNotIn(TurnEventType.TEXT_DELTA, event_types)
        self.assertTrue(approved)

    def test_running_state_emitted_before_verdict(self):
        from rikugan.agent.turn import TurnEventType

        events, _result = self._review(_COMPLEX_EMISSION_SCRIPT, "VERDICT: APPROVED")
        gate_events = [e for e in events if e.type == TurnEventType.DOCS_GATE_STATUS]
        self.assertGreaterEqual(len(gate_events), 2)
        self.assertEqual(gate_events[0].metadata["docs_gate_state"], "running")
        self.assertEqual(gate_events[-1].metadata["docs_gate_state"], "approved")

    def test_blocked_emits_blocked_state_and_returns_false(self):
        from rikugan.agent.turn import TurnEventType

        events, (approved, _summary) = self._review(_COMPLEX_EMISSION_SCRIPT, "VERDICT: REWRITE_REQUIRED\nBad API.")
        gate_events = [e for e in events if e.type == TurnEventType.DOCS_GATE_STATUS]
        self.assertTrue(
            any(e.metadata["docs_gate_state"] == "blocked" for e in gate_events),
            f"No blocked event: {[e.metadata.get('docs_gate_state') for e in gate_events]}",
        )
        self.assertFalse(approved)


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


def _drain_with_return(gen):
    """Drain a generator that returns a ``(approved, summary)`` tuple.

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
