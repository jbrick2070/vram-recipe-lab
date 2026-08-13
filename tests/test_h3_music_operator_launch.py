from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))

SCRIPT = SCRATCH / "record_h3_music_operator_launch.py"
LAUNCHER = SCRATCH / "start_h3_music_attempt3.ps1"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "h3_music_operator_launch_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REC = load_module()


def clean_state(_root: Path, _coordinator):
    return {
        "gpu_lock_exists": False,
        "suite_lock_exists": False,
        "server_pid_receipt_exists": False,
        "server_pid_receipt": None,
        "server_pid_create_time": None,
        "queue_quarantine_exists": False,
        "listener_pids_8199": [],
        "expected_server_identity_live": False,
    }


class H3MusicOperatorLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in REC.SOURCE_PATHS.values():
            source = ROOT / relative
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        (self.root / ".coordinator.mutex").write_bytes(b"\0")
        self.paths = REC.expected_paths(self.root)
        self.paths["attempt_directory"].mkdir(parents=True)
        self.paths["stdout"].write_bytes(b"campaign stdout\n")
        self.paths["stderr"].write_bytes(b"")
        self.capture = {
            "authority": "PowerShell Start-Process -Wait -PassThru",
            "pid": 4242,
            "started_at_utc": "2026-08-10T04:00:00.0000000Z",
            "ended_at_utc": "2026-08-10T04:05:00.0000000Z",
            "exit_code": 0,
            "cwd": str(self.root.resolve()),
            "stdout_log": str(self.paths["stdout"]),
            "stderr_log": str(self.paths["stderr"]),
            "argv": REC.expected_campaign_argv(self.root),
        }
        self.coordinator = {
            "path": ".coordinator.mutex",
            "carrier_preexisted": True,
            "carrier_bytes": 1,
            "carrier_sha256": REC.sha256_bytes(b"\0"),
            "acquired_nonblocking": True,
        }
        self.write_terminal_lifecycle()

    def tearDown(self):
        self.temporary.cleanup()

    def operator_transport_preflight(self, sources=None):
        sources = sources or REC.source_snapshots(self.root)
        identities = {}
        for label, fd in (("stdout", 1), ("stderr", 2)):
            stat_result = self.paths[label].stat()
            identities[label] = {
                "path": str(self.paths[label]),
                "fd": fd,
                "device": int(stat_result.st_dev),
                "inode": int(stat_result.st_ino),
                "link_count": int(stat_result.st_nlink),
                "regular_file": True,
            }
        return {
            "contract": REC.expected_operator_log_contract(self.root, sources),
            "attempt_directory_entries": ["stderr.log", "stdout.log"],
            "fd_identities": identities,
            "growing_log_bytes_hashed_as_sources": False,
        }

    def write_terminal_lifecycle(
        self, event="campaign_completed", *, operator_transport_preflight=None
    ):
        sources = REC.source_snapshots(self.root)
        preflight = (
            self.operator_transport_preflight(sources)
            if operator_transport_preflight is None
            else operator_transport_preflight
        )
        ledger = REC.canon.AppendOnlyLifecycle(
            self.paths["lifecycle"], REC.ATTEMPT_ID
        )
        ledger.append(
            "campaign_started",
            {
                "sources": {
                    lifecycle_label: sources[current_label]
                    for lifecycle_label, current_label in REC.CAMPAIGN_SOURCE_LABELS.items()
                },
                "operator_logs": REC.expected_operator_log_contract(
                    self.root, sources
                ),
                "operator_transport_preflight": preflight,
            },
        )
        ledger.append(
            event,
            {"status": "COMPLETE" if event == "campaign_completed" else "FAILED"},
        )

    def cli_args(self, *, write=False, quiet=False):
        values = [
            "--pid",
            str(self.capture["pid"]),
            "--started-at-utc",
            self.capture["started_at_utc"],
            "--ended-at-utc",
            self.capture["ended_at_utc"],
            "--exit-code",
            str(self.capture["exit_code"]),
            "--cwd",
            self.capture["cwd"],
            "--stdout-log",
            self.capture["stdout_log"],
            "--stderr-log",
            self.capture["stderr_log"],
        ]
        if write:
            values.insert(0, "--write")
        if quiet:
            values.insert(0, "--quiet")
        return values

    def payload(self, capture=None):
        return REC.build_receipt(
            self.root,
            capture or self.capture,
            clean_state(self.root, self.coordinator),
            self.coordinator,
        )

    def test_payload_binds_exact_paths_argv_sources_logs_and_terminal(self):
        payload = self.payload()
        self.assertEqual(payload["attempt_id"], REC.ATTEMPT_ID)
        self.assertEqual(payload["campaign_argv"], REC.expected_campaign_argv(self.root))
        self.assertEqual(payload["powershell_capture"], self.capture)
        self.assertEqual(payload["campaign_terminal"]["event"], "campaign_completed")
        self.assertEqual(payload["operator_logs"]["stdout"]["bytes"], 16)
        self.assertTrue(payload["operator_logs"]["stderr"]["empty"])
        self.assertIsInstance(payload["operator_logs"]["stdout"]["device"], int)
        self.assertIsInstance(payload["operator_logs"]["stdout"]["inode"], int)
        self.assertEqual(payload["operator_logs"]["stdout"]["link_count"], 1)
        self.assertEqual(
            payload["operator_transport_preflight"]["fd_identities"]["stdout"][
                "inode"
            ],
            payload["operator_logs"]["stdout"]["inode"],
        )
        self.assertEqual(set(payload["source_sha256s"]), set(REC.SOURCE_PATHS))
        self.assertEqual(
            payload["certification_effect"], REC.TRANSPORT_CERTIFICATION_EFFECT
        )

    def test_default_is_read_only(self):
        lifecycle_before = self.paths["lifecycle"].read_bytes()
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = REC.main(
                self.cli_args(), root=self.root, state_probe=clean_state
            )
        self.assertEqual(status, 0)
        self.assertFalse(self.paths["receipt"].exists())
        self.assertEqual(self.paths["lifecycle"].read_bytes(), lifecycle_before)
        proposed = json.loads(stdout.getvalue())
        self.assertEqual(proposed["status"], "TRANSPORT_CAPTURED")
        self.assertFalse(
            proposed["certification_effect"]["recipe_or_pair_certification_granted"]
        )

    def test_write_is_o_excl_and_appends_one_separate_event(self):
        lifecycle_before = self.paths["lifecycle"].read_bytes()
        stdout_before = self.paths["stdout"].read_bytes()
        stderr_before = self.paths["stderr"].read_bytes()
        with redirect_stdout(io.StringIO()):
            status = REC.main(
                self.cli_args(write=True), root=self.root, state_probe=clean_state
            )
        self.assertEqual(status, 0)
        receipt_before = self.paths["receipt"].read_bytes()
        self.assertFalse(receipt_before.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.paths["lifecycle"].read_bytes().startswith(lifecycle_before))
        rows = [
            json.loads(line)
            for line in self.paths["lifecycle"].read_text(encoding="utf-8").splitlines()
        ]
        events = [row for row in rows if row["campaign_id"] == REC.OPERATOR_EVENT_ID]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "operator_launch_recorded")
        self.assertFalse(
            events[0]["details"]["certification_effect"][
                "recipe_or_pair_certification_granted"
            ]
        )
        with redirect_stdout(io.StringIO()):
            status = REC.main(
                ["--write"], root=self.root, state_probe=clean_state
            )
        self.assertEqual(status, 0)
        self.assertEqual(self.paths["receipt"].read_bytes(), receipt_before)
        rows_after = self.paths["lifecycle"].read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows_after), len(rows))
        self.assertEqual(self.paths["stdout"].read_bytes(), stdout_before)
        self.assertEqual(self.paths["stderr"].read_bytes(), stderr_before)

    def test_existing_receipt_without_event_recovers_only_event(self):
        payload = self.payload()
        receipt = REC.exclusive_write(self.root, payload)
        lifecycle_before = self.paths["lifecycle"].read_bytes()
        receipt_before = self.paths["receipt"].read_bytes()
        self.assertFalse(
            REC.validate_existing_event(
                REC.validate_lifecycle(self.root, REC.source_snapshots(self.root)),
                receipt,
            )
        )
        with redirect_stdout(io.StringIO()):
            status = REC.main(
                ["--write"], root=self.root, state_probe=clean_state
            )
        self.assertEqual(status, 0)
        self.assertEqual(self.paths["receipt"].read_bytes(), receipt_before)
        self.assertTrue(self.paths["lifecycle"].read_bytes().startswith(lifecycle_before))
        lifecycle = REC.validate_lifecycle(self.root, REC.source_snapshots(self.root))
        self.assertTrue(REC.validate_existing_event(lifecycle, receipt))

    def test_exit120_and_brokenpipe_stderr_are_transport_only(self):
        self.capture["exit_code"] = 120
        self.paths["stderr"].write_text(
            "Exception ignored in: <_io.TextIOWrapper name='<stdout>'>\n"
            "BrokenPipeError: [Errno 32] Broken pipe\n",
            encoding="utf-8",
        )
        payload = self.payload()
        observed = payload["stderr_observations"]
        self.assertTrue(observed["exit_code_120_observed"])
        self.assertTrue(observed["possible_cpython_broken_pipe_marker_observed"])
        self.assertFalse(observed["cause_confirmed"])
        self.assertFalse(
            observed["certification_effect"]["exit_120_reclassified_as_success"]
        )
        self.assertFalse(
            payload["certification_effect"]["recipe_or_pair_certification_granted"]
        )

    def test_capture_path_argv_time_and_exit_drift_are_rejected(self):
        cases = {
            "cwd": str(self.root / "wrong"),
            "stdout_log": str(self.root / "wrong.log"),
            "argv": ["wrong"],
            "started_at_utc": "not-a-time",
            "ended_at_utc": "2026-08-10T03:00:00.0000000Z",
            "exit_code": 2**40,
            "pid": 0,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                capture = copy.deepcopy(self.capture)
                capture[field] = value
                with self.assertRaises(REC.OperatorLaunchError):
                    self.payload(capture)

    def test_extra_entry_and_hardlinked_logs_are_rejected(self):
        extra = self.paths["attempt_directory"] / "unexpected.txt"
        extra.write_bytes(b"unexpected")
        with self.assertRaisesRegex(REC.OperatorLaunchError, "entries drift"):
            self.payload()
        extra.unlink()
        self.paths["stderr"].unlink()
        os.link(self.paths["stdout"], self.paths["stderr"])
        with self.assertRaisesRegex(REC.OperatorLaunchError, "same file"):
            self.payload()

    def test_replaced_log_after_campaign_start_is_rejected_even_with_same_bytes(self):
        original = self.root / "preserved-start-stdout.log"
        stdout_raw = self.paths["stdout"].read_bytes()
        self.paths["stdout"].rename(original)
        self.paths["stdout"].write_bytes(stdout_raw)
        self.assertNotEqual(
            (original.stat().st_dev, original.stat().st_ino),
            (self.paths["stdout"].stat().st_dev, self.paths["stdout"].stat().st_ino),
        )
        with self.assertRaisesRegex(REC.OperatorLaunchError, "identity changed"):
            self.payload()

    def test_external_hardlink_to_operator_log_is_rejected(self):
        external = self.root / "external-stdout-hardlink.log"
        os.link(self.paths["stdout"], external)
        self.assertEqual(self.paths["stdout"].stat().st_nlink, 2)
        with self.assertRaisesRegex(REC.OperatorLaunchError, "link count"):
            self.payload()

    def test_operator_transport_preflight_shape_and_identity_drift_are_rejected(self):
        clean = self.operator_transport_preflight()
        cases = {}
        missing = copy.deepcopy(clean)
        missing.pop("fd_identities")
        cases["missing field"] = missing
        extra = copy.deepcopy(clean)
        extra["unexpected"] = False
        cases["extra field"] = extra
        entries = copy.deepcopy(clean)
        entries["attempt_directory_entries"] = ["stdout.log", "stderr.log"]
        cases["entry order"] = entries
        growing = copy.deepcopy(clean)
        growing["growing_log_bytes_hashed_as_sources"] = True
        cases["growing logs"] = growing
        shared_fd = copy.deepcopy(clean)
        shared_fd["fd_identities"]["stderr"]["fd"] = 1
        cases["shared fd"] = shared_fd
        wrong_inode = copy.deepcopy(clean)
        wrong_inode["fd_identities"]["stdout"]["inode"] += 1
        cases["wrong inode"] = wrong_inode
        wrong_contract = copy.deepcopy(clean)
        wrong_contract["contract"]["authority"] = "untrusted"
        cases["wrong contract"] = wrong_contract

        for label, preflight in cases.items():
            with self.subTest(label=label):
                self.paths["lifecycle"].unlink()
                self.write_terminal_lifecycle(
                    operator_transport_preflight=preflight
                )
                with self.assertRaises(REC.OperatorLaunchError):
                    self.payload()

    def test_missing_terminal_or_source_drift_is_rejected(self):
        self.paths["lifecycle"].unlink()
        sources = REC.source_snapshots(self.root)
        ledger = REC.canon.AppendOnlyLifecycle(
            self.paths["lifecycle"], REC.ATTEMPT_ID
        )
        ledger.append(
            "campaign_started",
            {
                "sources": {
                    lifecycle_label: sources[current_label]
                    for lifecycle_label, current_label in REC.CAMPAIGN_SOURCE_LABELS.items()
                },
                "operator_logs": REC.expected_operator_log_contract(
                    self.root, sources
                ),
                "operator_transport_preflight": self.operator_transport_preflight(
                    sources
                ),
            },
        )
        with self.assertRaisesRegex(REC.OperatorLaunchError, "terminal"):
            self.payload()

        ledger.append("campaign_failed", {"status": "FAILED"})
        campaign = self.root / REC.CAMPAIGN_RELATIVE
        campaign.write_bytes(campaign.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(REC.OperatorLaunchError, "source evidence"):
            self.payload()

    def test_dirty_state_fails_before_publication(self):
        dirty = clean_state(self.root, self.coordinator)
        dirty["gpu_lock_exists"] = True

        def dirty_probe(_root, _coordinator):
            return dirty

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = REC.main(
                self.cli_args(write=True, quiet=False),
                root=self.root,
                state_probe=dirty_probe,
            )
        self.assertEqual(status, 2)
        self.assertFalse(self.paths["receipt"].exists())
        self.assertIn("gpu_lock_exists", stderr.getvalue())

    def test_launcher_has_durable_no_pipe_exitcode_contract(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        for required in (
            "[switch]$Run",
            '"-u"',
            '"--resume-attempt-002"',
            '"--operator-stdout-log"',
            '"--operator-stderr-log"',
            '$env:PYTHONUNBUFFERED = "1"',
            "New-Item -ItemType Directory -Path $AttemptDirectory -ErrorAction Stop",
            "-RedirectStandardOutput $StdoutLog",
            "-RedirectStandardError $StderrLog",
            "-WindowStyle Hidden",
            "-Wait",
            "-PassThru",
            "$CampaignProcess.ExitCode",
            '"--write"',
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        for forbidden in (
            "$LASTEXITCODE",
            "Tee-Object",
            "2>&1",
            "Remove-Item",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertLess(source.index("$CampaignProcess.ExitCode"), source.index("$RecorderArguments"))

    def test_recorder_has_no_render_query_network_or_overwrite_surface(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.O_CREAT | os.O_EXCL | os.O_WRONLY", source)
        self.assertIn("operator transport only", source)
        for forbidden in (
            "requests.",
            "urllib.",
            "http://127.0.0.1",
            '"/prompt"',
            "subprocess.",
            "os.replace",
            "shutil.move",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
