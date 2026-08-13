from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
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


class Attempt5CampaignTests(unittest.TestCase):
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
                self.results / "h3_unconditioned_music_campaign" / "lifecycle.jsonl"
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
            "runner": {"sha256": campaign.ATTEMPT5_RUNNER_SHA256},
            "attempt4_recovery_recorder": {
                "sha256": campaign.ATTEMPT4_RECOVERY_RECORDER_SHA256
            },
            "attempt4_recovery_receipt": {
                "sha256": campaign.ATTEMPT4_RECOVERY_RECEIPT_SHA256
            },
            "attempt5_operator_launcher": {
                "path": "launcher",
                "bytes": campaign.ATTEMPT5_OPERATOR_LAUNCHER_BYTES,
                "sha256": campaign.ATTEMPT5_OPERATOR_LAUNCHER_SHA256,
            },
            "attempt5_operator_recorder": {
                "path": "recorder",
                "bytes": campaign.ATTEMPT5_OPERATOR_RECORDER_BYTES,
                "sha256": campaign.ATTEMPT5_OPERATOR_RECORDER_SHA256,
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
            "argv": campaign.expected_operator_campaign_argv(
                self.layout, attempt_id=campaign.RESUME_ATTEMPT4_CAMPAIGN_ID
            ),
        }

    def test_runbook_carries_nine_and_schedules_only_four_new_legs(self) -> None:
        plan = campaign.runbook(
            campaign.RESUME_ATTEMPT4_CAMPAIGN_ID,
            self.layout,
            resume_attempt_004=True,
        )
        self.assertEqual(plan["carried_pair_count"], 9)
        self.assertEqual(plan["executed_pair_count"], 2)
        self.assertEqual(plan["new_execution_count"], 4)
        self.assertEqual(plan["failed_historical_execution_count"], 1)
        self.assertEqual(
            [row["action"] for row in plan["pairs"]],
            ["carry_forward"] * 9 + ["execute", "execute"],
        )
        pair10, pair11 = plan["pairs"][9:]
        self.assertEqual(
            pair10["receipt_schedule"]["allowed_run_numbers"], [1, 2, 3]
        )
        self.assertEqual(
            (
                pair10["receipt_schedule"]["cold_artifact_index"],
                pair10["receipt_schedule"]["warm_artifact_index"],
            ),
            (1, 2),
        )
        self.assertEqual(
            pair11["receipt_schedule"]["completion_timeout_s"], 5_400
        )
        commands = [
            pair10["cold"],
            pair10["warm_shutdown"],
            pair11["cold"],
            pair11["warm_shutdown"],
        ]
        self.assertEqual(
            [command[command.index("--completion-timeout-s") + 1] for command in commands],
            ["3600", "3600", "5400", "5400"],
        )
        nonces = [
            command[command.index("--executor-cache-nonce") + 1]
            for command in commands
        ]
        self.assertEqual(len(set(nonces)), 4)

    def test_operator_argv_and_source_keys_are_attempt005_exact(self) -> None:
        # The completed attempt pins its source bundle in the post-run gap
        # receipt.  Today's runner must fail closed instead of being treated
        # as the historical attempt-005 runner.
        gap_recovery = (
            campaign.CAMPAIGN_RESULTS
            / "recoveries"
            / f"{campaign.RESUME_ATTEMPT4_CAMPAIGN_ID}-operator-gap-recovery.json"
        )
        sources = json.loads(gap_recovery.read_text(encoding="utf-8"))["finalized_sources"][
            "literal_finalized_pins"
        ]
        for key in (
            "campaign",
            "attempt5_operator_launcher",
            "attempt5_operator_recorder",
            "attempt4_recovery_recorder",
            "attempt4_recovery_receipt",
        ):
            self.assertIn(key, sources)
        self.assertEqual(sources["runner"]["sha256"], campaign.ATTEMPT5_RUNNER_SHA256)
        self.assertNotEqual(
            sources["runner"]["sha256"],
            campaign.sha256_bytes((ROOT / "run_recipe.py").read_bytes()),
        )
        with self.assertRaisesRegex(campaign.CampaignError, "literal source pin drifted: runner"):
            campaign.source_evidence()
        argv = campaign.expected_operator_campaign_argv(
            self.layout, attempt_id=campaign.RESUME_ATTEMPT4_CAMPAIGN_ID
        )
        self.assertIn("--resume-attempt-004", argv)
        self.assertNotIn("--resume-attempt-003", argv)
        self.assertEqual(
            campaign.validate_campaign_process_identity(
                self.campaign_process(),
                self.layout,
                attempt_id=campaign.RESUME_ATTEMPT4_CAMPAIGN_ID,
            ),
            self.campaign_process(),
        )

    def test_real_corrected_recovery_rehashes_pairs_1_through_9(self) -> None:
        # The strict start-boundary check applies only before attempt-005.
        # Its complete append-only ledger is now the live historical state.
        evidence = campaign.verify_attempt4_preserved_evidence(
            require_initial_history=False
        )
        self.assertEqual(
            evidence["recovery4"]["sha256"],
            campaign.ATTEMPT4_RECOVERY_RECEIPT_SHA256,
        )
        self.assertEqual(sorted(evidence["pairs"]), list(range(1, 10)))
        self.assertFalse(
            evidence["pair10_failed_run1"]["qualifying_study_leg"]
        )

    def test_pair10_pristine_gate_accepts_only_failed_run1_without_output(self) -> None:
        spec = campaign.load_specs(self.layout)[9]
        source = ROOT / "results" / f"{spec.name}_run1.json"
        shutil.copy2(source, self.results / source.name)
        shutil.copy2(source, self.results / f"{spec.name}.json")
        log_path = campaign.pair_log_path(
            spec, 10, campaign.RESUME_ATTEMPT4_CAMPAIGN_ID, self.layout
        )
        campaign.ensure_pristine_pair(
            spec,
            log_path,
            self.layout,
            resume_attempt_004=True,
            pair_index=10,
        )
        (self.outputs / f"{spec.prefix}_00001_.mp4").write_bytes(b"unexpected")
        with self.assertRaisesRegex(campaign.CampaignError, "initial failed history"):
            campaign.ensure_pristine_pair(
                spec,
                log_path,
                self.layout,
                resume_attempt_004=True,
                pair_index=10,
            )

    def test_carried_alias_and_exact_history_reject_mutation_or_extras(self) -> None:
        spec = campaign.load_specs(self.layout)[2]
        schedule = campaign.pair_run_schedule(3, False, False, True, False)
        for number in schedule["allowed_run_numbers"]:
            (self.results / f"{spec.name}_run{number}.json").write_bytes(
                f"receipt-{number}".encode("ascii")
            )
        warm_archive = self.results / f"{spec.name}_run2.json"
        alias = self.results / f"{spec.name}.json"
        alias.write_bytes(warm_archive.read_bytes())
        for number in schedule["allowed_artifact_indices"]:
            (self.outputs / f"{spec.prefix}_{number:05d}_.mp4").write_bytes(
                f"artifact-{number}".encode("ascii")
            )
        campaign._require_alias_matches_archive(alias, warm_archive, "test pair")
        campaign._require_exact_carried_history(spec, schedule, self.layout, 3)
        alias.write_bytes(b"mutated")
        with self.assertRaisesRegex(campaign.CampaignError, "certified warm archive"):
            campaign._require_alias_matches_archive(alias, warm_archive, "test pair")
        alias.write_bytes(warm_archive.read_bytes())
        (self.results / f"{spec.name}_run3.json").write_bytes(b"extra")
        with self.assertRaisesRegex(campaign.CampaignError, "history drifted"):
            campaign._require_exact_carried_history(spec, schedule, self.layout, 3)

    def test_attempt005_manager_log_prefix_is_exact_initial_and_final(self) -> None:
        campaign.require_attempt_manager_log_set(
            campaign.RESUME_ATTEMPT4_CAMPAIGN_ID,
            (),
            self.layout,
            label="initial",
        )
        specs = campaign.load_specs(self.layout)
        expected = (
            campaign.pair_log_path(
                specs[9], 10, campaign.RESUME_ATTEMPT4_CAMPAIGN_ID, self.layout
            ),
            campaign.pair_log_path(
                specs[10], 11, campaign.RESUME_ATTEMPT4_CAMPAIGN_ID, self.layout
            ),
        )
        for path in expected:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        campaign.require_attempt_manager_log_set(
            campaign.RESUME_ATTEMPT4_CAMPAIGN_ID,
            expected,
            self.layout,
            label="final",
        )
        extra = expected[0].parent / (
            f"{campaign.RESUME_ATTEMPT4_CAMPAIGN_ID}-unexpected.log"
        )
        extra.touch()
        with self.assertRaisesRegex(campaign.CampaignError, "log set drifted"):
            campaign.require_attempt_manager_log_set(
                campaign.RESUME_ATTEMPT4_CAMPAIGN_ID,
                expected,
                self.layout,
                label="final",
            )

    def test_execute_attempt005_carries_nine_and_invokes_only_tail(self) -> None:
        specs = campaign.load_specs(self.layout)
        self.layout.lifecycle.parent.mkdir(parents=True, exist_ok=True)
        live_lifecycle = campaign.LIFECYCLE.read_bytes()
        frozen_prefix = live_lifecycle[: campaign.ATTEMPT4_LIFECYCLE_PREFIX_BYTES]
        self.assertEqual(len(frozen_prefix), campaign.ATTEMPT4_LIFECYCLE_PREFIX_BYTES)
        self.assertEqual(
            campaign.sha256_bytes(frozen_prefix), campaign.ATTEMPT4_LIFECYCLE_PREFIX_SHA256
        )
        self.layout.lifecycle.write_bytes(frozen_prefix)
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
        pairs = {
            index: pair_evidence(hex(index)[-1], identity)
            for index in range(1, 10)
        }
        pair10 = pair_evidence("a", identity)
        pair11 = pair_evidence("b", identity)
        recovery4 = {
            "pairs": pairs,
            "pair_sources": {
                index: {
                    "source_campaign_id": (
                        campaign.RESUME_CAMPAIGN_ID
                        if index == 1
                        else (
                            campaign.RESUME_ATTEMPT2_CAMPAIGN_ID
                            if index == 2
                            else campaign.RESUME_ATTEMPT3_CAMPAIGN_ID
                        )
                    ),
                    "manager_log": str(self.temp / f"p{index}.log"),
                    "receipt_schedule": campaign.pair_run_schedule(
                        index, False, False, True, False
                    ),
                }
                for index in range(1, 10)
            },
            "recovery4": {
                "sha256": campaign.ATTEMPT4_RECOVERY_RECEIPT_SHA256
            },
            "lifecycle": {"prefix": {}},
            "attempt4_status": "FAILED",
            "attempt4_ledger_completed_pair_count": 9,
            "carried_pair_count": 9,
            "failed_historical_execution_count": 1,
            "valid_orphan_historical_cold_count": 1,
            "human_judgment": "PENDING_HUMAN",
        }
        sources = self.frozen_sources()
        states = iter((clean, clean, warm, clean, clean, warm, clean, clean))
        child_calls: list[list[str]] = []

        def child(command, environment, cwd):
            child_calls.append(list(command))
            Path(environment["LAB_MANAGER_PROBE_LOG"]).touch(exist_ok=True)
            return campaign.canon.ChildOutcome(returncode=0)

        def operator_probe(stdout_log, stderr_log, current_sources):
            return {
                "contract": campaign.operator_log_contract(
                    current_sources,
                    self.layout,
                    attempt_id=campaign.RESUME_ATTEMPT4_CAMPAIGN_ID,
                )
            }

        with mock.patch.object(
            campaign, "runbook", return_value={"pairs": []}
        ), mock.patch.object(
            campaign, "source_evidence", return_value=sources
        ), mock.patch.object(
            campaign, "ensure_pristine_pair"
        ), mock.patch.object(
            campaign,
            "verify_attempt4_recovery_receipt",
            return_value=recovery4,
        ), mock.patch.object(
            campaign,
            "verify_attempt4_preserved_evidence",
            return_value=recovery4,
        ) as preserve_check, mock.patch.object(
            campaign,
            "verify_run_receipt",
            return_value={"server_instance": identity},
        ), mock.patch.object(
            campaign.canon, "require_observed_child_server"
        ), mock.patch.object(
            campaign,
            "verify_pair",
            side_effect=(pair10, pair11, pair10, pair11),
        ):
            result = campaign.execute_campaign(
                campaign_id=campaign.RESUME_ATTEMPT4_CAMPAIGN_ID,
                campaign_layout=self.layout,
                child_runner=child,
                state_probe=lambda expected=None: copy.deepcopy(next(states)),
                cleanup_owned_server=lambda: {"success": True},
                resume_attempt_004=True,
                operator_stdout_log="stdout",
                operator_stderr_log="stderr",
                operator_transport_probe=operator_probe,
                campaign_process_probe=self.campaign_process,
            )

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["carried_pair_count"], 9)
        self.assertEqual(result["new_execution_count"], 4)
        self.assertEqual(len(child_calls), 4)
        self.assertEqual(
            [Path(command[2]).stem for command in child_calls],
            [specs[9].name, specs[9].name, specs[10].name, specs[10].name],
        )
        self.assertGreaterEqual(preserve_check.call_count, 6)
        rows = [
            json.loads(line)
            for line in self.layout.lifecycle.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(rows[-1]["event"], "campaign_completed")
        self.assertEqual(rows[-1]["ledger_sequence"], 88)
        self.assertEqual(rows[-1]["campaign_sequence"], 23)
        self.assertEqual(rows[-1]["details"]["carried_pair_count"], 9)
        self.assertEqual(rows[-1]["details"]["failed_historical_execution_count"], 1)


if __name__ == "__main__":
    unittest.main()
