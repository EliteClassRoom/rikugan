"""Tool registry: discovers, stores, and dispatches tool calls."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from ..constants import TOOL_RESULT_TRUNCATE_LEN
from ..core.errors import ToolError, ToolNotFoundError, ToolValidationError
from ..core.logging import log_debug
from .base import ToolDefinition
from .cache import ToolResultCache
from .coercion import coerce_bool

# Default timeout for tool execution (seconds).  Per-tool overrides via ToolDefinition.timeout.
_DEFAULT_TOOL_TIMEOUT = 30.0

# Shared executor — single thread is sufficient since IDA tools run on main thread via idasync
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tool-timeout")


class ToolRegistry:
    """Central registry of all available tools.

    Parameters
    ----------
    dispatch_wrapper : callable, optional
        A wrapper applied around every tool handler at execution time to
        marshal calls onto the correct thread.  Host-specific registries
        pass ``idasync`` here; standalone/test environments omit it.
    """

    def __init__(self, dispatch_wrapper: Callable | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._schema_cache: list[dict[str, Any]] | None = None
        self._result_cache = ToolResultCache()
        self._capabilities: dict[str, bool] = {}
        self._dispatch_wrapper = dispatch_wrapper
        self._lock = threading.RLock()  # protects against MCP thread concurrent registration

    @staticmethod
    def _coerce_arguments(defn: ToolDefinition, arguments: dict[str, Any]) -> dict[str, Any]:
        """Coerce mistyped tool arguments to match the schema.

        LLMs sometimes send integers as strings (e.g. "30" instead of 30).
        Walk the parameter schema and cast values to their declared types.
        """
        coerced = dict(arguments)
        if not defn.parameters or not coerced:
            return coerced

        param_types = {p.name: p.type for p in defn.parameters}

        for key, value in coerced.items():
            expected = param_types.get(key)
            if expected is None:
                continue

            try:
                if expected == "integer":
                    # bool is a subclass of int — check bool FIRST
                    if isinstance(value, bool):
                        coerced[key] = int(value)
                    elif not isinstance(value, int):
                        # Handle "30", "30.0", etc.
                        coerced[key] = int(float(value))
                elif expected == "number" and not isinstance(value, (int, float)):
                    coerced[key] = float(value)
                elif expected == "boolean" and not isinstance(value, bool):
                    coerced[key] = coerce_bool(value)
                elif expected == "string" and not isinstance(value, str):
                    coerced[key] = str(value)
            except (ValueError, TypeError) as e:
                log_debug(f"_coerce_arguments: coercion failed for {key!r}: {e}")  # handler will raise validation error

        return coerced

    def coerce_arguments_for(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return *arguments* coerced to match the schema registered for *name*.

        This is the public entry point for callers that need a single
        normalized argument dict for pre-state capture, execution,
        reverse-record building, and post-state verification.

        Raises :class:`ToolNotFoundError` when *name* is not registered.
        """
        with self._lock:
            defn = self._tools.get(name)
        if defn is None:
            raise ToolNotFoundError(f"Tool not found: {name}", tool_name=name)
        return self._coerce_arguments(defn, arguments)

    def register(self, defn: ToolDefinition) -> None:
        with self._lock:
            self._tools[defn.name] = defn
            self._schema_cache = None  # invalidate
        log_debug(f"Registered tool: {defn.name}")

    def register_function(self, func: Callable[..., Any]) -> None:
        defn = getattr(func, "_tool_definition", None)
        if defn is None:
            raise ValueError(f"{func.__name__} is not decorated with @tool")
        self.register(defn)

    def register_module(self, module: Any) -> None:
        """Register all @tool-decorated functions in a module.

        Collects tool definitions first, then registers them under a single
        lock acquisition (instead of locking/unlocking for each tool).
        """
        defs: list[ToolDefinition] = []
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and isinstance(getattr(obj, "_tool_definition", None), ToolDefinition):
                defs.append(obj._tool_definition)
        if defs:
            with self._lock:
                for d in defs:
                    self._tools[d.name] = d
                self._schema_cache = None
            for d in defs:
                log_debug(f"Registered tool: {d.name}")

    def unregister_by_prefix(self, prefix: str) -> int:
        """Remove all tools whose name starts with *prefix*. Returns count removed."""
        with self._lock:
            to_remove = [name for name in self._tools if name.startswith(prefix)]
            for name in to_remove:
                del self._tools[name]
            if to_remove:
                self._schema_cache = None
        if to_remove:
            log_debug(f"Unregistered {len(to_remove)} tools with prefix {prefix!r}")
        return len(to_remove)

    def set_capabilities(self, capabilities: dict[str, bool]) -> None:
        """Declare which host capabilities are available (e.g. hexrays, ida_struct)."""
        with self._lock:
            self._capabilities.update(capabilities)
            self._schema_cache = None  # invalidate — available tools may have changed

    def _available(self, defn: ToolDefinition) -> bool:
        """Check if all requirements of a tool definition are met.

        Requirements default to False when not explicitly declared —
        tools must opt-in via ``set_capabilities()``.
        """
        for req in defn.requires:
            if not self._capabilities.get(req, False):
                return False
        return True

    def get(self, name: str) -> ToolDefinition | None:
        with self._lock:
            return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        with self._lock:
            return list(self._tools.values())

    def list_available_tools(self) -> list[ToolDefinition]:
        """Return only tools whose capability requirements are satisfied.

        Filters with ``_available()`` so callers (e.g. headless ``/tools``
        endpoint) see exactly the same subset the provider schema exposes.
        """
        with self._lock:
            return [t for t in self._tools.values() if self._available(t)]

    def list_names(self) -> list[str]:
        with self._lock:
            return list(self._tools.keys())

    def to_provider_format(self) -> list[dict[str, Any]]:
        """Return tool schemas in provider-compatible format.

        Returns a shallow copy of the cached list. The schema dicts are
        shared by reference — callers MUST treat them as read-only and must
        not mutate nested ``properties``/``required`` data in place. Build a
        new dict instead. (Called once per turn from the agent loop; the deep
        copy it used to do duplicated 60+ nested schemas every turn for no
        benefit, since every call site only filters the list and appends.)
        """
        with self._lock:
            if self._schema_cache is None:
                self._schema_cache = [t.to_provider_format() for t in self._tools.values() if self._available(t)]
            return list(self._schema_cache)

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        with self._lock:
            defn = self._tools.get(name)
            if defn is None:
                raise ToolNotFoundError(f"Unknown tool: {name}", tool_name=name)
            if defn.handler is None:
                raise ToolError(f"Tool {name} has no handler", tool_name=name)
            if not self._available(defn):
                missing = [r for r in defn.requires if not self._capabilities.get(r, False)]
                raise ToolError(
                    f"Tool {name} unavailable — requires: {', '.join(missing)}",
                    tool_name=name,
                )
            handler = defn.handler
            timeout = defn.timeout if defn.timeout is not None else _DEFAULT_TOOL_TIMEOUT
            is_mutating = defn.mutating
            dispatch_wrapper = self._dispatch_wrapper

        arguments = self._coerce_arguments(defn, arguments)

        # Check cache for read-only tools
        cached = self._result_cache.get(name, arguments)
        if cached is not None:
            return cached

        if dispatch_wrapper is not None:
            handler = dispatch_wrapper(handler)

        try:
            future = _executor.submit(handler, **arguments)
            result = future.result(timeout=timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise ToolError(
                f"Tool {name} timed out after {timeout}s",
                tool_name=name,
            ) from None
        except (ToolError, ToolValidationError):
            raise
        except TypeError as e:
            raise ToolValidationError(f"Invalid arguments for {name}: {e}", tool_name=name) from e
        except Exception as e:
            raise ToolError(f"Tool {name} failed: {e}", tool_name=name) from e

        result_str = self._format_result(result)
        if len(result_str) > TOOL_RESULT_TRUNCATE_LEN:
            result_str = result_str[:TOOL_RESULT_TRUNCATE_LEN] + "\n... (truncated)"

        # Cache result for read-only tools; invalidate on mutating tools
        self._result_cache.put(name, arguments, result_str)
        if is_mutating:
            self._result_cache.invalidate()

        return result_str

    def execute_current_thread(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool directly on the current thread (no thread-pool dispatch).

        Use this when you are already running on a designated work thread
        (e.g. the IDA main thread) and submitting to the thread pool would
        cause a deadlock — the pool worker would wait for
        ``ida_kernwin.execute_sync`` while the caller blocks on the future.

        Validates, coerces, caches, and truncates like ``execute()``, but
        does **not** enforce the thread-pool timeout (``tool_timeout``) —
        the caller is responsible for any deadline.
        """
        with self._lock:
            defn = self._tools.get(name)
            if defn is None:
                raise ToolNotFoundError(f"Unknown tool: {name}", tool_name=name)
            if defn.handler is None:
                raise ToolError(f"Tool {name} has no handler", tool_name=name)
            if not self._available(defn):
                missing = [r for r in defn.requires if not self._capabilities.get(r, False)]
                raise ToolError(
                    f"Tool {name} unavailable — requires: {', '.join(missing)}",
                    tool_name=name,
                )
            handler = defn.handler
            is_mutating = defn.mutating
            dispatch_wrapper = self._dispatch_wrapper

        arguments = self._coerce_arguments(defn, arguments)

        cached = self._result_cache.get(name, arguments)
        if cached is not None:
            return cached

        if dispatch_wrapper is not None:
            handler = dispatch_wrapper(handler)

        try:
            result = handler(**arguments)
        except (ToolError, ToolValidationError):
            raise
        except TypeError as e:
            raise ToolValidationError(f"Invalid arguments for {name}: {e}", tool_name=name) from e
        except Exception as e:
            raise ToolError(f"Tool {name} failed: {e}", tool_name=name) from e

        result_str = self._format_result(result)
        if len(result_str) > TOOL_RESULT_TRUNCATE_LEN:
            result_str = result_str[:TOOL_RESULT_TRUNCATE_LEN] + "\n... (truncated)"

        self._result_cache.put(name, arguments, result_str)
        if is_mutating:
            self._result_cache.invalidate()

        return result_str

    @staticmethod
    def _format_result(result: Any) -> str:
        if result is None:
            return "OK"
        if isinstance(result, str):
            return result
        if isinstance(result, (dict, list)):
            return json.dumps(result, indent=2, default=str)
        return str(result)
