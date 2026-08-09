import copy
import hashlib
import json
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from duration_match import duration_match
from scratch.build_ltx_audio_motion_ladder import (
    BASE_DURATION,
    COMFYUI_COMMIT,
    DOUBLE_DURATION,
    M0_PATH,
    M0_SHA256,
    M1_NAME,
    M1_PROMPT,
    M2_NAME,
    M3_FIXTURE,
    M3_FIXTURE_PATH,
    M3_NAME,
    M3_RECEIPT_PATH,
    NODE_SOURCE_SHA256,
    OFFICIAL_TEMPLATE_SHA256,
    SOURCE_FIXTURE,
    make_variants,
    sha256_file,
    verify_local_grounding,
)
from validate_recipes import validate_recipe_file


ROOT = Path(__file__).resolve().parent.parent


class LTXAudioMotionLadderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_bytes = M0_PATH.read_bytes()
        cls.base = json.loads(cls.base_bytes.decode("utf-8"))
        cls.receipt_bytes = M3_RECEIPT_PATH.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes.decode("utf-8"))
        cls.generated = make_variants(cls.receipt)
        cls.recipes = {
            name: json.loads(
                (ROOT / "recipes" / f"{name}.json").read_text(encoding="utf-8")
            )
            for name in (M1_NAME, M2_NAME, M3_NAME)
        }

    def test_m0_is_the_immutable_existing_control(self):
        self.assertEqual(hashlib.sha256(self.base_bytes).hexdigest(), M0_SHA256)
        self.assertEqual(self.base["name"], "ltx_audio_gguf_music_opening")
        self.assertEqual(self.base["prompt"]["9"]["inputs"], {"noise_seed": 42})
        self.assertEqual(self.base["prompt"]["16"]["inputs"]["strength"], 1.0)
        self.assertEqual(self.base["contract"]["duration_s"], 3.88)

    def test_builder_is_byte_semantically_idempotent(self):
        for name, expected in self.generated.items():
            path = ROOT / "recipes" / f"{name}.json"
            raw = path.read_bytes()
            with self.subTest(name=name):
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertTrue(raw.endswith(b"\n"))
                self.assertEqual(json.loads(raw.decode("utf-8")), expected)
        self.assertFalse(self.receipt_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.receipt_bytes.endswith(b"\n"))

    def test_m1_changes_only_positive_prompt_payload(self):
        recipe = self.recipes[M1_NAME]
        expected = copy.deepcopy(self.base)
        expected["name"] = M1_NAME
        expected["prompt"]["75"]["inputs"]["filename_prefix"] = f"{M1_NAME}_out"
        expected["prompt"]["4"]["inputs"]["text"] = M1_PROMPT
        expected["experiment"]["timing_plan"] = recipe["experiment"]["timing_plan"]
        expected["motion_ladder"] = recipe["motion_ladder"]
        expected["receipt_requirements"] = recipe["receipt_requirements"]
        self.assertEqual(recipe, expected)
        self.assertEqual(
            recipe["motion_ladder"]["changed_payload_fields"],
            ["prompt.4.inputs.text"],
        )
        for token in ("continuous", "sweep", "pulse", "spin", "sway", "drifts", "parallax"):
            self.assertIn(token, M1_PROMPT.lower())
        self.assertIn("locked camera", M1_PROMPT.lower())

    def test_m2_changes_only_documented_strength_payload(self):
        recipe = self.recipes[M2_NAME]
        expected = copy.deepcopy(self.base)
        expected["name"] = M2_NAME
        expected["prompt"]["75"]["inputs"]["filename_prefix"] = f"{M2_NAME}_out"
        expected["prompt"]["16"]["inputs"]["strength"] = 0.7
        expected["experiment"]["timing_plan"] = recipe["experiment"]["timing_plan"]
        expected["motion_ladder"] = recipe["motion_ladder"]
        expected["receipt_requirements"] = recipe["receipt_requirements"]
        self.assertEqual(recipe, expected)
        self.assertEqual(
            recipe["motion_ladder"]["changed_payload_fields"],
            ["prompt.16.inputs.strength"],
        )
        grounding = recipe["motion_ladder"]["strength_grounding"]
        self.assertEqual(grounding["control_value"], 1.0)
        self.assertEqual(grounding["documented_soft_anchor_value"], 0.7)
        self.assertEqual(grounding["official_template_sha256"], OFFICIAL_TEMPLATE_SHA256)
        self.assertEqual(grounding["installed_source_sha256"], NODE_SOURCE_SHA256)
        self.assertEqual(grounding["comfyui_commit"], COMFYUI_COMMIT)
        self.assertIn("1.0 - strength", grounding["semantics"])
        verify_local_grounding()

    def test_m3_is_exact_double_duration_with_only_dependent_graph_changes(self):
        recipe = self.recipes[M3_NAME]
        prompt = recipe["prompt"]
        plan = duration_match(Decimal("7.76"), "ltx")
        self.assertEqual(BASE_DURATION, Decimal("3.88"))
        self.assertEqual(DOUBLE_DURATION, Decimal("7.76"))
        self.assertEqual(plan["frame_count"], 201)
        self.assertEqual(plan["trim_frames"], 7)
        self.assertEqual(plan["rendered_s"], Fraction(201, 25))
        self.assertEqual(plan["delivered_s"], Decimal("7.76"))
        self.assertEqual(plan["tail_trim_s"], 0)

        contract = recipe["contract"]
        self.assertEqual(contract["render_frames"], 201)
        self.assertEqual(contract["frames"], 194)
        self.assertEqual(contract["trim_frames"], 7)
        self.assertEqual(contract["fps"], 25.0)
        self.assertEqual(contract["target_s"], 7.76)
        self.assertEqual(contract["delivered_s"], 7.76)
        self.assertEqual(194 / 25, 7.76)
        self.assertEqual((201 - 1) % 8, 0)

        self.assertEqual(set(prompt) - set(self.base["prompt"]), {"34"})
        changed_shared_nodes = {
            node_id
            for node_id in self.base["prompt"]
            if prompt[node_id] != self.base["prompt"][node_id]
        }
        self.assertEqual(changed_shared_nodes, {"11", "20", "21", "35", "75"})
        self.assertEqual(prompt["11"]["inputs"]["length"], 201)
        self.assertEqual(prompt["20"]["inputs"]["audio"], M3_FIXTURE)
        self.assertEqual(prompt["21"]["inputs"]["duration"], 7.76)
        self.assertEqual(
            prompt["34"],
            {
                "class_type": "ImageFromBatch",
                "inputs": {"image": ["33", 0], "batch_index": 0, "length": 194},
            },
        )
        self.assertEqual(prompt["35"]["inputs"]["images"], ["34", 0])
        self.assertEqual(prompt["9"]["inputs"], {"noise_seed": 42})
        self.assertEqual(prompt["16"]["inputs"]["strength"], 1.0)
        self.assertEqual(prompt["4"]["inputs"]["text"], self.base["prompt"]["4"]["inputs"]["text"])

    def test_m3_audio_derivative_is_exact_and_receipted(self):
        receipt = self.receipt
        self.assertEqual(receipt["fixture"], M3_FIXTURE)
        self.assertEqual(receipt["sha256"], sha256_file(M3_FIXTURE_PATH))
        self.assertEqual(receipt["derived_from"]["fixture"], SOURCE_FIXTURE)
        self.assertTrue(receipt["ear_gate_pass"])
        self.assertEqual(receipt["ffprobe"]["sample_rate_hz"], 32_000)
        self.assertEqual(receipt["ffprobe"]["duration_samples"], 248_320)
        self.assertEqual(receipt["ffprobe"]["duration_s"], 7.76)
        self.assertEqual(receipt["loudness"]["integrated_lufs"], -25.6)
        self.assertEqual(
            receipt["loudness"]["integrated_lufs"],
            self.base["experiment"]["measured_lufs"],
        )
        self.assertLessEqual(
            abs(
                receipt["matrix_window"]["matched_lufs"]
                - receipt["matrix_window"]["target_lufs"]
            ),
            receipt["matrix_window"]["tolerance_lu"],
        )
        for command in ("ffprobe", "volumedetect", "matrix_loudness", "derivation"):
            self.assertTrue(receipt["commands"][command])

    def test_seed_still_models_sampler_scheduler_and_canvas_are_constant(self):
        invariant_contract_keys = ("engine", "mode", "width", "height", "fps", "vram_ceiling_gb")
        invariant_nodes = ("1", "2", "3", "5", "6", "7", "8", "9", "10", "13", "14", "15", "16", "22", "23", "24", "30", "31", "32", "33")
        for name, recipe in self.recipes.items():
            with self.subTest(name=name):
                for key in invariant_contract_keys:
                    self.assertEqual(recipe["contract"][key], self.base["contract"][key])
                for node_id in invariant_nodes:
                    if name == M2_NAME and node_id == "16":
                        continue
                    self.assertEqual(recipe["prompt"][node_id], self.base["prompt"][node_id])
                self.assertEqual(recipe["prompt"]["13"]["inputs"]["image"], "scene_still.png")
                self.assertEqual(recipe["prompt"]["9"]["inputs"]["noise_seed"], 42)

    def test_all_three_recipes_pass_offline_topology_validation(self):
        for name in (M1_NAME, M2_NAME, M3_NAME):
            with self.subTest(name=name):
                validation = validate_recipe_file(ROOT / "recipes" / f"{name}.json")
                self.assertTrue(validation["valid"], validation["errors"])


if __name__ == "__main__":
    unittest.main()
