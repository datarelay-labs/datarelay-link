#!/usr/bin/env python3
"""Focused regression for Codex E2E D001 public navigation / Master drift."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md"
CLI = ROOT / "tools/frpctl"


class CurrentPublicNavigationMasterTests(unittest.TestCase):
    def test_server_and_agent_document_public_session_history_clear(self):
        doc = MASTER.read_text(encoding="utf-8")
        agent = doc.split("# 47. Agent local lifecycle", 1)[1].split("# 48.", 1)[0]
        server = doc.split("## 49.5 System", 1)[1].split("# 50.", 1)[0]
        source = CLI.read_text(encoding="utf-8")
        for command in ("system history", "system clear"):
            self.assertIn(command, source, "public executable advertises "+command)
            for section in (agent, server):
                self.assertIn(command, section)
        self.assertIn("session", agent.lower())
        self.assertIn("screen", server.lower())


if __name__ == "__main__":
    unittest.main()
