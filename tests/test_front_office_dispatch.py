import contextlib
import copy
import io
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import front_office
import front_office_dispatch


class FrontOfficeDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = front_office.PROFILE_DIR / "comfy0311-h3.json"
        cls.profile = json.loads(path.read_text(encoding="utf-8"))
        cls.profile["status"] = front_office.PROFILE_STATUS_DISPATCHABLE

    def execution_spec(self, profile=None):
        selected = self.profile if profile is None else profile
        return {
            "semantic": {
                "profile": {
                    "id": selected["id"],
                    "sha256": front_office.canonical_sha256(selected),
                }
            }
        }

    def invoke(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = front_office_dispatch.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dispatch_uses_only_pinned_direct_argv_and_sanitized_environment(self):
        profile = copy.deepcopy(self.profile)
        spec = self.execution_spec(profile)
        spec_path = front_office.REPO_ROOT / ".runtime" / "front-office-execution-test.json"
        completed = subprocess.CompletedProcess(args=[], returncode=23)
        with mock.patch.object(
            front_office, "resolve_execution_spec_path", return_value=spec_path
        ) as resolve, mock.patch.object(front_office, "load_execution_spec", return_value=spec), mock.patch.object(
            front_office, "validate_execution_spec"
        ) as validate, mock.patch.object(
            front_office, "load_enrolled_profile", return_value=profile
        ), mock.patch.object(front_office_dispatch.subprocess, "run", return_value=completed) as run, mock.patch.dict(
            os.environ,
            {
                "LAB_RESERVE_VRAM_GB": "0",
                "CUDA_VISIBLE_DEVICES": "7",
                "HF_TOKEN": "not-in-child",
                "PYTHONPATH": "unsafe",
                "SystemRoot": "C:\\Windows",
                "PATH": "C:\\Windows\\System32",
                "USERNAME": "Jeffrey",
                "USERPROFILE": "C:\\Users\\jeffr",
                "HOMEDRIVE": "C:",
                "HOMEPATH": "\\Users\\jeffr",
                "LOCALAPPDATA": "C:\\Users\\jeffr\\AppData\\Local",
                "APPDATA": "C:\\Users\\jeffr\\AppData\\Roaming",
            },
            clear=True,
        ):
            code = front_office_dispatch.dispatch_execution_spec("front-office-execution-test.json")

        self.assertEqual(code, 23)
        resolve.assert_called_once_with("front-office-execution-test.json")
        validate.assert_called_once_with(spec)
        argv = run.call_args.args[0]
        self.assertEqual(
            argv,
            [
                profile["python"]["path"],
                profile["floor_runner"]["path"],
                "--front-office-spec",
                str(spec_path),
            ],
        )
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["cwd"], str(front_office.REPO_ROOT))
        child_environment = run.call_args.kwargs["env"]
        self.assertEqual(child_environment["HF_HOME"], profile["environment"]["HF_HOME"])
        self.assertEqual(child_environment["SystemRoot"], "C:\\Windows")
        self.assertEqual(child_environment["USERNAME"], "Jeffrey")
        self.assertEqual(child_environment["USERPROFILE"], "C:\\Users\\jeffr")
        self.assertEqual(child_environment["LOCALAPPDATA"], "C:\\Users\\jeffr\\AppData\\Local")
        self.assertNotIn("LAB_RESERVE_VRAM_GB", child_environment)
        self.assertNotIn("CUDA_VISIBLE_DEVICES", child_environment)
        self.assertNotIn("HF_TOKEN", child_environment)
        self.assertNotIn("PYTHONPATH", child_environment)

    def test_dispatch_refuses_static_profile_before_subprocess(self):
        profile = copy.deepcopy(self.profile)
        profile["status"] = front_office.PROFILE_STATUS_STATIC_ONLY
        spec = self.execution_spec(profile)
        with mock.patch.object(
            front_office, "resolve_execution_spec_path", return_value=Path("C:/trusted/spec.json")
        ), mock.patch.object(front_office, "load_execution_spec", return_value=spec), mock.patch.object(
            front_office, "load_enrolled_profile", return_value=profile
        ), mock.patch.object(front_office_dispatch.subprocess, "run") as run:
            with self.assertRaisesRegex(front_office_dispatch.DispatchError, "ENROLLED_DISPATCHABLE"):
                front_office_dispatch.dispatch_execution_spec("front-office-execution-test.json")
        run.assert_not_called()

    def test_cli_accepts_only_spec_flag(self):
        code, _, stderr = self.invoke(["--spec", "x", "--root", "C:/untrusted"])
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", stderr)

    def test_dispatcher_source_uses_direct_subprocess_without_a_shell_string(self):
        source = Path(front_office_dispatch.__file__).read_text(encoding="utf-8")
        self.assertIn("subprocess.run(", source)
        self.assertIn("shell=False", source)
        self.assertNotIn("cmd.exe", source.lower())
        self.assertNotIn("powershell", source.lower())
