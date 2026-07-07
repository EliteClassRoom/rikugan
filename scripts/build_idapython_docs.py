"""Build the offline IDAPython docs bundle from Hex-Rays upstream.

Runs at dev/CI time (NOT inside IDA). Produces raw RST files + MANIFEST.json
under rikugan/data/idapython-docs/. See:
docs/superpowers/specs/2026-07-07-idapython-offline-docs-design.md
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (no magic numbers; values from spec section Components)
#
# NOTE: This module is built up incrementally across tasks 1-6.  Only the
# constants and imports needed for the current task are present; later
# tasks (fetch/manifest/build/verify) will add urllib, hashlib, json, etc.
# ---------------------------------------------------------------------------

BASE_URL: str = "https://python.docs.hex-rays.com"
UPSTREAM_INDEX_URL: str = f"{BASE_URL}/"
SOURCES_URL_TEMPLATE: str = f"{BASE_URL}/_sources/{{module}}/index.rst.txt"

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Path = REPO_ROOT / "rikugan" / "data" / "idapython-docs"
MANIFEST_PATH: Path = OUTPUT_DIR / "MANIFEST.json"

MANIFEST_SCHEMA_VERSION: int = 1

HTTP_TIMEOUT_SECONDS: float = 30.0
MAX_RETRIES: int = 3
INITIAL_BACKOFF_SECONDS: float = 1.0
BACKOFF_MULTIPLIER: float = 2.0

# Module names are [a-z0-9_]+ per spec; we accept that here, and a Sphinx
# index page contains <a href="ida_typeinf/"> style entries.
_MODULE_LINK_RE: re.Pattern[str] = re.compile(r'<a\s+href="(?P<module>[a-z0-9_]+)/?"')


# ---------------------------------------------------------------------------
# HTML index parser — Task 1 deliverable
# ---------------------------------------------------------------------------


def discover_modules_from_index(html_content: str) -> list[str]:
    """Parse the Hex-Rays index page and return module names.

    Args:
        html_content: Raw HTML of https://python.docs.hex-rays.com/

    Returns:
        Sorted list of unique module names matching the Sphinx index
        pattern (e.g. ``["ida_name", "ida_typeinf", "idautils"]``).
        External URLs, fragments, and non-module hrefs are skipped.
    """
    modules = set(_MODULE_LINK_RE.findall(html_content))
    return sorted(modules)


def fetch_with_retry(
    url: str,
    max_retries: int = MAX_RETRIES,
    timeout: float = HTTP_TIMEOUT_SECONDS,
) -> str | None:
    """Fetch ``url`` with exponential backoff on transient network errors.

    Retryable errors (caught and retried up to ``max_retries`` times):
        ``socket.timeout``, ``ConnectionError``, ``TimeoutError``,
        ``urllib.error.URLError`` (network-level). HTTP 5xx is also
        treated as transient and retried.

    Non-retryable (return ``None`` immediately, no retry):
        ``urllib.error.HTTPError`` with a 4xx status — the module path is
        genuinely wrong and retrying will not help.

    Args:
        url: URL to fetch.
        max_retries: Maximum number of attempts before giving up.
        timeout: Per-request timeout in seconds.

    Returns:
        Response body as a UTF-8 string on success, or ``None`` if all
        attempts fail. This function does NOT raise — it logs warnings to
        stderr and returns ``None`` so the build loop can continue.
    """
    last_error: BaseException | None = None
    backoff = INITIAL_BACKOFF_SECONDS
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # 4xx is permanent (bad URL/path); 5xx is transient
            if 400 <= exc.code < 500:
                print(f"[skip] {url}: HTTP {exc.code}", file=sys.stderr)
                return None
            last_error = exc
        except (TimeoutError, ConnectionError, urllib.error.URLError, OSError) as exc:
            last_error = exc
        # Backoff before next attempt (skip on last attempt)
        if attempt < max_retries - 1:
            time.sleep(backoff)
            backoff *= BACKOFF_MULTIPLIER
    print(f"[fail] {url}: {type(last_error).__name__}: {last_error}", file=sys.stderr)
    return None


def write_atomic(path: Path, content: str | bytes) -> None:
    """Write ``content`` to ``path`` atomically (no partial reads ever).

    Strategy: write to ``path.with_suffix(path.suffix + ".tmp")`` in the
    same directory, fsync, then ``os.replace()`` (POSIX-atomic, atomic
    on Windows for same-volume). If the parent directory does not exist,
    create it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = content.encode("utf-8") if isinstance(content, str) else content
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup of leftover temp file
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def sha256_text(text: str) -> str:
    """Return hex SHA-256 digest of ``text`` (UTF-8 encoded)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "BACKOFF_MULTIPLIER",
    "BASE_URL",
    "HTTP_TIMEOUT_SECONDS",
    "INITIAL_BACKOFF_SECONDS",
    "MANIFEST_PATH",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_RETRIES",
    "OUTPUT_DIR",
    "SOURCES_URL_TEMPLATE",
    "UPSTREAM_INDEX_URL",
    "discover_modules_from_index",
    "fetch_with_retry",
    "sha256_text",
    "write_atomic",
]
