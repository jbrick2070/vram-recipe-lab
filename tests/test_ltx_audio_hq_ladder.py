import copy
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from duration_match import duration_match
from scratch import build_ltx_audio_hq_ladder as builder
from validate_recipes import validate_recipe_file


ROOT = Path(__file__).resolve().parents[1]


class LTXAudioHQLadderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_raw = builder.BASE_PATH.read_bytes()
        cls.base = json.loads(cls.base_raw.decode("utf-8"))
        cls.receipt_raw = builder.LONG_RECEIPT_PATH.read_bytes()
        cls.receipt = json.loads(cls.receipt_raw.decode("utf-8"))
        cls.generated = builder.make_variants(cls.receipt)
        cls.recipes = {
            name: json.loads(
                (builder.RECIPES / f"{name}.json").read_text(encoding="utf-8")
            )
            for name in builder.VARIANT_NAMES
        }

    def test_certified_base_and_completed_motion_ladder_are_preserved(self):
        self.assertEqual(hashlib.sha256(self.base_raw).hexdigest(), builder.BASE_SHA256)
        builder.verify_preserved_recipes()
        for filename, expected in builder.PRESERVED_RECIPE_SHA256S.items():
            with self.subTest(filename=filename):
                self.assertEqual(builder.sha256_file(builder.RECIPES / filename), expected)

    def test_generator_and_generated_files_are_byte_semantically_exact(self):
        for name, expected in self.generated.items():
            raw = (builder.RECIPES / f"{name}.json").read_bytes()
            with self.subTest(name=name):
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r\n", raw)
                self.assertEqual(json.loads(raw.decode("utf-8")), expected)
        self.assertFalse(self.receipt_raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.receipt_raw.endswith(b"\n"))

    def test_h1_changes_only_the_1024x576_canvas_payload(self):
        recipe = self.recipes[builder.H1_NAME]
        self.assertEqual(
            builder.difference_paths(self.base["prompt"], recipe["prompt"]),
            builder.H1_PROMPT_DIFFS,
        )
        self.assertEqual(
            builder.difference_paths(self.base["contract"], recipe["contract"]),
            {"width", "height"},
        )
        self.assertEqual((recipe["contract"]["width"], recipe["contract"]["height"]), (1024, 576))
        self.assertEqual(
            (recipe["prompt"]["11"]["inputs"]["width"], recipe["prompt"]["11"]["inputs"]["height"]),
            (1024, 576),
        )
        self.assertEqual(
            (
                recipe["prompt"]["14"]["inputs"]["resize_type.width"],
                recipe["prompt"]["14"]["inputs"]["resize_type.height"],
            ),
            (1024, 576),
        )
        self.assertEqual(
            (recipe["prompt"]["23"]["inputs"]["width"], recipe["prompt"]["23"]["inputs"]["height"]),
            (1024, 576),
        )
        self.assertEqual(recipe["contract"]["frames"], 97)
        self.assertEqual(recipe["contract"]["duration_s"], 3.88)
        self.assertEqual(recipe["prompt"]["20"], self.base["prompt"]["20"])
        self.assertEqual(recipe["hq_ladder"]["independent_variable"], "canvas_resolution")
        self.assertFalse(recipe["hq_ladder"]["compositional_candidate"])

    def test_h2_changes_only_exact_193_frame_duration_payload(self):
        recipe = self.recipes[builder.H2_NAME]
        plan = duration_match(Decimal("7.72"), "ltx")
        self.assertEqual(plan["frame_count"], 193)
        self.assertEqual(plan["delivered_frame_count"], 193)
        self.assertEqual(plan["trim_frames"], 0)
        self.assertEqual(plan["rendered_s"], Fraction(193, 25))
        self.assertEqual(plan["delivered_s"], Decimal("7.72"))
        self.assertEqual(plan["tail_trim_s"], 0)
        self.assertEqual(
            builder.difference_paths(self.base["prompt"], recipe["prompt"]),
            builder.H2_PROMPT_DIFFS,
        )
        self.assertEqual(
            builder.difference_paths(self.base["contract"], recipe["contract"]),
            {"frames", "duration_s"},
        )
        self.assertEqual(recipe["contract"]["frames"], 193)
        self.assertEqual(recipe["contract"]["duration_s"], 7.72)
        self.assertEqual(recipe["prompt"]["11"]["inputs"]["length"], 193)
        self.assertEqual(recipe["prompt"]["20"]["inputs"]["audio"], builder.LONG_FIXTURE)
        self.assertEqual(recipe["prompt"]["21"]["inputs"]["duration"], 7.72)
        self.assertEqual(recipe["contract"]["width"], 832)
        self.assertEqual(recipe["contract"]["height"], 480)
        self.assertEqual(recipe["hq_ladder"]["independent_variable"], "duration")
        self.assertFalse(recipe["hq_ladder"]["compositional_candidate"])

    def test_h3_is_exact_composition_of_h1_and_h2_payloads(self):
        h1 = self.recipes[builder.H1_NAME]
        h2 = self.recipes[builder.H2_NAME]
        h3 = self.recipes[builder.H3_NAME]
        self.assertEqual(
            builder.difference_paths(self.base["prompt"], h3["prompt"]),
            builder.H3_PROMPT_DIFFS,
        )
        self.assertEqual(
            builder.difference_paths(self.base["contract"], h3["contract"]),
            {"width", "height", "frames", "duration_s"},
        )
        for node_id, key in (
            ("11", "width"),
            ("11", "height"),
            ("14", "resize_type.width"),
            ("14", "resize_type.height"),
            ("23", "width"),
            ("23", "height"),
        ):
            self.assertEqual(h3["prompt"][node_id]["inputs"][key], h1["prompt"][node_id]["inputs"][key])
        for node_id, key in (("11", "length"), ("20", "audio"), ("21", "duration")):
            self.assertEqual(h3["prompt"][node_id]["inputs"][key], h2["prompt"][node_id]["inputs"][key])
        self.assertEqual(
            (h3["contract"]["width"], h3["contract"]["height"], h3["contract"]["frames"], h3["contract"]["duration_s"]),
            (1024, 576, 193, 7.72),
        )
        self.assertTrue(h3["hq_ladder"]["compositional_candidate"])
        self.assertIn("both H1 and H2", h3["hq_ladder"]["go_no_go"])

    def test_long_audio_is_exact_hash_bound_and_loudness_matched(self):
        receipt = self.receipt
        self.assertEqual(receipt["fixture"], builder.LONG_FIXTURE)
        self.assertEqual(receipt["sha256"], builder.sha256_file(builder.LONG_FIXTURE_PATH))
        self.assertEqual(receipt["derived_from"]["fixture"], builder.SOURCE_FIXTURE)
        self.assertEqual(receipt["derived_from"]["sha256"], builder.SOURCE_SHA256)
        self.assertTrue(receipt["ear_gate_pass"])
        self.assertEqual(receipt["ffprobe"]["duration_s"], 7.72)
        self.assertEqual(receipt["ffprobe"]["duration_samples"], 247_040)
        self.assertEqual(receipt["ffprobe"]["sample_rate_hz"], 32_000)
        self.assertEqual(receipt["loudness"]["integrated_lufs"], -25.6)
        self.assertEqual(
            receipt["loudness"]["integrated_lufs"],
            self.base["experiment"]["measured_lufs"],
        )
        self.assertEqual(receipt["derivation"]["gain_db"], -12.4)
        self.assertEqual(receipt["derivation"]["builder_sha256"], builder.sha256_file(Path(builder.__file__)))
        for command in ("ffprobe", "volumedetect", "matrix_loudness", "derivation"):
            self.assertTrue(receipt["commands"][command])

    def test_all_non_factor_graph_settings_remain_identical(self):
        invariant_node_ids = {
            node_id for node_id in self.base["prompt"] if node_id not in {"11", "14", "20", "21", "23", "75"}
        }
        for name, recipe in self.recipes.items():
            with self.subTest(name=name):
                self.assertEqual(set(recipe["prompt"]), set(self.base["prompt"]))
                self.assertEqual(recipe["topology_contract"], self.base["topology_contract"])
                for node_id in invariant_node_ids:
                    self.assertEqual(recipe["prompt"][node_id], self.base["prompt"][node_id])
                self.assertEqual(recipe["prompt"]["9"]["inputs"], {"noise_seed": 42})
                self.assertEqual(recipe["prompt"]["16"]["inputs"]["strength"], 1.0)
                self.assertEqual(recipe["prompt"]["4"]["inputs"]["text"], self.base["prompt"]["4"]["inputs"]["text"])
                self.assertEqual(recipe["prompt"]["7"], self.base["prompt"]["7"])
                self.assertEqual(recipe["prompt"]["8"], self.base["prompt"]["8"])
                self.assertEqual(recipe["prompt"]["10"], self.base["prompt"]["10"])

    def test_receipt_timing_contract_and_unrendered_status_are_explicit(self):
        for name, recipe in self.recipes.items():
            with self.subTest(name=name):
                timing = recipe["receipt_requirements"]["timing"]
                self.assertTrue(timing["ffprobe_required"])
                self.assertEqual(timing["absolute_duration_error_lte_s"], 1 / 25)
                self.assertEqual(recipe["experiment"]["render_status"], "unrendered")
                self.assertEqual(
                    recipe["experiment"]["behavioral_claim_status"],
                    "unrendered and unproven",
                )

    def test_all_hq_recipes_pass_paper_validation(self):
        for name in builder.VARIANT_NAMES:
            with self.subTest(name=name):
                report = validate_recipe_file(builder.RECIPES / f"{name}.json")
                self.assertTrue(report["valid"], report["errors"])

    def test_immutable_writer_accepts_identity_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "generated.json"
            payload = b"{}\n"
            self.assertTrue(builder.immutable_write(path, payload))
            self.assertFalse(builder.immutable_write(path, payload))
            with self.assertRaisesRegex(RuntimeError, "Immutable generated file differs"):
                builder.immutable_write(path, b'{"drift": true}\n')


if __name__ == "__main__":
    unittest.main()
