import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scratch import build_cross_engine_duration_candidates as builder
from validate_recipes import topology_contract_errors, validate_recipe_file


REPO_ROOT = Path(__file__).parent.parent.resolve()
MANIFEST_PATH = REPO_ROOT / "models_manifest.md"


class CrossEngineDurationCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = builder.recipes()
        cls.paths = {
            name: REPO_ROOT / "recipes" / f"{name}.json"
            for name in cls.expected
        }
        cls.actual = {
            name: json.loads(path.read_text(encoding="utf-8"))
            for name, path in cls.paths.items()
        }

    def test_generated_recipes_are_canonical_and_immutable(self):
        self.assertEqual(self.actual, self.expected)
        for path in self.paths.values():
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
            self.assertNotIn(b"\r\n", raw, path)
            self.assertTrue(raw.endswith(b"\n"), path)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            first = builder.write_immutable_recipes(output)
            self.assertEqual(len(first), 3)
            self.assertEqual(builder.write_immutable_recipes(output), [])
            drifted = output / f"{builder.WAN_COMPARE_NAME}.json"
            drifted.write_bytes(b"{}\n")
            with self.assertRaisesRegex(RuntimeError, "Immutable generated recipe differs"):
                builder.write_immutable_recipes(output)

    def test_pair_is_same_canvas_same_duration_and_grid_legal(self):
        wan = self.actual[builder.WAN_COMPARE_NAME]
        ltx = self.actual[builder.LTX_COMPARE_NAME]
        for recipe in (wan, ltx):
            contract = recipe["contract"]
            self.assertEqual(
                (
                    contract["width"],
                    contract["height"],
                    contract["frames"],
                    contract["fps"],
                    contract["duration_s"],
                ),
                (832, 480, 193, 25.0, 7.72),
            )
            self.assertEqual(contract["frames"] / contract["fps"], 7.72)
            self.assertEqual(recipe["receipt_requirements"]["warm_gate"]["required_consecutive_runs"], 2)
            self.assertEqual(recipe["receipt_requirements"]["warm_gate"]["peak_vram_gb_lte"], 14.5)

        self.assertEqual((193 - 1) % 4, 0)
        self.assertEqual((193 - 1) % 8, 0)
        self.assertEqual(
            wan["experiment"]["comparison_controls"],
            ltx["experiment"]["comparison_controls"],
        )

    def test_pair_holds_fixture_prompt_seed_decode_and_delivery_constant(self):
        wan = self.actual[builder.WAN_COMPARE_NAME]["prompt"]
        ltx = self.actual[builder.LTX_COMPARE_NAME]["prompt"]
        self.assertEqual(wan["7"], ltx["7"])
        self.assertEqual(wan["4"]["inputs"]["text"], ltx["4"]["inputs"]["text"])
        self.assertEqual(wan["5"]["inputs"]["text"], ltx["5"]["inputs"]["text"])
        self.assertEqual(wan["9"]["inputs"]["seed"], 42)
        self.assertEqual(ltx["9"]["inputs"]["noise_seed"], 42)
        for prompt in (wan, ltx):
            self.assertEqual(prompt["10"]["class_type"], "VAEDecode")
            self.assertEqual(prompt["11"]["class_type"], "CreateVideo")
            self.assertEqual(prompt["11"]["inputs"]["fps"], 25.0)
            self.assertEqual(prompt["11"]["inputs"]["bit_depth"], 8)
            self.assertEqual(prompt["12"]["class_type"], "SaveVideo")

    def test_wan_ti2v_uses_proven_5b_native_topology(self):
        prompt = self.actual[builder.WAN_COMPARE_NAME]["prompt"]
        self.assertEqual(prompt["1"]["class_type"], "UnetLoaderGGUF")
        self.assertEqual(prompt["1"]["inputs"]["unet_name"], "Wan2.2-TI2V-5B-Q5_K_M.gguf")
        self.assertEqual(prompt["2"]["inputs"], {"model": ["1", 0], "shift": 5.0})
        self.assertEqual(prompt["8"]["class_type"], "Wan22ImageToVideoLatent")
        self.assertEqual(prompt["8"]["inputs"]["start_image"], ["7", 0])
        self.assertEqual(prompt["8"]["inputs"]["vae"], ["6", 0])
        self.assertEqual(prompt["9"]["inputs"]["latent_image"], ["8", 0])
        self.assertEqual(prompt["9"]["inputs"]["steps"], 30)
        self.assertEqual(prompt["9"]["inputs"]["cfg"], 5.0)
        self.assertEqual(prompt["9"]["inputs"]["sampler_name"], "euler")
        self.assertEqual(prompt["9"]["inputs"]["scheduler"], "simple")

    def test_ltx_2b_uses_distilled_scheduler_and_image_latent(self):
        prompt = self.actual[builder.LTX_COMPARE_NAME]["prompt"]
        self.assertEqual(prompt["1"]["inputs"]["ckpt_name"], "ltxv-2b-0.9.8-distilled.safetensors")
        self.assertEqual(prompt["3"]["inputs"]["device"], "cpu")
        self.assertEqual(prompt["8"]["class_type"], "LTXVImgToVideo")
        self.assertEqual(prompt["8"]["inputs"]["image"], ["7", 0])
        self.assertEqual(prompt["16"]["inputs"]["steps"], 8)
        self.assertEqual(prompt["16"]["inputs"]["latent"], ["8", 2])
        self.assertEqual(prompt["9"]["class_type"], "SamplerCustom")
        self.assertEqual(prompt["9"]["inputs"]["sigmas"], ["16", 0])
        self.assertEqual(prompt["9"]["inputs"]["latent_image"], ["8", 2])
        self.assertEqual(prompt["9"]["inputs"]["cfg"], 1.0)
        self.assertNotIn("latent", prompt["2"]["inputs"])

    def test_wan14_exoneration_is_short_grid_and_lane_bound(self):
        recipe = self.actual[builder.WAN14_EXONERATION_NAME]
        contract = recipe["contract"]
        self.assertEqual(
            (
                contract["width"],
                contract["height"],
                contract["frames"],
                contract["fps"],
                contract["duration_s"],
            ),
            (832, 480, 33, 25.0, 1.32),
        )
        self.assertEqual((contract["frames"] - 1) % 4, 0)
        self.assertEqual(contract["target_card_budget_gb"], 12.0)
        self.assertTrue(contract["requires_disable_pinned_memory"])
        self.assertEqual(contract["clamp_peak_minus_baseline_gb_lte"], 12.0)
        self.assertIn("no-pinned", contract["required_boot_lane"])
        self.assertIn("clamp-12gb", contract["required_boot_lane"])
        self.assertEqual(
            recipe["receipt_requirements"]["warm_gate"]["required_lane"],
            "--clamp 12 --disable-pinned-memory",
        )

        prompt = recipe["prompt"]
        self.assertEqual(prompt["1"]["class_type"], "UNETLoader")
        self.assertEqual(
            prompt["1"]["inputs"]["unet_name"],
            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        )
        self.assertEqual(prompt["2"]["inputs"]["shift"], 8.0)
        self.assertEqual(prompt["8"]["class_type"], "WanImageToVideo")
        self.assertEqual(prompt["8"]["inputs"]["start_image"], ["7", 0])
        self.assertEqual(prompt["9"]["inputs"]["steps"], 20)
        self.assertEqual(prompt["9"]["inputs"]["cfg"], 3.5)
        self.assertEqual(prompt["9"]["inputs"]["sampler_name"], "uni_pc")

    def test_models_are_manifested_and_prefixes_are_globally_unique(self):
        manifest = MANIFEST_PATH.read_text(encoding="utf-8")
        required_models = {
            "Wan2.2-TI2V-5B-Q5_K_M.gguf",
            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
            "ltxv-2b-0.9.8-distilled.safetensors",
            "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
            "t5xxl_fp16.safetensors",
            "wan2.2_vae.safetensors",
            "wan_2.1_vae.safetensors",
        }
        for model in required_models:
            self.assertIn(f"`{model}`", manifest)

        all_prefixes: list[str] = []
        for path in (REPO_ROOT / "recipes").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            all_prefixes.extend(
                node["inputs"]["filename_prefix"]
                for node in data.get("prompt", {}).values()
                if node.get("class_type") == "SaveVideo"
                and isinstance(node.get("inputs", {}).get("filename_prefix"), str)
            )
        for prefix in (
            builder.WAN_COMPARE_PREFIX,
            builder.LTX_COMPARE_PREFIX,
            builder.WAN14_EXONERATION_PREFIX,
        ):
            self.assertEqual(all_prefixes.count(prefix), 1, prefix)

    def test_topology_contracts_and_offline_validation_are_clean(self):
        for name, recipe in self.actual.items():
            with self.subTest(name=name):
                topology = recipe["topology_contract"]
                self.assertTrue(topology["exact_node_set"])
                self.assertEqual(topology_contract_errors(recipe, recipe["prompt"]), [])
                result = validate_recipe_file(self.paths[name])
                self.assertTrue(result["valid"], result)
                classes = {node["class_type"] for node in recipe["prompt"].values()}
                self.assertNotIn("VAEDecodeTiled", classes)
                self.assertNotIn("LoadAudio", classes)

    def test_topology_contract_detects_a_silent_wiring_regression(self):
        recipe = deepcopy(self.actual[builder.WAN_COMPARE_NAME])
        recipe["prompt"]["8"]["inputs"].pop("start_image")
        errors = topology_contract_errors(recipe, recipe["prompt"])
        self.assertTrue(any("8.start_image" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
