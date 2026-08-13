from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
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
SCRIPT = ROOT / "scratch" / "record_h3_music_recovery.py"


def load_module():
    spec = importlib.util.spec_from_file_location("h3_music_recovery_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RECOVERY = load_module()
FIXED_NS = 1_786_330_000_123_456_789


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


class H3MusicRecoveryTests(unittest.TestCase):
    fixture_paths = (
        RECOVERY.LIFECYCLE,
        RECOVERY.RUN1,
        RECOVERY.ALIAS,
        RECOVERY.SERVER_LOG,
        RECOVERY.ARTIFACT,
        *RECOVERY.SOURCE_PATHS.values(),
    )

    def copy_fixture(self, destination: Path) -> None:
        for relative in self.fixture_paths:
            # The live alias legitimately advanced to attempt-002 run3.  This
            # recorder's frozen fixture predates that advance, so reconstruct
            # its already-published input by copying immutable run1 bytes into
            # the alias path instead of weakening the recorder's literal pin.
            source = ROOT / (RECOVERY.RUN1 if relative == RECOVERY.ALIAS else relative)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        (destination / ".coordinator.mutex").write_bytes(b"\0")

    def payload(self, root: Path):
        coordinator = {
            "path": ".coordinator.mutex",
            "carrier_preexisted": True,
            "carrier_bytes": 1,
            "carrier_sha256": RECOVERY.sha256_bytes(b"\0"),
            "acquired_nonblocking": True,
        }
        return RECOVERY.build_receipt(
            root,
            clean_state(root, coordinator),
            coordinator,
            recorded_at_ns=FIXED_NS,
        )

    def test_frozen_attempt_001_evidence_matches_all_literal_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            evidence = RECOVERY.collect_immutable_evidence(root)
        self.assertEqual(
            evidence["lifecycle"]["prefix"],
            {
                "bytes": 28_706,
                "sha256": RECOVERY.LIFECYCLE_PREFIX_SHA256,
                "row_count": 5,
                "last_event_sha256": RECOVERY.LIFECYCLE_LAST_EVENT_SHA256,
            },
        )
        self.assertEqual(evidence["run1_receipt"]["sha256"], RECOVERY.RUN1_SHA256)
        self.assertTrue(evidence["alias"]["byte_equal_to_run1"])
        self.assertEqual(evidence["alias"]["sha256"], RECOVERY.RUN1_SHA256)
        self.assertEqual(evidence["server_log"]["sha256"], RECOVERY.SERVER_LOG_SHA256)
        self.assertEqual(evidence["artifact"]["sha256"], RECOVERY.ARTIFACT_SHA256)
        self.assertEqual(
            evidence["server_identity_from_run1"],
            {
                "serving_pid": 51_136,
                "process_create_time": 1_786_329_027.50907,
            },
        )

    def test_receipt_is_honest_about_failed_cold_only_evidence_and_operator_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            payload = self.payload(root)
        self.assertEqual(payload["recovery_id"], f"{RECOVERY.FAILED_CAMPAIGN_ID}-recovery-001")
        self.assertEqual(payload["recorded_at_ns"], FIXED_NS)
        self.assertEqual(
            payload["failed_incident"]["error"],
            "executor cache field drift: queued_prompt_sha256",
        )
        self.assertEqual(
            payload["failed_incident"]["pending_monitor_errors"],
            RECOVERY.FAILED_PENDING_MONITOR_ERRORS,
        )
        captured = payload["operator_captured_cleanup"]
        self.assertEqual(
            captured["shutdown_lab_server_return"],
            RECOVERY.OPERATOR_CAPTURED_SHUTDOWN,
        )
        self.assertEqual(captured["console_lines"], RECOVERY.OPERATOR_CAPTURED_CONSOLE)
        self.assertIn("operator capture", captured["authority"])
        certification = payload["certification_effect"]
        self.assertEqual(certification["attempt_001_status"], "FAILED")
        self.assertTrue(certification["run1_is_valid_cold_evidence"])
        self.assertFalse(certification["run1_is_warm_evidence"])
        self.assertEqual(certification["completed_pair_count"], 0)
        self.assertFalse(certification["normal_runner_shutdown_proved"])
        self.assertFalse(certification["promotion_or_pass_granted"])

    def test_recovery_policy_requires_fresh_run2_cold_then_immediate_run3_warm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            policy = self.payload(root)["recovery_policy"]
        self.assertEqual(policy["resume_campaign_id"], RECOVERY.RESUME_CAMPAIGN_ID)
        self.assertTrue(policy["preserve_run1_immutable"])
        self.assertTrue(policy["run1_may_not_pair_with_a_later_warm_run"])
        self.assertEqual(
            policy["run2"],
            {
                "run_number": 2,
                "config_run_count": 1,
                "role": "cold",
                "new_server_identity_required": True,
            },
        )
        self.assertEqual(
            policy["run3"],
            {
                "run_number": 3,
                "config_run_count": 2,
                "role": "warm",
                "must_immediately_follow": "run2",
                "same_server_identity_as": "run2",
                "shutdown_required": True,
            },
        )

    def test_current_clean_state_has_exact_canonical_shape_and_fails_closed(self):
        state = clean_state(ROOT, {})
        RECOVERY.require_clean_state(state)
        for field, dirty_value in (
            ("gpu_lock_exists", True),
            ("suite_lock_exists", True),
            ("server_pid_receipt_exists", True),
            ("queue_quarantine_exists", True),
            ("expected_server_identity_live", True),
            ("server_pid_receipt", 51_136),
            ("server_pid_create_time", RECOVERY.SERVER_PROCESS_CREATE_TIME),
            ("listener_pids_8199", [51_136]),
        ):
            dirty = dict(state)
            dirty[field] = dirty_value
            with self.subTest(field=field):
                with self.assertRaises(RECOVERY.RecoveryError):
                    RECOVERY.require_clean_state(dirty)
        extra = dict(state)
        extra["untrusted_extra"] = False
        with self.assertRaises(RECOVERY.RecoveryError):
            RECOVERY.require_clean_state(extra)

    def test_all_frozen_file_tampering_is_rejected(self):
        cases = (
            RECOVERY.LIFECYCLE,
            RECOVERY.RUN1,
            RECOVERY.ALIAS,
            RECOVERY.SERVER_LOG,
            RECOVERY.ARTIFACT,
        )
        for relative in cases:
            with self.subTest(path=relative.as_posix()):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copy_fixture(root)
                    path = root / relative
                    path.write_bytes(path.read_bytes() + b"tamper")
                    with self.assertRaises(RECOVERY.RecoveryError):
                        self.payload(root)

    def test_alias_must_be_a_distinct_file_not_a_hardlink_to_run1(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            alias = root / RECOVERY.ALIAS
            alias.unlink()
            os.link(root / RECOVERY.RUN1, alias)
            self.assertTrue(os.path.samefile(root / RECOVERY.RUN1, alias))
            with self.assertRaisesRegex(RECOVERY.RecoveryError, "same file"):
                self.payload(root)

    def test_source_bindings_avoid_main_campaign_fixed_point(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            payload = self.payload(root)
        self.assertEqual(set(payload["source_sha256s"]), set(RECOVERY.SOURCE_PATHS))
        self.assertNotIn("main_music_campaign", payload["source_sha256s"])
        self.assertFalse(payload["anti_circularity"]["main_music_campaign_source_included"])
        self.assertFalse(
            payload["anti_circularity"]["receipt_is_resume_authority_without_external_sha_pin"]
        )
        for snapshot in payload["source_sha256s"].values():
            self.assertEqual(len(snapshot["sha256"]), 64)
            self.assertGreater(snapshot["bytes"], 0)

    def test_default_cli_is_read_only_and_write_is_o_excl(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            immutable_before = {
                relative: (root / relative).read_bytes()
                for relative in (
                    RECOVERY.LIFECYCLE,
                    RECOVERY.RUN1,
                    RECOVERY.ALIAS,
                    RECOVERY.SERVER_LOG,
                    RECOVERY.ARTIFACT,
                )
            }
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = RECOVERY.main(
                    [], root=root, state_probe=clean_state, clock_ns=lambda: FIXED_NS
                )
            self.assertEqual(status, 0)
            self.assertFalse((root / RECOVERY.RECOVERY).exists())
            proposed = json.loads(stdout.getvalue())
            self.assertEqual(proposed["recorded_at_ns"], FIXED_NS)
            self.assertEqual(
                immutable_before,
                {
                    relative: (root / relative).read_bytes()
                    for relative in immutable_before
                },
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = RECOVERY.main(
                    ["--write"],
                    root=root,
                    state_probe=clean_state,
                    clock_ns=lambda: FIXED_NS,
                )
            self.assertEqual(status, 0)
            destination = root / RECOVERY.RECOVERY
            before = destination.read_bytes()
            self.assertFalse(before.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(json.loads(before.decode("utf-8"))["recovery_id"], RECOVERY.RECOVERY_ID)
            self.assertEqual(
                immutable_before,
                {
                    relative: (root / relative).read_bytes()
                    for relative in immutable_before
                },
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = RECOVERY.main(
                    ["--write"],
                    root=root,
                    state_probe=clean_state,
                    clock_ns=lambda: FIXED_NS + 1,
                )
            self.assertEqual(status, 2)
            self.assertIn("already exists", stderr.getvalue())
            self.assertEqual(destination.read_bytes(), before)

    def test_recorder_has_no_campaign_import_or_remote_io_surface(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.O_CREAT | os.O_EXCL | os.O_WRONLY", source)
        for forbidden in (
            "import run_recipe",
            "import run_h3_canonical_campaign",
            "import run_h3_unconditioned_music_campaign",
            "requests.",
            "urllib.",
            "http://127.0.0.1",
            "/prompt",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
