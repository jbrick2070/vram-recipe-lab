from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scratch" / "build_otr_humo_bakeoff.py"
SPEC = importlib.util.spec_from_file_location("build_otr_humo_bakeoff", MODULE)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class OtrHumoBakeoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = [run["name"] for run in builder.RUNS]
        names.extend(("humo_character_lane_bakeoff", "otr_worktree_integrity"))
        cls.docs = {
            name: json.loads((builder.RESULTS / f"{name}.json").read_text(encoding="utf-8"))
            for name in names
        }

    def test_three_humo_receipts_are_measurement_only(self):
        names = [run["name"] for run in builder.RUNS]
        self.assertEqual(len(names), 3)
        for name in names:
            receipt = self.docs[name]
            self.assertEqual(receipt["measured"], "otr-side production lane")
            self.assertFalse(receipt["lab_gate_evaluated"])
            for field in ("gate_pass", "pass", "warm_pass", "marginal"):
                self.assertIsNone(receipt[field])
            self.assertFalse(receipt["promotion_ready"])
            self.assertEqual(set(receipt["human_verdicts"].values()), {"PENDING_HUMAN"})

    def test_fixture_copy_chain_and_review_video_are_exact(self):
        for run in builder.RUNS:
            receipt = self.docs[run["name"]]
            self.assertEqual(receipt["fixture_sha256s"]["portrait.png"], builder.PORTRAIT_SHA)
            self.assertEqual(receipt["fixture_sha256s"]["tts_dialogue.wav"], builder.TTS_SHA)
            hashes = {row["sha256"] for row in receipt["fixture_contract"]["copy_chain"].values()}
            self.assertEqual(hashes, {builder.PORTRAIT_SHA, builder.TTS_SHA})
            self.assertEqual(len(receipt["native_and_review_video_stream_sha256"]), 64)

    def test_sampling_cadence_and_media_contract(self):
        for run in builder.RUNS:
            receipt = self.docs[run["name"]]
            self.assertGreater(receipt["monitor"]["sample_count"], 1000)
            self.assertEqual(receipt["monitor"]["sample_error_count"], 0)
            self.assertLess(receipt["monitor"]["max_gap_s"], 0.5)
            self.assertEqual(receipt["encoded_frame_count"], run["frames"])
            self.assertEqual(receipt["encoded_width"], run["width"])
            self.assertEqual(receipt["encoded_height"], run["height"])
            self.assertAlmostEqual(
                receipt["render_seconds_per_output_second"],
                receipt["duration_s"] / receipt["video_duration_s"], places=12,
            )

    def test_two_1p7b_runs_are_independent_fixed_seed_evidence(self):
        first = self.docs["humo_1_7b_bakeoff_take1"]
        second = self.docs["humo_1_7b_bakeoff_take2"]
        self.assertEqual(first["seed_effective"], 7)
        self.assertEqual(second["seed_effective"], 7)
        self.assertNotEqual(first["cache_buster"], second["cache_buster"])
        self.assertNotEqual(first["monitor"]["telemetry_sha256"], second["monitor"]["telemetry_sha256"])
        self.assertEqual(first["native_silent_artifact_sha256"], second["native_silent_artifact_sha256"])
        self.assertIsNotNone(first["failed_preflight_attempt"])
        self.assertFalse(first["failed_preflight_attempt"]["accepted_prompt"])

    def test_combined_package_has_five_clips_four_categories(self):
        package = self.docs["humo_character_lane_bakeoff"]
        self.assertEqual(package["review_clip_count"], 5)
        self.assertEqual(package["measurement_category_count"], 4)
        self.assertEqual(len(package["entries"]), 5)
        self.assertTrue(package["fixture_parity"])
        self.assertFalse(package["workload_duration_parity"])

    def test_frozen_files_use_canonical_utf8_json(self):
        for name, payload in self.docs.items():
            path = builder.RESULTS / f"{name}.json"
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.read_bytes(), builder.encoded_json(payload))
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_otr_worktree_matches_dirty_entry_baseline(self):
        receipt = self.docs["otr_worktree_integrity"]
        self.assertTrue(receipt["matched_captured_entry_baseline"])
        self.assertTrue(receipt["entry_dirty"])
        self.assertTrue(receipt["final_dirty"])
        self.assertFalse(receipt["clean_claim_possible"])
        self.assertFalse(receipt["production_code_changed_by_session"])


if __name__ == "__main__":
    unittest.main()
