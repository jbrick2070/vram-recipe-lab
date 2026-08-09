import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import run_h3_suite
import run_recipe
import validate_recipes
from scratch import build_clean_h3_recipes as builder


REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = REPO_ROOT / "recipes" / "h3_i2v_suite_sentinel.json"
CURRENT_MANIFEST_PATH = REPO_ROOT / "suites" / "h3_best_suite_cache_classic.json"
HISTORICAL_MANIFEST_PATH = REPO_ROOT / "suites" / "h3_best_suite.json"


class TestH3SuiteSentinel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = RECIPE_PATH.read_bytes()
        cls.recipe = json.loads(cls.raw.decode("utf-8"))
        cls.prompt = cls.recipe["prompt"]
        cls.topology = cls.recipe["topology_contract"]

    def test_recipe_is_canonical_generator_output_and_immutable(self):
        generated = builder.make_h3_i2v_suite_sentinel_recipe()
        expected = (json.dumps(generated, indent=2) + "\n").encode("utf-8")
        self.assertEqual(self.raw, expected)
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", self.raw)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertTrue(builder.write_h3_i2v_suite_sentinel(output))
            first = (output / RECIPE_PATH.name).read_bytes()
            self.assertFalse(builder.write_h3_i2v_suite_sentinel(output))
            self.assertEqual((output / RECIPE_PATH.name).read_bytes(), first)
            (output / RECIPE_PATH.name).write_bytes(first + b" ")
            with self.assertRaisesRegex(RuntimeError, "Immutable generated recipe differs"):
                builder.write_h3_i2v_suite_sentinel(output)

    def test_exact_current_official_node_set_and_topology_contract(self):
        expected_nodes = {
            "1": "UNETLoader",
            "2": "CLIPLoader",
            "3": "VAELoader",
            "4": "VAELoader",
            "5": "RandomNoise",
            "6": "BasicGuider",
            "7": "MiniMaxH3ImageToVideo",
            "8": "SamplerCustomAdvanced",
            "9": "VAEDecode",
            "10": "CreateVideo",
            "11": "LoadImage",
            "12": "SaveVideo",
            "13": "KSamplerSelect",
            "14": "BasicScheduler",
            "15": "VAEDecodeAudio",
        }
        self.assertEqual(
            {node_id: node["class_type"] for node_id, node in self.prompt.items()},
            expected_nodes,
        )
        self.assertIs(self.topology["exact_node_set"], True)
        self.assertEqual(self.topology["required_nodes"], expected_nodes)
        self.assertEqual(self.topology["required_absent_inputs"], ["7.last_frame"])
        self.assertEqual(
            validate_recipes.topology_contract_errors(self.recipe, self.prompt), []
        )

    def test_sampled_target_latent_drives_native_video_and_audio_delivery(self):
        self.assertEqual(self.prompt["9"]["inputs"]["samples"], ["8", 0])
        self.assertEqual(self.prompt["15"]["inputs"]["samples"], ["8", 0])
        self.assertEqual(self.prompt["9"]["inputs"]["vae"], ["3", 0])
        self.assertEqual(self.prompt["15"]["inputs"]["vae"], ["4", 0])
        self.assertEqual(self.prompt["10"]["inputs"]["images"], ["9", 0])
        self.assertEqual(self.prompt["10"]["inputs"]["audio"], ["15", 0])
        self.assertEqual(self.prompt["12"]["inputs"]["video"], ["10", 0])
        self.assertEqual(
            set(run_recipe.prompt_output_ancestors(self.prompt)), set(self.prompt)
        )
        classes = {node["class_type"] for node in self.prompt.values()}
        self.assertNotIn("LoadAudio", classes)
        self.assertNotIn("MiniMaxH3SigmaShift", classes)

    def test_dimensions_models_seed_fixture_and_current_schema_are_pinned(self):
        self.assertEqual(
            self.recipe["contract"],
            {
                "engine": "minimax_h3",
                "mode": "i2v",
                "width": 864,
                "height": 480,
                "frames": 124,
                "fps": 24.0,
                "duration_s": 5.17,
                "requires_audio": True,
                "required_boot_lane": "lab-8199, sage-free",
                "vram_ceiling_gb": 14.5,
            },
        )
        self.assertEqual(self.prompt["5"]["inputs"], {"noise_seed": 42})
        self.assertEqual(
            self.prompt["7"]["inputs"],
            {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "prompt": builder.H3_DEFAULT_PROMPT,
                "width": 864,
                "height": 480,
                "length": 124,
                "first_frame": ["11", 0],
            },
        )
        self.assertEqual(self.prompt["11"]["inputs"]["image"], "scene_still.png")
        self.assertEqual(
            self.prompt["12"]["inputs"]["filename_prefix"],
            builder.H3_I2V_SUITE_SENTINEL_PREFIX,
        )
        self.assertEqual(self.prompt["13"]["inputs"]["sampler_name"], "res_multistep")
        self.assertEqual(
            self.prompt["14"]["inputs"],
            {"model": ["1", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0},
        )

        schema = self.topology["installed_schema"]
        self.assertEqual(schema["comfyui_version"], "0.31.1")
        self.assertEqual(schema["git_commit"], builder.COMFYUI_SCHEMA_COMMIT)
        self.assertEqual(schema["node_source"], builder.H3_NODE_SOURCE)
        source = run_recipe.COMFYUI_ROOT / schema["node_source"]
        self.assertTrue(source.is_file())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), schema["node_source_sha256"])

        frozen = self.topology["frozen_template"]
        frozen_path = REPO_ROOT / frozen["path"]
        self.assertEqual(hashlib.sha256(frozen_path.read_bytes()).hexdigest(), frozen["sha256"])
        scene = REPO_ROOT / "fixtures" / "scene_still.png"
        self.assertEqual(
            hashlib.sha256(scene.read_bytes()).hexdigest(),
            self.topology["fixture_hashes"]["scene_still.png"],
        )
        run_recipe.validate_fixture_hash_contract(
            self.recipe, {"scene_still.png": scene.read_bytes()}
        )

    def test_models_are_present_in_the_frozen_local_manifest(self):
        manifest = (REPO_ROOT / "models_manifest.md").read_text(encoding="utf-8")
        referenced = {
            self.prompt["1"]["inputs"]["unet_name"],
            self.prompt["2"]["inputs"]["clip_name"],
            self.prompt["3"]["inputs"]["vae_name"],
            self.prompt["4"]["inputs"]["vae_name"],
        }
        self.assertTrue(all(f"`{model}`" in manifest for model in referenced))

    def test_cache_classic_suite_uses_av_sentinel_and_preserves_history_manifest(self):
        manifest = json.loads(CURRENT_MANIFEST_PATH.read_text(encoding="utf-8"))
        actual = tuple(
            (member["label"], member["recipe"], member["role"])
            for member in manifest["sequence"]
        )
        self.assertEqual(actual, run_h3_suite.CANONICAL_SEQUENCE)
        sentinel_members = [member for member in manifest["sequence"] if member["label"][0] in "WS"]
        self.assertEqual(len(sentinel_members), 5)
        self.assertTrue(
            all(member["recipe"] == builder.H3_I2V_SUITE_SENTINEL_NAME for member in sentinel_members)
        )
        self.assertIn(builder.H3_I2V_SUITE_SENTINEL_NAME, validate_recipes.REQUIRED_RECIPES)

        historical_sha256 = hashlib.sha256(HISTORICAL_MANIFEST_PATH.read_bytes()).hexdigest()
        self.assertEqual(
            historical_sha256,
            "69421ebbbd8612a8791a146f79b517c03df654b820190ff1b33bd8a57ea35c94",
        )

    def test_offline_validator_accepts_the_new_recipe(self):
        report = validate_recipes.validate_recipe_file(RECIPE_PATH)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["node_count"], 15)


if __name__ == "__main__":
    unittest.main()
