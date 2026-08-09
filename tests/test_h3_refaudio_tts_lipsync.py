import copy
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from scratch import build_h3_refaudio_matrix as builder
from validate_recipes import topology_contract_errors, validate_recipe_file


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "recipes" / "h3_r2v_refaudio_tts_dialogue.json"
CLONE_PATH = ROOT / "recipes" / "h3_r2v_refaudio_tts_lipsync.json"


def prompt_assertion(recipe: dict) -> dict:
    matches = [
        assertion
        for assertion in recipe["topology_contract"]["required_input_values"]
        if (assertion.get("node"), assertion.get("input")) == ("7", "prompt")
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one prompt assertion, found {len(matches)}")
    return matches[0]


class H3RefAudioTTSLipSyncTests(unittest.TestCase):
    def setUp(self):
        self.source_raw = SOURCE_PATH.read_bytes()
        self.clone_raw = CLONE_PATH.read_bytes()
        self.source = json.loads(self.source_raw.decode("utf-8"))
        self.clone = json.loads(self.clone_raw.decode("utf-8"))

    def test_source_hash_and_clone_generator_are_exact(self):
        self.assertEqual(
            hashlib.sha256(self.source_raw).hexdigest(),
            builder.EXPECTED_TTS_DIALOGUE_RECIPE_SHA256,
        )
        self.assertFalse(self.clone_raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.clone_raw.endswith(b"\n"))
        self.assertNotIn(b"\r\n", self.clone_raw)
        self.assertEqual(self.clone, builder.build_tts_lipsync_prompt_clone())

    def test_execution_graph_diff_is_only_action_prompt_and_output_prefix(self):
        paths = builder.difference_paths(self.source["prompt"], self.clone["prompt"])
        self.assertEqual(
            paths,
            {
                "7.inputs.prompt",
                "12.inputs.filename_prefix",
            },
        )
        self.assertEqual(
            set(self.source["prompt"]),
            set(self.clone["prompt"]),
        )
        self.assertEqual(
            self.clone["prompt"]["12"]["inputs"]["filename_prefix"],
            builder.TTS_LIPSYNC_OUTPUT_PREFIX,
        )

    def test_full_recipe_normalizes_exactly_to_source(self):
        normalized = copy.deepcopy(self.clone)
        normalized["name"] = self.source["name"]
        normalized["experiment"] = copy.deepcopy(self.source["experiment"])
        normalized["prompt"]["7"]["inputs"]["prompt"] = self.source["prompt"]["7"][
            "inputs"
        ]["prompt"]
        normalized["prompt"]["12"]["inputs"]["filename_prefix"] = self.source[
            "prompt"
        ]["12"]["inputs"]["filename_prefix"]
        prompt_assertion(normalized)["equals"] = prompt_assertion(self.source)["equals"]
        self.assertEqual(normalized, self.source)

        full_paths = builder.difference_paths(self.source, self.clone)
        prompt_mirror_path = next(
            path
            for path in full_paths
            if path.startswith("topology_contract.required_input_values[")
        )
        permitted = {
            "name",
            "prompt.7.inputs.prompt",
            "prompt.12.inputs.filename_prefix",
            prompt_mirror_path,
        }
        forbidden = {
            path
            for path in full_paths
            if not path.startswith("experiment.") and path not in permitted
        }
        self.assertEqual(forbidden, set())
        self.assertTrue(prompt_mirror_path.endswith(".equals"))

    def test_fixtures_settings_and_flat_v3_ancestry_are_identical(self):
        source_prompt = self.source["prompt"]
        clone_prompt = self.clone["prompt"]
        inputs = clone_prompt["7"]["inputs"]
        self.assertEqual(inputs["ref_image_size"], "match")
        self.assertEqual(inputs["ref_images.ref_image_0"], ["11", 0])
        self.assertEqual(inputs["ref_images.ref_image_1"], ["17", 0])
        self.assertEqual(inputs["ref_audios.ref_audio_0"], ["16", 0])
        self.assertEqual(clone_prompt["11"], source_prompt["11"])
        self.assertEqual(clone_prompt["17"], source_prompt["17"])
        self.assertEqual(clone_prompt["16"], source_prompt["16"])
        self.assertEqual(clone_prompt["5"], source_prompt["5"])
        self.assertEqual(clone_prompt["13"], source_prompt["13"])
        self.assertEqual(clone_prompt["14"], source_prompt["14"])
        self.assertEqual(self.clone["contract"], self.source["contract"])
        self.assertEqual(
            self.clone["topology_contract"]["fixture_hashes"],
            self.source["topology_contract"]["fixture_hashes"],
        )

    def test_native_target_audio_delivery_is_unchanged_and_source_is_not_muxed(self):
        prompt = self.clone["prompt"]
        self.assertEqual(
            builder.source_consumers(prompt, "16"),
            {("7", "ref_audios.ref_audio_0")},
        )
        self.assertEqual(prompt["15"]["inputs"], {"samples": ["8", 0], "vae": ["4", 0]})
        self.assertEqual(prompt["10"]["inputs"]["audio"], ["15", 0])
        self.assertNotEqual(prompt["10"]["inputs"]["audio"], ["16", 0])
        self.assertFalse(self.clone["experiment"]["external_source_mux"])

    def test_action_prompt_is_exact_and_makes_no_behavioral_success_claim(self):
        prompt = self.clone["prompt"]["7"]["inputs"]["prompt"]
        self.assertEqual(prompt, builder.TTS_LIPSYNC_PROMPT)
        self.assertIn("medium close shot", prompt)
        self.assertIn("speaking directly to camera", prompt)
        self.assertIn("lip movements matching <Audio 1> precisely", prompt)
        self.assertIn("final mouth closure", prompt)
        self.assertEqual(
            set(re.findall(r"<(?:Picture|Video|Audio) \d+>", prompt)),
            {"<Picture 1>", "<Picture 2>", "<Audio 1>"},
        )
        self.assertEqual(
            self.clone["experiment"]["behavioral_claim_status"],
            "unrendered and unproven",
        )
        self.assertEqual(
            self.clone["experiment"]["independent_variable"], "action_prompt"
        )

    def test_topology_and_standard_offline_validator_accept_clone(self):
        self.assertEqual(
            prompt_assertion(self.clone)["equals"], builder.TTS_LIPSYNC_PROMPT
        )
        self.assertEqual(
            topology_contract_errors(self.clone, self.clone["prompt"]), []
        )
        report = validate_recipe_file(CLONE_PATH)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["node_count"], 17)

    def test_immutable_writer_is_idempotent_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertTrue(builder.write_tts_lipsync_prompt_clone(output))
            path = output / f"{builder.TTS_LIPSYNC_RECIPE_NAME}.json"
            first = path.read_bytes()
            self.assertFalse(builder.write_tts_lipsync_prompt_clone(output))
            self.assertEqual(path.read_bytes(), first)
            path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(RuntimeError, "Immutable generated recipe differs"):
                builder.write_tts_lipsync_prompt_clone(output)


if __name__ == "__main__":
    unittest.main()
