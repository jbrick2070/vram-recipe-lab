import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertEqual(
            json.loads(stdout)["profiles"], ["comfy0311-h3", "comfy0320-h3"]
        )

        code, stdout, stderr = self.invoke(
            ["validate-profile", "comfy0320-h3", "--json"]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["status"], "VALID_STATIC_ENROLLMENT")

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

    def test_stale_historical_static_profile_refuses_a_live_plan(self):
        code, stdout, stderr = self.invoke(
            [
                "plan",
                "front-office-static-h3/h3-ref2va-seed42",
                "--profile",
                "comfy0311-h3",
                "--json",
            ]
        )
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("drifted", stderr)

    def test_blocked_c032_and_static_launch_both_fail_closed(self):
        code, _, stderr = self.invoke(
            ["plan", "h3-c032/h3-i2v-sentinel", "--profile", "comfy0311-h3", "--json"]
        )
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED_PROFILE_ENROLLMENT", stderr)

        code, stdout, stderr = self.invoke(
            ["launch", "front-office-static-h3/h3-ref2va-seed42", "--profile", "comfy0311-h3", "--json"]
        )
        self.assertEqual(code, 2, stderr)
        self.assertEqual(stdout, "")
        self.assertIn("not READY_FOR_DISPATCH", stderr)

    def test_launch_seals_dispatchable_cell_and_returns_child_code(self):
        spec = {"launch_spec_sha256": "a" * 64}
        destination = Path("C:/trusted/.runtime/front-office-execution-test.json")
        with mock.patch.object(labctl.front_office, "build_execution_spec", return_value=spec) as build, mock.patch.object(
            labctl.front_office, "write_execution_spec", return_value=destination
        ) as write, mock.patch.object(
            labctl.front_office_dispatch, "dispatch_execution_spec", return_value=17
        ) as dispatch:
            code, stdout, stderr = self.invoke(
                ["launch", "ready-campaign/control-cell", "--profile", "dispatchable-profile", "--json"]
            )
        self.assertEqual(code, 17, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "DISPATCHED")
        self.assertEqual(payload["child_returncode"], 17)
        self.assertEqual(payload["launch_spec_sha256"], "a" * 64)
        build.assert_called_once_with("ready-campaign", "control-cell", "dispatchable-profile")
        write.assert_called_once_with(spec)
        dispatch.assert_called_once_with(destination)

    def test_launch_rejects_caller_roots_argv_and_environment(self):
        for forbidden in (
            ["--root", "C:/untrusted"],
            ["--argv", "python.exe"],
            ["--env", "LAB_RESERVE_VRAM_GB=0"],
        ):
            code, _, stderr = self.invoke(
                [
                    "launch",
                    "front-office-static-h3/h3-ref2va-seed42",
                    "--profile",
                    "comfy0311-h3",
                    *forbidden,
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("unrecognized arguments", stderr)

    def test_cli_has_no_process_or_shell_launcher(self):
        source = Path(labctl.__file__).read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("Popen(", source)
