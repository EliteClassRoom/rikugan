"""Thread-safety utilities for IDA API access."""

from __future__ import annotations

import functools
import importlib
import threading
from collections.abc import Callable
from typing import Any, TypeVar

from .host import IDA_AVAILABLE as _IDA_AVAILABLE

F = TypeVar("F", bound=Callable[..., Any])

if _IDA_AVAILABLE:
    ida_kernwin = importlib.import_module("ida_kernwin")


_TRACE_ENABLED: bool | None = None


_trace_enabled_checked_at: float = 0.0


def _log(msg: str) -> None:
    """Low-level log that avoids circular imports with logging.py.

    Re-checks the effective log level periodically (every 30 s) so that
    changing the level at runtime (e.g. via settings reload) eventually
    enables TRACE output without a restart.
    """
    global _TRACE_ENABLED, _trace_enabled_checked_at
    try:
        import logging as _logging
        import time as _time

        from .logging import get_logger, log_trace

        now = _time.monotonic()
        if _TRACE_ENABLED is None or now - _trace_enabled_checked_at > 30:
            _TRACE_ENABLED = get_logger().isEnabledFor(_logging.DEBUG)
            _trace_enabled_checked_at = now
        if not _TRACE_ENABLED:
            return
        log_trace(msg)
    except ImportError:
        return  # logging module unavailable during early bootstrap — skip silently


def idasync(func: F) -> F:
    """Decorator: execute *func* on IDA main thread when required.

    IDA: uses ``ida_kernwin.execute_sync`` with ``MFF_WRITE``.
    Other hosts: executes directly.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        fname = func.__name__
        on_main = threading.current_thread() is threading.main_thread()

        if _IDA_AVAILABLE:
            if on_main:
                _log(f"idasync: {fname} on main thread — direct call")
                return func(*args, **kwargs)

            _log(f"idasync: {fname} on {threading.current_thread().name} — execute_sync START")
            result_holder: list = []
            error_holder: list = []

            def _thunk() -> int:
                try:
                    _log(f"idasync: {fname} _thunk executing on main thread")
                    result_holder.append(func(*args, **kwargs))
                    _log(f"idasync: {fname} _thunk OK")
                except Exception as exc:
                    _log(f"idasync: {fname} _thunk ERROR: {exc}")
                    error_holder.append(exc)
                return 0

            rc = ida_kernwin.execute_sync(_thunk, ida_kernwin.MFF_WRITE)
            _log(f"idasync: {fname} execute_sync returned rc={rc}")

            if error_holder:
                raise error_holder[0]
            return result_holder[0] if result_holder else None

        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def run_in_background(func: Callable[..., Any], *args: Any, **kwargs: Any) -> threading.Thread:
    """Run *func* in a daemon background thread."""
    thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread
