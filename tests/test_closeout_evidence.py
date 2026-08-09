import json
import unittest
from pathlib import Path

from scratch import build_closeout_evidence as builder


ROOT = Path(__file__).resolve().parents[1]


class CloseoutEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = builder.build_documents()

    def test_checked_in_receipts_match_deterministic_builder(self):
        self.assertEqual(
            set(self.documents),
            {path.name for path in (ROOT / "results" / "comparisons").glob("*.json")},
        )
        for filename, payload in self.documents.items():
            path = ROOT / "results" / "comparisons" / filename
            self.assertEqual(path.read_bytes(), builder.canonical_bytes(payload))
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_same_canvas_speed_math_and_winner(self):
        payload = self.documents["general_video_speed_pair.json"]
        self.assertEqual(payload["controls"]["canvas"], "832x480")
        self.assertEqual(payload["controls"]["frames"], 193)
        self.assertAlmostEqual(payload["lanes"][0]["megapixel_frames"], 77.07648)
        self.assertAlmostEqual(payload["lanes"][0]["render_seconds_per_output_second"], 52.784974)
        self.assertAlmostEqual(payload["lanes"][1]["render_seconds_per_output_second"], 1.787565)
        self.assertAlmostEqual(payload["ltx_wall_clock_speedup_over_wan"], 29.528986)
        self.assertTrue(all(not row["ranking_eligible"] for row in payload["unnormalized_reported_rows"]))

    def test_h3_pair_is_two_take_lab_only_package(self):
        payload = self.documents["h3_lipsync_ab_package.json"]
        self.assertEqual([row["seed"] for row in payload["takes"]], [42, 43])
        self.assertTrue(all(row["machine_gate_pass"] for row in payload["takes"]))
        self.assertTrue(all(not row["warm_pass"] for row in payload["takes"]))
        self.assertIn("HuMo", payload["lab_scope"])
        self.assertEqual(
            payload["fixture_contract"]["actual_conditioning_inputs"],
            ["fixtures/portrait.png", "fixtures/tts_dialogue.wav"],
        )
        self.assertIn("uses the ordered", payload["fixture_contract"]["comparison_caveat"])
        self.assertTrue(
            all(row["status"] == "GATE PASS (cold-only)" for row in payload["takes"])
        )
        self.assertEqual(
            [row["artifact_sha256"] for row in payload["technical_screen_review"]["takes"]],
            [row["artifact_sha256"] for row in payload["takes"]],
        )
        self.assertIn("not a phoneme-sync", payload["technical_screen_review"]["scope"])

    def test_h3_refaudio_reconstruction_is_receipt_bound(self):
        payload = self.documents["h3_refaudio_reconstruction.json"]
        self.assertGreater(payload["analysis"]["waveform_pearson_r"], 0.94)
        self.assertGreater(payload["analysis"]["rms_envelope_pearson_r"], 0.94)
        self.assertEqual(len(payload["source_fixture_sha256"]), 64)
        self.assertEqual(len(payload["source_run"]["receipt_sha256"]), 64)
        self.assertEqual(len(payload["source_run"]["artifact_sha256"]), 64)

    def test_h3_human_review_amendments_are_hash_bound(self):
        payload = self.documents["h3_refaudio_human_reviews.json"]
        self.assertEqual([row["eyeball"] for row in payload["reviews"]], [
            "untested:prompt_did_not_request_lipsync",
            "ok-experimental",
        ])
        self.assertTrue(all(len(row["current_alias"]["receipt_sha256"]) == 64 for row in payload["reviews"]))
        self.assertTrue(all(len(row["immutable_machine_receipt_sha256"]) == 64 for row in payload["reviews"]))

    def test_hq_h3_is_best_warm_machine_configuration(self):
        payload = self.documents["ltx_audio_hq_ladder.json"]
        self.assertEqual(payload["best_machine_certified_configuration"], "H3_canvas_and_duration")
        self.assertTrue(all(row["warm_pass"] for row in payload["rungs"]))
        self.assertEqual(payload["rungs"][2]["width"], 1024)
        self.assertEqual(payload["rungs"][2]["encoded_frames"], 193)

    def test_h3_token_estimator_uses_local_core_grid(self):
        payload = self.documents["h3_token_budget_check.json"]
        self.assertEqual(builder.h3_latent_t(124), 37)
        self.assertEqual(builder.h3_latent_t(192), 57)
        self.assertEqual(builder.visual_tokens(864, 480, 124), 14985)
        self.assertEqual(builder.visual_tokens(864, 480, 192), 23085)
        self.assertEqual(payload["external_reported_claim"]["output_visual_tokens_derived"], 27588)
        self.assertEqual(payload["external_reported_claim"]["gpu_vram_gib_reported"], 8)
        self.assertIn("EXTERNAL-REPORTED", payload["feasibility_estimator"]["status"])
        self.assertIn("EXTERNAL-REPORTED", payload["vocal_separation_claim"]["status"])
        self.assertEqual(payload["ref_image_size_check"]["value"], "match")
        self.assertEqual(len(payload["ref_image_size_check"]["recipe_sha256"]), 64)
        self.assertTrue(all(len(row["receipt_sha256"]) == 64 for row in payload["local_checks"]))
        self.assertTrue(all(len(row["artifact_sha256"]) == 64 for row in payload["local_checks"]))
        with self.assertRaises(ValueError):
            builder.h3_latent_t(193)

    def test_failed_sage_and_pending_human_gates_stay_fail_closed(self):
        sage = self.documents["h3_sage_patch_probe.json"]
        mime = self.documents["h3_mime_unconditioned.json"]
        self.assertFalse(sage["output_produced"])
        self.assertFalse(sage["machine_evidence"]["machine_gate_pass"])
        excerpt = ROOT / sage["error_evidence"]["tracked_excerpt_path"]
        self.assertEqual(
            builder.sha256_file(excerpt),
            sage["error_evidence"]["tracked_excerpt_sha256"],
        )
        self.assertEqual(
            mime["human_inverted_ear_gate"][
                "no_speech_like_or_vocal_like_content_of_any_intelligibility"
            ],
            "pending",
        )
        self.assertEqual(mime["human_inverted_ear_gate"]["coherent_diegetic_sync"], "pending")


if __name__ == "__main__":
    unittest.main()
