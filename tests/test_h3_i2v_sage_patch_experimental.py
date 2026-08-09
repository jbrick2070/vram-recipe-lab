import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from scratch import build_h3_i2v_sage_patch_experimental as builder
from validate_recipes import topology_contract_errors, validate_recipe_file


ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = ROOT / "recipes" / "h3_i2v_sage_patch_fp16pv_experimental.json"


def difference_paths(left: Any, right: Any, path: str = "") -> set[str]:
    if type(left) is not type(right):
        return {path or "<root>"}
    if isinstance(left, dict):
        paths: set[str] = set()
        for key in set(left) | set(right):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                paths.add(child)
            else:
                paths.update(difference_paths(left[key], right[key], child))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return {path}
        paths: set[str] = set()
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            paths.update(
                difference_paths(left_item, right_item, f"{path}[{index}]")
            )
        return paths
    return set() if left == right else {path}


class H3I2VSagePatchExperimentalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = RECIPE_PATH.read_bytes()
        cls.recipe = json.loads(cls.raw.decode("utf-8"))
        cls.base_raw = builder.BASE_RECIPE.read_bytes()
        cls.base = json.loads(cls.base_raw.decode("utf-8"))

    def test_builder_matches_canonical_utf8_lf_recipe(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.raw.endswith(b"\n"))
        self.assertNotIn(b"\r\n", self.raw)
        self.assertEqual(
            hashlib.sha256(self.base_raw).hexdigest(),
            builder.EXPECTED_BASE_RECIPE_SHA256,
        )
        self.assertEqual(self.recipe, builder.build_recipe())

    def test_execution_graph_diff_is_only_patch_edges_node_and_unique_prefix(self):
        self.assertEqual(
            difference_paths(self.base["prompt"], self.recipe["prompt"]),
            {
                "16",
                "6.inputs.model[0]",
                "14.inputs.model[0]",
                "12.inputs.filename_prefix",
            },
        )
        prompt = self.recipe["prompt"]
        self.assertEqual(
            prompt["16"],
            {
                "class_type": "PathchSageAttentionKJ",
                "inputs": {
                    "model": ["1", 0],
                    "sage_attention": "sageattn_qk_int8_pv_fp16_cuda",
                    "allow_compile": False,
                },
            },
        )
        self.assertEqual(prompt["6"]["inputs"]["model"], ["16", 0])
        self.assertEqual(prompt["14"]["inputs"]["model"], ["16", 0])
        self.assertEqual(
            prompt["12"]["inputs"]["filename_prefix"], builder.OUTPUT_PREFIX
        )

    def test_same_canvas_pair_keeps_all_sampling_and_content_inputs_exact(self):
        prompt = self.recipe["prompt"]
        base_prompt = self.base["prompt"]
        for node_id in ("1", "2", "3", "4", "5", "7", "8", "9", "10", "11", "13", "15"):
            self.assertEqual(prompt[node_id], base_prompt[node_id])
        self.assertEqual(prompt["5"]["inputs"]["noise_seed"], 42)
        self.assertEqual(prompt["7"]["inputs"]["length"], 124)
        self.assertEqual(prompt["7"]["inputs"]["width"], 864)
        self.assertEqual(prompt["7"]["inputs"]["height"], 480)
        self.assertEqual(
            prompt["7"]["inputs"]["prompt"], base_prompt["7"]["inputs"]["prompt"]
        )
        for field in ("width", "height", "frames", "fps", "duration_s", "requires_audio", "vram_ceiling_gb"):
            self.assertEqual(
                self.recipe["contract"][field], self.base["contract"][field]
            )
        self.assertEqual(
            self.recipe["contract"]["required_boot_lane"], "lab-8199, sage-free"
        )

    def test_patch_is_per_model_and_boot_default_remains_sage_free(self):
        source = builder.KJ_NODE_SOURCE.read_text(encoding="utf-8")
        registry = builder.KJ_REGISTRY_SOURCE.read_text(encoding="utf-8")
        self.assertIn("class PathchSageAttentionKJ", source)
        self.assertIn('"PathchSageAttentionKJ"', registry)
        self.assertIn("model_clone = model.clone()", source)
        self.assertIn(
            'model_clone.model_options["transformer_options"]["optimized_attention_override"]',
            source,
        )
        self.assertIn("return model_clone,", source)
        self.assertIn(builder.SAGE_MODE, source)
        self.assertEqual(
            builder.sha256_file(builder.KJ_NODE_SOURCE),
            builder.EXPECTED_KJ_NODE_SOURCE_SHA256,
        )
        self.assertEqual(
            builder.sha256_file(builder.KJ_REGISTRY_SOURCE),
            builder.EXPECTED_KJ_REGISTRY_SOURCE_SHA256,
        )

        executable_boot = "\n".join(
            line
            for line in builder.BOOT_SCRIPT.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().lower().startswith("rem ")
        )
        self.assertNotIn("--use-sage-attention", executable_boot)
        patch = self.recipe["experiment"]["attention_patch"]
        self.assertFalse(patch["global_boot_flag_enabled"])
        self.assertFalse(patch["global_default_changed"])
        self.assertFalse(patch["allow_compile"])

    def test_local_sage_source_has_explicit_mode_and_sm120_evidence(self):
        core = builder.SAGE_CORE_SOURCE.read_text(encoding="utf-8")
        self.assertIn("def sageattn_qk_int8_pv_fp16_cuda(", core)
        self.assertIn('elif arch == "sm120"', core)
        self.assertEqual(
            builder.sha256_file(builder.SAGE_CORE_SOURCE),
            builder.EXPECTED_SAGE_CORE_SOURCE_SHA256,
        )
        sage = self.recipe["experiment"]["speed_stack_inventory"][
            "per_model_sage_fp16pv"
        ]
        self.assertEqual(
            sage["status"], "BUILDABLE_UNRENDERED_HUMAN_GATE_REQUIRED"
        )
        self.assertTrue(sage["buildable"])

    def test_missing_turbo_components_are_explicitly_blocked(self):
        inventory = self.recipe["experiment"]["speed_stack_inventory"]
        w4a8 = inventory["kijai_h3_w4a8_mixed"]
        self.assertEqual(w4a8["status"], "BLOCKED_MISSING_WEIGHT")
        self.assertFalse(w4a8["buildable"])
        self.assertIsNone(w4a8["local_filename"])
        self.assertIsNone(w4a8["sha256"])

        lightx = inventory["h3_lightx2v_four_step"]
        self.assertEqual(lightx["status"], "BLOCKED_MISSING_LORA")
        self.assertFalse(lightx["buildable"])
        self.assertIsNone(lightx["local_filename"])
        self.assertIsNone(lightx["sha256"])
        confusable = lightx["confusable_local_wan_lora"]
        self.assertEqual(confusable["block_count"], 40)
        self.assertEqual(confusable["block_range"], [0, 39])
        self.assertEqual(confusable["bytes"], builder.WAN_LIGHTX_SIZE)
        self.assertEqual(
            builder.sha256_file(builder.MODEL_ROOT / "loras" / builder.WAN_LIGHTX_NAME),
            builder.WAN_LIGHTX_SHA256,
        )

        current = inventory["current_h3_i2v_weight"]
        self.assertEqual(current["bytes"], builder.FL2VA_SIZE)
        self.assertEqual(current["sha256"], builder.FL2VA_SHA256)
        self.assertEqual(current["quantization"]["quant_record_count"], 200)
        self.assertEqual(
            current["quantization"]["quant_record"],
            {
                "format": "int8_tensorwise",
                "convrot": True,
                "convrot_groupsize": 256,
            },
        )

    def test_human_gate_is_mandatory_and_machine_pass_is_insufficient(self):
        gate = self.recipe["experiment"]["human_gate"]
        self.assertEqual(gate["status"], "pending")
        self.assertTrue(gate["mandatory"])
        self.assertTrue(gate["machine_pass_is_insufficient"])
        receipt_gate = self.recipe["receipt_requirements"]["human_visual_gate"]
        self.assertEqual(receipt_gate["status"], "pending_human")
        self.assertEqual(receipt_gate["pass_values"]["eyeball"], "ok")
        self.assertEqual(
            receipt_gate["pass_values"]["eyeball_source"], "human"
        )

    def test_topology_contract_and_offline_validator_accept_recipe(self):
        topology = self.recipe["topology_contract"]
        self.assertEqual(topology["required_nodes"]["16"], builder.PATCH_CLASS_TYPE)
        self.assertEqual(topology["required_connections"]["16.model"], ["1", 0])
        self.assertEqual(topology["required_connections"]["6.model"], ["16", 0])
        self.assertEqual(topology["required_connections"]["14.model"], ["16", 0])
        self.assertEqual(
            topology_contract_errors(self.recipe, self.recipe["prompt"]), []
        )
        report = validate_recipe_file(RECIPE_PATH)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["node_count"], 16)

    def test_immutable_writer_is_idempotent_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertTrue(builder.write_recipe(output))
            path = output / f"{builder.RECIPE_NAME}.json"
            first = path.read_bytes()
            self.assertFalse(builder.write_recipe(output))
            self.assertEqual(path.read_bytes(), first)
            path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(RuntimeError, "Immutable generated recipe differs"):
                builder.write_recipe(output)


if __name__ == "__main__":
    unittest.main()
