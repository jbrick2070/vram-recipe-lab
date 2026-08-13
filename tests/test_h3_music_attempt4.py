from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import record_h3_music_attempt4_operator_launch as operator4
import run_h3_unconditioned_music_campaign as campaign


def clean_state() -> dict[str, object]:
    return {
        "gpu_lock_exists": False,
        "suite_lock_exists": False,
        "server_pid_receipt_exists": False,
        "server_pid_receipt": None,
        "server_pid_create_time": None,
        "queue_quarantine_exists": False,
        "expected_server_identity_live": False,
        "listener_pids_8199": [],
    }


def pair_evidence(prefix: str, identity: dict[str, object]) -> dict[str, object]:
    return {
        "cold": {
            "receipt_sha256": prefix + "1" * 63,
            "artifact": {"sha256": prefix + "2" * 63},
            "run_identity_sha256": prefix + "3" * 63,
            "server_instance": identity,
        },
        "warm": {
            "receipt_sha256": prefix + "4" * 63,
            "artifact": {"sha256": prefix + "5" * 63},
            "run_identity_sha256": prefix + "3" * 63,
            "server_instance": identity,
        },
        "final_manager_log": {"log": {"sha256": prefix + "6" * 63}},
    }


class Attempt4CampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_owner = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_owner.name)
        self.results = self.temp / "results"
        self.outputs = self.temp / "outputs"
        self.results.mkdir()
        self.outputs.mkdir()
        base = campaign.DEFAULT_LAYOUT
        self.layout = campaign.canon.Layout(
            root=ROOT,
            results=self.results,
            outputs=self.outputs,
            lifecycle=(
                self.results
                / "h3_unconditioned_music_campaign"
                / "lifecycle.jsonl"
            ),
            runner=ROOT / "run_recipe.py",
            lab_locks=ROOT / "lab_locks.py",
            boot_cmd=ROOT / "boot_lab_server.cmd",
            actual_manager_config=base.actual_manager_config,
            lab_manager_config=base.lab_manager_config,
            actual_user_directory=base.actual_user_directory,
            comfyui_main=base.comfyui_main,
            python=base.python,
            gpu_lock=self.temp / ".gpu.lock",
            suite_lock=self.temp / ".suite.lock",
            server_pid=self.temp / ".server.pid",
            queue_quarantine=self.temp / ".queue.quarantine.json",
        )

    def tearDown(self) -> None:
        self.temp_owner.cleanup()

    @staticmethod
    def frozen_sources() -> dict[str, object]:
        return {
            "frozen": True,
            "attempt4_operator_launcher": {
                "path": "launcher",
                "bytes": 1,
                "sha256": "7" * 64,
            },
            "attempt4_operator_recorder": {
                "path": "recorder",
                "bytes": 1,
                "sha256": "8" * 64,
            },
        }

    def campaign_process(self) -> dict[str, object]:
        return {
            "authority": "campaign self-observation via psutil",
            "pid": 777,
            "process_create_time": 1_786_400_000.25,
            "cwd": str(self.layout.root),
            "invoked_executable": str(self.layout.python),
            "process_image": str(self.layout.python),
            "argv": campaign.expected_operator_campaign_argv(self.layout),
        }

    def test_attempt4_runbook_carries_pairs_1_and_2_only(self) -> None:
        plan = campaign.runbook(
            campaign.RESUME_ATTEMPT3_CAMPAIGN_ID,
            self.layout,
            resume_attempt_003=True,
        )
        self.assertEqual(plan["pair_count"], 11)
        self.assertEqual(plan["carried_pair_count"], 2)
        self.assertEqual(plan["executed_pair_count"], 9)
        self.assertEqual(plan["new_execution_count"], 18)
        self.assertEqual(
            [row["action"] for row in plan["pairs"]],
            ["carry_forward", "carry_forward"] + ["execute"] * 9,
        )
        self.assertEqual(
            [row["source_campaign_id"] for row in plan["pairs"][:2]],
            [campaign.RESUME_CAMPAIGN_ID, campaign.RESUME_ATTEMPT2_CAMPAIGN_ID],
        )
        nonces: list[str] = []
        logs: list[str] = []
        for expected_index, row in enumerate(plan["pairs"][2:], start=3):
            self.assertEqual(row["pair_index"], expected_index)
            logs.append(row["manager_log"])
            for command in (row["cold"], row["warm_shutdown"]):
                nonce = command[command.index("--executor-cache-nonce") + 1]
                self.assertIn(f":p{expected_index:02d}:", nonce)
                nonces.append(nonce)
        self.assertEqual(len(set(nonces)), 18)
        self.assertFalse(any(":p01:" in nonce or ":p02:" in nonce for nonce in nonces))
        self.assertEqual(len(set(logs)), 9)
        self.assertTrue(
            all(campaign.RESUME_ATTEMPT3_CAMPAIGN_ID in log for log in logs)
        )
        attempt = plan["attempt_004_execution"]
        self.assertIn(
            campaign.RESUME_ATTEMPT3_CAMPAIGN_ID,
            attempt["operator_attempt_directory"],
        )

    def test_published_attempt4_recovery_keeps_historical_sources_and_pairs(self) -> None:
        # The recovery sealed the attempt-004 runner source.  The current
        # runner has advanced, so source_evidence() must not be used to
        # retroactively prove those historical bytes.
        recovery_payload = json.loads(
            campaign.ATTEMPT4_CORRECTED_RECOVERY_RECEIPT.read_text(
                encoding="utf-8"
            )
        )
        sources = recovery_payload["immutable_evidence"]["sources"]
        self.assertEqual(
            sources["runner"]["sha256"], campaign.ATTEMPT4_FROZEN_RUNNER_SHA256
        )
        self.assertEqual(
            sources["attempt4_launcher"]["sha256"],
            campaign.ATTEMPT4_OPERATOR_LAUNCHER_SHA256,
        )
        self.assertNotEqual(
            sources["runner"]["sha256"],
            campaign.sha256_bytes((ROOT / "run_recipe.py").read_bytes()),
        )
        with self.assertRaisesRegex(campaign.CampaignError, "literal source pin drifted: runner"):
            campaign.source_evidence()
        verified = campaign.verify_attempt3_preserved_evidence()
        self.assertEqual(
            verified["recovery3"]["sha256"],
            campaign.ATTEMPT3_RECOVERY_RECEIPT_SHA256,
        )
        self.assertEqual(
            verified["pair1"]["warm"]["receipt_sha256"],
            campaign.ATTEMPT2_RUN3_SHA256,
        )
        self.assertEqual(
            verified["pair2"]["warm"]["receipt_sha256"],
            campaign.ATTEMPT3_PAIR2_WARM_SHA256,
        )

    def test_attempt4_refuses_an_extended_attempt3_start_boundary(self) -> None:
        self.layout.lifecycle.parent.mkdir(parents=True)
        prefix = campaign.LIFECYCLE.read_bytes()[
            : campaign.ATTEMPT3_LIFECYCLE_PREFIX_BYTES
        ]
        self.layout.lifecycle.write_bytes(prefix + b"{}\n")
        with self.assertRaisesRegex(campaign.CampaignError, "immediately after"):
            campaign.verify_attempt3_recovery_receipt(
                {}, clean_state(), self.layout
            )

    def test_attempt4_operator_transport_is_attempt_unique(self) -> None:
        paths = campaign.operator_transport_paths(
            self.layout, campaign.RESUME_ATTEMPT3_CAMPAIGN_ID
        )
        paths["attempt_directory"].mkdir(parents=True)
        sources = self.frozen_sources()
        with paths["stdout"].open("wb", buffering=0) as stdout, paths[
            "stderr"
        ].open("wb", buffering=0) as stderr:
            evidence = campaign.validate_operator_transport(
                paths["stdout"],
                paths["stderr"],
                sources,
                self.layout,
                attempt_id=campaign.RESUME_ATTEMPT3_CAMPAIGN_ID,
                stdout_fd=stdout.fileno(),
                stderr_fd=stderr.fileno(),
            )
        expected = campaign.operator_log_contract(
            sources,
            self.layout,
            attempt_id=campaign.RESUME_ATTEMPT3_CAMPAIGN_ID,
        )
        self.assertEqual(evidence["contract"], expected)
        self.assertEqual(
            expected["launcher_source"]["sha256"],
            sources["attempt4_operator_launcher"]["sha256"],
        )
        self.assertFalse(paths["launch_receipt"].exists())

    def test_campaign_self_report_allows_python_base_image_but_pins_tail(self) -> None:
        value = self.campaign_process()
        base_image = str((self.temp / "base-python.exe").resolve())
        value["process_image"] = base_image
        value["argv"] = [base_image, *value["argv"][1:]]
        self.assertEqual(
            campaign.validate_campaign_process_identity(value, self.layout), value
        )
        value["argv"] = [base_image, *value["argv"][2:]]
        with self.assertRaisesRegex(campaign.CampaignError, "identity drifted"):
            campaign.validate_campaign_process_identity(value, self.layout)

    def test_attempt4_success_carries_two_and_invokes_only_pair3(self) -> None:
        specs = campaign.load_specs(self.layout)[:3]
        identity = {"serving_pid": 321, "process_create_time": 654.25}
        clean = clean_state()
        warm = {
            **clean,
            "server_pid_receipt_exists": True,
            "server_pid_receipt": identity["serving_pid"],
            "server_pid_create_time": identity["process_create_time"],
            "expected_server_identity_live": True,
            "listener_pids_8199": [identity["serving_pid"]],
        }
        pair1 = pair_evidence("a", identity)
        pair2 = pair_evidence("b", identity)
        pair3 = pair_evidence("c", identity)
        preserved = {
            "pair1": pair1,
            "pair2": pair2,
            "recovery3": {"sha256": campaign.ATTEMPT3_RECOVERY_RECEIPT_SHA256},
            "lifecycle": {
                "prefix": {"sha256": campaign.ATTEMPT3_LIFECYCLE_PREFIX_SHA256}
            },
            "attempt3_status": "FAILED",
            "attempt3_ledger_completed_pair_count": 1,
            "human_judgment": "PENDING",
        }
        sources = self.frozen_sources()
        states = iter((clean, clean, warm, clean, clean))
        child_calls: list[list[str]] = []

        def child(command, environment, cwd):
            child_calls.append(list(command))
            return campaign.canon.ChildOutcome(returncode=0)

        def operator_probe(stdout_log, stderr_log, current_sources):
            return {
                "contract": campaign.operator_log_contract(
                    current_sources,
                    self.layout,
                    attempt_id=campaign.RESUME_ATTEMPT3_CAMPAIGN_ID,
                )
            }

        with mock.patch.object(
            campaign, "load_specs", return_value=specs
        ), mock.patch.object(
            campaign, "runbook", return_value={"pairs": []}
        ), mock.patch.object(
            campaign, "source_evidence", return_value=sources
        ), mock.patch.object(
            campaign, "ensure_pristine_pair"
        ), mock.patch.object(
            campaign,
            "verify_attempt3_recovery_receipt",
            return_value=preserved,
        ), mock.patch.object(
            campaign,
            "verify_attempt3_preserved_evidence",
            return_value=preserved,
        ) as preserve_check, mock.patch.object(
            campaign,
            "verify_run_receipt",
            return_value={"server_instance": identity},
        ), mock.patch.object(
            campaign.canon, "require_observed_child_server"
        ), mock.patch.object(
            campaign, "verify_pair", side_effect=(pair3, pair3)
        ) as pair_check:
            result = campaign.execute_campaign(
                campaign_id=campaign.RESUME_ATTEMPT3_CAMPAIGN_ID,
                campaign_layout=self.layout,
                child_runner=child,
                state_probe=lambda expected=None: copy.deepcopy(next(states)),
                cleanup_owned_server=lambda: {"success": True},
                resume_attempt_003=True,
                operator_stdout_log="stdout",
                operator_stderr_log="stderr",
                operator_transport_probe=operator_probe,
                campaign_process_probe=self.campaign_process,
            )

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["carried_pair_count"], 2)
        self.assertEqual(result["new_execution_count"], 18)
        self.assertEqual(len(result["pairs"]), 3)
        self.assertEqual(
            [row.get("status", "EXECUTED") for row in result["pairs"]],
            ["CARRIED_FORWARD", "CARRIED_FORWARD", "EXECUTED"],
        )
        self.assertEqual(len(child_calls), 2)
        self.assertTrue(all(Path(command[2]) == specs[2].path for command in child_calls))
        self.assertTrue(
            all(":p03:" in command[command.index("--executor-cache-nonce") + 1]
                for command in child_calls)
        )
        self.assertEqual(preserve_check.call_count, 5)
        self.assertEqual(pair_check.call_count, 2)

        rows = [
            json.loads(line)
            for line in self.layout.lifecycle.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(rows[-1]["event"], "campaign_completed")
        self.assertEqual(
            [row["disposition"] for row in rows[-1]["details"]["final_evidence_audit"]],
            ["CARRIED_FORWARD", "CARRIED_FORWARD", "EXECUTED"],
        )

    def test_attempt4_first_new_child_failure_preserves_both_carries(self) -> None:
        specs = campaign.load_specs(self.layout)[:3]
        identity = {"serving_pid": 321, "process_create_time": 654.25}
        preserved = {
            "pair1": pair_evidence("a", identity),
            "pair2": pair_evidence("b", identity),
            "recovery3": {"sha256": campaign.ATTEMPT3_RECOVERY_RECEIPT_SHA256},
            "lifecycle": {"prefix": {}},
            "attempt3_status": "FAILED",
            "attempt3_ledger_completed_pair_count": 1,
            "human_judgment": "PENDING",
        }
        sources = self.frozen_sources()
        calls: list[list[str]] = []

        def child(command, environment, cwd):
            calls.append(list(command))
            return campaign.canon.ChildOutcome(returncode=120)

        def operator_probe(stdout_log, stderr_log, current_sources):
            return {
                "contract": campaign.operator_log_contract(
                    current_sources,
                    self.layout,
                    attempt_id=campaign.RESUME_ATTEMPT3_CAMPAIGN_ID,
                )
            }

        with mock.patch.object(
            campaign, "load_specs", return_value=specs
        ), mock.patch.object(
            campaign, "runbook", return_value={"pairs": []}
        ), mock.patch.object(
            campaign, "source_evidence", return_value=sources
        ), mock.patch.object(
            campaign, "ensure_pristine_pair"
        ), mock.patch.object(
            campaign,
            "verify_attempt3_recovery_receipt",
            return_value=preserved,
        ), mock.patch.object(
            campaign,
            "verify_attempt3_preserved_evidence",
            return_value=preserved,
        ):
            with self.assertRaisesRegex(campaign.CampaignError, "returned 120"):
                campaign.execute_campaign(
                    campaign_id=campaign.RESUME_ATTEMPT3_CAMPAIGN_ID,
                    campaign_layout=self.layout,
                    child_runner=child,
                    state_probe=lambda expected=None: copy.deepcopy(clean_state()),
                    cleanup_owned_server=lambda: {"success": True},
                    resume_attempt_003=True,
                    operator_stdout_log="stdout",
                    operator_stderr_log="stderr",
                    operator_transport_probe=operator_probe,
                    campaign_process_probe=self.campaign_process,
                )
        self.assertEqual(len(calls), 1)
        self.assertEqual(Path(calls[0][2]), specs[2].path)
        rows = [
            json.loads(line)
            for line in self.layout.lifecycle.read_text(encoding="utf-8").splitlines()
        ]
        events = [row["event"] for row in rows]
        self.assertEqual(events.count("pair_carried_forward"), 2)
        self.assertLess(events.index("pair_carried_forward"), events.index("pair_started"))
        terminal = rows[-1]
        self.assertEqual(terminal["event"], "campaign_failed")
        self.assertEqual(terminal["details"]["completed_pair_count"], 2)
        self.assertEqual(terminal["details"]["carried_pair_count"], 2)
        self.assertEqual(terminal["details"]["new_verified_pair_count"], 0)


class Attempt4OperatorRecorderTests(unittest.TestCase):
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
        sequence: int,
        previous: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "ledger_sequence": sequence,
            "campaign_id": operator4.ATTEMPT_ID,
            "campaign_sequence": sequence,
            "event": event,
            "previous_event_sha256": previous,
            "details": details,
        }
        return {**body, "event_sha256": operator4.sha256_bytes(operator4.canonical_bytes(body))}

    def make_completed_transport(self) -> None:
        source_raw = {
            "campaign": (ROOT / operator4.CAMPAIGN).read_bytes(),
            "launcher": (ROOT / operator4.LAUNCHER).read_bytes(),
            "recorder": (ROOT / operator4.RECORDER).read_bytes(),
            "coordinator_implementation": (
                ROOT / operator4.COORDINATOR_IMPLEMENTATION
            ).read_bytes(),
        }
        for label, relative in (
            ("campaign", operator4.CAMPAIGN),
            ("launcher", operator4.LAUNCHER),
            ("recorder", operator4.RECORDER),
            (
                "coordinator_implementation",
                operator4.COORDINATOR_IMPLEMENTATION,
            ),
        ):
            self.write(relative, source_raw[label])
        self.write(operator4.STDOUT, b'{"status":"COMPLETE"}\n')
        self.write(operator4.STDERR, b"")
        self.write(Path(".coordinator.mutex"), b"\0")
        snapshots = operator4.source_snapshots(self.root)
        contract = operator4.expected_operator_contract(self.root, snapshots)
        _, stdout_snapshot = operator4.snapshot(
            self.root, operator4.STDOUT, "operator stdout"
        )
        _, stderr_snapshot = operator4.snapshot(
            self.root, operator4.STDERR, "operator stderr"
        )
        preflight = {
            "contract": contract,
            "attempt_directory_entries": ["stderr.log", "stdout.log"],
            "fd_identities": {
                label: {
                    "path": snapshot["path"],
                    "fd": fd,
                    "device": snapshot["device"],
                    "inode": snapshot["inode"],
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
        started = self.lifecycle_row(
            "campaign_started",
            1,
            None,
            {
                "sources": {
                    "campaign": snapshots["campaign"],
                    "attempt4_operator_launcher": snapshots["launcher"],
                    "attempt4_operator_recorder": snapshots["recorder"],
                    "attempt3_recovery_recorder": snapshots[
                        "coordinator_implementation"
                    ],
                },
                "operator_logs": contract,
                "operator_transport_preflight": preflight,
                "campaign_process": {
                    "authority": "campaign self-observation via psutil",
                    "pid": 123,
                    "process_create_time": 1_786_320_000.0,
                    "cwd": str(self.root.resolve()),
                    "invoked_executable": str(operator4.PYTHON),
                    "process_image": str(operator4.PYTHON),
                    "argv": operator4.expected_campaign_argv(self.root),
                },
            },
        )
        terminal = self.lifecycle_row(
            "campaign_completed",
            2,
            started["event_sha256"],
            {"status": "COMPLETE"},
        )
        raw = b"".join(
            (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
            for row in (started, terminal)
        )
        self.write(operator4.LIFECYCLE, raw)

    def test_default_is_read_only(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(operator4.main([], root=self.root), 0)
        self.assertFalse((self.root / operator4.RECEIPT).exists())

    def test_build_binds_sources_logs_terminal_and_o_excl(self) -> None:
        self.make_completed_transport()
        payload = operator4.build_receipt(
            root=self.root,
            pid=123,
            started_at_utc="2026-08-10T00:00:00Z",
            ended_at_utc="2026-08-10T00:00:01Z",
            exit_code=0,
            cwd=self.root,
            stdout_log=self.root / operator4.STDOUT,
            stderr_log=self.root / operator4.STDERR,
        )
        self.assertEqual(payload["attempt_id"], operator4.ATTEMPT_ID)
        self.assertEqual(payload["terminal"]["event"], "campaign_completed")
        self.assertEqual(payload["process"]["exit_code"], 0)
        build = lambda: operator4.build_receipt(
            root=self.root,
            pid=123,
            started_at_utc="2026-08-10T00:00:00Z",
            ended_at_utc="2026-08-10T00:00:01Z",
            exit_code=0,
            cwd=self.root,
            stdout_log=self.root / operator4.STDOUT,
            stderr_log=self.root / operator4.STDERR,
        )
        with operator4.held_coordinator(self.root) as coordinator:
            published = operator4.exclusive_write(
                self.root,
                payload,
                coordinator=coordinator,
                final_payload_builder=build,
            )
        self.assertEqual(
            published["sha256"],
            operator4.sha256_bytes((self.root / operator4.RECEIPT).read_bytes()),
        )
        self.assertTrue((self.root / operator4.RECEIPT).exists())

    def test_mutation_between_build_and_o_excl_fails_before_publication(self) -> None:
        self.make_completed_transport()
        kwargs = {
            "root": self.root,
            "pid": 123,
            "started_at_utc": "2026-08-10T00:00:00Z",
            "ended_at_utc": "2026-08-10T00:00:01Z",
            "exit_code": 0,
            "cwd": self.root,
            "stdout_log": self.root / operator4.STDOUT,
            "stderr_log": self.root / operator4.STDERR,
        }
        with operator4.held_coordinator(self.root) as coordinator:
            payload = operator4.build_receipt(**kwargs)
            (self.root / operator4.CAMPAIGN).write_bytes(b"mutated\n")
            with self.assertRaises(operator4.OperatorReceiptError):
                operator4.exclusive_write(
                    self.root,
                    payload,
                    coordinator=coordinator,
                    final_payload_builder=lambda: operator4.build_receipt(**kwargs),
                )
        self.assertFalse((self.root / operator4.RECEIPT).exists())

    def test_process_capture_must_match_self_report_and_strict_utc(self) -> None:
        self.make_completed_transport()
        common = {
            "root": self.root,
            "pid": 123,
            "started_at_utc": "2026-08-10T00:00:00Z",
            "ended_at_utc": "2026-08-10T00:00:01Z",
            "exit_code": 0,
            "cwd": self.root,
            "stdout_log": self.root / operator4.STDOUT,
            "stderr_log": self.root / operator4.STDERR,
        }
        bad_pid = {**common, "pid": 999_999_999}
        with self.assertRaisesRegex(operator4.OperatorReceiptError, "process identity"):
            operator4.build_receipt(**bad_pid)
        bad_time = {**common, "started_at_utc": "not-a-time"}
        with self.assertRaisesRegex(operator4.OperatorReceiptError, "ISO-8601"):
            operator4.build_receipt(**bad_time)

    def test_coordinator_code_is_loaded_only_from_exact_pinned_bytes(self) -> None:
        recorder_text = (ROOT / operator4.RECORDER).read_text(encoding="utf-8")
        self.assertNotIn("import record_h3_music_attempt3_recovery", recorder_text)
        self.make_completed_transport()
        (self.root / operator4.COORDINATOR_IMPLEMENTATION).write_bytes(b"forged\n")
        with self.assertRaisesRegex(
            operator4.OperatorReceiptError, "implementation pin drifted"
        ):
            with operator4.held_coordinator(self.root):
                self.fail("drifted coordinator implementation was executed")
        self.assertFalse((self.root / operator4.RECEIPT).exists())


if __name__ == "__main__":
    unittest.main()
