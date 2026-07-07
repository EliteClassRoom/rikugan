"""Unit tests for scripts/build_idapython_docs.py — HTML index parser."""

from __future__ import annotations

import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from scripts.build_idapython_docs import discover_modules_from_index, fetch_with_retry


class TestDiscoverModules(unittest.TestCase):
    def test_parses_module_links_from_index_html(self):
        # Hex-Rays index page has <a href="ida_typeinf/"> links for each module
        html = """
        <html><body>
        <a href="ida_typeinf/">ida_typeinf</a>
        <a href="ida_name/">ida_name</a>
        <a href="idautils/">idautils</a>
        <a href="idaapi/">idaapi</a>
        <a href="https://example.com/external/">skip me</a>
        <a href="#fragment">skip me too</a>
        </body></html>
        """
        result = discover_modules_from_index(html)
        self.assertEqual(
            sorted(result),
            ["ida_name", "ida_typeinf", "idaapi", "idautils"],
        )

    def test_empty_html_returns_empty_list(self):
        self.assertEqual(discover_modules_from_index(""), [])

    def test_malformed_html_no_modules_returns_empty(self):
        # If no <a href="<module>/"> matches, parser returns empty
        html = "<html><body><p>no modules here</p></body></html>"
        self.assertEqual(discover_modules_from_index(html), [])


class TestFetchWithRetry(unittest.TestCase):
    def test_successful_fetch_returns_body(self):
        mock_response = MagicMock()
        mock_response.read.return_value = b"ida_typeinf module docs"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = fetch_with_retry("https://example.com/test")
        self.assertEqual(result, "ida_typeinf module docs")

    def test_retries_on_timeout_then_succeeds(self):
        # First 2 calls raise timeout, 3rd succeeds
        mock_response = MagicMock()
        mock_response.read.return_value = b"success"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch(
            "urllib.request.urlopen",
            side_effect=[TimeoutError("net"), TimeoutError("net"), mock_response],
        ):
            with patch("time.sleep"):  # Don't actually sleep in tests
                result = fetch_with_retry("https://example.com/test", max_retries=3)
        self.assertEqual(result, "success")

    def test_persistent_timeout_returns_none(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("net")):
            with patch("time.sleep"):
                result = fetch_with_retry("https://example.com/test", max_retries=2)
        self.assertIsNone(result)

    def test_http_404_returns_none_no_retry(self):
        # 4xx is not retried — module path is genuinely wrong
        error = urllib.error.HTTPError("https://example.com/x", 404, "Not Found", {}, None)
        with patch("urllib.request.urlopen", side_effect=error):
            result = fetch_with_retry("https://example.com/x", max_retries=3)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
