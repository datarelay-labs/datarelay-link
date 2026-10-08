#!/usr/bin/env python3
"""Enrollment URL authority is immutable local trust for signed Agent updates.

Pure, isolated parsing regression: no network, real Agent, signer, or update.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_v30_agent_artifact import AgentArtifactError
from drlink_v30_agent_local_trust import _enrolled_https_origin


class EnrolledAgentArtifactOriginTests(unittest.TestCase):
    def test_empty_or_nonempty_url_credentials_fail_closed(self):
        # Even empty @ credentials must be rejected rather than silently
        # normalized away: only an absolute authority with no userinfo qualifies.
        for url in (
            "https://@enrolled.example.invalid/enroll",
            "https://:@enrolled.example.invalid/enroll",
            "https://user@enrolled.example.invalid/enroll",
            "https://user:@enrolled.example.invalid/enroll",
            "https://:secret@enrolled.example.invalid/enroll",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(
                AgentArtifactError, "AGENT_ARTIFACT_UNQUALIFIED"
            ):
                _enrolled_https_origin({"allocator_url": url})

    def test_plain_enrolled_origin_retains_https_authority(self):
        self.assertEqual(
            _enrolled_https_origin(
                {"allocator_url": "https://enrolled.example.invalid:8443/enroll"}
            ),
            "https://enrolled.example.invalid:8443",
        )
        self.assertEqual(
            _enrolled_https_origin(
                {"allocator_url": "https://[::1]/enroll"}
            ),
            "https://[::1]",
        )

    def test_single443_remap_requires_unambiguous_public_port(self):
        self.assertEqual(
            _enrolled_https_origin({
                "allocator_url": "https://enrolled.example.invalid:6099/enroll",
                "frp_transport": "wss",
                "frp_server_port": 443,
            }),
            "https://enrolled.example.invalid",
        )
        for public_port in ("6099", "0", "", "65536"):
            with self.subTest(public_port=public_port), self.assertRaises(
                AgentArtifactError
            ):
                _enrolled_https_origin({
                    "allocator_url": "https://enrolled.example.invalid:6099/enroll",
                    "frp_transport": "wss",
                    "frp_server_port": public_port,
                })


if __name__ == "__main__":
    unittest.main()
