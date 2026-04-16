"""Tool result cache with automatic invalidation on mutating operations."""

from __future__ import annotations

import threading
import time
from typing import Any

from ..core.logging import log_debug

# Tool names whose results are safe to cache (read-only, deterministic
# for a given binary state).  Both IDA and BN registries use the same
# tool names for these.
CACHEABLE_TOOLS: frozenset[str] = frozenset(
    {
        "list_functions",
        "list_strings",
        "get_binary_info",
        "decompile_function",
        "function_xrefs",
    }
)

# Cache key: (tool_name, frozen_args) → (timestamp, result_str)
_CacheEntry = tuple[float, str]
_CacheKey = tuple[str, tuple[tuple[str, Any], ...]]


class ToolResultCache:
    """Thread-safe cache for tool results, invalidated by mutating tools."""

    def __init__(self, ttl: float | None = None):
        self._store: dict[_CacheKey, _CacheEntry] = {}
        self._ttl = ttl
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(tool_name: str, arguments: dict[str, Any]) -> _CacheKey:
        """Build a hashable cache key from tool name and arguments."""
        try:
            frozen = tuple(
                sorted(
                    (
                        k,
                        v if isinstance(v, (str, int, float, bool, type(None))) else str(v),
                    )
                    for k, v in arguments.items()
                )
            )
        except Exception:
            frozen = ()
        return (tool_name, frozen)

    def get(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        """Return cached result or None on miss."""
        if tool_name not in CACHEABLE_TOOLS:
            return None
        key = self._make_key(tool_name, arguments)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            ts, result = entry
            if self._ttl is not None and (time.monotonic() - ts) > self._ttl:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            log_debug(f"Cache hit: {tool_name} (hits={self._hits})")
            return result

    def put(self, tool_name: str, arguments: dict[str, Any], result: str) -> None:
        """Store a result in the cache."""
        if tool_name not in CACHEABLE_TOOLS:
            return
        key = self._make_key(tool_name, arguments)
        with self._lock:
            self._store[key] = (time.monotonic(), result)

    def invalidate(self) -> None:
        """Flush the entire cache (called after any mutating tool)."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
        if count:
            log_debug(f"Cache invalidated: {count} entries flushed")

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    @property
    def stats(self) -> tuple[int, int]:
        """Return (hits, misses)."""
        with self._lock:
            return self._hits, self._misses
