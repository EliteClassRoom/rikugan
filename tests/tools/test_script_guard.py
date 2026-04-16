"""Tests for rikugan/tools/script_guard.py."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.tools.script_guard import _check_ast, run_guarded_script


def _empty_ns():
    return {}


class TestCheckAst(unittest.TestCase):
    def test_blocks_subprocess(self):
        assert _check_ast("import subprocess") is not None

    def test_blocks_os_system(self):
        assert _check_ast("os.system('ls')") is not None

    def test_blocks_os_popen(self):
        assert _check_ast("os.popen('ls')") is not None

    def test_blocks_import_subprocess_via_dunder(self):
        assert _check_ast("__import__('subprocess')") is not None

    def test_blocks_os_exec(self):
        assert _check_ast("os.execv('/bin/sh', [])") is not None

    def test_blocks_os_spawn(self):
        assert _check_ast("os.spawnl(0, '/bin/sh')") is not None

    def test_blocks_exec_call(self):
        assert _check_ast("exec('code')") is not None

    def test_blocks_eval_call(self):
        assert _check_ast("eval('1+1')") is not None

    def test_blocks_from_subprocess_import(self):
        assert _check_ast("from subprocess import Popen") is not None

    def test_blocks_syntax_error(self):
        assert _check_ast("def f(:\n    pass") is not None

    def test_allows_harmless_code(self):
        assert _check_ast("x = 1 + 2") is None

    def test_allows_print(self):
        assert _check_ast("print('hello')") is None

    def test_allows_os_path(self):
        assert _check_ast("os.path.join('a', 'b')") is None


class TestRunGuardedScript(unittest.TestCase):
    def test_blocked_subprocess(self):
        result = run_guarded_script("import subprocess", _empty_ns)
        assert result.startswith("Error: Blocked")
        assert "subprocess" in result

    def test_blocked_os_system(self):
        result = run_guarded_script("os.system('ls')", _empty_ns)
        assert "Blocked" in result

    def test_stdout_captured(self):
        result = run_guarded_script("print('hello')", _empty_ns)
        assert "hello" in result
        assert "stdout" in result

    def test_stderr_on_exception(self):
        result = run_guarded_script("raise ValueError('oops')", _empty_ns)
        assert "ValueError" in result
        assert "oops" in result
        assert "stderr" in result

    def test_no_output_placeholder(self):
        result = run_guarded_script("x = 1 + 2", _empty_ns)
        assert result == "(no output)"

    def test_namespace_provided_to_exec(self):
        ns_calls = []
        def ns_factory():
            d = {"captured": ns_calls}
            ns_calls.append("called")
            return d
        result = run_guarded_script("captured.append('exec')", ns_factory)
        assert "exec" in ns_calls
        assert result == "(no output)"

    def test_stdout_and_stderr_combined(self):
        code = "print('out'); raise RuntimeError('err')"
        result = run_guarded_script(code, _empty_ns)
        assert "stdout" in result
        assert "out" in result
        assert "stderr" in result
        assert "RuntimeError" in result

    def test_syntax_error_in_code(self):
        result = run_guarded_script("def f(:\n    pass", _empty_ns)
        assert "Error" in result

    def test_namespace_factory_called_fresh_each_time(self):
        calls = []
        def factory():
            calls.append(1)
            return {}
        run_guarded_script("x = 1", factory)
        run_guarded_script("y = 2", factory)
        assert len(calls) == 2


if __name__ == "__main__":
    unittest.main()
