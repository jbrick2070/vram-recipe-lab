import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from scratch import build_h3_refaudio_exact_lipsync_pair as builder
from validate_recipes import topology_contract_errors, validate_recipe_file


ROOT = Path(__file__).resolve().parents[1]
SEED42_PATH = ROOT / "recipes" / f"{builder.SEED42_NAME}.json"
SEED43_PATH = ROOT / "recipes" / f"{builder.SEED43_NAME}.json"


class H3RefAudioExactLipSyncPairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed42_raw = SEED42_PATH.read_bytes()
        cls.seed43_raw = SEED43_PATH.read_bytes()
        cls.seed42 = json.loads(cls.seed42_raw.decode("utf-8"))
        cls.seed43 = json.loads(cls.seed43_raw.decode("utf-8"))

    def test_hash_pinned_source_and_fixture_bytes_are_unchanged(self):
        self.assertEqual(
            hashlib.sha256(builder.SOURCE_RECIPE.read_bytes()).hexdigest(),
            builder.EXPECTED_SOURCE_RECIPE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(builder.PORTRAIT_FIXTURE.read_bytes()).hexdigest(),
            builder.PORTRAIT_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(builder.TTS_FIXTURE.read_bytes()).hexdigest(),
            builder.TTS_SHA256,
        )

    def test_committed_pair_is_canonical_utf8_lf_builder_output(self):
        built42, built43 = builder.build_pair()
        self.assertEqual(self.seed42, built42)
        self.assertEqual(self.seed43, built43)
        for raw in (self.seed42_raw, self.seed43_raw):
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertTrue(raw.endswith(b"\n"))
            self.assertNotIn(b"\r\n", raw)

    def test_exact_fixture_and_reference_socket_set(self):
        for recipe in (self.seed42, self.seed43):
            prompt = recipe["prompt"]
            image_nodes = {
                node_id: node["inputs"]
                for node_id, node in prompt.items()
                if node["class_type"] == "LoadImage"
            }
            audio_nodes = {
                node_id: node["inputs"]
                for node_id, node in prompt.items()
                if node["class_type"] == "LoadAudio"
            }
            self.assertEqual(image_nodes, {"11": {"image": "portrait.png"}})
            self.assertEqual(audio_nodes, {"16": {"audio": "tts_dialogue.wav"}})
            self.assertNotIn("17", prompt)

            inputs = prompt["7"]["inputs"]
            reference_inputs = {
                key: value
                for key, value in inputs.items()
                if key.startswith((
                    "ref_images.",
                    "ref_audios.",
                    "ref_videos.",
                    "ref_video_audios.",
                ))
            }
            self.assertEqual(
                reference_inputs,
                {
                    "ref_images.ref_image_0": ["11", 0],
                    "ref_audios.ref_audio_0": ["16", 0],
                },
            )
            self.assertEqual(inputs["ref_image_size"], "match")
            self.assertEqual(
                recipe["topology_contract"]["fixture_hashes"],
                {
                    "portrait.png": builder.PORTRAIT_SHA256,
                    "tts_dialogue.wav": builder.TTS_SHA256,
                },
            )

    def test_prompt_is_exact_and_has_no_picture_two_reference(self):
        for recipe in (self.seed42, self.seed43):
            prompt = recipe["prompt"]["7"]["inputs"]["prompt"]
            self.assertEqual(prompt, builder.ACTION_PROMPT)
            self.assertEqual(
                set(re.findall(r"<(?:Picture|Video|Audio) \d+>", prompt)),
                {"<Picture 1>", "<Audio 1>"},
            )
            canonical = builder.canonical_json_bytes(recipe)
            self.assertNotIn(b"scene_still.png", canonical)
            self.assertNotIn(b"<Picture 2>", canonical)

    def test_raw_audio_is_conditioning_only_and_delivery_is_native(self):
        for recipe in (self.seed42, self.seed43):
            prompt = recipe["prompt"]
            self.assertEqual(
                builder.source_consumers(prompt, "16"),
                {("7", "ref_audios.ref_audio_0")},
            )
            audio_decoders = {
                node_id: node["inputs"]
                for node_id, node in prompt.items()
                if node["class_type"] == "VAEDecodeAudio"
            }
            self.assertEqual(
                audio_decoders,
                {"15": {"samples": ["8", 0], "vae": ["4", 0]}},
            )
            self.assertEqual(prompt["10"]["inputs"]["audio"], ["15", 0])
            self.assertNotEqual(prompt["10"]["inputs"]["audio"], ["16", 0])
            self.assertFalse(recipe["experiment"]["external_source_mux"])

    def test_official_sampler_family_scheduler_and_model_pins_survive(self):
        for recipe in (self.seed42, self.seed43):
            prompt = recipe["prompt"]
            self.assertEqual(
                prompt["13"]["inputs"], {"sampler_name": "res_multistep"}
            )
            self.assertEqual(
                prompt["14"]["inputs"],
                {
                    "model": ["1", 0],
                    "scheduler": "simple",
                    "steps": 20,
                    "denoise": 1.0,
                },
            )
            self.assertEqual(
                prompt["1"]["inputs"],
                {"unet_name": builder.UNET_NAME, "weight_dtype": "default"},
            )
            self.assertEqual(
                prompt["2"]["inputs"]["clip_name"], builder.CLIP_NAME
            )
            self.assertEqual(
                prompt["3"]["inputs"], {"vae_name": builder.VIDEO_VAE_NAME}
            )
            self.assertEqual(
                prompt["4"]["inputs"], {"vae_name": builder.AUDIO_VAE_NAME}
            )

    def test_pairwise_execution_diff_is_seed_and_prefix_only(self):
        self.assertEqual(
            builder.difference_paths(self.seed42["prompt"], self.seed43["prompt"]),
            {"5.inputs.noise_seed", "12.inputs.filename_prefix"},
        )
        self.assertEqual(self.seed42["prompt"]["5"]["inputs"]["noise_seed"], 42)
        self.assertEqual(self.seed43["prompt"]["5"]["inputs"]["noise_seed"], 43)

        seed_path, prefix_path = builder._mirrored_value_paths(self.seed42)
        self.assertEqual(
            builder.difference_paths(self.seed42, self.seed43),
            {
                "name",
                "prompt.5.inputs.noise_seed",
                "prompt.12.inputs.filename_prefix",
                seed_path,
                prefix_path,
            },
        )
        self.assertEqual(self.seed42["experiment"], self.seed43["experiment"])
        self.assertEqual(self.seed42["contract"], self.seed43["contract"])

    def test_topology_contract_and_offline_validator_accept_both(self):
        for path, recipe in (
            (SEED42_PATH, self.seed42),
            (SEED43_PATH, self.seed43),
        ):
            self.assertEqual(topology_contract_errors(recipe, recipe["prompt"]), [])
            report = validate_recipe_file(path)
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["warnings"], [])
            self.assertEqual(report["node_count"], 16)

    def test_immutable_writer_is_idempotent_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertEqual(
                builder.write_pair(output),
                {builder.SEED42_NAME: True, builder.SEED43_NAME: True},
            )
            first42 = (output / f"{builder.SEED42_NAME}.json").read_bytes()
            first43 = (output / f"{builder.SEED43_NAME}.json").read_bytes()
            self.assertEqual(
                builder.write_pair(output),
                {builder.SEED42_NAME: False, builder.SEED43_NAME: False},
            )
            self.assertEqual(
                (output / f"{builder.SEED42_NAME}.json").read_bytes(), first42
            )
            self.assertEqual(
                (output / f"{builder.SEED43_NAME}.json").read_bytes(), first43
            )
            (output / f"{builder.SEED43_NAME}.json").write_bytes(b"{}\n")
            with self.assertRaisesRegex(
                RuntimeError, "Immutable generated recipe differs"
            ):
                builder.write_pair(output)


if __name__ == "__main__":
    unittest.main()
