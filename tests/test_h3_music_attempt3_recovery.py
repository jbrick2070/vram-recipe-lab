import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))

import record_h3_music_attempt3_recovery as recovery


class H3MusicAttempt3RecoveryTests(unittest.TestCase):
    @staticmethod
    def frozen_lifecycle_prefix() -> bytes:
        """Return the immutable attempt-003 prefix from the live ledger."""
        raw = (ROOT / recovery.LIFECYCLE).read_bytes()
        prefix = raw[: recovery.LIFECYCLE_BYTES]
        if len(prefix) != recovery.LIFECYCLE_BYTES or (
            recovery.sha256_bytes(prefix) != recovery.LIFECYCLE_SHA256
        ):
            raise AssertionError("attempt-003 lifecycle prefix SHA drifted")
        return prefix

    @staticmethod
    def published_payload() -> tuple[bytes, dict[str, object]]:
        raw = (ROOT / recovery.RECOVERY).read_bytes()
        if (
            len(raw) != recovery.EXPECTED_RECEIPT_BYTES
            or recovery.sha256_bytes(raw) != recovery.EXPECTED_RECEIPT_SHA256
        ):
            raise AssertionError("published attempt-003 recovery receipt drifted")
        return raw, json.loads(raw.decode("utf-8"))

    def test_published_candidate_is_exact_and_preserved_after_ledger_advance(self):
        # Recovery-003 was published before later attempts appended rows and
        # cleaned up the stale PID receipt.  Re-running its one-shot builder
        # against today's worktree would be a false historical check.
        first_raw, first = self.published_payload()
        self.assertEqual(first_raw, recovery.receipt_bytes(first))
        self.assertEqual(len(first_raw), recovery.EXPECTED_RECEIPT_BYTES)
        self.assertEqual(
            recovery.sha256_bytes(first_raw), recovery.EXPECTED_RECEIPT_SHA256
        )
        self.assertEqual(
            first["status"], "ATTEMPT_003_FAILED_PAIR2_MACHINE_RECOVERED"
        )
        self.assertEqual(
            first["incident_classification"]["classification"],
            "EXPECTED_SERVER_EXITED_STALE_PID_RECEIPT_UNLINK_FAILED",
        )
        self.assertEqual(
            first["recovery_policy"]["carry_pair_indices"], [1, 2]
        )
        self.assertEqual(
            first["recovery_policy"]["execute_pair_indices"], list(range(3, 12))
        )
        pair2 = first["full_pair_verification"]["pair2"]
        self.assertEqual(pair2["canonical_result_sha256"], recovery.PAIR_CANONICAL_SHA256)
        self.assertEqual(pair2["cold_peak_vram_gb"], 7.58)
        self.assertEqual(pair2["warm_peak_vram_gb"], 7.58)
        self.assertEqual(pair2["cold_duration_s"], 902.2)
        self.assertEqual(pair2["warm_duration_s"], 893.0)
        self.assertEqual(pair2["human_judgment"], "PENDING")

    def test_default_main_is_read_only(self):
        destination = ROOT / recovery.RECOVERY
        before = destination.read_bytes()
        carrier = ROOT / recovery.COORDINATOR_MUTEX
        carrier_before = carrier.read_bytes()
        carrier_stat_before = carrier.stat()
        # The stale receipt was intentionally removed later, after the
        # published recovery authorized independent cleanup.  The archived
        # recorder must reject the advanced ledger without recreating it.
        self.assertFalse((ROOT / recovery.STALE_PID).exists())
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            stderr
        ):
            self.assertEqual(recovery.main(["--quiet"], root=ROOT), 1)
        self.assertIn("runner byte-count pin drifted", stderr.getvalue())
        self.assertEqual(destination.read_bytes(), before)
        self.assertFalse((ROOT / recovery.STALE_PID).exists())
        carrier_stat_after = carrier.stat()
        self.assertEqual(carrier.read_bytes(), carrier_before)
        self.assertEqual(carrier_stat_after.st_size, carrier_stat_before.st_size)
        self.assertEqual(carrier_stat_after.st_mtime_ns, carrier_stat_before.st_mtime_ns)

    def test_missing_coordinator_carrier_fails_without_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mutex = recovery.ExistingCoordinatorMutex(root)
            with self.assertRaisesRegex(recovery.RecoveryError, "missing"):
                mutex.acquire()
            self.assertFalse((root / recovery.COORDINATOR_MUTEX).exists())

    def test_lifecycle_validator_rejects_any_byte_change(self):
        raw = self.frozen_lifecycle_prefix()
        verified = recovery.validate_lifecycle(raw)
        self.assertEqual(verified["prefix"]["row_count"], 22)
        forged = bytearray(raw)
        forged[len(forged) // 2] ^= 1
        with self.assertRaisesRegex(recovery.RecoveryError, "full-file pin"):
            recovery.validate_lifecycle(bytes(forged))

    def test_operator_transcript_binds_exact_shutdown_lines(self):
        stdout = (ROOT / recovery.OPERATOR_STDOUT).read_bytes()
        stderr = (ROOT / recovery.OPERATOR_STDERR).read_bytes()
        evidence = recovery.validate_operator_streams(stdout, stderr)
        self.assertEqual(evidence["shutdown_start"]["line_number"], 65)
        self.assertEqual(evidence["receipt_unlink_failure"]["line_number"], 66)
        self.assertIn("WinError 32", evidence["receipt_unlink_failure"]["text"])
        with self.assertRaisesRegex(recovery.RecoveryError, "transcript"):
            recovery.validate_operator_streams(
                stdout.replace(b"WinError 32", b"WinError 33"), stderr
            )

    def test_stale_receipt_is_exact_and_never_removed_by_build(self):
        _raw, payload = self.published_payload()
        snapshot = payload["immutable_evidence"]["stale_pid_receipt"]
        self.assertEqual(snapshot["bytes"], len(recovery.STALE_PID_BYTES))
        self.assertEqual(snapshot["sha256"], recovery.STALE_PID_SHA256)
        self.assertEqual(snapshot["utf8_text"], recovery.STALE_PID_BYTES.decode("ascii"))
        self.assertTrue(snapshot["present_during_recovery_recording"])
        # Its later absence is expected; the receipt preserves the historical
        # bytes and does not authorize reconstructing a stale PID file.
        self.assertFalse((ROOT / recovery.STALE_PID).exists())

    def test_exclusive_write_is_one_shot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {
                "kind": "unit-test-only",
                "stale_receipt_removed": False,
            }
            encoded = recovery.receipt_bytes(payload)
            with mock.patch.object(
                recovery, "EXPECTED_RECEIPT_BYTES", len(encoded)
            ), mock.patch.object(
                recovery,
                "EXPECTED_RECEIPT_SHA256",
                recovery.sha256_bytes(encoded),
            ):
                first = recovery.exclusive_write(
                    root,
                    payload,
                    coordinator=SimpleNamespace(acquired=True),
                    final_payload_builder=lambda: copy.deepcopy(payload),
                )
            destination = root / recovery.RECOVERY
            self.assertTrue(destination.is_file())
            self.assertEqual(destination.read_bytes(), recovery.receipt_bytes(payload))
            self.assertEqual(first["sha256"], recovery.sha256_bytes(destination.read_bytes()))
            with mock.patch.object(
                recovery, "EXPECTED_RECEIPT_BYTES", len(encoded)
            ), mock.patch.object(
                recovery,
                "EXPECTED_RECEIPT_SHA256",
                recovery.sha256_bytes(encoded),
            ):
                with self.assertRaisesRegex(recovery.RecoveryError, "already exists"):
                    recovery.exclusive_write(
                        root,
                        copy.deepcopy(payload),
                        coordinator=SimpleNamespace(acquired=True),
                        final_payload_builder=lambda: copy.deepcopy(payload),
                    )

    def test_publication_rejects_unpinned_payload_before_creating_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = (root / recovery.RECOVERY).parent
            with self.assertRaisesRegex(recovery.RecoveryError, "candidate byte-count"):
                recovery.exclusive_write(
                    root,
                    {"arbitrary": True},
                    coordinator=SimpleNamespace(acquired=True),
                    final_payload_builder=lambda: {"arbitrary": True},
                )
            self.assertFalse(parent.exists())

    def test_publication_final_rehash_mismatch_precedes_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {"candidate": "sealed"}
            encoded = recovery.receipt_bytes(payload)
            with mock.patch.object(
                recovery, "EXPECTED_RECEIPT_BYTES", len(encoded)
            ), mock.patch.object(
                recovery,
                "EXPECTED_RECEIPT_SHA256",
                recovery.sha256_bytes(encoded),
            ):
                with self.assertRaisesRegex(recovery.RecoveryError, "changed before"):
                    recovery.exclusive_write(
                        root,
                        payload,
                        coordinator=SimpleNamespace(acquired=True),
                        final_payload_builder=lambda: {"candidate": "changed"},
                    )
            self.assertFalse((root / recovery.RECOVERY).parent.exists())

    def test_publication_requires_held_coordinator(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(recovery.RecoveryError, "held lab coordinator"):
                recovery.exclusive_write(
                    Path(temporary),
                    {"candidate": "sealed"},
                    coordinator=SimpleNamespace(acquired=False),
                    final_payload_builder=lambda: {"candidate": "sealed"},
                )

    def test_recorder_source_has_no_live_probe_or_cleanup_primitive(self):
        source = Path(recovery.__file__).read_text(encoding="utf-8")
        forbidden = (
            "requests.",
            "urllib.",
            "nvidia-smi",
            "psutil.Process",
            "socket.",
            "unlink(",
            "remove(",
            "shutdown_lab_server",
            "run_recipe.py --",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertNotIn(
            "import run_h3_unconditioned_music_campaign", source
        )
        self.assertIn("sys.dont_write_bytecode = True", source)
        self.assertIn("with held_coordinator(root) as coordinator", source)


if __name__ == "__main__":
    unittest.main()
