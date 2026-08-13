import contextlib
import io
import json
import unittest
from pathlib import Path

import labctl


class LabctlTests(unittest.TestCase):
    def invoke(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = labctl.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_profiles_and_validation_accept_only_enrolled_ids(self):
        code, stdout, stderr = self.invoke(["profiles", "--json"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["profiles"], ["comfy0311-h3"])

        code, stdout, stderr = self.invoke(["validate-profile", "unknown-profile", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("unknown enrolled profile", stderr)

    def test_plan_never_accepts_an_arbitrary_root_or_raw_argv(self):
        code, _, stderr = self.invoke(
            [
                "plan",
                "front-office-static-h3/h3-ref2va-seed42",
                "--profile",
                "comfy0311-h3",
                "--root",
                "C:\\untrusted",
            ]
        )
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", stderr)

    def test_plan_is_static_and_sealed(self):
        code, stdout, stderr = self.invoke(
            [
                "plan",
                "front-office-static-h3/h3-ref2va-seed42",
                "--profile",
                "comfy0311-h3",
                "--json",
            ]
        )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["semantic"]["execution_state"], "STATIC_ONLY_NOT_DISPATCHABLE")
        self.assertEqual(payload["semantic"]["profile"]["id"], "comfy0311-h3")
        self.assertNotIn("--use-sage-attention", payload["semantic"]["server"]["argv"])

    def test_blocked_c032_and_launch_both_fail_closed(self):
        code, _, stderr = self.invoke(
            ["plan", "h3-c032/h3-i2v-sentinel", "--profile", "comfy0311-h3", "--json"]
        )
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED_PROFILE_ENROLLMENT", stderr)

        code, stdout, stderr = self.invoke(
            ["launch", "front-office-static-h3/h3-ref2va-seed42", "--profile", "comfy0311-h3", "--json"]
        )
        self.assertEqual(code, 2, stderr)
        self.assertEqual(json.loads(stdout)["status"], "DIRECT_LAUNCH_NOT_INTEGRATED")

    def test_cli_has_no_process_or_shell_launcher(self):
        source = Path(labctl.__file__).read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("Popen(", source)
