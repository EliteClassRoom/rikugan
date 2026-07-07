"""Real-network integration test for the IDAPython docs build script.

Gated behind ``RUN_NETWORK_TESTS=1`` env var. By default pytest skips this
file so CI without network access stays green.

Run locally with:
    RUN_NETWORK_TESTS=1 pytest tests/test_build_idapython_docs_integration.py -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pytest


@pytest.mark.skipif(
    not os.getenv("RUN_NETWORK_TESTS"),
    reason="opt-in: set RUN_NETWORK_TESTS=1 to run",
)
class TestRealFetchIntegration(unittest.TestCase):
    """End-to-end: fetch one real module from Hex-Rays."""

    def test_fetch_ida_typeinf_end_to_end(self):
        # Fetch just one module (ida_typeinf is large enough to be
        # representative, small enough to be fast).
        #
        # The build script uses stdlib urllib internally; we exercise it
        # through its public API rather than pulling in an HTTP client dep.
        from scripts.build_idapython_docs import (
            SOURCES_URL_TEMPLATE,
            fetch_with_retry,
            sha256_text,
            write_atomic,
        )

        url = SOURCES_URL_TEMPLATE.format(module="ida_typeinf")
        body = fetch_with_retry(url, max_retries=2)
        self.assertIsNotNone(body, "fetch_with_retry returned None — network?")
        assert body is not None  # for type checker

        # Should contain key API names we know exist
        for token in ("create_udt", "apply_cdecl", "BTF_STRUCT"):
            self.assertIn(
                token,
                body,
                f"ida_typeinf.rst.txt missing expected token {token!r}",
            )

        # sha256 is deterministic
        h1 = sha256_text(body)
        h2 = sha256_text(body)
        self.assertEqual(h1, h2)

        # Atomic write round-trips
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ida_typeinf.rst.txt"
            write_atomic(target, body)
            self.assertEqual(target.read_text(encoding="utf-8"), body)
