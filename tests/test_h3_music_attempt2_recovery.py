from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scratch" / "record_h3_music_attempt2_recovery.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "h3_music_attempt2_recovery_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RECOVERY = load_module()
FIXED_NS = 1_786_334_500_123_456_789


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


def coordinator_evidence():
    return {
        "path": ".coordinator.mutex",
        "carrier_preexisted": True,
        "carrier_bytes": 1,
        "carrier_sha256": RECOVERY.sha256_bytes(b"\0"),
        "acquired_nonblocking": True,
    }


class H3MusicAttempt2RecoveryTests(unittest.TestCase):
    evidence_paths = (
        RECOVERY.LIFECYCLE,
        RECOVERY.RECOVERY1,
        RECOVERY.RUN1,
        RECOVERY.RUN2,
        RECOVERY.RUN3,
        RECOVERY.ALIAS,
        RECOVERY.ATTEMPT2_LOG,
        RECOVERY.ARTIFACT1,
        RECOVERY.ARTIFACT2,
        RECOVERY.ARTIFACT3,
    )
    source_paths = (
        RECOVERY.RECORDER_SOURCE,
        *(pin[0] for pin in RECOVERY.SOURCE_PINS.values()),
    )

    @classmethod
    def setUpClass(cls):
        # Publication intentionally ended the recorder's buildable fixed point:
        # the live campaign source is now attempt-003, while this receipt pins
        # the exact 8aec attempt-002 verifier.  Post-publication tests consume
        # the externally SHA-pinned immutable receipt rather than pretending the
        # one-shot recorder should still run against changed source bytes.
        path = ROOT / RECOVERY.RECOVERY
        raw = path.read_bytes()
        expected_sha = "32a9e9403388d76e190082a04937fb83446b4b3617c0a2178cd4eb673de4911d"
        if RECOVERY.sha256_bytes(raw) != expected_sha:
            raise AssertionError("published recovery-002 receipt SHA drifted")
        cls.payload = json.loads(raw.decode("utf-8"))

    def copy_paths(self, destination: Path, paths) -> None:
        for relative in dict.fromkeys(paths):
            source = ROOT / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == RECOVERY.LIFECYCLE:
                # The live lifecycle is append-only and has advanced past this
                # attempt.  Recovery-002 verifies its sealed 13-row prefix,
                # not the later attempt-003/004/005 rows.
                raw = source.read_bytes()
                frozen = raw[: RECOVERY.LIFECYCLE_BYTES]
                self.assertEqual(len(frozen), RECOVERY.LIFECYCLE_BYTES)
                self.assertEqual(
                    RECOVERY.sha256_bytes(frozen), RECOVERY.LIFECYCLE_SHA256
                )
                target.write_bytes(frozen)
            else:
                shutil.copy2(source, target)

    def test_full_frozen_lifecycle_and_pair_verifier_pass(self):
        lifecycle = self.payload["immutable_evidence"]["lifecycle"]
        self.assertEqual(
            lifecycle["current_prefix"],
            {
                "path": RECOVERY.LIFECYCLE.as_posix(),
                "bytes": 110_592,
                "sha256": RECOVERY.LIFECYCLE_SHA256,
                "row_count": 13,
                "last_event_sha256": RECOVERY.ATTEMPT2_LAST_EVENT_SHA256,
                "hash_chain_verified": True,
            },
        )
        terminal = lifecycle["attempt2_terminal_failure"]
        self.assertEqual(terminal["status"], "FAILED")
        self.assertEqual(terminal["completed_pair_count"], 0)
        self.assertEqual(terminal["warm_child_returncode"], 120)

        verified = self.payload["pair1_machine_verification"]
        self.assertEqual(verified["status"], "RECOVERABLE_COMPLETE")
        self.assertEqual(verified["human_judgment"], "PENDING")
        self.assertFalse(verified["promotion_granted"])
        full = verified["full_final_verifier"]
        self.assertTrue(full["invoked"])
        self.assertTrue(full["returned_without_error"])
        self.assertEqual(full["function"], "verify_pair")
        self.assertEqual(
            full["call"],
            {
                "campaign_id": RECOVERY.ATTEMPT2_ID,
                "pair_index": 1,
                "recipe": RECOVERY.CONTROL_NAME,
                "cold_run_number": 2,
                "cold_config_run_count": 1,
                "warm_run_number": 3,
                "warm_config_run_count": 2,
                "allowed_run_numbers": [1, 2, 3],
                "manager_log": RECOVERY.ATTEMPT2_LOG.as_posix(),
            },
        )
        self.assertEqual(len(full["canonical_result_sha256"]), 64)
        self.assertEqual(
            full["final_manager_log"]["sha256"], RECOVERY.ATTEMPT2_LOG_SHA256
        )
        self.assertEqual(full["final_manager_log"]["execution_marker_count"], 4)

    def test_receipt_keeps_failed_ledger_and_unknown_exit_cause_truthful(self):
        self.assertEqual(
            self.payload["status"], "ATTEMPT_002_FAILED_PAIR1_MACHINE_RECOVERED"
        )
        incident = self.payload["failed_incident"]
        self.assertEqual(incident["error"], RECOVERY.ATTEMPT2_ERROR)
        self.assertEqual(incident["completed_pair_count"], 0)
        cause = incident["exit_120_cause"]
        self.assertEqual(cause["classification"], "UNKNOWN_UNPROVED")
        self.assertFalse(cause["causal_claim_asserted"])
        self.assertFalse(cause["operator_attribution_recorded_here"])
        self.assertIsNone(cause["operator_attribution"])

        certification = self.payload["certification_effect"]
        self.assertEqual(certification["attempt_002_status"], "FAILED")
        self.assertEqual(certification["attempt_002_ledger_completed_pair_count"], 0)
        self.assertTrue(certification["pair1_machine_pair_recoverable_and_complete"])
        self.assertTrue(
            certification["pair1_completion_basis_is_full_final_verifier_only"]
        )
        self.assertEqual(certification["human_judgment"], "PENDING")
        self.assertFalse(certification["promotion_or_study_pass_granted"])

    def test_attempt3_policy_skips_pair1_and_has_exact_twenty_executions(self):
        policy = self.payload["recovery_policy"]
        self.assertEqual(policy["resume_campaign_id"], RECOVERY.ATTEMPT3_ID)
        self.assertEqual(policy["skip_pair_indices"], [1])
        self.assertEqual(policy["next_pair_index"], 2)
        self.assertEqual(policy["remaining_pair_indices"], list(range(2, 12)))
        self.assertEqual(policy["remaining_pair_count"], 10)
        self.assertEqual(policy["executions_per_pair"], 2)
        self.assertEqual(policy["remaining_execution_count"], 20)
        self.assertEqual(
            policy["first_execution"],
            {
                "pair_index": 2,
                "role": "cold",
                "run_number": 1,
                "config_run_count": 1,
            },
        )

    def test_source_set_pins_old_main_and_excludes_future_main(self):
        source_map = self.payload["source_sha256s"]
        self.assertEqual(
            set(source_map), {"recorder", *RECOVERY.SOURCE_PINS.keys()}
        )
        self.assertEqual(
            source_map["attempt2_campaign"]["sha256"],
            "8aec4108559618963b1210ad4a58cdb9d28b55853137746577c4db7da3703e97",
        )
        self.assertEqual(
            source_map["attempt1_recovery_receipt"]["sha256"],
            RECOVERY.RECOVERY1_SHA256,
        )
        self.assertEqual(
            source_map["recorder"]["sha256"],
            RECOVERY.sha256_bytes(SCRIPT.read_bytes()),
        )
        anti = self.payload["anti_circularity"]
        self.assertTrue(anti["exact_attempt_002_campaign_source_included"])
        self.assertFalse(anti["future_attempt_003_main_source_included"])
        self.assertFalse(anti["receipt_is_resume_authority_without_external_sha_pin"])

    def test_every_frozen_evidence_surface_rejects_tampering(self):
        for relative in self.evidence_paths:
            with self.subTest(path=relative.as_posix()):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copy_paths(root, self.evidence_paths)
                    path = root / relative
                    path.write_bytes(path.read_bytes() + b"tamper")
                    with self.assertRaises(RECOVERY.RecoveryError):
                        RECOVERY.collect_immutable_evidence(root)

    def test_every_literal_source_surface_rejects_tampering(self):
        lifecycle_sources = self.payload["immutable_evidence"]["lifecycle"][
            "attempt2_sources"
        ]
        old_main = RECOVERY.SOURCE_PINS["attempt2_campaign"][0]
        with self.assertRaisesRegex(RECOVERY.RecoveryError, "immutable byte count drift"):
            RECOVERY.collect_source_sha256s(ROOT, lifecycle_sources)

        remaining_pins = {
            label: pin
            for label, pin in RECOVERY.SOURCE_PINS.items()
            if label != "attempt2_campaign"
        }
        literal_sources = tuple(pin[0] for pin in remaining_pins.values())
        self.assertNotIn(old_main, literal_sources)
        for relative in literal_sources:
            with self.subTest(path=relative.as_posix()):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copy_paths(root, self.source_paths)
                    path = root / relative
                    path.write_bytes(path.read_bytes() + b"tamper")
                    with mock.patch.object(RECOVERY, "SOURCE_PINS", remaining_pins):
                        with self.assertRaises(RECOVERY.RecoveryError):
                            RECOVERY.collect_source_sha256s(root, lifecycle_sources)

    def test_alias_and_artifacts_must_not_be_hardlinks(self):
        cases = (
            (RECOVERY.ALIAS, RECOVERY.RUN3),
            (RECOVERY.ARTIFACT2, RECOVERY.ARTIFACT3),
        )
        for replaced, source in cases:
            with self.subTest(path=replaced.as_posix()):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copy_paths(root, self.evidence_paths)
                    (root / replaced).unlink()
                    os.link(root / source, root / replaced)
                    self.assertTrue(os.path.samefile(root / source, root / replaced))
                    with self.assertRaisesRegex(
                        RECOVERY.RecoveryError, "hardlinks"
                    ):
                        RECOVERY.collect_immutable_evidence(root)

    def test_full_verifier_failure_refuses_certification(self):
        schedule = RECOVERY._exact_schedule()
        fake_specs = [SimpleNamespace(name=RECOVERY.CONTROL_NAME)] + [
            SimpleNamespace(name=f"unused-{index}") for index in range(2, 12)
        ]
        fake_campaign = SimpleNamespace(
            DEFAULT_LAYOUT=SimpleNamespace(root=ROOT),
            load_specs=lambda _layout: fake_specs,
            pair_run_schedule=lambda _index, _resume: schedule,
            pair_log_path=lambda *_args: ROOT / RECOVERY.ATTEMPT2_LOG,
            verify_pair=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("forced full-verifier failure")
            ),
        )
        lifecycle_sources = self.payload["immutable_evidence"]["lifecycle"][
            "attempt2_sources"
        ]
        with self.assertRaisesRegex(
            RECOVERY.RecoveryError, "full attempt-002 verify_pair did not pass"
        ):
            RECOVERY.invoke_full_pair_verifier(
                ROOT,
                lifecycle_sources,
                campaign_loader=lambda _root: fake_campaign,
            )

    def test_current_clean_state_exact_shape_and_dirty_values_fail_closed(self):
        state = clean_state(ROOT, {})
        RECOVERY.require_clean_state(state)
        for field, value in (
            ("gpu_lock_exists", True),
            ("suite_lock_exists", True),
            ("server_pid_receipt_exists", True),
            ("server_pid_receipt", 6_824),
            ("server_pid_create_time", RECOVERY.PAIR_SERVER_IDENTITY["process_create_time"]),
            ("queue_quarantine_exists", True),
            ("listener_pids_8199", [6_824]),
            ("expected_server_identity_live", True),
        ):
            dirty = dict(state)
            dirty[field] = value
            with self.subTest(field=field):
                with self.assertRaises(RECOVERY.RecoveryError):
                    RECOVERY.require_clean_state(dirty)
        extra = dict(state)
        extra["untrusted_extra"] = False
        with self.assertRaises(RECOVERY.RecoveryError):
            RECOVERY.require_clean_state(extra)
        with self.assertRaisesRegex(RECOVERY.RecoveryError, "under the lab coordinator"):
            RECOVERY.build_receipt(
                ROOT,
                state,
                {"acquired_nonblocking": False},
                recorded_at_ns=FIXED_NS,
            )

    def test_published_recorder_now_refuses_changed_main_without_writing(self):
        destination = ROOT / RECOVERY.RECOVERY
        self.assertTrue(destination.exists())
        receipt_before = destination.read_bytes()
        before = {
            relative: RECOVERY.sha256_bytes((ROOT / relative).read_bytes())
            for relative in self.evidence_paths
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), mock.patch("sys.stderr", stderr):
            status = RECOVERY.main(
                [], root=ROOT, state_probe=clean_state, clock_ns=lambda: FIXED_NS
            )
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("immutable byte count drift", stderr.getvalue())
        self.assertEqual(destination.read_bytes(), receipt_before)
        self.assertEqual(
            before,
            {
                relative: RECOVERY.sha256_bytes((ROOT / relative).read_bytes())
                for relative in self.evidence_paths
            },
        )

    def test_write_is_fixed_o_excl_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RECOVERY.RecoveryError, "pre-existing"):
                RECOVERY.exclusive_write(root, {"recovery_id": "no-parent"})
            self.assertFalse((root / RECOVERY.RECOVERY.parent).exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / RECOVERY.RECOVERY.parent).mkdir(parents=True)
            first = RECOVERY.exclusive_write(root, {"recovery_id": "first"})
            destination = root / RECOVERY.RECOVERY
            frozen = destination.read_bytes()
            self.assertEqual(first["sha256"], RECOVERY.sha256_bytes(frozen))
            self.assertFalse(frozen.startswith(b"\xef\xbb\xbf"))
            with self.assertRaisesRegex(RECOVERY.RecoveryError, "already exists"):
                RECOVERY.exclusive_write(root, {"recovery_id": "second"})
            self.assertEqual(destination.read_bytes(), frozen)

    def test_recorder_exposes_no_boot_query_render_or_network_surface(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.O_CREAT | os.O_EXCL | os.O_WRONLY", source)
        self.assertNotIn("source_evidence(", source)
        for forbidden in (
            "import requests",
            "import urllib",
            "import socket",
            "import subprocess",
            "http://127.0.0.1",
            "run_recipe.shutdown_lab_server",
            '"/prompt"',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
