from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))

import record_h3_music_attempt5_operator_launch as operator5


LAUNCHER = ROOT / "scratch/start_h3_music_attempt5.ps1"
RECORDER = ROOT / "scratch/record_h3_music_attempt5_operator_launch.py"


class Attempt5OperatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_owner = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_owner.name)

    def tearDown(self) -> None:
        self.temp_owner.cleanup()

    def write(self, relative: Path, raw: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    @staticmethod
    def lifecycle_row(
        event: str,
        ledger_sequence: int,
        campaign_sequence: int,
        previous: str | None,
        details: dict[str, object],
        *,
        campaign_id: str = operator5.ATTEMPT_ID,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "ledger_sequence": ledger_sequence,
            "campaign_id": campaign_id,
            "campaign_sequence": campaign_sequence,
            "event": event,
            "previous_event_sha256": previous,
            "details": details,
        }
        return {
            **body,
            "event_sha256": operator5.sha256_bytes(
                operator5.canonical_bytes(body)
            ),
        }

    def make_transport(
        self,
        *,
        terminal_event: str = "campaign_completed",
        terminal_status: str = "COMPLETE",
        process_overrides: dict[str, object] | None = None,
        descriptor_drift: bool = False,
    ) -> None:
        for relative in operator5.SOURCE_PATHS.values():
            self.write(relative, (ROOT / relative).read_bytes())
        self.write(operator5.STDOUT, b'{"status":"COMPLETE"}\n')
        self.write(operator5.STDERR, b"")
        self.write(Path(".coordinator.mutex"), b"\0")

        sources = operator5.source_snapshots(self.root)
        contract = operator5.expected_operator_contract(self.root, sources)
        _, stdout_snapshot = operator5.snapshot(
            self.root, operator5.STDOUT, "operator stdout"
        )
        _, stderr_snapshot = operator5.snapshot(
            self.root, operator5.STDERR, "operator stderr"
        )
        process: dict[str, object] = {
            "authority": "campaign self-observation via psutil",
            "pid": 123,
            "process_create_time": datetime(
                2026, 8, 10, tzinfo=timezone.utc
            ).timestamp(),
            "cwd": str(self.root.resolve()),
            "invoked_executable": str(operator5.PYTHON),
            "process_image": str(operator5.PYTHON),
            "argv": operator5.expected_campaign_argv(self.root),
        }
        process.update(process_overrides or {})
        preflight = {
            "contract": contract,
            "attempt_directory_entries": ["stderr.log", "stdout.log"],
            "fd_identities": {
                label: {
                    "path": snapshot["path"],
                    "fd": fd,
                    "device": snapshot["device"],
                    "inode": snapshot["inode"] + (1 if descriptor_drift else 0),
                    "link_count": 1,
                    "regular_file": True,
                }
                for label, snapshot, fd in (
                    ("stdout", stdout_snapshot, 1),
                    ("stderr", stderr_snapshot, 2),
                )
            },
            "growing_log_bytes_hashed_as_sources": False,
        }
        started_details = {
            "sources": sources,
            "operator_logs": contract,
            "operator_transport_preflight": preflight,
            "campaign_process": process,
        }
        if terminal_event == "campaign_completed":
            rows: list[dict[str, object]] = []
            previous: str | None = None
            for sequence in range(1, 66):
                row = self.lifecycle_row(
                    "historical_event",
                    sequence,
                    sequence,
                    previous,
                    {},
                    campaign_id="historical-campaign",
                )
                rows.append(row)
                previous = row["event_sha256"]
            recovery_started = self.lifecycle_row(
                "recovery_started", 66, 1, previous, {}
            )
            rows.append(recovery_started)
            started = self.lifecycle_row(
                "campaign_started", 67, 2, recovery_started["event_sha256"], started_details
            )
            rows.append(started)
            previous = started["event_sha256"]
            for campaign_sequence in range(3, 23):
                row = self.lifecycle_row(
                    "attempt5_event",
                    65 + campaign_sequence,
                    campaign_sequence,
                    previous,
                    {},
                )
                rows.append(row)
                previous = row["event_sha256"]
            terminal_details: dict[str, object] = {
                "status": terminal_status,
                "pair_count": 11,
                "carried_pair_count": 9,
                "executed_pair_count": 2,
                "new_execution_count": 4,
                "study_leg_count": 22,
                "pairs": [{"pair_index": index} for index in range(1, 12)],
                "final_state": dict(operator5.SUCCESS_CLEAN_STATE),
                "final_evidence_audit": [
                    {
                        "pair_index": index,
                        "disposition": (
                            "CARRIED_FORWARD" if index <= 9 else "EXECUTED"
                        ),
                    }
                    for index in range(1, 12)
                ],
            }
            terminal = self.lifecycle_row(
                terminal_event,
                88,
                23,
                previous,
                terminal_details,
            )
            rows.append(terminal)
        else:
            started = self.lifecycle_row(
                "campaign_started",
                1,
                1,
                None,
                started_details,
            )
            terminal = self.lifecycle_row(
                terminal_event,
                2,
                2,
                started["event_sha256"],
                {"status": terminal_status},
            )
            rows = [started, terminal]
        raw = b"".join(
            (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
            for row in rows
        )
        self.write(operator5.LIFECYCLE, raw)

    def mutate_success_terminal(self, mutate) -> None:
        path = self.root / operator5.LIFECYCLE
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        terminal = rows[-1]
        mutate(terminal["details"])
        body = dict(terminal)
        body.pop("event_sha256", None)
        terminal["event_sha256"] = operator5.sha256_bytes(
            operator5.canonical_bytes(body)
        )
        path.write_bytes(
            b"".join(
                (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
                for row in rows
            )
        )

    def build(self, *, exit_code: int = 0, started: str = "2026-08-10T00:00:00Z"):
        return operator5.build_receipt(
            root=self.root,
            pid=123,
            started_at_utc=started,
            ended_at_utc="2026-08-10T00:00:01Z",
            exit_code=exit_code,
            cwd=self.root,
            stdout_log=self.root / operator5.STDOUT,
            stderr_log=self.root / operator5.STDERR,
        )

    def test_default_is_read_only(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(operator5.main([], root=self.root), 0)
        self.assertTrue(json.loads(output.getvalue())["default_read_only"])
        self.assertFalse((self.root / operator5.RECEIPT).exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_launcher_is_exact_atomic_hidden_and_records_before_exit_throw(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertFalse(LAUNCHER.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertIn(operator5.ATTEMPT_ID, source)
        self.assertIn('"--resume-attempt-004"', source)
        self.assertNotIn('"--resume-attempt-003"', source)
        self.assertIn("New-Item -ItemType Directory -Path $AttemptDirectory", source)
        self.assertNotIn("New-Item -ItemType Directory -Path $AttemptDirectory -Force", source)
        self.assertGreaterEqual(source.count("-WindowStyle Hidden"), 2)
        self.assertIn("-Wait `", source)
        self.assertIn("-PassThru", source)
        recorder_start = source.index("$RecorderProcess = Start-Process")
        campaign_throw = source.index("if ($CampaignExitCode -ne 0)")
        self.assertLess(recorder_start, campaign_throw)
        self.assertIn("--write", source)
        self.assertIn("immutable transport evidence was retained", source)

    def test_build_binds_exact_argv_sources_streams_recovery_and_terminal(self) -> None:
        self.make_transport()
        payload = self.build()
        self.assertEqual(payload["attempt_id"], operator5.ATTEMPT_ID)
        self.assertEqual(
            payload["process"]["argv"], operator5.expected_campaign_argv(self.root)
        )
        self.assertIn("--resume-attempt-004", payload["process"]["argv"])
        self.assertEqual(payload["terminal"]["event"], "campaign_completed")
        self.assertTrue(payload["lifecycle"]["terminal_is_last_row"])
        self.assertEqual(payload["lifecycle"]["row_count"], 88)
        self.assertEqual(
            payload["success_completion_boundary"],
            {
                "lifecycle_row_count": 88,
                "terminal_ledger_sequence": 88,
                "terminal_campaign_sequence": 23,
                "pair_count": 11,
                "carried_pair_count": 9,
                "executed_pair_count": 2,
                "new_execution_count": 4,
                "study_leg_count": 22,
                "final_evidence_audit_count": 11,
                "final_state": operator5.SUCCESS_CLEAN_STATE,
                "verified": True,
            },
        )
        self.assertEqual(
            set(operator5.SOURCE_PATHS),
            {
                "campaign",
                "attempt5_operator_launcher",
                "attempt5_operator_recorder",
                "attempt4_recovery_recorder",
                "attempt4_recovery_receipt",
            },
        )
        recovery = payload["recovery_authority"]
        self.assertEqual(recovery["recovery_id"], operator5.RECOVERY_ID)
        self.assertEqual(
            recovery["pair11_recipe"],
            "h3_unconditioned_music_scene_seed42_f277",
        )
        self.assertFalse(recovery["superseded_recovery_usable_as_authority"])
        self.assertEqual(
            recovery["receipt"]["sha256"], operator5.RECOVERY4_RECEIPT_SHA256
        )

    def test_failed_exit_binds_only_failed_terminal_and_status(self) -> None:
        self.make_transport(terminal_event="campaign_failed", terminal_status="FAILED")
        payload = self.build(exit_code=7)
        self.assertEqual(payload["terminal"]["event"], "campaign_failed")
        self.assertEqual(payload["terminal"]["status"], "FAILED")
        self.assertIsNone(payload["success_completion_boundary"])
        with self.assertRaisesRegex(
            operator5.OperatorReceiptError, "terminal disagree"
        ):
            self.build(exit_code=0)

    def test_valid_row_after_attempt_terminal_is_rejected(self) -> None:
        self.make_transport()
        path = self.root / operator5.LIFECYCLE
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        extra = self.lifecycle_row(
            "unrelated_event",
            89,
            1,
            rows[-1]["event_sha256"],
            {},
            campaign_id="foreign-campaign",
        )
        path.write_bytes(
            path.read_bytes() + (json.dumps(extra, sort_keys=True) + "\n").encode("utf-8")
        )
        with self.assertRaisesRegex(operator5.OperatorReceiptError, "not terminal"):
            self.build()

    def test_success_boundary_rejects_count_audit_and_dirty_final_state(self) -> None:
        mutations = (
            ("count", lambda details: details.__setitem__("pair_count", 10), "count/sequence"),
            (
                "audit",
                lambda details: details["final_evidence_audit"].pop(),
                "audit count",
            ),
            (
                "dirty state",
                lambda details: details["final_state"].__setitem__(
                    "gpu_lock_exists", True
                ),
                "not exactly clean",
            ),
        )
        for label, mutate, error in mutations:
            with self.subTest(label=label):
                self.make_transport()
                self.mutate_success_terminal(mutate)
                with self.assertRaisesRegex(operator5.OperatorReceiptError, error):
                    self.build()

        self.make_transport()
        raw, lifecycle_snapshot = operator5.snapshot(
            self.root, operator5.LIFECYCLE, "lifecycle"
        )
        lifecycle = operator5.validate_lifecycle(raw, lifecycle_snapshot)
        lifecycle["snapshot"]["row_count"] = 87
        with self.assertRaisesRegex(operator5.OperatorReceiptError, "count/sequence"):
            operator5.validate_success_completion_boundary(lifecycle)

    def test_process_source_and_descriptor_drift_fail_closed(self) -> None:
        self.make_transport()
        argv = operator5.expected_campaign_argv(self.root)
        argv.remove("--resume-attempt-004")
        with self.assertRaisesRegex(operator5.OperatorReceiptError, "process identity"):
            operator5.validate_campaign_process(
                self.root,
                {
                    "authority": "campaign self-observation via psutil",
                    "pid": 123,
                    "process_create_time": datetime(
                        2026, 8, 10, tzinfo=timezone.utc
                    ).timestamp(),
                    "cwd": str(self.root),
                    "invoked_executable": str(operator5.PYTHON),
                    "process_image": str(operator5.PYTHON),
                    "argv": argv,
                },
                captured_pid=123,
                captured_started=datetime(2026, 8, 10, tzinfo=timezone.utc),
            )
        launcher = self.root / operator5.LAUNCHER
        launcher.write_bytes(launcher.read_bytes() + b"# drift\n")
        with self.assertRaisesRegex(operator5.OperatorReceiptError, "source binding"):
            self.build()

        self.make_transport(descriptor_drift=True)
        with self.assertRaisesRegex(operator5.OperatorReceiptError, "descriptor"):
            self.build()

    def test_strict_utc_and_literal_recovery_pins(self) -> None:
        self.make_transport()
        with self.assertRaisesRegex(operator5.OperatorReceiptError, "ISO-8601"):
            self.build(started="not-a-time")
        snapshots = operator5.source_snapshots(self.root)
        self.assertEqual(
            snapshots["attempt4_recovery_recorder"]["sha256"],
            operator5.RECOVERY4_RECORDER_SHA256,
        )
        correction = self.root / operator5.RECOVERY4_RECEIPT
        correction.write_bytes(correction.read_bytes() + b"\n")
        with self.assertRaisesRegex(operator5.OperatorReceiptError, "literal recovery4 pin"):
            operator5.source_snapshots(self.root)

    def test_o_excl_publish_and_prepublication_mutation_guard(self) -> None:
        self.make_transport()
        payload = self.build()
        with operator5.held_coordinator(self.root) as coordinator:
            published = operator5.exclusive_write(
                self.root,
                payload,
                coordinator=coordinator,
                final_payload_builder=self.build,
            )
        receipt_path = self.root / operator5.RECEIPT
        self.assertTrue(receipt_path.exists())
        self.assertEqual(
            published["sha256"], operator5.sha256_bytes(receipt_path.read_bytes())
        )

        with tempfile.TemporaryDirectory() as temp:
            prior_root = self.root
            self.root = Path(temp)
            try:
                self.make_transport()
                candidate = self.build()
                with operator5.held_coordinator(self.root) as coordinator:
                    (self.root / operator5.LAUNCHER).write_bytes(b"mutated\n")
                    with self.assertRaises(operator5.OperatorReceiptError):
                        operator5.exclusive_write(
                            self.root,
                            candidate,
                            coordinator=coordinator,
                            final_payload_builder=self.build,
                        )
                self.assertFalse((self.root / operator5.RECEIPT).exists())
            finally:
                self.root = prior_root

    def test_recorder_has_no_probe_or_process_launch_lane(self) -> None:
        source = RECORDER.read_text(encoding="utf-8")
        self.assertFalse(RECORDER.read_bytes().startswith(b"\xef\xbb\xbf"))
        for forbidden in (
            "subprocess.",
            "psutil.",
            "requests.",
            "urllib.",
            "http://",
            "127.0.0.1",
            "8188",
            "run_recipe.py",
            "os.replace",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("terminal_is_last_row", source)
        self.assertNotIn("listener_pids_8199(", source)


if __name__ == "__main__":
    unittest.main()
