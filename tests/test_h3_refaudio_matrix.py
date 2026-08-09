import copy
import importlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import validate_recipes
from scratch import build_clean_h3_recipes as clean_builder
from scratch import build_h3_refaudio_matrix as matrix


ROOT = Path(__file__).resolve().parents[1]


class H3RefAudioMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipes = matrix.build_matrix()
        cls.by_name = {recipe["name"]: recipe for recipe in cls.recipes}

    def test_exact_three_recipe_identities(self):
        self.assertEqual(
            set(self.by_name),
            {
                "h3_r2v_refaudio_static_control",
                "h3_r2v_refaudio_tts_dialogue",
                "h3_r2v_refaudio_music_opening",
            },
        )
        self.assertTrue(all(recipe["tier"] == "experiment" for recipe in self.recipes))
        self.assertTrue(all(recipe["blocked"] is False for recipe in self.recipes))

    def test_clean_r2v_builder_and_committed_recipes_use_flat_v3_sockets(self):
        for tier, width, height in (("low", 864, 480), ("best", 1344, 768)):
            path = ROOT / "recipes" / f"h3_r2v_{tier}.json"
            recipe = json.loads(path.read_text(encoding="utf-8"))
            generated = clean_builder.make_h3_prompt(
                "r2v", width, height, 124, is_best=(tier == "best")
            )
            self.assertEqual(recipe["prompt"], generated)
            inputs = recipe["prompt"]["7"]["inputs"]
            self.assertEqual(inputs["ref_images.ref_image_0"], ["11", 0])
            self.assertNotIn("ref_images", inputs)

        topology = clean_builder.make_topology_contract("r2v")
        self.assertEqual(
            topology["required_connections"]["7.ref_images.ref_image_0"],
            ["11", 0],
        )
        self.assertNotIn("7.ref_images", topology["required_connections"])

    def test_committed_recipe_bytes_are_canonical_builder_output(self):
        for recipe in self.recipes:
            path = ROOT / "recipes" / f"{recipe['name']}.json"
            self.assertTrue(path.is_file(), path)
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(raw, matrix.canonical_json_bytes(recipe))
            self.assertEqual(json.loads(raw.decode("utf-8")), recipe)

    def test_standard_paper_validator_accepts_every_cell(self):
        for recipe in self.recipes:
            path = ROOT / "recipes" / f"{recipe['name']}.json"
            result = validate_recipes.validate_recipe_file(path)
            self.assertTrue(result["valid"], result["errors"])
            self.assertEqual(result["warnings"], [])
            self.assertEqual(result["node_count"], 17)

    def test_topology_contract_accepts_every_cell(self):
        for recipe in self.recipes:
            self.assertEqual(
                validate_recipes.topology_contract_errors(recipe, recipe["prompt"]),
                [],
            )

    def test_extra_valid_flat_reference_socket_fails_enforced_topology_gate(self):
        clean_r2v = json.loads(
            (ROOT / "recipes" / "h3_r2v_best.json").read_text(encoding="utf-8")
        )
        cases = (
            (clean_r2v, "ref_videos.ref_video_0", ["11", 0]),
            (self.recipes[0], "ref_audios.ref_audio_1", ["16", 0]),
        )
        for source, socket, link in cases:
            with self.subTest(recipe=source["name"], socket=socket):
                recipe = copy.deepcopy(source)
                recipe["prompt"]["7"]["inputs"][socket] = link
                errors = validate_recipes.topology_contract_errors(
                    recipe, recipe["prompt"]
                )
                expected = f"7.{socket} must be absent"
                self.assertTrue(any(expected in error for error in errors), errors)

                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / f"{recipe['name']}.json"
                    path.write_bytes((json.dumps(recipe, indent=2) + "\n").encode("utf-8"))
                    report = validate_recipes.validate_recipe_file(path)
                self.assertFalse(report["valid"], report)
                self.assertTrue(
                    any(expected in error for error in report["errors"]),
                    report["errors"],
                )

    def test_exact_node_set_and_classes(self):
        for recipe in self.recipes:
            actual = {
                node_id: node["class_type"]
                for node_id, node in recipe["prompt"].items()
            }
            self.assertEqual(actual, matrix.EXPERIMENT_NODE_CLASSES)
            self.assertEqual(
                recipe["topology_contract"]["required_nodes"],
                matrix.EXPERIMENT_NODE_CLASSES,
            )

    def test_shared_generation_settings_are_frozen(self):
        for recipe in self.recipes:
            contract = recipe["contract"]
            prompt = recipe["prompt"]
            self.assertEqual(
                (contract["width"], contract["height"], contract["frames"]),
                (864, 480, 124),
            )
            self.assertEqual(contract["fps"], 24.0)
            self.assertEqual(contract["vram_ceiling_gb"], 14.5)
            self.assertEqual(contract["required_boot_lane"], "lab-8199, sage-free")
            self.assertEqual(prompt["5"]["inputs"]["noise_seed"], 42)
            self.assertEqual(prompt["13"]["inputs"]["sampler_name"], "res_multistep")
            self.assertEqual(
                prompt["14"]["inputs"],
                {
                    "model": ["1", 0],
                    "scheduler": "simple",
                    "steps": 20,
                    "denoise": 1.0,
                },
            )
            self.assertEqual(prompt["10"]["inputs"]["bit_depth"], 8)

    def test_reference_order_and_prompt_tags_are_exact(self):
        prompts = set()
        for recipe in self.recipes:
            inputs = recipe["prompt"]["7"]["inputs"]
            prompts.add(inputs["prompt"])
            self.assertEqual(inputs["ref_images.ref_image_0"], ["11", 0])
            self.assertEqual(inputs["ref_images.ref_image_1"], ["17", 0])
            self.assertEqual(inputs["ref_audios.ref_audio_0"], ["16", 0])
            self.assertNotIn("ref_images", inputs)
            self.assertNotIn("ref_audios", inputs)
            self.assertNotIn("ref_videos", inputs)
            self.assertNotIn("ref_video_audios", inputs)
            self.assertNotIn("first_frame", inputs)
            self.assertNotIn("last_frame", inputs)
            tags = set(re.findall(r"<(?:Picture|Video|Audio) \d+>", inputs["prompt"]))
            self.assertEqual(tags, {"<Picture 1>", "<Picture 2>", "<Audio 1>"})
        self.assertEqual(prompts, {matrix.SHARED_PROMPT})

    def test_exact_absent_dynamic_sockets(self):
        expected_absent = {
            *(f"7.ref_images.ref_image_{index}" for index in range(2, 9)),
            *(f"7.ref_videos.ref_video_{index}" for index in range(3)),
            *(f"7.ref_video_audios.ref_video_audio_{index}" for index in range(3)),
            *(f"7.ref_audios.ref_audio_{index}" for index in range(1, 3)),
        }
        for recipe in self.recipes:
            topology = recipe["topology_contract"]
            self.assertEqual(set(topology["required_absent_sockets"]), expected_absent)
            inputs = recipe["prompt"]["7"]["inputs"]
            self.assertEqual(
                {key for key in inputs if key.startswith("ref_images.")},
                {"ref_images.ref_image_0", "ref_images.ref_image_1"},
            )
            self.assertEqual(
                {key for key in inputs if key.startswith("ref_audios.")},
                {"ref_audios.ref_audio_0"},
            )

    def test_installed_comfy_parser_consumes_flat_autogrow_and_ignores_nested(self):
        comfy_root = matrix.INSTALLED_COMFY_ROOT
        self.assertTrue((comfy_root / "execution.py").is_file())
        root_text = str(comfy_root)
        added = root_text not in sys.path
        if added:
            sys.path.insert(0, root_text)
        try:
            comfy_execution = importlib.import_module("execution")
            h3_nodes = importlib.import_module("comfy_extras.nodes_minimax_h3")
            class_def = h3_nodes.MiniMaxH3ReferenceToVideo

            flat = copy.deepcopy(self.recipes[0]["prompt"]["7"]["inputs"])
            nested = copy.deepcopy(flat)
            nested["ref_images"] = {
                "ref_image_0": nested.pop("ref_images.ref_image_0"),
                "ref_image_1": nested.pop("ref_images.ref_image_1"),
            }
            nested["ref_audios"] = {
                "ref_audio_0": nested.pop("ref_audios.ref_audio_0")
            }

            flat_data, flat_missing, flat_v3 = comfy_execution.get_input_data(
                flat, class_def, "7"
            )
            nested_data, _, nested_v3 = comfy_execution.get_input_data(
                nested, class_def, "7"
            )
        finally:
            if added:
                sys.path.remove(root_text)

        expected_sockets = {
            "ref_images.ref_image_0",
            "ref_images.ref_image_1",
            "ref_audios.ref_audio_0",
        }
        self.assertTrue(expected_sockets.issubset(flat_data))
        self.assertTrue(expected_sockets.issubset(flat_missing))
        self.assertTrue(expected_sockets.issubset(flat_v3["dynamic_paths"]))
        self.assertTrue(expected_sockets.isdisjoint(nested_data))
        self.assertTrue(expected_sockets.isdisjoint(nested_v3["dynamic_paths"]))
        self.assertNotIn("ref_images", nested_data)
        self.assertNotIn("ref_audios", nested_data)

    def test_reference_audio_has_only_the_conditioning_consumer(self):
        for recipe in self.recipes:
            prompt = recipe["prompt"]
            self.assertEqual(
                matrix.source_consumers(prompt, "16"),
                {("7", "ref_audios.ref_audio_0")},
            )
            self.assertEqual(prompt["16"]["class_type"], "LoadAudio")
            self.assertEqual(prompt["7"]["class_type"], "MiniMaxH3ReferenceToVideo")

    def test_builder_rejects_legacy_nested_autogrow_links_as_dead_sources(self):
        recipe = copy.deepcopy(self.recipes[0])
        inputs = recipe["prompt"]["7"]["inputs"]
        inputs["ref_images"] = {
            "ref_image_0": inputs.pop("ref_images.ref_image_0"),
            "ref_image_1": inputs.pop("ref_images.ref_image_1"),
        }
        inputs["ref_audios"] = {
            "ref_audio_0": inputs.pop("ref_audios.ref_audio_0")
        }
        cell = next(cell for cell in matrix.CELLS if cell.recipe_name == recipe["name"])
        with self.assertRaisesRegex(RuntimeError, "flat dotted sockets"):
            matrix.validate_recipe(recipe, cell)
        with self.assertRaisesRegex(RuntimeError, "nodes do not reach SaveVideo"):
            matrix.validate_dag(recipe["prompt"], recipe["name"])

    def test_saved_audio_is_only_sampled_target_latent_decode(self):
        for recipe in self.recipes:
            prompt = recipe["prompt"]
            self.assertEqual(prompt["8"]["inputs"]["latent_image"], ["7", 1])
            self.assertEqual(
                prompt["15"]["inputs"],
                {"samples": ["8", 0], "vae": ["4", 0]},
            )
            self.assertEqual(prompt["10"]["inputs"]["audio"], ["15", 0])
            self.assertNotEqual(prompt["10"]["inputs"]["audio"], ["16", 0])
            self.assertFalse(recipe["experiment"]["external_source_mux"])
            self.assertFalse(
                recipe["topology_contract"]["audio_path_contract"]["external_source_mux"]
            )

    def test_every_node_is_acyclic_and_reaches_savevideo(self):
        for recipe in self.recipes:
            matrix.validate_dag(recipe["prompt"], recipe["name"])

    def test_pairwise_diff_is_identity_audio_and_prefix_only(self):
        for index, left in enumerate(self.recipes):
            for right in self.recipes[index + 1 :]:
                paths = matrix.difference_paths(left, right)
                self.assertIn("name", paths)
                self.assertIn("prompt.16.inputs.audio", paths)
                self.assertIn("prompt.12.inputs.filename_prefix", paths)
                self.assertTrue(any(path.startswith("experiment.") for path in paths))
                self.assertTrue(
                    all(matrix.pairwise_path_is_allowed(path) for path in paths),
                    sorted(paths),
                )
                self.assertEqual(
                    matrix.normalized_recipe(left),
                    matrix.normalized_recipe(right),
                )

    def test_conditioning_wavs_are_exact_receipt_bound_3p88s_cells(self):
        cells = {cell.recipe_name: cell for cell in matrix.CELLS}
        for recipe in self.recipes:
            cell = cells[recipe["name"]]
            receipt, receipt_bytes = matrix.load_audio_receipt(cell)
            self.assertEqual(
                recipe["prompt"]["16"]["inputs"]["audio"],
                cell.conditioning_fixture,
            )
            self.assertEqual(receipt["ffprobe"]["duration_s"], 3.88)
            self.assertEqual(receipt["ffprobe"]["duration_samples"], 124160)
            self.assertEqual(receipt["ffprobe"]["sample_rate_hz"], 32000)
            self.assertEqual(receipt["ffprobe"]["channels"], 1)
            self.assertEqual(
                recipe["experiment"]["conditioning_receipt_sha256"],
                matrix.sha256_bytes(receipt_bytes),
            )

    def test_model_stack_matches_local_manifest_names(self):
        manifest = (ROOT / "models_manifest.md").read_text(encoding="utf-8")
        for model_name in (
            matrix.UNET_NAME,
            matrix.CLIP_NAME,
            matrix.VIDEO_VAE_NAME,
            matrix.AUDIO_VAE_NAME,
        ):
            self.assertIn(model_name, manifest)
        for recipe in self.recipes:
            prompt = recipe["prompt"]
            self.assertEqual(prompt["1"]["inputs"]["unet_name"], matrix.UNET_NAME)
            self.assertEqual(prompt["2"]["inputs"]["clip_name"], matrix.CLIP_NAME)
            self.assertEqual(prompt["3"]["inputs"]["vae_name"], matrix.VIDEO_VAE_NAME)
            self.assertEqual(prompt["4"]["inputs"]["vae_name"], matrix.AUDIO_VAE_NAME)

    def test_frozen_template_base_recipe_and_installed_schema_are_pinned(self):
        self.assertEqual(
            matrix.sha256_file(matrix.BASE_RECIPE),
            matrix.EXPECTED_BASE_RECIPE_SHA256,
        )
        self.assertEqual(
            matrix.sha256_file(matrix.FROZEN_TEMPLATE),
            matrix.EXPECTED_FROZEN_TEMPLATE_SHA256,
        )
        self.assertEqual(
            matrix.sha256_file(matrix.INSTALLED_NODE_SOURCE),
            matrix.EXPECTED_INSTALLED_NODE_SOURCE_SHA256,
        )
        matrix.validate_installed_schema()

    def test_evidence_metadata_records_unlicensed_sources_as_uncopied(self):
        evidence = self.recipes[0]["topology_contract"]["evidence"]
        self.assertIn("Unlicensed community JSON", evidence["no_license_caveat"])
        unlicensed = [
            item
            for group in (
                "community_topology_evidence_only",
                "rejected_as_implementation_source",
            )
            for item in evidence[group]
            if item.get("license") == "no repository license found"
        ]
        self.assertTrue(unlicensed)
        self.assertTrue(all(item["copied"] is False for item in unlicensed))

    def test_builder_is_idempotent_and_refuses_immutable_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = matrix.write_all(output)
            first_bytes = {
                path.name: path.read_bytes() for path in output.glob("*.json")
            }
            second = matrix.write_all(output)
            second_bytes = {
                path.name: path.read_bytes() for path in output.glob("*.json")
            }
            self.assertTrue(all(first.values()))
            self.assertTrue(all(changed is False for changed in second.values()))
            self.assertEqual(first_bytes, second_bytes)

            victim = output / "h3_r2v_refaudio_tts_dialogue.json"
            modified = copy.deepcopy(json.loads(victim.read_text(encoding="utf-8")))
            modified["prompt"]["5"]["inputs"]["noise_seed"] = 43
            victim.write_text(json.dumps(modified), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Immutable generated recipe differs"):
                matrix.write_all(output)


if __name__ == "__main__":
    unittest.main()
