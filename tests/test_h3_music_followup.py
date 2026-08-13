from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_h3_music_followup as builder
import run_h3_music_followup_campaign as campaign
import run_recipe


def load_descriptor_wrapper():
    path = SCRATCH / "h3_music_machine_descriptors" / "analyze_manifest.py"
    spec = importlib.util.spec_from_file_location("_test_h3_descriptor_wrapper", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


descriptor = load_descriptor_wrapper()


class H3MusicFollowupTests(unittest.TestCase):
    def test_exact_authorized_order_and_counts(self) -> None:
        specs = builder.followup_specs()
        self.assertEqual(len(specs), 11)
        self.assertEqual([spec.order for spec in specs], list(range(1, 12)))
        self.assertEqual([spec.job for spec in specs], [2] * 5 + [3] * 4 + [4] * 2)
        self.assertEqual([spec.cell for spec in specs[:5]], ["2a", "2b", "2c", "2d", "2e"])
        self.assertEqual([spec.seed for spec in specs[5:9]], [43, 44, 45, 46])
        self.assertEqual([spec.frames for spec in specs[-2:]], [192, 277])
        self.assertEqual([spec.timeout_s for spec in specs[-2:]], [3_600, 5_400])
        self.assertTrue(all(spec.name.startswith("h3_music_followup_") for spec in specs))
        requested_phrases = [
            "warm lighthearted orchestral score",
            "tense orchestral drama score",
            "warm lighthearted orchestral score",
            "tense driving noir strings",
            "playful ragtime piano",
        ]
        for spec, phrase in zip(specs[:5], requested_phrases):
            self.assertIn(phrase, spec.prompt)
            self.assertNotIn("wordless", spec.prompt.lower())

    def test_job1_is_exact_local_schema_rejection_not_runtime_claim(self) -> None:
        finding = builder.job1_structural_finding()
        preflight = finding["compatibility_preflight"]
        self.assertEqual(finding["disposition"], "LOCAL_SCHEMA_REJECTED_NO_RENDER")
        self.assertFalse(finding["exact_pinned_old_recipe_bytes_present"])
        self.assertFalse(finding["execution_authorized"])
        self.assertEqual(finding["job1b_render_leg_count"], 0)
        self.assertEqual(
            preflight["error_verbatim"], builder.EXPECTED_NESTED_REJECTION
        )
        self.assertEqual(
            preflight["status"], "REJECTED_BY_LOCAL_LAB_SCHEMA_VALIDATOR"
        )
        limit = preflight["authority_limit"]
        self.assertIn("No server was booted or queried", limit)
        self.assertIn("not evidence of a node runtime error", limit)

    def test_generated_recipes_are_flat_native_audio_exploratory_singles(self) -> None:
        q4b_prompt = builder.score_prompt()
        for spec in builder.followup_specs():
            recipe = builder.build_recipe(spec)
            inputs = recipe["prompt"]["7"]["inputs"]
            self.assertEqual(inputs["ref_images.ref_image_0"], ["11", 0])
            self.assertNotIn("ref_images", inputs)
            self.assertFalse(any(key.startswith("ref_audios") for key in inputs))
            self.assertEqual(recipe["prompt"]["15"]["inputs"]["samples"], ["8", 0])
            self.assertEqual(recipe["prompt"]["10"]["inputs"]["audio"], ["15", 0])
            followup = recipe["followup"]
            self.assertTrue(followup["exploratory_single_leg"])
            self.assertFalse(followup["warm_certification_claimed"])
            self.assertFalse(followup["conditional_bonus_authorized"])
            self.assertEqual(followup["quality_judgment"], "PENDING_HUMAN")
            self.assertTrue(
                followup["preboot_gpu_idle_gate_required"][
                    "vram_used_recorded_non_gating"
                ]
            )
            self.assertTrue(
                followup["preboot_gpu_idle_gate_required"][
                    "advisory_unreadable_processes_retained_non_gating"
                ]
            )
            self.assertTrue(
                followup["preboot_gpu_idle_gate_required"][
                    "shared_positive_workload_classifier_required"
                ]
            )
            self.assertTrue(
                followup["preboot_gpu_idle_gate_required"][
                    "optional_verified_direct_windows_venv_launcher_exclusion"
                ]
            )
            self.assertEqual(
                followup["preboot_gpu_idle_gate_required"][
                    "windows_venv_launcher_exclusion_max_count"
                ],
                1,
            )
            self.assertTrue(
                followup["preboot_gpu_idle_gate_required"][
                    "display_active_recorded_non_gating"
                ]
            )
            self.assertEqual(
                followup["preboot_gpu_idle_gate_required"][
                    "display_active_allowed_measured_states"
                ],
                ["Disabled", "Enabled"],
            )
            self.assertEqual(
                followup["preboot_gpu_idle_gate_required"][
                    "process_scan_result_fields"
                ],
                ["blocking_processes", "advisory_unreadable_processes"],
            )
            self.assertEqual(
                followup["preboot_gpu_idle_gate_required"][
                    "redacted_process_schema"
                ],
                builder.REDACTED_WORKLOAD_PROCESS_SCHEMA,
            )
            self.assertTrue(
                followup["operator_idle_policy"][
                    "baseline_vram_recorded_advisory"
                ]
            )
            self.assertFalse(
                followup["operator_idle_policy"]["baseline_numeric_rejection"]
            )
            self.assertEqual(
                followup["operator_idle_policy"]["elevated_baseline_stamp"],
                "elevated-baseline lane, operator-authorized 2026-08-10",
            )
            self.assertTrue(
                followup["operator_idle_policy"][
                    "per_leg_immediate_prequeue_known_workload_scan_required"
                ]
            )
            self.assertTrue(
                followup["operator_idle_policy"][
                    "unreadable_unknown_python_advisory_non_gating"
                ]
            )
            operator_policy = followup["operator_idle_policy"]
            self.assertTrue(
                operator_policy[
                    "optional_verified_direct_owned_server_windows_venv_launcher_exclusion"
                ]
            )
            self.assertEqual(
                operator_policy[
                    "owned_server_windows_venv_launcher_exclusion_max_count"
                ],
                1,
            )
            self.assertEqual(
                operator_policy["owned_server_excluded_process_count_allowed"],
                [1, 2],
            )
            self.assertEqual(
                operator_policy["owned_lab_server_exclusion_schema"],
                builder.OWNED_LAB_SERVER_EXCLUSION_SCHEMA,
            )
            self.assertEqual(
                operator_policy[
                    "verified_owned_server_windows_venv_launcher_schema"
                ],
                builder.VERIFIED_OWNED_SERVER_WINDOWS_VENV_LAUNCHER_SCHEMA,
            )
            self.assertEqual(
                operator_policy["excluded_owned_lab_server_row_schema"],
                builder.EXCLUDED_OWNED_LAB_SERVER_ROW_SCHEMA,
            )
            if spec.job == 2:
                self.assertNotIn("wordless", spec.prompt.lower())
            if spec.job in {3, 4}:
                self.assertEqual(spec.prompt, q4b_prompt)

    def test_runner_scope_accepts_only_new_followup_prefix(self) -> None:
        for spec in builder.followup_specs():
            scope = run_recipe.manager_probe_recipe_scope(spec.name)
            self.assertEqual(scope["scope"], "h3-music-followup")
            self.assertEqual(scope["match_type"], "prefix")
            self.assertEqual(scope["match_value"], "h3_music_followup_")

    def test_runbook_is_eleven_single_cold_shutdown_legs(self) -> None:
        runbook = campaign.runbook("unit-test")
        self.assertEqual(runbook["new_render_leg_count"], 11)
        self.assertEqual(runbook["job_counts"], {"job1_render_legs": 0, "job2": 5, "job3": 4, "job4": 2})
        self.assertFalse(runbook["conditional_bonus_implemented"])
        self.assertFalse(runbook["warm_certification_claimed"])
        self.assertEqual(runbook["quality_judgment"], "PENDING_HUMAN")
        self.assertEqual(
            runbook["operator_idle_policy"],
            campaign.expected_operator_idle_policy(),
        )
        for leg in runbook["ordered_legs"]:
            argv = leg["argv"]
            self.assertIn("--shutdown", argv)
            self.assertIn("--manager-offline-test", argv)
            phase = argv.index("--manager-probe-phase")
            self.assertEqual(argv[phase + 1], "cold")
            self.assertIn("--completion-timeout-s", argv)
            self.assertNotIn("--force", argv)
            self.assertNotIn("--suite", argv)
            self.assertTrue(leg["exploratory_single_cold_leg"])
            self.assertTrue(leg["shutdown_in_same_child"])
        self.assertEqual([leg["job"] for leg in runbook["ordered_legs"][-2:]], [4, 4])

    def test_skip_job4_is_explicit_nine_leg_plan(self) -> None:
        runbook = campaign.runbook("unit-test-skip", skip_job4=True)
        self.assertEqual(runbook["new_render_leg_count"], 9)
        self.assertEqual(runbook["job_counts"]["job4"], 0)
        self.assertTrue(all(leg["job"] in {2, 3} for leg in runbook["ordered_legs"]))

    def test_child_environment_is_offline_and_scrubbed(self) -> None:
        source = {
            "HF_API_TOKEN": "secret",
            "HUGGINGFACE_HUB_TOKEN": "secret",
            "LAB_EXTRA_WHITELIST": "unsafe",
            "LAB_SUITE_NONCE": "unsafe",
        }
        log = campaign.SERVER_LOGS / "unit.log"
        environment = campaign.child_environment(log, source)
        self.assertNotIn("HF_API_TOKEN", environment)
        self.assertNotIn("HUGGINGFACE_HUB_TOKEN", environment)
        self.assertNotIn("LAB_EXTRA_WHITELIST", environment)
        self.assertNotIn("LAB_SUITE_NONCE", environment)
        self.assertEqual(environment["LAB_RESERVE_VRAM_GB"], "12")
        self.assertEqual(environment["LAB_CACHE_CLASSIC"], "1")
        self.assertEqual(environment["LAB_MANAGER_PROBE_LOG"], str(log.resolve()))
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")

    def test_coordinator_has_no_child_termination_surface(self) -> None:
        source = (SCRATCH / "run_h3_music_followup_campaign.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(".terminate(", source)
        self.assertNotIn(".kill(", source)
        self.assertNotIn("subprocess.TimeoutExpired", source)
        self.assertIn("returncode = process.wait()", source)
        for spec in builder.followup_specs():
            argv = campaign.child_command("unit-timeout", spec)
            position = argv.index("--completion-timeout-s")
            self.assertEqual(argv[position + 1], str(spec.timeout_s))

    def test_clean_state_ignores_persistent_mutex_but_requires_idle_sidecar_absent(self) -> None:
        clean = {
            "gpu_lock_exists": False,
            "suite_lock_exists": False,
            "server_pid_receipt_exists": False,
            "server_idle_gate_receipt_exists": False,
            "queue_quarantine_exists": False,
            "listeners_8199": [],
        }
        campaign.require_clean_state(clean, "unit")
        dirty = dict(clean)
        dirty["server_idle_gate_receipt_exists"] = True
        with self.assertRaises(campaign.CampaignError):
            campaign.require_clean_state(dirty, "unit")
        source = (SCRATCH / "run_h3_music_followup_campaign.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"coordinator_mutex_exists"', source)

    def test_finalized_runner_idle_contract_and_sidecar_binding_are_pinned(self) -> None:
        # The follow-up receipts bind the historical 85a... runner contract.
        # The current runner intentionally has a newer, stricter 6d6... idle
        # policy, so it must not be mistaken for the historical bundle.
        historical_receipt = json.loads(
            (
                ROOT
                / "results"
                / "h3_music_followup_mood_dim_lighthearted_seed42_f124_run1.json"
            ).read_text(encoding="utf-8")
        )
        historical_contract = historical_receipt["preboot_gpu_idle_gate_contract"]
        self.assertEqual(
            historical_contract["collector"]["sha256"],
            historical_receipt["runner_sha256"],
        )
        self.assertEqual(
            historical_contract["policy"]["advisory_vram_used_mib"], 3072.0
        )
        self.assertFalse(
            historical_contract["policy"]["vram_used_mib_threshold_gating"]
        )
        contract = run_recipe.gpu_idle_gate_contract()
        self.assertEqual(contract["sample_count"], 5)
        self.assertEqual(contract["sampling_interval_s"], 0.2)
        self.assertEqual(contract["policy"]["maximum_vram_used_mib"], 3072.0)
        self.assertTrue(contract["policy"]["vram_used_mib_threshold_gating"])
        self.assertNotEqual(
            contract["collector"]["sha256"], historical_contract["collector"]["sha256"]
        )
        self.assertTrue(contract["policy"]["gpu_utilization_recorded_non_gating"])
        self.assertTrue(
            contract["policy"]["desktop_graphics_signals_retained_but_not_required"]
        )
        self.assertEqual(
            contract["policy"]["display_active_allowed_measured_states"],
            ["Disabled", "Enabled"],
        )
        self.assertTrue(contract["policy"]["display_active_recorded_non_gating"])
        self.assertNotIn("required_display_active", contract["policy"])
        self.assertEqual(
            contract["policy"]["known_workload_classifier"],
            campaign.expected_known_workload_classifier_contract(),
        )
        current_operator_policy = run_recipe.operator_idle_policy_contract()
        self.assertEqual(current_operator_policy["preboot_baseline_maximum_mib"], 3072.0)
        self.assertTrue(current_operator_policy["preboot_baseline_threshold_gating"])
        self.assertNotEqual(
            current_operator_policy,
            campaign.expected_operator_idle_policy(),
        )
        self.assertEqual(
            contract["collector"]["sha256"], campaign.sha256_file(ROOT / "run_recipe.py")
        )
        server = {"serving_pid": 123, "process_create_time": 456.25}
        gate = {"evidence_sha256": "a" * 64, "server_instance": server}
        raw = (
            json.dumps(
                gate,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        snapshot = {
            "path": str(campaign.DEFAULT_LAYOUT.server_idle_gate.resolve()),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "identity": [1, 2, stat.S_IFREG | 0o600, 1, len(raw), 3],
            "evidence_sha256": gate["evidence_sha256"],
            "server_instance": server,
        }
        receipt = {"preboot_gpu_idle_gate_sidecar": snapshot, "identity": {}}
        self.assertEqual(
            campaign.verify_idle_gate_sidecar_receipt(
                receipt, gate, server, campaign.DEFAULT_LAYOUT
            ),
            snapshot,
        )
        drifted = json.loads(json.dumps(receipt))
        drifted["preboot_gpu_idle_gate_sidecar"]["sha256"] = "0" * 64
        with self.assertRaises(campaign.CampaignError):
            campaign.verify_idle_gate_sidecar_receipt(
                drifted, gate, server, campaign.DEFAULT_LAYOUT
            )
        argv = campaign.expected_server_argv(campaign.DEFAULT_LAYOUT)
        scan_contract = run_recipe.prequeue_known_workload_scan_contract()
        scan_body = {
            "schema_version": 1,
            "kind": "per-leg-immediate-prequeue-known-workload-scan",
            "status": "clean",
            "scan_ran": True,
            "sampled_at_ns": 1,
            "sampled_at_utc": "2026-08-10T00:00:00Z",
            "completed_at_ns": 2,
            "contract": scan_contract,
            "server_instance": server,
            "server_argv": argv,
            "listener_pid_before": 123,
            "listener_pid_after": 123,
            "current_runner_exclusion": {
                "pid": 999,
                "process_create_time": 1234.25,
                "resolved_runner_path": str((ROOT / "run_recipe.py").resolve()),
                "narrowly_verified": True,
                "excluded_pid_only": True,
                "process_identity": {
                    "pid": 999,
                    "exists": True,
                    "name": "python.exe",
                    "executable": str(campaign.PYTHON),
                    "command_line": [
                        str(campaign.PYTHON),
                        str((ROOT / "run_recipe.py").resolve()),
                    ],
                    "process_create_time": 1234.25,
                    "identity_errors": [],
                },
                "verified_windows_venv_launcher": None,
                "expected_excluded_process_count": 1,
            },
            "owned_lab_server_exclusion": {
                "pid": 123,
                "process_create_time": 456.25,
                "server_instance": server,
                "process_identity": {
                    "pid": 123,
                    "exists": True,
                    "name": "python.exe",
                    "executable": str(campaign.PYTHON),
                    "command_line": list(argv),
                    "process_create_time": 456.25,
                    "identity_errors": [],
                },
                "narrowly_verified": True,
                "excluded_pid_only": True,
                "argv_match": {
                    "matches": True,
                    "match_mode": "exact-self-reported-argv",
                    "actual_argv": list(argv),
                    "reported_server_argv": list(argv),
                },
                "verified_windows_venv_launcher": None,
                "expected_excluded_process_count": 1,
            },
            "scanned_process_count": 2,
            "excluded_current_runner": [
                {
                    "pid": 999,
                    "process_create_time": 1234.25,
                    "reason": "exact current run_recipe process",
                }
            ],
            "excluded_owned_lab_server": [
                {
                    "pid": 123,
                    "process_create_time": 456.25,
                    "reason": "exact owned port-8199 server PID/create-time/argv",
                }
            ],
            "blocking_processes": [],
            "advisory_unreadable_processes": [
                {
                    "pid": 777,
                    "process_create_time": None,
                    "process_basename": "python.exe",
                    "executable_basename": None,
                    "target_basename": None,
                    "matched_markers": [],
                    "match_basis": [
                        "advisory_python_without_positive_marker"
                    ],
                    "argv_sha256": "5" * 64,
                }
            ],
            "scan_errors": [],
        }
        scan = {
            **scan_body,
            "evidence_sha256": run_recipe.stable_identity(scan_body),
        }
        scan_receipt = {
            "prequeue_known_workload_scan_contract": scan_contract,
            "prequeue_known_workload_scan": scan,
            "identity": {
                "prequeue_known_workload_scan_contract": scan_contract
            },
        }
        self.assertEqual(
            campaign.verify_prequeue_known_workload_scan(
                scan_receipt, run_recipe, server, argv
            ),
            scan,
        )
        launcher_receipt = json.loads(json.dumps(scan_receipt))
        launcher_scan = launcher_receipt["prequeue_known_workload_scan"]
        current = launcher_scan["current_runner_exclusion"]
        launcher_path = str(
            (Path(sys.prefix).resolve() / "Scripts" / "python.exe").resolve()
        )
        current["process_identity"]["executable"] = str(
            Path(getattr(sys, "_base_executable", sys.executable)).resolve()
        )
        launcher_identity = {
            "pid": 998,
            "exists": True,
            "name": "python.exe",
            "executable": launcher_path,
            "command_line": [
                launcher_path,
                str((ROOT / "run_recipe.py").resolve()),
            ],
            "process_create_time": 1234.0,
            "identity_errors": [],
        }
        current["verified_windows_venv_launcher"] = {
            "pid": 998,
            "process_create_time": 1234.0,
            "expected_launcher_path": launcher_path,
            "direct_child_pid": 999,
            "direct_parent_verified": True,
            "launcher_identity_live": True,
            "child_identity_live": True,
            "argv_tail_matches_child": True,
            "both_exact_runner_target": True,
            "child_executable_differs": True,
            "creation_delta_s": 0.25,
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": launcher_identity,
        }
        current["expected_excluded_process_count"] = 2
        launcher_scan["scanned_process_count"] = 3
        launcher_scan["excluded_current_runner"].append(
            {
                "pid": 998,
                "process_create_time": 1234.0,
                "reason": "exact verified direct Windows venv launcher stub",
            }
        )
        launcher_scan.pop("evidence_sha256")
        launcher_scan["evidence_sha256"] = run_recipe.stable_identity(
            launcher_scan
        )
        self.assertEqual(
            campaign.verify_prequeue_known_workload_scan(
                launcher_receipt, run_recipe, server, argv
            ),
            launcher_scan,
        )
        forged_launcher = json.loads(json.dumps(launcher_receipt))
        forged_launcher["prequeue_known_workload_scan"][
            "current_runner_exclusion"
        ]["verified_windows_venv_launcher"]["direct_parent_verified"] = False
        forged_body = forged_launcher["prequeue_known_workload_scan"]
        forged_body.pop("evidence_sha256")
        forged_body["evidence_sha256"] = run_recipe.stable_identity(forged_body)
        with self.assertRaises(campaign.CampaignError):
            campaign.verify_prequeue_known_workload_scan(
                forged_launcher, run_recipe, server, argv
            )
        owned_launcher_receipt = json.loads(json.dumps(scan_receipt))
        owned_launcher_scan = owned_launcher_receipt[
            "prequeue_known_workload_scan"
        ]
        owned = owned_launcher_scan["owned_lab_server_exclusion"]
        owned["process_identity"]["executable"] = str(
            Path(getattr(sys, "_base_executable", sys.executable)).resolve()
        )
        owned_launcher_identity = {
            "pid": 122,
            "exists": True,
            "name": "python.exe",
            "executable": launcher_path,
            "command_line": list(argv),
            "process_create_time": 456.0,
            "identity_errors": [],
        }
        owned_launcher_argv_match = {
            "matches": True,
            "match_mode": "exact-self-reported-argv",
            "actual_argv": list(argv),
            "reported_server_argv": list(argv),
        }
        owned["verified_windows_venv_launcher"] = {
            "pid": 122,
            "process_create_time": 456.0,
            "expected_launcher_path": launcher_path,
            "direct_child_pid": 123,
            "direct_parent_verified": True,
            "launcher_identity_live": True,
            "child_identity_live": True,
            "argv_tail_matches_child": True,
            "both_exact_validated_server_argv": True,
            "child_executable_differs": True,
            "creation_delta_s": 0.25,
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": owned_launcher_identity,
            "argv_match": owned_launcher_argv_match,
        }
        owned["expected_excluded_process_count"] = 2
        owned_launcher_scan["scanned_process_count"] = 3
        owned_launcher_scan["excluded_owned_lab_server"].append(
            {
                "pid": 122,
                "process_create_time": 456.0,
                "reason": (
                    "exact verified direct Windows venv owned-server launcher stub"
                ),
            }
        )
        owned_launcher_scan.pop("evidence_sha256")
        owned_launcher_scan["evidence_sha256"] = run_recipe.stable_identity(
            owned_launcher_scan
        )
        self.assertEqual(
            campaign.verify_prequeue_known_workload_scan(
                owned_launcher_receipt, run_recipe, server, argv
            ),
            owned_launcher_scan,
        )
        forged_owned_launcher = json.loads(json.dumps(owned_launcher_receipt))
        forged_owned_scan = forged_owned_launcher[
            "prequeue_known_workload_scan"
        ]
        forged_owned_scan["owned_lab_server_exclusion"][
            "verified_windows_venv_launcher"
        ]["argv_tail_matches_child"] = False
        forged_owned_scan.pop("evidence_sha256")
        forged_owned_scan["evidence_sha256"] = run_recipe.stable_identity(
            forged_owned_scan
        )
        with self.assertRaises(campaign.CampaignError):
            campaign.verify_prequeue_known_workload_scan(
                forged_owned_launcher, run_recipe, server, argv
            )
        tampered_scan = json.loads(json.dumps(scan_receipt))
        tampered_scan["prequeue_known_workload_scan"]["listener_pid_after"] = 999
        with self.assertRaises(campaign.CampaignError):
            campaign.verify_prequeue_known_workload_scan(
                tampered_scan, run_recipe, server, argv
            )
        misclassified_scan = json.loads(json.dumps(scan_receipt))
        advisory = misclassified_scan["prequeue_known_workload_scan"][
            "advisory_unreadable_processes"
        ][0]
        advisory["matched_markers"] = ["main.py"]
        advisory["match_basis"] = ["python_script_target"]
        body = dict(misclassified_scan["prequeue_known_workload_scan"])
        body.pop("evidence_sha256")
        misclassified_scan["prequeue_known_workload_scan"][
            "evidence_sha256"
        ] = run_recipe.stable_identity(body)
        with self.assertRaises(campaign.CampaignError):
            campaign.verify_prequeue_known_workload_scan(
                misclassified_scan, run_recipe, server, argv
            )
        source = (SCRATCH / "run_h3_music_followup_campaign.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("gpu_idle_gate_validation_errors", source)
        self.assertIn("stable_identity(identity)", source)

    def test_single_leg_operator_idle_metrics_enforce_stamp_and_net(self) -> None:
        policy = campaign.expected_operator_idle_policy()
        elevated = {
            "baseline_vram_gb": 2.57,
            "peak_vram_gb": 12.34,
            "absolute_peak_vram_gb": 12.34,
            "net_peak_vram_gb": 9.77,
            "elevated_baseline_lane": True,
            "baseline_lane_stamp": (
                "elevated-baseline lane, operator-authorized 2026-08-10"
            ),
            "operator_idle_policy": policy,
            "identity": {"operator_idle_policy": policy},
            "vram_measurement": {
                "units": "GiB (nvidia-smi MiB / 1024)",
                "baseline_measurement_point": (
                    "immediately before prompt queue; includes owned lab server "
                    "and desktop load"
                ),
                "baseline_absolute_gib": 2.57,
                "peak_absolute_gib": 12.34,
                "net_peak_gib": 9.77,
                "net_peak_formula": "peak_vram_gb - baseline_vram_gb",
            },
            "baseline_advisory": {
                "schema_version": 1,
                "kind": "per-leg-prequeue-baseline-advisory",
                "baseline_vram_gb": 2.57,
                "advisory_threshold_gb": 3.0,
                "threshold_exceeded": False,
                "gating": False,
                "disposition": "record-only; proceed regardless of baseline",
            },
            "cold_warm_baseline_drift_advisory": {
                "schema_version": 1,
                "kind": "same-identity-cold-warm-baseline-drift-advisory",
                "applicable": False,
                "measurement_available": False,
                "previous_baseline_vram_gb": None,
                "current_baseline_vram_gb": 2.57,
                "absolute_drift_gb": None,
                "advisory_threshold_gb": 0.5,
                "threshold_exceeded": False,
                "gating": False,
                "disposition": "record-only; no same-identity prior leg",
            },
        }
        self.assertEqual(
            campaign.verify_operator_idle_measurement(elevated, "unit")[
                "net_peak_vram_gb"
            ],
            9.77,
        )
        for field, value in (
            ("net_peak_vram_gb", 9.76),
            ("elevated_baseline_lane", False),
            ("baseline_lane_stamp", None),
        ):
            with self.subTest(field=field):
                tampered = json.loads(json.dumps(elevated))
                tampered[field] = value
                with self.assertRaises(campaign.CampaignError):
                    campaign.verify_operator_idle_measurement(tampered, "unit")

        high_baseline = json.loads(json.dumps(elevated))
        high_baseline.update(
            {"baseline_vram_gb": 3.01, "net_peak_vram_gb": 9.33}
        )
        high_baseline["vram_measurement"].update(
            {"baseline_absolute_gib": 3.01, "net_peak_gib": 9.33}
        )
        high_baseline["baseline_advisory"].update(
            {"baseline_vram_gb": 3.01, "threshold_exceeded": True}
        )
        high_baseline["cold_warm_baseline_drift_advisory"].update(
            {"current_baseline_vram_gb": 3.01}
        )
        campaign.verify_operator_idle_measurement(high_baseline, "unit")

        ordinary = json.loads(json.dumps(elevated))
        ordinary.update(
            {
                "baseline_vram_gb": 2.0,
                "net_peak_vram_gb": 10.34,
                "elevated_baseline_lane": False,
                "baseline_lane_stamp": None,
            }
        )
        ordinary["vram_measurement"].update(
            {"baseline_absolute_gib": 2.0, "net_peak_gib": 10.34}
        )
        ordinary["baseline_advisory"].update(
            {"baseline_vram_gb": 2.0, "threshold_exceeded": False}
        )
        ordinary["cold_warm_baseline_drift_advisory"].update(
            {"current_baseline_vram_gb": 2.0}
        )
        campaign.verify_operator_idle_measurement(ordinary, "unit")
        source = (SCRATCH / "run_h3_music_followup_campaign.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"absolute_peak_vram_gb"', source)
        self.assertIn('"net_peak_vram_gb"', source)

    def test_manifest_structure_is_closed_and_pending_human(self) -> None:
        digest = "0" * 64
        payload = {
            "schema_version": 1,
            "quality_judgment": "PENDING_HUMAN",
            "clips": [
                {
                    "label": "J2-2a",
                    "filename": "h3_music_followup_x_out_00001_.mp4",
                    "recipe": "h3_music_followup_x",
                    "sha256": digest,
                    "recipe_sha256": digest,
                    "receipt_sha256": digest,
                    "receipt_path": "results/h3_music_followup_x_run1.json",
                }
            ],
        }
        clips = descriptor.validate_manifest_structure(payload)
        self.assertEqual(len(clips), 1)
        rejected = json.loads(json.dumps(payload))
        rejected["quality_judgment"] = "machine-approved"
        with self.assertRaises(descriptor.ManifestError):
            descriptor.validate_manifest_structure(rejected)
        rejected = json.loads(json.dumps(payload))
        rejected["clips"][0]["recipe"] = "h3_unconditioned_music_old"
        with self.assertRaises(descriptor.ManifestError):
            descriptor.validate_manifest_structure(rejected)

    def test_lifecycle_is_hash_chained_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lifecycle.jsonl"
            ledger = campaign.AppendOnlyLifecycle(path, "unit")
            first = ledger.append("campaign_started", {"value": 1})
            second = ledger.append("leg_completed", {"recipe": "x"})
            self.assertEqual(second["previous_event_sha256"], first["event_sha256"])
            replay = campaign.AppendOnlyLifecycle(path, "unit")
            self.assertEqual(len(replay.events), 2)
            raw = path.read_bytes().replace(b'"value":1', b'"value":2', 1)
            path.write_bytes(raw)
            with self.assertRaises(campaign.CampaignError):
                campaign.AppendOnlyLifecycle(path, "unit")

    def test_terminal_report_keeps_machine_and_human_boundaries_explicit(self) -> None:
        report = (ROOT / "docs" / "H3_MUSIC_FOLLOWUP.md").read_text(encoding="utf-8")
        self.assertIn("Status: **TERMINAL - MACHINE-GATE FAILURE ON THE FINAL LEG**", report)
        self.assertIn(builder.EXPECTED_NESTED_REJECTION, report)
        self.assertIn("It is not a MiniMax node runtime error", report)
        self.assertIn("14.722 GiB absolute", report)
        self.assertIn("peak and the coordinator terminated", report)
        self.assertIn("No warm certification, production", report)
        self.assertIn("promotion, dropdown entry", report)
        self.assertIn("PENDING_HUMAN", report)
        self.assertIn("No production,", report)


if __name__ == "__main__":
    unittest.main()
