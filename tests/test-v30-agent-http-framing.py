#!/usr/bin/env python3
"""Malformed HTTPS artifact framing must fail closed with a bounded error.

This is an isolated parser regression: no network, installed Agent, or public
rollout Apply is contacted.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_v30_agent_artifact as signed
import drlink_v30_agent_artifact_transport as transport


class _Response:
    status = 200

    def __init__(self, length: str | None, payload: bytes):
        self.length = length
        self.payload = payload

    def getheader(self, name: str) -> str | None:
        assert name == "Content-Length"
        return self.length

    def read(self, size: int) -> bytes:
        return self.payload[:size]


class _Connection:
    def __init__(self, response: _Response):
        self.response = response
        self.requested = False
        self.closed = False

    def request(self, method, path, headers):
        self.requested = (method == "GET" and path == "/artifacts/manifest.json")

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class SignedArtifactHTTPSFramingTests(unittest.TestCase):
    def _download(self, length: str | None, payload: bytes = b"abc") -> bytes:
        connection = _Connection(_Response(length, payload))
        with patch.object(transport.http.client, "HTTPSConnection", return_value=connection):
            try:
                result = transport._https_get(
                    "example.invalid", 443, "/artifacts/manifest.json",
                    32, object(),
                )
            finally:
                self.assertTrue(connection.requested)
                self.assertTrue(connection.closed)
        return result

    def test_valid_bounded_content_length(self):
        self.assertEqual(self._download("3"), b"abc")

    def test_missing_content_length_remains_size_bounded(self):
        self.assertEqual(self._download(None), b"abc")

    def test_empty_content_length_fails_closed_without_unhandled_exception(self):
        with self.assertRaisesRegex(
            signed.AgentArtifactError, "Content-Length is invalid"
        ):
            self._download("")

    def test_truncated_and_oversized_content_length_denied(self):
        for length in ("4", "33", "not-an-integer", "-1", "0"):
            with self.subTest(length=length):
                with self.assertRaises(signed.AgentArtifactError):
                    self._download(length)

    def test_content_length_must_use_ascii_decimal_digits_only(self):
        # RFC Content-Length = 1*DIGIT, not Python int() syntax.
        for invalid in ("+3", " 3", "3 ", "3,3", "٣"):
            with self.subTest(content_length=invalid):
                with self.assertRaisesRegex(
                    signed.AgentArtifactError, "Content-Length is invalid"
                ):
                    self._download(invalid)
        self.assertEqual(self._download("003"), b"abc")


if __name__ == "__main__":
    unittest.main()
