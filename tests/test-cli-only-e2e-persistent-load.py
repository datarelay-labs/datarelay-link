#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import unittest
p=Path(__file__).resolve().parents[1]/"tools/cli_only_e2e_persistent_load.py"
spec=importlib.util.spec_from_file_location("cli_only_load",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PersistentLoadTests(unittest.TestCase):
    def test_all_original_unshortened_duration_profiles(self):
        self.assertEqual(m.PROFILES,
                         {"warmup":60,"steady":300,"soak":3600,
                          "extended":28800,"endurance":86400})
    def test_only_real_traffic_no_shell_or_cli_mutation(self):
        for args in (["bash","-c","true"],["drlink","unset","server"],
                     ["ssh","test-host","true"],["curl","token=private"]):
            with self.assertRaises(ValueError):
                m.validate_command(args)
        m.validate_command(["curl","--fail","--silent","https://example.test/"])
    def test_unknown_durations_rejected(self):
        with self.assertRaises(ValueError):
            m.duration("5seconds")

if __name__=="__main__":
    unittest.main()
