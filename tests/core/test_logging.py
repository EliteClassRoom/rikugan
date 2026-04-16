"""Tests for the logging module."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tests.mocks.ida_mock import install_ida_mocks
install_ida_mocks()

from rikugan.core.logging import (
    get_logger,
    log_info,
    log_warning,
    log_error,
    log_debug,
    log_trace,
    IDAHandler,
    _FlushFileHandler,
)


class _CaptureHandler(logging.Handler):
    """Test handler that captures log records."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestLogFunctions(unittest.TestCase):
    """Test the convenience logging functions."""

    def setUp(self):
        self._capture = _CaptureHandler()
        get_logger().addHandler(self._capture)

    def tearDown(self):
        get_logger().removeHandler(self._capture)

    def test_get_logger_returns_logger(self):
        logger = get_logger()
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "Rikugan")

    def test_get_logger_singleton(self):
        a = get_logger()
        b = get_logger()
        self.assertIs(a, b)

    def test_logger_has_handlers(self):
        logger = get_logger()
        handler_types = {type(h) for h in logger.handlers}
        self.assertIn(IDAHandler, handler_types)

    def test_log_info(self):
        log_info("info_test_message")
        matching = [r for r in self._capture.records
                    if r.levelno == logging.INFO and "info_test_message" in r.getMessage()]
        self.assertEqual(len(matching), 1)

    def test_log_warning(self):
        log_warning("warn_test_message")
        matching = [r for r in self._capture.records
                    if r.levelno == logging.WARNING and "warn_test_message" in r.getMessage()]
        self.assertEqual(len(matching), 1)

    def test_log_error(self):
        log_error("error_test_message")
        matching = [r for r in self._capture.records
                    if r.levelno == logging.ERROR and "error_test_message" in r.getMessage()]
        self.assertEqual(len(matching), 1)

    def test_log_debug(self):
        log_debug("debug_test_message")
        matching = [r for r in self._capture.records
                    if r.levelno == logging.DEBUG and "debug_test_message" in r.getMessage()]
        self.assertEqual(len(matching), 1)

    def test_log_trace(self):
        log_trace("trace_label")
        matching = [r for r in self._capture.records
                    if r.levelno == logging.DEBUG and "TRACE trace_label" in r.getMessage()]
        self.assertEqual(len(matching), 1)


class TestIDAHandler(unittest.TestCase):
    def test_emit_formats_and_delivers(self):
        handler = IDAHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )
        # Should not raise (delivers to ida_kernwin.msg mock or stderr)
        handler.emit(record)

    def test_emit_to_stderr_when_no_host_sink(self):
        """When no host sink is registered, HostOutputHandler falls back to stderr."""
        import io
        import rikugan.core.log_sinks as sinks_mod

        handler = IDAHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0,
            msg="stderr test", args=(), exc_info=None,
        )
        saved_sink = sinks_mod._host_sink
        saved_resolve = sinks_mod._resolve_host_sink
        sinks_mod._host_sink = None
        sinks_mod._resolve_host_sink = lambda: None  # prevent auto-detection
        captured = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured
        try:
            handler.emit(record)
        finally:
            sys.stderr = old_stderr
            sinks_mod._host_sink = saved_sink
            sinks_mod._resolve_host_sink = saved_resolve

        self.assertIn("stderr test", captured.getvalue())


class TestFlushFileHandler(unittest.TestCase):
    def test_emit_and_flush(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            path = f.name

        try:
            handler = _FlushFileHandler(path, mode="w")
            handler.setFormatter(logging.Formatter("%(message)s"))
            record = logging.LogRecord(
                name="test", level=logging.INFO,
                pathname="", lineno=0,
                msg="flush test", args=(), exc_info=None,
            )
            handler.emit(record)
            handler.close()

            with open(path) as f:
                content = f.read()
            self.assertIn("flush test", content)
        finally:
            os.unlink(path)

    def test_log_file_path_creates_directory(self):
        from rikugan.core.log_sinks import _log_file_path
        path = _log_file_path()
        self.assertTrue(os.path.isdir(os.path.dirname(path)))
        self.assertTrue(path.endswith("rikugan_debug.log"))


if __name__ == "__main__":
    unittest.main()
