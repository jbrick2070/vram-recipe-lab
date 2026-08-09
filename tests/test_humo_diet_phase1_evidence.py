from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scratch" / "build_humo_diet_phase1_evidence.py"
SPEC = importlib.util.spec_from_file_location("build_humo_diet_phase1_evidence", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


class HumoDietPhase1EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = evidence.build(ROOT)

    def test_build_is_deterministic_and_committed_output_is_exact(self):
        again = evidence.build(ROOT)
        self.assertEqual(
            evidence.canonical_json_bytes(self.payload),
            evidence.canonical_json_bytes(again),
        )
        output = ROOT / evidence.OUTPUT
        self.assertEqual(output.read_bytes(), evidence.canonical_json_bytes(self.payload))

    def test_warm_clamp13_is_machine_winner_but_human_gate_remains(self):
        verdict = self.payload["machine_verdict"]
        self.assertEqual(verdict["result"], "ZERO_GRAPH_CHANGE_MACHINE_WINNER")
        self.assertEqual(verdict["phase1_winner"], "clamp13_warm")
        self.assertEqual(verdict["absolute_peak_vram_gib"], 12.84)
        self.assertEqual(verdict["diet_target_headroom_gib"], 0.66)
        self.assertEqual(
            verdict["metric_sources"]["production_peak_range"],
            ["production_take1_receipt", "production_take2_receipt"],
        )
        self.assertEqual(verdict["human_quality"], "PENDING_HUMAN")
        self.assertFalse(verdict["promotion_ready"])

    def test_clamp12_cold_failure_is_preserved_without_rounded_subtraction(self):
        stopped = self.payload["clamp12_stop"]
        self.assertEqual(stopped["absolute_peak_vram_gib"], 14.47)
        self.assertEqual(stopped["runner_reported_net_vram_gib"], 12.28)
        self.assertEqual(stopped["clamp_target_gib"], 12.0)
        self.assertIn("STOP_NO_FORCE", stopped["disposition"])

    def test_phase_peaks_are_recomputed_from_raw_samples(self):
        runs = {row["run_id"]: row for row in self.payload["lab_runs"]}
        expected = {
            "clamp13_cold": {
                "umt5_text_conditioning": 10.575195,
                "humo_denoise": 14.209961,
                "vae_decode_and_save": 13.225586,
            },
            "clamp13_warm": {
                "humo_denoise": 12.226562,
                "vae_decode_and_save": 12.84082,
            },
            "clamp12_cold": {
                "umt5_text_conditioning": 10.59668,
                "humo_denoise": 14.46582,
                "vae_decode_and_save": 13.404297,
            },
        }
        for run_id, phase_expectations in expected.items():
            phases = {
                phase["phase"]: phase
                for phase in runs[run_id]["phase_analysis"]["phases"]
            }
            for phase_name, peak in phase_expectations.items():
                with self.subTest(run_id=run_id, phase=phase_name):
                    self.assertEqual(phases[phase_name]["peak_vram_gib"], peak)

    def test_memory_hog_finding_separates_weights_from_peak_phase(self):
        finding = self.payload["memory_hog_finding"]
        weight = finding["largest_staged_weight_component"]
        self.assertEqual(weight["model"], "WanTEModel (UMT5 text encoder)")
        self.assertEqual(weight["staged_size_mb_as_logged"], 6419)
        self.assertEqual(weight["humo_dit_staged_size_mb_as_logged"], 3320)
        self.assertEqual(
            finding["observed_peak_phases"],
            {
                "clamp13_cold": "humo_denoise",
                "clamp13_warm": "vae_decode_and_save",
                "clamp12_cold": "humo_denoise",
            },
        )
        self.assertIn("do not prove", finding["conclusion"])

    def test_ab_package_is_hash_bound_and_review_only(self):
        package = self.payload["ab_review_package"]
        self.assertEqual(package["artifact"]["sha256"], evidence.AB_ARTIFACT_SHA256)
        self.assertEqual(package["artifact"]["bytes"], 633940)
        self.assertEqual(package["probe"]["width"], 960)
        self.assertEqual(package["probe"]["height"], 832)
        self.assertEqual(package["probe"]["frame_count"], 129)
        self.assertEqual(package["probe"]["container_duration_s"], 5.16)
        self.assertIn("not model evidence", package["policy"])

    def test_all_primary_inputs_are_sha256_pinned(self):
        sources = self.payload["source_refs"]
        self.assertEqual(set(sources), set(evidence.PINNED_SOURCES))
        for source_id, source in sources.items():
            with self.subTest(source=source_id):
                self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
                self.assertGreater(source["bytes"], 0)


if __name__ == "__main__":
    unittest.main()
