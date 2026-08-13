from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scratch" / "record_h3_music_attempt5_operator_gap_recovery.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "h3_music_attempt5_operator_gap_recovery_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REC = load_module()


class H3MusicAttempt5OperatorGapRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lifecycle_raw = (ROOT / REC.LIFECYCLE).read_bytes()
        # This post-run gap receipt is intentionally already published.  Its
        # only legitimate live state is immutable presence plus the still
        # absent launch.json; rebuilding would violate the O_EXCL boundary.
        raw = (ROOT / REC.RECOVERY).read_bytes()
        if REC.sha256_bytes(raw) != "21abba5bffabd2ad9a49365d488adddd00b4a542955c81fbbfb3a8dff1122289":
            raise AssertionError("published attempt-005 operator-gap receipt drifted")
        cls.payload = json.loads(raw.decode("utf-8"))

    def test_real_evidence_builds_only_a_post_run_capture_gap(self) -> None:
        payload = self.payload
        self.assertEqual(
            payload["receipt_kind"],
            "h3-unconditioned-music-attempt-005-operator-gap-recovery",
        )
        self.assertEqual(payload["status"], "POST_RUN_OPERATOR_CAPTURE_GAP")
        self.assertTrue(payload["launch_receipt_absent"])
        self.assertTrue(payload["exact_process_end_time_unknown"])
        self.assertTrue(payload["exit_code_not_independently_recoverable"])
        self.assertTrue(payload["must_not_substitute_for_launch_receipt"])
        self.assertTrue(payload["no_certification_effect"])
        capture = payload["operator_capture_gap"]
        self.assertFalse(capture["independent_operator_capture_present"])
        self.assertFalse(capture["powershell_start_process_capture_claimed"])
        self.assertIsNone(capture["captured_pid"])
        self.assertIsNone(capture["captured_process_end_time"])
        self.assertIsNone(capture["captured_exit_code"])
        self.assertIsNone(capture["recovered_exit_code"])
        self.assertEqual(
            payload["certification_effect"], REC.NO_CERTIFICATION_EFFECT
        )
        self.assertEqual(payload["certification_effect"]["effect"], "NONE")

    def test_lifecycle_is_exact_complete_terminal_and_hash_chained(self) -> None:
        lifecycle = self.payload["lifecycle"]
        terminal = self.payload["campaign_terminal_evidence"]
        self.assertEqual(lifecycle["row_count"], 88)
        self.assertEqual(lifecycle["attempt_row_count"], 23)
        self.assertEqual(lifecycle["terminal_ledger_sequence"], 88)
        self.assertEqual(lifecycle["terminal_campaign_sequence"], 23)
        self.assertTrue(lifecycle["hash_chain_verified"])
        self.assertTrue(lifecycle["terminal_is_last_row"])
        self.assertEqual(lifecycle["sha256"], REC.LIFECYCLE_SHA256)
        self.assertEqual(terminal["event"], "campaign_completed")
        self.assertEqual(terminal["status"], "COMPLETE")
        self.assertEqual(terminal["success_counts"], REC.SUCCESS_COUNTS)
        self.assertEqual(terminal["final_evidence_audit_count"], 11)
        self.assertEqual(terminal["quality_judgment"], "PENDING_HUMAN")
        self.assertTrue(terminal["verified"])

    def test_all_terminal_files_and_manager_offline_logs_are_rehashed(self) -> None:
        audit = self.payload["terminal_file_audit"]
        self.assertEqual(audit["receipt_count"], 22)
        self.assertEqual(audit["artifact_count"], 22)
        self.assertEqual(audit["manager_log_count"], 11)
        self.assertTrue(audit["all_terminal_receipts_rehashed"])
        self.assertTrue(audit["all_terminal_artifacts_rehashed"])
        self.assertTrue(audit["all_final_manager_logs_rehashed"])
        self.assertTrue(
            audit["all_final_manager_logs_server_reported_offline"]
        )
        self.assertEqual(
            [item["pair_index"] for item in audit["manager_logs"]],
            list(range(1, 12)),
        )
        self.assertTrue(
            all(
                item["server_reported_network_mode"] == "offline"
                and item["status"] == "pass"
                for item in audit["manager_logs"]
            )
        )
        self.assertEqual(
            len({item["path"].lower() for item in audit["receipts"]}), 22
        )
        self.assertEqual(
            len({item["path"].lower() for item in audit["artifacts"]}), 22
        )

    def test_finalized_sources_and_operator_streams_are_exactly_pinned(self) -> None:
        sources = self.payload["finalized_sources"]
        self.assertEqual(sources["lifecycle_snapshot_reference_count"], 33)
        self.assertEqual(sources["unique_source_file_count"], 32)
        self.assertTrue(sources["all_recorded_file_sources_rehashed"])
        self.assertEqual(
            set(sources["literal_finalized_pins"]), set(REC.FINAL_SOURCE_PINS)
        )
        for label, (_path, expected_bytes, expected_sha) in REC.FINAL_SOURCE_PINS.items():
            evidence = sources["literal_finalized_pins"][label]
            self.assertEqual(evidence["bytes"], expected_bytes)
            self.assertEqual(evidence["sha256"], expected_sha)
        streams = self.payload["operator_streams"]
        self.assertEqual(streams["stdout"]["bytes"], REC.STDOUT_BYTES)
        self.assertEqual(streams["stdout"]["sha256"], REC.STDOUT_SHA256)
        self.assertEqual(streams["stderr"]["bytes"], 0)
        self.assertEqual(streams["stderr"]["sha256"], REC.STDERR_SHA256)
        self.assertTrue(
            streams["snapshotted_through_stable_regular_file_descriptors"]
        )
        self.assertTrue(streams["rechecked_by_double_build_before_publication"])

    def test_operator_directory_requires_only_streams_and_launch_absence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / REC.OPERATOR_DIRECTORY
            directory.mkdir(parents=True)
            (directory / "stdout.log").write_bytes(b"complete\n")
            (directory / "stderr.log").write_bytes(b"")
            evidence = REC.validate_attempt_directory(root)
            self.assertEqual(evidence["entries"], ["stderr.log", "stdout.log"])
            self.assertTrue(evidence["launch_receipt_absent"])
            (directory / "launch.json").write_bytes(b"{}\n")
            with self.assertRaisesRegex(REC.OperatorGapError, "entries drifted"):
                REC.validate_attempt_directory(root)

    def test_lifecycle_full_file_pin_and_hash_chain_reject_mutation(self) -> None:
        validated = REC.validate_lifecycle(self.lifecycle_raw)
        self.assertEqual(validated["snapshot"]["row_count"], 88)
        mutated = bytearray(self.lifecycle_raw)
        mutated[-2] ^= 1
        with self.assertRaisesRegex(REC.OperatorGapError, "full-file pin"):
            REC.validate_lifecycle(bytes(mutated))

    def test_default_main_is_read_only_and_does_not_publish(self) -> None:
        destination = ROOT / REC.RECOVERY
        prior = destination.read_bytes()
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            status = REC.main([], root=ROOT)
        self.assertEqual(status, 1)
        self.assertIn("operator-gap recovery receipt must remain absent", stderr.getvalue())
        self.assertEqual(destination.read_bytes(), prior)

    def test_exclusive_writer_is_recovery_scoped_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / REC.RECOVERY.parent).mkdir(parents=True)
            payload = {
                "receipt_kind": "test-only-operator-gap",
                "status": "POST_RUN_OPERATOR_CAPTURE_GAP",
                "must_not_substitute_for_launch_receipt": True,
            }
            coordinator = SimpleNamespace(acquired=True)
            published = REC.exclusive_write(
                root,
                payload,
                coordinator=coordinator,
                final_payload_builder=lambda: dict(payload),
            )
            destination = root / REC.RECOVERY
            raw = destination.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(json.loads(raw), payload)
            self.assertEqual(published["bytes"], len(raw))
            with self.assertRaisesRegex(REC.OperatorGapError, "already exists"):
                REC.exclusive_write(
                    root,
                    {"different": True},
                    coordinator=coordinator,
                    final_payload_builder=lambda: {"different": True},
                )
            self.assertEqual(destination.read_bytes(), raw)
            self.assertFalse((root / REC.OPERATOR_DIRECTORY / "launch.json").exists())

    def test_recorder_has_no_process_server_gpu_port_or_network_query_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.O_CREAT | os.O_EXCL | os.O_WRONLY", source)
        self.assertIn("final_payload_builder=lambda: build_receipt(root)", source)
        self.assertIn("with held_coordinator(Path(root)) as coordinator", source)
        self.assertNotIn("subprocess.", source)
        self.assertNotIn("psutil.", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib.", source)
        self.assertNotIn("socket.", source)
        self.assertNotIn("http://127.0.0.1", source)
        self.assertNotIn("nvidia-smi", source)
        self.assertNotIn("Get-NetTCPConnection", source)
        self.assertNotIn("os.replace", source)
        self.assertNotIn("Remove-Item", source)
        self.assertNotIn("run_recipe.py\", \"--run", source)
        self.assertNotEqual(REC.RECOVERY.parent, REC.OPERATOR_DIRECTORY)
        self.assertEqual(
            REC.RECOVERY.name,
            f"{REC.ATTEMPT_ID}-operator-gap-recovery.json",
        )


if __name__ == "__main__":
    unittest.main()
