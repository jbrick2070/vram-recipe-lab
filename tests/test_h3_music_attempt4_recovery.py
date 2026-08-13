from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scratch" / "record_h3_music_attempt4_recovery.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "h3_music_attempt4_recovery_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REC = load_module()


class H3MusicAttempt4RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        live_lifecycle = (ROOT / REC.LIFECYCLE).read_bytes()
        cls.lifecycle_raw = live_lifecycle[: REC.LIFECYCLE_BYTES]
        if (
            len(cls.lifecycle_raw) != REC.LIFECYCLE_BYTES
            or REC.sha256_bytes(cls.lifecycle_raw) != REC.LIFECYCLE_SHA256
        ):
            raise AssertionError("attempt-004 lifecycle prefix SHA drifted")
        cls.superseded_raw = (ROOT / REC.SUPERSEDED_RECOVERY).read_bytes()
        # Attempt-005 has legitimately appended to the live ledger and this
        # one-shot correction was published.  Consume the sealed receipt,
        # rather than attempting to rebuild an historical prefix from today.
        raw = (ROOT / REC.RECOVERY).read_bytes()
        if REC.sha256_bytes(raw) != "fef1ef0401b5e4f13dc11b7405224e6b792a1a18c3b607fce806468f598f7dcd":
            raise AssertionError("published attempt-004 correction receipt drifted")
        cls.payload = json.loads(raw.decode("utf-8"))

    def test_real_evidence_validates_pairs_1_through_9_and_exact_tail(self) -> None:
        payload = self.payload
        self.assertEqual(payload["failed_campaign_id"], REC.ATTEMPT_ID)
        self.assertEqual(payload["resume_campaign_id"], REC.RESUME_ID)
        self.assertEqual(payload["recovery_id"], REC.RECOVERY_ID)
        superseded = payload["immutable_evidence"]["superseded_recovery"]
        self.assertEqual(superseded["classification"], "UNUSABLE_RESUME_AUTHORITY")
        self.assertEqual(
            superseded["snapshot"]["sha256"],
            "a76d05fb4d0d01afa90b705ba654af6c8b56344bd93478e653fa9a3146e1f88f",
        )
        self.assertEqual(
            superseded["exact_error"],
            {
                "field": "recovery_policy.pair11.recipe",
                "recorded": REC.ERRONEOUS_PAIR11,
                "required": REC.PAIR11,
            },
        )
        lifecycle = payload["immutable_evidence"]["lifecycle"]
        self.assertEqual(lifecycle["prefix"]["row_count"], 65)
        self.assertEqual(lifecycle["prefix"]["bytes"], 1_513_119)
        self.assertEqual(
            lifecycle["prefix"]["last_event_sha256"],
            REC.LIFECYCLE_LAST_EVENT_SHA256,
        )
        terminal = lifecycle["terminal_failure"]
        self.assertEqual(terminal["completed_pair_count"], 9)
        self.assertEqual(terminal["failure_state"], REC.CLEAN_STATE)

        pairs = payload["full_pair_verification"]
        self.assertEqual([pair["pair_index"] for pair in pairs], list(range(1, 10)))
        self.assertTrue(all(pair["status"] == "MACHINE_COMPLETE" for pair in pairs))
        self.assertEqual(
            {pair["pair_index"]: pair["canonical_result_sha256"] for pair in pairs},
            REC.PAIR_RESULT_SHA256S,
        )

        failed = payload["immutable_evidence"]["pair10_failed_run1"]
        self.assertFalse(failed["classification"]["artifact_finalized"])
        self.assertFalse(failed["classification"]["qualifying_cold_leg"])
        self.assertEqual(failed["classification"]["sampling_steps_completed"], 20)
        self.assertEqual(
            failed["receipt"]["sha256"],
            "4ab72334bc80d8155d1b1d1466258922a7a9e1ad2e289f37b07a510115d164bf",
        )
        self.assertTrue(
            payload["immutable_evidence"]["operator_streams"]
            ["launch_receipt_absent"]["absent"]
        )
        self.assertEqual(
            payload["canonical_unfinished_specs"][1],
            {
                "pair_index": 11,
                "recipe": "h3_unconditioned_music_scene_seed42_f277",
                "recipe_sha256": REC.PAIR11_RECIPE_SHA256,
                "frames": 277,
            },
        )

    def test_policy_authorizes_attempt005_and_exactly_four_new_legs(self) -> None:
        policy = REC.recovery_policy()
        self.assertEqual(policy["resume_campaign_id"], REC.RESUME_ID)
        self.assertEqual(policy["carry_pair_indices"], list(range(1, 10)))
        self.assertEqual(policy["execute_pair_indices"], [10, 11])
        self.assertEqual(policy["new_leg_count"], 4)
        self.assertEqual(
            (policy["pair10"]["cold_run_number"], policy["pair10"]["warm_run_number"]),
            (2, 3),
        )
        self.assertEqual(
            (policy["pair11"]["cold_run_number"], policy["pair11"]["warm_run_number"]),
            (1, 2),
        )
        self.assertEqual(policy["pair11"]["recipe"], REC.PAIR11)
        self.assertNotEqual(policy["pair11"]["recipe"], REC.ERRONEOUS_PAIR11)
        absent_paths = {path.as_posix() for path in REC.ABSENT_PATHS}
        self.assertIn(f"results/{REC.PAIR11}_run1.json", absent_paths)
        self.assertFalse(any(REC.ERRONEOUS_PAIR11 in path for path in absent_paths))
        self.assertTrue(policy["all_other_pair_execution_forbidden"])
        self.assertTrue(policy["attempt004_run1_must_not_be_reclassified_or_overwritten"])

    def test_lifecycle_full_file_pin_rejects_any_mutation(self) -> None:
        lifecycle = REC.validate_lifecycle(self.lifecycle_raw)
        self.assertEqual(lifecycle["prefix"]["row_count"], 65)
        mutated = bytearray(self.lifecycle_raw)
        mutated[-2] ^= 1
        with self.assertRaisesRegex(REC.RecoveryError, "full-file pin"):
            REC.validate_lifecycle(bytes(mutated))

    def test_default_main_is_read_only(self) -> None:
        destination = ROOT / REC.RECOVERY
        superseded = ROOT / REC.SUPERSEDED_RECOVERY
        prior_destination = destination.read_bytes()
        prior = superseded.read_bytes()
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            status = REC.main(["--quiet"], root=ROOT)
        self.assertEqual(status, 1)
        self.assertIn("immutable byte/SHA pin drifted: attempt-004 lifecycle", stderr.getvalue())
        self.assertEqual(destination.read_bytes(), prior_destination)
        self.assertEqual(superseded.read_bytes(), prior)

    def test_superseded_receipt_is_exactly_pinned_and_unusable(self) -> None:
        classification = REC.validate_superseded_recovery(self.superseded_raw)
        self.assertTrue(classification["must_not_authorize_render"])
        self.assertTrue(classification["must_not_be_deleted_or_overwritten"])
        mutated = bytearray(self.superseded_raw)
        mutated[-2] ^= 1
        with self.assertRaises(REC.RecoveryError):
            REC.validate_superseded_recovery(bytes(mutated))

    def test_exclusive_writer_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / REC.COORDINATOR_MUTEX).write_bytes(b"\0")
            payload = {
                "receipt_kind": "test-only",
                "resume_campaign_id": REC.RESUME_ID,
            }
            with REC.held_coordinator(root) as coordinator:
                published = REC.exclusive_write(
                    root, payload, coordinator=coordinator
                )
                raw = (root / REC.RECOVERY).read_bytes()
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertEqual(json.loads(raw), payload)
                self.assertEqual(published["bytes"], len(raw))
                with self.assertRaisesRegex(REC.RecoveryError, "already exists"):
                    REC.exclusive_write(
                        root, {"different": True}, coordinator=coordinator
                    )
            self.assertEqual((root / REC.RECOVERY).read_bytes(), raw)

    def test_absence_gate_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative = Path("outputs/forbidden.mp4")
            self.assertTrue(REC.require_absent(root, relative)["absent"])
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(b"unexpected")
            with self.assertRaisesRegex(REC.RecoveryError, "expected absent"):
                REC.require_absent(root, relative)

    def test_recorder_has_no_render_process_server_or_overwrite_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.O_CREAT | os.O_EXCL | os.O_WRONLY", source)
        self.assertIn('self.path.open("r+b", buffering=0)', source)
        self.assertIn("with held_coordinator(root) as coordinator", source)
        self.assertNotIn("subprocess.", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib.", source)
        self.assertNotIn("http://127.0.0.1", source)
        self.assertNotIn("psutil.", source)
        self.assertNotIn("os.replace", source)
        self.assertNotIn("Remove-Item", source)
        self.assertNotIn("run_recipe.py\", \"--run", source)


if __name__ == "__main__":
    unittest.main()
