import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scratch" / "build_humo_14b_diet.py"
SPEC = importlib.util.spec_from_file_location("build_humo_14b_diet", MODULE_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class HuMo14BDietRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = {
            path: path.read_bytes() for path in (builder.PORTRAIT_RECIPE, builder.LANDSCAPE_RECIPE)
        }
        cls.recipes = {
            path: json.loads(raw.decode("utf-8")) for path, raw in cls.raw.items()
        }
        cls.portrait = cls.recipes[builder.PORTRAIT_RECIPE]
        cls.landscape = cls.recipes[builder.LANDSCAPE_RECIPE]

    def test_generated_bytes_are_reproducible_utf8_without_bom(self):
        generated = builder.build_all()
        self.assertEqual(set(generated), set(self.raw))
        for path, raw in self.raw.items():
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(raw, generated[path])

    def test_every_static_source_class_model_and_fixture_is_present(self):
        inventory = builder.verify_static_inventory()
        self.assertEqual(
            inventory["models_manifest_sha256"], builder.MANIFEST_SHA256
        )
        self.assertEqual(set(inventory["models"]), set(builder.MODEL_ASSETS))
        self.assertEqual(
            inventory["required_classes"], sorted(builder.CLASS_SOURCES)
        )
        self.assertEqual(inventory["manager_network_mode"], "offline")
        for model in inventory["models"].values():
            self.assertTrue(model["manifest_present"])
            self.assertTrue(model["disk_present"])

    def test_exact_bakeoff_models_sampler_seed_and_fixtures(self):
        for recipe in (self.portrait, self.landscape):
            prompt = recipe["prompt"]
            self.assertEqual(
                prompt["1"]["inputs"],
                {
                    "unet_name": "Wan2_1-HuMo-14B_fp8_e4m3fn_scaled_KJ.safetensors",
                    "weight_dtype": "default",
                },
            )
            self.assertEqual(
                prompt["11"]["inputs"],
                {
                    "lora_name": "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
                    "strength_model": 1.0,
                    "model": ["1", 0],
                },
            )
            sampler = prompt["13"]["inputs"]
            self.assertEqual(
                {
                    key: sampler[key]
                    for key in (
                        "seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"
                    )
                },
                {
                    "seed": 7,
                    "steps": 6,
                    "cfg": 1.0,
                    "sampler_name": "uni_pc",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            )
            self.assertEqual(prompt["3"]["inputs"]["text"], builder.POSITIVE)
            self.assertEqual(prompt["4"]["inputs"]["text"], builder.NEGATIVE)
            self.assertEqual(prompt["6"]["inputs"]["audio"], "tts_dialogue.wav")
            self.assertEqual(prompt["9"]["inputs"]["image"], "portrait.png")
            self.assertEqual(
                recipe["topology_contract"]["fixture_hashes"], builder.FIXTURE_HASHES
            )

    def test_orientation_is_the_only_generation_pair_variable(self):
        pp = self.portrait["prompt"]
        lp = self.landscape["prompt"]
        self.assertEqual(
            (pp["10"]["inputs"]["width"], pp["10"]["inputs"]["height"]),
            (480, 832),
        )
        self.assertEqual(
            (lp["10"]["inputs"]["width"], lp["10"]["inputs"]["height"]),
            (832, 480),
        )
        self.assertEqual(pp["10"]["inputs"]["length"], 97)
        self.assertEqual(lp["10"]["inputs"]["length"], 97)
        self.assertEqual(builder.normalized_pair_prompt(pp), builder.normalized_pair_prompt(lp))
        self.assertEqual(480 * 832, 832 * 480)

    def test_bakeoff_source_and_dimension_mapper_are_hash_pinned(self):
        for recipe in (self.portrait, self.landscape):
            evidence = recipe["topology_contract"]["source_graph_evidence"]
            self.assertEqual(evidence["otr_bakeoff_commit"], builder.OTR_BAKEOFF_COMMIT)
            self.assertEqual(
                evidence["engine_source_sha256"],
                builder.OTR_SOURCE_HASHES["nodes/_otr_video_engines/eng_humo.py"],
            )
            self.assertEqual(
                evidence["request_source_sha256"],
                builder.OTR_SOURCE_HASHES["nodes/_otr_video_engines/render_driver.py"],
            )
            self.assertEqual(evidence["dimension_source"], "nodes/_otr_shared/aspect.py")
            self.assertEqual(
                evidence["dimension_source_sha256"],
                builder.OTR_SOURCE_HASHES["nodes/_otr_shared/aspect.py"],
            )

    def test_engine_ids_and_production_comparator_are_explicit(self):
        self.assertEqual(self.portrait["contract"]["engine_id"], "humo")
        self.assertEqual(
            self.landscape["contract"]["engine_id"], "humo_14B_169"
        )
        self.assertEqual(
            self.portrait["experiment"]["production_comparator_clip"],
            "outputs/humo_14b_fp8_bakeoff_take1.mp4",
        )
        self.assertIsNone(
            self.landscape["experiment"]["production_comparator_clip"]
        )

    def test_direct_reserve_boot_and_cold_warm_contract(self):
        for recipe in (self.portrait, self.landscape):
            contract = recipe["contract"]
            boot = contract["diet_boot"]
            self.assertEqual(boot["reserve_vram_gib"], 2.921)
            self.assertEqual(
                boot["comfyui_argv_delta"],
                ["--reserve-vram", "2.921", "--disable-pinned-memory"],
            )
            self.assertNotIn("--clamp", boot["comfyui_argv_delta"])
            self.assertTrue(boot["disable_pinned_memory"])
            self.assertEqual(boot["manager_network_mode_before_boot"], "offline")
            self.assertEqual(contract["same_server_consecutive_runs"], 2)
            self.assertTrue(contract["fresh_server_per_orientation"])
            plan = contract["execution_plan"]
            self.assertEqual([leg["role"] for leg in plan], ["cold", "warm"])
            self.assertTrue(plan[0]["fresh_server"])
            self.assertFalse(plan[1]["fresh_server"])
            self.assertEqual(
                len({leg["executor_cache_nonce"] for leg in plan}), 2
            )

    def test_source_audio_conditions_and_is_delivered_after_decode(self):
        for recipe in (self.portrait, self.landscape):
            prompt = recipe["prompt"]
            self.assertEqual(prompt["8"]["inputs"]["audio"], ["6", 0])
            self.assertEqual(
                prompt["10"]["inputs"]["audio_encoder_output"], ["8", 0]
            )
            self.assertEqual(prompt["15"]["inputs"]["images"], ["14", 0])
            self.assertEqual(prompt["15"]["inputs"]["audio"], ["6", 0])
            audio = recipe["topology_contract"]["audio_path_contract"]
            self.assertTrue(audio["same_source_node_for_conditioning_and_delivery"])
            self.assertFalse(audio["delivery_tail_changes_generation"])

    def test_topology_freezes_values_links_source_projection_and_reachability(self):
        for recipe in (self.portrait, self.landscape):
            prompt = recipe["prompt"]
            topology = recipe["topology_contract"]
            self.assertEqual(
                topology["required_connections"], builder.required_connections(prompt)
            )
            self.assertEqual(
                topology["required_input_values"], builder.required_input_values(prompt)
            )
            self.assertEqual(
                topology["source_graph_evidence"]["source_graph_projection_sha256"],
                builder.canonical_sha256(builder.source_graph_projection(prompt)),
            )
            self.assertEqual(
                topology["source_graph_evidence"]["source_graph_node_count"], 14
            )
            reachable = {topology["terminal_node"]}
            stack = [topology["terminal_node"]]
            while stack:
                node_id = stack.pop()
                for value in prompt[node_id]["inputs"].values():
                    if (
                        isinstance(value, list)
                        and len(value) == 2
                        and isinstance(value[0], str)
                        and value[0] not in reachable
                    ):
                        reachable.add(value[0])
                        stack.append(value[0])
            self.assertEqual(reachable, set(prompt))

    def test_no_recipe_declares_rendered_or_passing_evidence(self):
        for recipe in (self.portrait, self.landscape):
            self.assertFalse(recipe["blocked"])
            self.assertEqual(recipe["experiment"]["render_status"], "unrendered")
            self.assertEqual(
                recipe["experiment"]["behavioral_claim_status"], "unmeasured"
            )
            self.assertEqual(
                recipe["receipt_requirements"]["quality_gate"]["status"],
                "PENDING_HUMAN",
            )


if __name__ == "__main__":
    unittest.main()
