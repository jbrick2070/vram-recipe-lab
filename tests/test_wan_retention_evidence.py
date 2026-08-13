from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scratch" / "build_wan_retention_evidence.py"
SPEC = importlib.util.spec_from_file_location("build_wan_retention_evidence", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)

INVALID_ATTEMPT = (
    ROOT
    / "results"
    / "otr_side"
    / "wan_retention"
    / "telemetry"
    / "phase1_wan_ti2v_long_first.json"
)
VALID_PHASE1 = (
    ROOT
    / "results"
    / "otr_side"
    / "wan_retention"
    / "telemetry"
    / "phase1_wan_ti2v_long_first_planned.json"
)
PHASE3_BUNDLE_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\output\otr\episodes\_shared"
    r"\wan_retention_measurement"
)


def event(text: str, observed_ns: int) -> dict:
    return {
        "text": text,
        "observed_at_ns": observed_ns,
        "observed_at_utc": f"synthetic-{observed_ns}",
        "start_offset": observed_ns * 10,
        "end_offset": observed_ns * 10 + len(text.encode("utf-8")),
        "raw_sha256": hashlib.sha256((text + "\n").encode("utf-8")).hexdigest(),
    }


class WanRetentionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipts, cls.comparison = evidence.build(ROOT)
        cls.phase1 = cls.receipts["phase1_wan_ti2v_long_first"]

    def test_build_is_deterministic_and_current_outputs_are_exact(self):
        receipts2, comparison2 = evidence.build(ROOT)
        self.assertEqual(
            evidence.canonical_json_bytes(self.comparison),
            evidence.canonical_json_bytes(comparison2),
        )
        self.assertEqual(set(self.receipts), set(receipts2))
        expected = evidence.expected_outputs(ROOT)
        for path, payload in expected.items():
            with self.subTest(path=path):
                self.assertEqual(path.read_bytes(), payload)

    def test_pre_render_attempt_is_rejected_and_cannot_mint_a_leg(self):
        key, receipt, audit = evidence.audit_attempt(ROOT, INVALID_ATTEMPT)
        self.assertIsNone(key)
        self.assertIsNone(receipt)
        self.assertFalse(audit["accepted"])
        self.assertIn("pre-render refusal attempt", audit["reason"])
        invalid_sha = hashlib.sha256(INVALID_ATTEMPT.read_bytes()).hexdigest()
        self.assertEqual(audit["source"]["sha256"], invalid_sha)

    def test_phase1_proves_chain_then_exact_s4_refusal(self):
        proof = self.phase1["topology_proof"]
        self.assertTrue(proof["long_chain_200_completed"])
        self.assertFalse(proof["small_65_completed"])
        self.assertEqual(proof["render_phase_count"], 2)
        refusal = proof["no_silent_resize_refusal"]
        self.assertEqual(refusal["shot_id"], "shot_b003")
        self.assertEqual(refusal["requested_frames"], 65)
        self.assertEqual(refusal["snapped_frames"], 65)
        self.assertEqual(refusal["affordable_frames"], 20)
        self.assertEqual(refusal["free_mb_reported_by_cost_model"], 9665)

    def test_phase1_metrics_are_recomputed_from_raw_200ms_samples(self):
        metrics = self.phase1["metrics"]
        self.assertEqual(metrics["sampler_interval_s"], 0.2)
        self.assertEqual(metrics["baseline"]["vram_used_mib"], 1179.0)
        self.assertEqual(
            metrics["whole_child_window"]["peak_vram"]["vram_used_mib"],
            12727.0,
        )
        self.assertEqual(metrics["inter_shot_boundary"]["vram_used_mib"], 6411.0)
        self.assertEqual(
            metrics["inter_shot_boundary"]["retained_above_start_baseline_gib"],
            5.109375,
        )
        self.assertEqual(
            [segment["sidecar_200ms"]["peak_vram"]["vram_used_mib"] for segment in metrics["render_segments"]],
            [9023.0, 12727.0],
        )
        self.assertEqual(
            [segment["wrapper_logged_post_mb"] for segment in metrics["render_segments"]],
            [6725, 8102],
        )
        self.assertEqual(metrics["post_terminal_cleanup_window"]["last"]["vram_used_mib"], 1291.0)

    def test_sidecar_and_wrapper_memory_surfaces_remain_separate(self):
        metrics = self.phase1["metrics"]
        self.assertEqual(metrics["render_segments"][1]["wrapper_logged_post_mb"], 8102)
        self.assertEqual(metrics["inter_shot_boundary"]["vram_used_mib"], 6411.0)
        self.assertIn("different measurement surface", self.phase1["interpretation_guardrail"])
        self.assertNotEqual(
            metrics["render_segments"][1]["wrapper_logged_post_mb"],
            metrics["inter_shot_boundary"]["vram_used_mib"],
        )

    def test_raw_event_hash_tamper_is_rejected(self):
        raw = json.loads(VALID_PHASE1.read_text(encoding="utf-8"))
        tampered = copy.deepcopy(raw)
        tampered["server_log"]["events"][0]["raw_sha256"] = "0" * 64
        with self.assertRaisesRegex(evidence.EvidenceError, "event 0 SHA drift"):
            evidence.validate_raw_envelope(tampered)

    def test_reproduction_flags_are_not_trusted(self):
        raw = json.loads(VALID_PHASE1.read_text(encoding="utf-8"))
        raw["retention_reproduction_evidence"]["long_chain_200_proved"] = False
        with self.assertRaisesRegex(evidence.EvidenceError, "flag disagrees"):
            evidence.validate_leg(ROOT, VALID_PHASE1, raw_override=raw)

    def test_small_first_success_requires_small_then_two_long_peaks(self):
        raw = {
            "engine": "wan_ti2v",
            "observed_outcome": "success",
            "command_returncode": 0,
            "server_log": {
                "events": [
                    event("[gpu_residency] lease acquired", 1),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 10 MB / post 5 MB", 2),
                    event("[gpu_residency] lease acquired", 3),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 11 MB / post 6 MB", 4),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 12 MB / post 7 MB", 5),
                    event("[OTR video] BEAT shot_b001 assembled from 2 chain segment(s) -> 200 frame(s)", 6),
                    event("Prompt executed in 1.0 seconds", 7),
                ]
            },
        }
        topology = evidence.validate_topology(raw, "small_then_long")
        self.assertTrue(topology["completed_small"])
        self.assertTrue(topology["completed_long"])
        self.assertEqual(
            len(topology["shot_peak_slices"][evidence.SMALL_SHOT_ID]), 1
        )
        self.assertEqual(
            len(topology["shot_peak_slices"][evidence.LONG_SHOT_ID]), 2
        )

    def test_small_first_wrong_order_is_rejected(self):
        raw = {
            "engine": "wan_ti2v",
            "observed_outcome": "success",
            "command_returncode": 0,
            "server_log": {
                "events": [
                    event("[gpu_residency] lease acquired", 1),
                    event("[gpu_residency] lease acquired", 2),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 10 MB / post 5 MB", 3),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 11 MB / post 6 MB", 4),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 12 MB / post 7 MB", 5),
                    event("[OTR video] BEAT shot_b001 assembled from 2 chain segment(s) -> 200 frame(s)", 6),
                    event("Prompt executed in 1.0 seconds", 7),
                ]
            },
        }
        with self.assertRaisesRegex(evidence.EvidenceError, "small-first render order drift"):
            evidence.validate_topology(raw, "small_then_long")

    def test_source_binding_is_commit_pinned_but_truthfully_caveated(self):
        binding = self.phase1["source_binding"]
        self.assertRegex(binding["otr_head_at_fixture_build"], r"^[0-9a-f]{40}$")
        self.assertEqual(binding["worktree_at_render"], "NOT_CAPTURED")
        self.assertIn("not proof", binding["caveat"])
        self.assertEqual(set(binding["committed_sources"]), set(evidence.OTR_SOURCE_PATHS))
        for source in binding["committed_sources"].values():
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(source["bytes"], 0)

    def test_engine_is_ledger_bound_and_force_map_label_is_not_trusted(self):
        fixture = self.phase1["fixture_contract"]
        self.assertEqual(fixture["ledger_engine_ids"], ["wan_ti2v"])
        self.assertEqual(
            fixture["engine_authority"],
            "baked_ledger.video.shots[*].engine_id",
        )
        self.assertEqual(
            fixture["sidecar_force_map_status"],
            "LEGACY_INCORRECT_DECLARATIVE_LABEL_NOT_SERVER_ENV_PROOF",
        )
        self.assertIn("did not inspect", self.phase1["engine_binding_caveat"])
        binding = fixture["raw_sidecar_source_binding"]
        self.assertEqual(
            binding["status"],
            "LEGACY_EXTERNAL_BINDING_ARCHIVED_IN_LAB_EVIDENCE",
        )
        self.assertEqual(
            binding["path"],
            "results/otr_side/wan_retention/evidence/wan_retention_sidecar_phase1_phase4_v1.py",
        )
        self.assertEqual(binding["sha256"], evidence.LEGACY_RAW_SIDECAR_SHA256)
        self.assertEqual(
            evidence.sha256_file(ROOT / binding["path"]),
            binding["sha256"],
        )

    def test_phase3_sidecar_self_hash_is_explicitly_unarchived(self):
        historical_sha256 = (
            "13e7fdcd735ba2db44aeac680955287f6387efe9734287293df572fe0d93bf62"
        )
        for key in (
            "phase3_fastwan_8gb_long_first",
            "phase3_ltx_video_long_first",
        ):
            binding = self.receipts[key]["fixture_contract"]["raw_sidecar_source_binding"]
            self.assertEqual(binding["status"], "EMBEDDED_SELF_HASH")
            self.assertEqual(binding["sha256"], historical_sha256)
            self.assertIn("does not archive the source bytes", binding["caveat"])
        self.assertNotEqual(
            evidence.sha256_file(ROOT / "scratch" / "wan_retention_sidecar.py"),
            historical_sha256,
        )

    def test_ltx_topology_can_be_proved_without_wan_only_peak_logs(self):
        raw = {
            "engine": "ltx_video",
            "observed_outcome": "success",
            "command_returncode": 0,
            "server_log": {
                "events": [
                    event("[gpu_residency] lease acquired", 1),
                    event("[eng_ltx_video] LTX-I2V: conditioning on init image a.png (832x480, length 169)", 2),
                    event("[eng_ltx_video] LTX-I2V: conditioning on init image b.png (832x480, length 169)", 3),
                    event("[OTR video] BEAT shot_b001 assembled from 2 chain segment(s) -> 200 frame(s)", 4),
                    event("[gpu_residency] lease acquired", 5),
                    event("[eng_ltx_video] LTX-I2V: conditioning on init image c.png (832x480, length 169)", 6),
                    event("[OTR video] BEAT shot_b003 assembled from 1 single segment(s) -> 65 frame(s)", 7),
                    event("Prompt executed in 1.0 seconds", 8),
                ]
            },
        }
        topology = evidence.validate_topology(raw, "long_then_small")
        self.assertTrue(topology["completed_long"])
        self.assertTrue(topology["completed_small"])
        self.assertEqual(topology["peaks"], [])

    def test_fastwan_inherited_wan_peak_label_is_explicitly_accepted(self):
        raw = {
            "engine": "fastwan_8gb",
            "observed_outcome": "success",
            "command_returncode": 0,
            "server_log": {
                "events": [
                    event("[gpu_residency] lease acquired", 1),
                    event("[OTR_DMDRestart] marker=aa transition=restart", 2),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 10 MB / post 5 MB", 3),
                    event("[OTR_DMDRestart] marker=bb transition=restart", 4),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 11 MB / post 6 MB", 5),
                    event("[OTR video] BEAT shot_b001 assembled from 2 chain segment(s) -> 200 frame(s)", 6),
                    event("[gpu_residency] lease acquired", 7),
                    event("[OTR_DMDRestart] marker=cc transition=restart", 8),
                    event("[OTR video] wan_ti2v VRAM render-phase peak 12 MB / post 7 MB", 9),
                    event("Prompt executed in 1.0 seconds", 10),
                ]
            },
        }
        topology = evidence.validate_topology(raw, "long_then_small")
        self.assertEqual(len(topology["peaks"]), 3)

    def test_engine_specific_legal_plans_preserve_delivered_targets(self):
        wan_long, wan_small = evidence.engine_plans("wan_ti2v")
        ltx_long, ltx_small = evidence.engine_plans("ltx_video")
        self.assertEqual(sum(s["render_frames"] - s["drop_head"] - s["trim_tail"] for s in wan_long), 200)
        self.assertEqual(sum(s["render_frames"] - s["drop_head"] - s["trim_tail"] for s in wan_small), 65)
        self.assertEqual(sum(s["render_frames"] - s["drop_head"] - s["trim_tail"] for s in ltx_long), 200)
        self.assertEqual(sum(s["render_frames"] - s["drop_head"] - s["trim_tail"] for s in ltx_small), 65)

    def test_phase3_engine_fixtures_normalize_to_the_same_control_origin(self):
        normalized_rows = []
        for engine in ("fastwan_8gb", "ltx_video"):
            bundle = PHASE3_BUNDLE_ROOT / f"{engine}_long_first_planned"
            contract = evidence.read_json(bundle / "fixture_contract.json")
            command = {
                "bundle": str(bundle),
                "fixture_contract_sha256": evidence.sha256_file(bundle / "fixture_contract.json"),
                "bundle_manifest_sha256": evidence.sha256_file(bundle / "bundle_manifest.json"),
                "baked_ledger_sha256": evidence.sha256_file(bundle / "baked_ledger.json"),
                "master_audio_sha256": evidence.sha256_file(bundle / "master.wav"),
                "otr_harness_sha256": contract["source_sha256s"]["otr_visual_smoke.py"],
            }
            _contract, _manifest, ledger, _refs, normalized = evidence.validate_bundle(
                {"engine": engine, "command": command}
            )
            normalized_rows.append(normalized)
            self.assertEqual(
                {shot["engine_id"] for shot in ledger["video"]["shots"]},
                {engine},
            )
            self.assertEqual(
                normalized["contract_class"],
                "phase3_cross_engine_neutral_diagnostic",
            )
        self.assertEqual(
            normalized_rows[0]["control_origin_ledger_sha256"],
            normalized_rows[1]["control_origin_ledger_sha256"],
        )
        self.assertEqual(
            normalized_rows[0]["source_capture_sha256"],
            normalized_rows[1]["source_capture_sha256"],
        )

    def test_historical_numbers_never_become_a_measured_row(self):
        historical = self.comparison["historical_context"]
        self.assertEqual(
            historical["evidence_class"],
            "HISTORICAL_WRAPPER_LOG_ONLY_NOT_SIDECAR_MEASURED",
        )
        self.assertEqual(
            [segment["wrapper_logged_peak_mb"] for segment in historical["segments"]],
            [10874, 13134],
        )
        self.assertEqual(
            [segment["wrapper_logged_post_mb"] for segment in historical["segments"]],
            [8206, 8190],
        )
        self.assertEqual(historical["follow_on_refusal"]["affordable_frames"], 19)
        self.assertNotIn("measured", historical)

    def test_unrun_legs_are_pending_not_inferred(self):
        required = self.comparison["required_legs"]
        self.assertEqual(required["phase1_wan_ti2v_long_first"]["status"], "MEASURED")
        for key in evidence.REQUIRED_LEGS:
            expected = "MEASURED" if key in self.receipts else "PENDING"
            self.assertEqual(required[key]["status"], expected)
        self.assertEqual(
            self.comparison["complete"],
            set(self.receipts) == set(evidence.REQUIRED_LEGS),
        )

    def test_all_four_legs_are_complete_with_disclosed_offline_incidents(self):
        self.assertEqual(set(self.receipts), set(evidence.REQUIRED_LEGS))
        self.assertTrue(self.comparison["complete"])
        self.assertEqual(
            self.comparison["completion_status"],
            "MEASUREMENT_COMPLETE_WITH_OFFLINE_POLICY_INCIDENT",
        )
        offline = self.comparison["offline_policy"]
        self.assertEqual(offline["status"], "INCIDENT")
        self.assertEqual(
            set(offline["incident_legs"]),
            {
                "phase3_fastwan_8gb_long_first",
                "phase3_ltx_video_long_first",
                "phase4_wan_ti2v_small_first",
            },
        )
        self.assertFalse(offline["model_weight_download_observed_in_appended_logs"])
        self.assertNotIn("LTX production-server", offline["caveat"])
        self.assertNotIn(
            "LTX production server",
            self.receipts["phase4_wan_ti2v_small_first"]["offline_policy"]["caveat"],
        )
        fastwan_incidents = self.receipts["phase3_fastwan_8gb_long_first"]["offline_policy"][
            "observed_incidents"
        ]
        registry_fetches = [
            item for item in fastwan_incidents if item["classification"] == "COMFY_REGISTRY_PAGED_FETCH"
        ]
        self.assertTrue(registry_fetches)
        self.assertEqual(registry_fetches[0]["event"]["event_index"], 0)
        self.assertEqual(
            registry_fetches[0]["endpoint_source_binding"]["sha256"],
            evidence.COMFY_REGISTRY_SOURCE_SHA256,
        )

    def test_phase3_cross_engine_outcomes_are_measured_not_profile_equivalent(self):
        outcome = self.comparison["cross_engine_outcome"]
        self.assertEqual(outcome["status"], "MEASURED")
        self.assertEqual(
            outcome["result"],
            "REFUSAL_OBSERVED_ONLY_IN_WAN_FAMILY_IN_THIS_MEASURED_SET",
        )
        self.assertEqual(outcome["wan_ti2v_outcome"], "refusal")
        self.assertEqual(outcome["fastwan_8gb_outcome"], "refusal")
        self.assertEqual(outcome["ltx_video_outcome"], "success")
        self.assertEqual(
            outcome["humo_disposition"]["status"],
            "BLOCKED_NOT_CHEAP_NOT_TOPOLOGY_EQUAL",
        )
        geometry = outcome["delivered_geometry_guardrail"]
        self.assertEqual(
            {(item["width"], item["height"]) for item in geometry["phase4_wan_ti2v"]},
            {(832, 480)},
        )
        self.assertEqual(
            {(item["width"], item["height"]) for item in geometry["phase3_ltx_video"]},
            {(832, 448)},
        )

    def test_phase3_measured_metrics_and_global_ceiling_are_explicit(self):
        rows = {row["leg_id"]: row for row in self.comparison["rows"]}
        fast = rows["phase3_fastwan_8gb_long_first"]
        self.assertEqual(fast["whole_child_peak_vram_gib"], 12.572266)
        self.assertEqual(fast["inter_shot_vram_gib"], 6.433594)
        self.assertEqual(fast["follow_on_refusal_affordable_frames"], 20)
        ltx = rows["phase3_ltx_video_long_first"]
        self.assertEqual(ltx["whole_child_peak_vram_gib"], 14.592773)
        self.assertEqual(ltx["whole_child_peak_host_ram_gib"], 52.325066)
        self.assertEqual(ltx["inter_shot_vram_gib"], 4.313477)
        self.assertTrue(ltx["global_14_5_gib_ceiling_exceeded"])
        self.assertEqual(ltx["headroom_to_14_5_gib"], -0.092773)

    def test_success_artifacts_are_hash_and_ffprobe_bound(self):
        expected = {
            "phase4_wan_ti2v_small_first": {
                (65, 832, 480): "538c15b04dd63a27e1dcbd85bfe3b0fcaf09a6d27fff96e06d73c41b39c13e45",
                (200, 832, 480): "ebd227ceaafeb698ef83a2365d07a348e9f776324d20589dcd26b1457fca2aed",
            },
            "phase3_ltx_video_long_first": {
                (200, 832, 448): "7f4b7f66db9b091cb9d715ad60688d360bb7825844da6e61146b2ba944ed3fdd",
                (65, 832, 448): "38b287496beb001e2c595bc5fc125df02ceac97f756e20fe3581a88e1708099b",
            },
        }
        for leg_id, expected_artifacts in expected.items():
            with self.subTest(leg_id=leg_id):
                binding = self.receipts[leg_id]["artifacts"]
                self.assertEqual(binding["status"], "DURABLE_SUCCESS_ARTIFACTS_BOUND")
                observed = {
                    (item["frame_count"], item["width"], item["height"]): item["sha256"]
                    for item in binding["artifacts"]
                }
                self.assertEqual(observed, expected_artifacts)
                for item in binding["artifacts"]:
                    self.assertEqual(item["validation"], "SHA256_BYTES_AND_FFPROBE_EXACT_SHAPE")
                    self.assertEqual(item["frame_rate"], "25/1")
                    self.assertEqual(item["audio_stream_count"], 0)
                    source = item["production_source"]
                    self.assertEqual(source["sha256"], item["sha256"])
                    self.assertEqual(source["bytes"], item["bytes"])
                    self.assertTrue(source["mtime_within_raw_child_window"])
                    self.assertTrue(source["source_matches_lab_copy"])
                    self.assertLessEqual(
                        source["raw_child_window_ns"][0],
                        source["mtime_ns"],
                    )
                    self.assertLessEqual(
                        source["mtime_ns"],
                        source["raw_child_window_ns"][1],
                    )

    def test_current_sidecar_and_fixture_builder_use_ledger_engine_binding(self):
        sidecar = (ROOT / "scratch/wan_retention_sidecar.py").read_text(encoding="utf-8")
        fixture_builder = (ROOT / "scratch/build_wan_retention_fixture.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("baked_ledger.video.shots[].engine_id", sidecar)
        self.assertNotIn("must be the server-bound OTR_FORCE_ENGINE_MAP", sidecar)
        self.assertIn('"engine_authority": "baked_ledger.video.shots[].engine_id"', fixture_builder)
        self.assertIn(
            '"engine_variable_status": "LEGACY_INCORRECT_DECLARATIVE_LABEL_NOT_ENGINE_AUTHORITY"',
            fixture_builder,
        )

    def test_fixture_contracts_are_bound_to_repo_local_copies(self):
        prefix = "results/otr_side/wan_retention/fixture_evidence/"
        for leg_id, receipt in self.receipts.items():
            with self.subTest(leg_id=leg_id):
                for name in ("fixture_contract", "bundle_manifest", "baked_ledger"):
                    self.assertTrue(receipt["source_refs"][name]["path"].startswith(prefix))
                self.assertIsNone(receipt["source_refs"]["master_audio"]["path"])
                self.assertEqual(
                    receipt["source_refs"]["master_audio"]["binding"],
                    "HASH_ONLY_FROM_DURABLE_BUNDLE_MANIFEST_AND_RAW_COMMAND",
                )

    def test_reverse_order_result_is_a_measured_dependency_not_a_fix(self):
        finding = self.comparison["order_sensitivity"]
        self.assertEqual(finding["status"], "MEASURED")
        self.assertEqual(finding["result"], "CONFIRMED_ORDER_DEPENDENT")
        self.assertEqual(finding["long_then_small"]["outcome"], "refusal")
        self.assertEqual(finding["small_then_long"]["outcome"], "success")
        self.assertIn("does not identify", finding["interpretation"])
        self.assertIn("does not", finding["interpretation"])

    def test_phase4_reverse_order_receipt_proves_both_shots_completed(self):
        phase4 = self.receipts["phase4_wan_ti2v_small_first"]
        self.assertEqual(phase4["observed_outcome"], "success")
        self.assertTrue(phase4["topology_proof"]["small_65_completed"])
        self.assertTrue(phase4["topology_proof"]["long_chain_200_completed"])
        metrics = phase4["metrics"]
        self.assertEqual(metrics["baseline"]["vram_used_mib"], 1110.0)
        self.assertEqual(metrics["whole_child_window"]["peak_vram"]["vram_used_mib"], 12676.0)
        self.assertEqual(metrics["inter_shot_boundary"]["vram_used_mib"], 6405.0)
        self.assertIn("second-shot lease/admission", metrics["inter_shot_boundary"]["definition"])
        self.assertEqual(
            [window["shot_id"] for window in metrics["shot_windows"]],
            ["shot_b003", "shot_b001"],
        )
        self.assertEqual(
            [segment["wrapper_logged_peak_mb"] for segment in metrics["render_segments"]],
            [7933, 11070, 12975],
        )
        state = phase4["production_state_snapshots"]
        self.assertNotEqual(
            state["manifest_before"]["sha256"], state["manifest_after"]["sha256"]
        )


if __name__ == "__main__":
    unittest.main()
