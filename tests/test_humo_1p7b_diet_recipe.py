import ast
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scratch" / "build_humo_1p7b_diet.py"
SPEC = importlib.util.spec_from_file_location("build_humo_1p7b_diet", MODULE_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

RECIPE_PATH = ROOT / "recipes" / "humo_1p7b_diet.json"


class HuMoDietRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = RECIPE_PATH.read_bytes()
        cls.recipe = json.loads(cls.raw.decode("utf-8"))
        cls.prompt = cls.recipe["prompt"]

    def test_generated_bytes_are_reproducible_utf8_without_bom(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.raw, builder.serialized_recipe(builder.build_recipe()))

    def test_frozen_source_and_fixture_identities_are_current(self):
        builder.verify_frozen_sources()
        evidence = self.recipe["topology_contract"]["source_graph_evidence"]
        self.assertEqual(evidence["otr_commit"], builder.OTR_COMMIT)
        self.assertEqual(
            evidence["engine_source_sha256"],
            builder.OTR_SOURCE_HASHES["nodes/_otr_video_engines/eng_humo.py"],
        )
        self.assertEqual(
            evidence["request_source_sha256"],
            builder.OTR_SOURCE_HASHES[
                "nodes/_otr_video_engines/render_driver.py"
            ],
        )
        self.assertEqual(
            self.recipe["topology_contract"]["fixture_hashes"],
            builder.FIXTURE_HASHES,
        )

    def test_load_bearing_otr_source_literals_are_present(self):
        engine_path = builder.OTR_ROOT / "nodes/_otr_video_engines/eng_humo.py"
        request_path = builder.OTR_ROOT / "nodes/_otr_video_engines/render_driver.py"
        engine_text = engine_path.read_text(encoding="utf-8")
        request_text = request_path.read_text(encoding="utf-8")
        ast.parse(engine_text)
        ast.parse(request_text)
        for literal in (
            '"humo_1.7B_fp16.safetensors"',
            '"umt5_xxl_fp8_e4m3fn_scaled.safetensors"',
            '"wan_2.1_vae.safetensors"',
            '"whisper_large_v3_fp16.safetensors"',
            '"WanHuMoImageToVideo"',
            '"uni_pc"',
            '"simple"',
            '"20"',
            '"1.0"',
            '"none"',
        ):
            self.assertIn(literal, engine_text)
        self.assertIn(builder.POSITIVE, request_text)
        self.assertIn("seed = (idx * 1009 + 7)", request_text)

    def test_exact_production_graph_plus_two_delivery_nodes(self):
        expected_map = builder.OTR_TO_LAB_NODE_MAP
        evidence = self.recipe["topology_contract"]["source_graph_evidence"]
        self.assertEqual(evidence["source_graph_node_count"], 13)
        self.assertEqual(set(expected_map.values()), {str(i) for i in range(1, 14)})
        self.assertEqual(set(self.prompt), {str(i) for i in range(1, 16)})
        self.assertEqual(
            evidence["source_graph_projection_sha256"],
            builder.canonical_sha256(builder.source_graph_projection(self.prompt)),
        )
        self.assertEqual(
            evidence["lab_only_delivery_nodes"],
            {"14": "CreateVideo", "15": "SaveVideo"},
        )
        for source_id, lab_id in expected_map.items():
            pair = evidence["source_to_lab_node_pairs"][source_id]
            self.assertEqual(pair["lab_node"], lab_id)
            self.assertEqual(pair["class_type"], self.prompt[lab_id]["class_type"])

    def test_production_settings_are_exact_and_lora_is_absent(self):
        self.assertEqual(
            self.prompt["1"]["inputs"],
            {
                "unet_name": "humo_1.7B_fp16.safetensors",
                "weight_dtype": "default",
            },
        )
        self.assertEqual(
            self.prompt["2"]["inputs"],
            {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default",
            },
        )
        self.assertEqual(self.prompt["3"]["inputs"]["text"], builder.POSITIVE)
        self.assertEqual(self.prompt["4"]["inputs"]["text"], builder.NEGATIVE)
        self.assertEqual(
            self.prompt["10"]["inputs"],
            {
                "width": 480,
                "height": 832,
                "length": 129,
                "batch_size": 1,
                "positive": ["3", 0],
                "negative": ["4", 0],
                "vae": ["5", 0],
                "audio_encoder_output": ["8", 0],
                "ref_image": ["9", 0],
            },
        )
        sampler = self.prompt["12"]["inputs"]
        self.assertEqual(
            {key: sampler[key] for key in (
                "seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"
            )},
            {
                "seed": 7,
                "steps": 20,
                "cfg": 1.0,
                "sampler_name": "uni_pc",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        )
        classes = {node["class_type"] for node in self.prompt.values()}
        self.assertNotIn("LoraLoaderModelOnly", classes)
        self.assertNotIn("VAEDecodeTiled", classes)

    def test_source_audio_conditions_and_is_delivered_only_after_decode(self):
        self.assertEqual(self.prompt["6"]["inputs"]["audio"], "tts_dialogue.wav")
        self.assertEqual(self.prompt["8"]["inputs"]["audio"], ["6", 0])
        self.assertEqual(
            self.prompt["10"]["inputs"]["audio_encoder_output"], ["8", 0]
        )
        self.assertEqual(self.prompt["14"]["inputs"]["audio"], ["6", 0])
        self.assertEqual(self.prompt["14"]["inputs"]["images"], ["13", 0])
        audio_contract = self.recipe["topology_contract"]["audio_path_contract"]
        self.assertTrue(audio_contract["same_source_node_for_conditioning_and_delivery"])
        self.assertFalse(audio_contract["delivery_tail_changes_generation"])
        self.assertEqual(audio_contract["production_native_output"], "silent by OTR policy")

    def test_clamp_floor_contract_has_zero_graph_changes_and_warm_two(self):
        experiment = self.recipe["experiment"]
        contract = self.recipe["contract"]
        self.assertEqual(experiment["independent_variable"], "boot_lane_target_card_budget_gb")
        self.assertEqual(experiment["single_variable_order"], [13.0, 12.0])
        self.assertEqual(
            experiment["execution_order"],
            [
                {"target_card_budget_gb": 13.0, "same_server_consecutive_runs": 2},
                {"target_card_budget_gb": 12.0, "same_server_consecutive_runs": 2},
            ],
        )
        self.assertEqual(experiment["graph_change_count"], 0)
        self.assertEqual(contract["diet_target_peak_vram_gb"], 13.5)
        self.assertEqual(contract["vram_ceiling_gb"], 14.5)
        self.assertEqual(contract["warm_runs_required"], 2)
        self.assertIs(contract["requires_human_eyeball"], True)
        self.assertTrue(contract["requires_disable_pinned_memory"])
        self.assertEqual(
            contract["clamp_experiment"]["ordered_target_card_budgets_gb"],
            [13.0, 12.0],
        )
        self.assertEqual(contract["clamp_experiment"]["consecutive_runs_per_budget"], 2)
        self.assertTrue(contract["clamp_experiment"]["fresh_server_between_budgets"])
        self.assertEqual(len(contract["required_boot_lanes"]), 2)
        self.assertEqual(contract["frames"] / contract["fps"], 5.16)

    def test_topology_contract_freezes_all_values_links_and_reachability(self):
        topology = self.recipe["topology_contract"]
        self.assertEqual(topology["required_connections"], builder.required_connections(self.prompt))
        self.assertEqual(topology["required_input_values"], builder.required_input_values(self.prompt))
        self.assertEqual(
            topology["required_nodes"],
            {node_id: node["class_type"] for node_id, node in self.prompt.items()},
        )
        reachable = {topology["terminal_node"]}
        stack = [topology["terminal_node"]]
        while stack:
            node_id = stack.pop()
            for value in self.prompt[node_id]["inputs"].values():
                if (
                    isinstance(value, list)
                    and len(value) == 2
                    and isinstance(value[0], str)
                    and value[0] not in reachable
                ):
                    reachable.add(value[0])
                    stack.append(value[0])
        self.assertEqual(reachable, set(self.prompt))


if __name__ == "__main__":
    unittest.main()
