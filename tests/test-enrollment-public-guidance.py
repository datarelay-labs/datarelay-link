#!/usr/bin/env python3
"""Public enrollment recovery must stay canonical without invoking enrollment."""
import os
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import frp_ctl_grammar as grammar


class EnrollmentPublicGuidance(unittest.TestCase):
    def test_options_cannot_enter_enrollment_backend_or_guided_flow(self):
        for mode in (None, "manual", "zero-touch", "bulk"):
            path = ["set", "enrollment"] + ([mode] if mode else [])
            for option in ("--help", "-h", "--ttl", "--one-line"):
                for tokens in (path + [option], path + [option, "?"], ["help"] + path + [option]):
                    with self.subTest(tokens=tokens):
                        result = grammar.match(tokens, "server")
                        self.assertEqual(result.get("status"), "error", result)
                        self.assertEqual(result.get("exit_code"), 2, result)
                        self.assertIn("commands do not use --options", result["message"])
                        self.assertNotIn("create zero-touch", result["message"])
                        self.assertNotIn("set client", result["message"])

    def test_binary_help_flags_cannot_select_lifecycle_effects(self):
        paths = (["system", "pause"], ["system", "restart"],
                 ["system", "resume"], ["system", "synchronize"],
                 ["unset", "remote-service", "example-service"],
                 ["system", "rollback", "1"], ["unset", "remote-access", "policy"])
        for role in ("client", "server"):
            for path in paths:
                for flag in ("--help", "-h"):
                    for tokens in (list(path) + [flag], list(path) + [flag, "?"], ["help"] + list(path) + [flag]):
                        with self.subTest(role=role, tokens=tokens):
                            result = grammar.match(tokens, role)
                            self.assertEqual(result.get("status"), "error", result)
                            self.assertEqual(result.get("exit_code"), 2, result)
                            self.assertIn("commands do not use --options", result["message"])

    def test_native_help_rejection_occurs_before_mocked_lifecycle_effects(self):
        source = (ROOT / "tools/frpctl").read_text()
        start = re.search(r"^frpctl_dispatch_canonical\(\) \{\n", source, re.M)
        self.assertIsNotNone(start)
        end = source.find("\n}\n", start.end())
        self.assertGreater(end, start.end())
        native = source[start.start():end + 3]
        # Actual native dispatch and matcher, but every effect boundary is inert.
        python_match = "import json,sys; sys.path.insert(0," + repr(str(ROOT / "lib")) + "); import frp_ctl_grammar as g; print(json.dumps(g.match(json.loads(sys.argv[1])['tokens'],'client')))"
        script = """
frpctl_grammar_call() { python3 -c MATCH_PROGRAM "$2"; }
frpctl_json_get() { python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2], ""))' "$1" "$2"; }
frpctl_require_client() { return 0; }
frpctl_is_client() { return 0; }
frpctl_is_server() { return 1; }
frpctl_load_passthrough() { _frpctl_pt=(); }
frpctl_invoke() { echo "STUB_EFFECT_TOOL:$*"; }
frpctl_control_plane_dispatch() { echo STUB_EFFECT_CONTROL_PLANE; }
""".replace("MATCH_PROGRAM", shlex.quote(python_match)) + native + '\nfrpctl_dispatch_canonical "$@"\nexit "$_FRP_CTL_RC"\n'
        for action in ("pause", "restart", "resume", "synchronize"):
            for flag in ("--help", "-h"):
                with self.subTest(action=action, flag=flag):
                    proc = subprocess.run(["bash", "-c", script, "native-inert-fixture", "system", action, flag], capture_output=True, text=True, timeout=10)
                    output = proc.stdout + proc.stderr
                    self.assertEqual(proc.returncode, 2, output)
                    self.assertNotIn("STUB_EFFECT", output)
                    self.assertIn("commands do not use --options", output)

    def test_native_enrollment_help_options_fail_without_state_change(self):
        with tempfile.TemporaryDirectory(prefix="drlink-enrollment-guidance-") as temp:
            config = Path(temp, "etc/drlink/config.json")
            config.parent.mkdir(parents=True)
            config.write_text('{"role":"server"}\n')
            env = dict(os.environ, FRP_CTL_TEST_ROOT=temp, FRP_DEPLOY_TEST_ROOT=temp)
            before = {str(p.relative_to(temp)): p.read_bytes() for p in Path(temp).rglob("*") if p.is_file()}
            for mode in ("manual", "zero-touch", "bulk"):
                for option in ("--help", "-h"):
                    with self.subTest(mode=mode, option=option):
                        proc = subprocess.run(["bash", str(ROOT / "tools/drlink"), "set", "enrollment", mode, option], env=env, capture_output=True, text=True, timeout=20)
                        output = proc.stdout + proc.stderr
                        self.assertEqual(proc.returncode, 2, output)
                        self.assertIn("commands do not use --options", output)
                        self.assertNotIn("set client", output)
                        self.assertNotIn("create zero-touch", output)
                        self.assertNotIn("frp-create-client", output)
            after = {str(p.relative_to(temp)): p.read_bytes() for p in Path(temp).rglob("*") if p.is_file()}
            self.assertEqual(after, before)

    def test_supported_help_and_unexpected_argument_guidance_are_canonical(self):
        for mode in ("manual", "zero-touch", "bulk"):
            result = grammar.match(["set", "enrollment", mode, "?"], "server")
            self.assertEqual(result.get("action"), "context_help", result)
            self.assertNotIn("set client", result["message"])
        result = grammar.match(["set", "enrollment", "zero-touch", "unexpected"], "server")
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("set enrollment zero-touch", result["message"])
        self.assertNotIn("create zero-touch", result["message"])
        self.assertNotIn("help clients", result["message"])
        for option in ("--help", "-h"):
            self.assertEqual(grammar.match([option], "server")["status"], "unknown")
            result = grammar.match(["system", "uninstall", option], "server")
            self.assertEqual(result.get("action"), "help", result)

    def test_internal_backend_help_recommends_current_public_entry(self):
        proc = subprocess.run([sys.executable, str(ROOT / "tools/frp-create-client"), "--help"], capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for mode in ("zero-touch", "manual", "bulk"):
            self.assertIn("set enrollment " + mode, proc.stdout)
        self.assertNotIn("set client", proc.stdout)
        self.assertIn("backend tool still accepts internal flags", proc.stdout)


if __name__ == "__main__":
    unittest.main()
