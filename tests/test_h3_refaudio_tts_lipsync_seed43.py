import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scratch import build_h3_refaudio_matrix as builder
from validate_recipes import topology_contract_errors, validate_recipe_file


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "recipes" / "h3_r2v_refaudio_tts_lipsync.json"
ALTERNATE_PATH = ROOT / "recipes" / "h3_r2v_refaudio_tts_lipsync_seed43.json"


def input_assertions(recipe: dict, node_id: str, input_name: str) -> list[dict]:
    return [
        assertion
        for assertion in recipe["topology_contract"]["required_input_values"]
        if (assertion.get("node"), assertion.get("input"))
        == (node_id, input_name)
    ]


class H3RefAudioTTSLipSyncSeed43Tests(unittest.TestCase):
    def setUp(self):
        self.source_raw = SOURCE_PATH.read_bytes()
        self.alternate_raw = ALTERNATE_PATH.read_bytes()
        self.source = json.loads(self.source_raw.decode("utf-8"))
        self.alternate = json.loads(self.alternate_raw.decode("utf-8"))

    def test_seed42_source_is_hash_pinned_and_untouched(self):
        self.assertEqual(
            hashlib.sha256(self.source_raw).hexdigest(),
            builder.EXPECTED_TTS_LIPSYNC_SEED42_RECIPE_SHA256,
        )
        self.assertEqual(self.source["prompt"]["5"]["inputs"]["noise_seed"], 42)
        self.assertEqual(self.source["name"], builder.TTS_LIPSYNC_RECIPE_NAME)

    def test_generator_matches_canonical_utf8_lf_recipe(self):
        self.assertFalse(self.alternate_raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.alternate_raw.endswith(b"\n"))
        self.assertNotIn(b"\r\n", self.alternate_raw)
        self.assertEqual(self.alternate, builder.build_tts_lipsync_seed43_clone())

    def test_seed_is_the_only_model_execution_variable(self):
        self.assertEqual(
            builder.difference_paths(
                self.source["prompt"], self.alternate["prompt"]
            ),
            {
                "5.inputs.noise_seed",
                "12.inputs.filename_prefix",
            },
        )
        self.assertEqual(
            self.alternate["prompt"]["5"]["inputs"]["noise_seed"],
            builder.TTS_LIPSYNC_ALTERNATE_SEED,
        )
        self.assertEqual(
            self.alternate["prompt"]["12"]["inputs"]["filename_prefix"],
            builder.TTS_LIPSYNC_SEED43_OUTPUT_PREFIX,
        )
        self.assertEqual(
            self.alternate["experiment"]["independent_variable"],
            "random_noise_seed",
        )

    def test_action_prompt_graph_fixtures_and_native_audio_are_identical(self):
        self.assertEqual(
            self.alternate["prompt"]["7"]["inputs"]["prompt"],
            self.source["prompt"]["7"]["inputs"]["prompt"],
        )
        for node_id in ("1", "2", "3", "4", "6", "7", "8", "9", "10", "11", "13", "14", "15", "16", "17"):
            self.assertEqual(
                self.alternate["prompt"][node_id], self.source["prompt"][node_id]
            )
        self.assertEqual(
            self.alternate["prompt"]["10"]["inputs"]["audio"], ["15", 0]
        )
        self.assertNotEqual(
            self.alternate["prompt"]["10"]["inputs"]["audio"], ["16", 0]
        )
        self.assertEqual(self.alternate["contract"], self.source["contract"])

    def test_topology_mirrors_seed_and_unique_prefix(self):
        seed = input_assertions(self.alternate, "5", "noise_seed")
        prefix = input_assertions(self.alternate, "12", "filename_prefix")
        self.assertEqual(len(seed), 1)
        self.assertEqual(seed[0]["equals"], builder.TTS_LIPSYNC_ALTERNATE_SEED)
        self.assertEqual(len(prefix), 1)
        self.assertEqual(prefix[0]["equals"], builder.TTS_LIPSYNC_SEED43_OUTPUT_PREFIX)
        self.assertEqual(
            topology_contract_errors(self.alternate, self.alternate["prompt"]), []
        )
        report = validate_recipe_file(ALTERNATE_PATH)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["warnings"], [])

    def test_behavioral_claim_remains_pending_human_evidence(self):
        self.assertEqual(
            self.alternate["experiment"]["behavioral_claim_status"],
            "unrendered and unproven",
        )
        self.assertEqual(self.alternate["experiment"]["render_status"], "unrendered")

    def test_immutable_writer_is_idempotent_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertTrue(builder.write_tts_lipsync_seed43_clone(output))
            path = output / f"{builder.TTS_LIPSYNC_SEED43_RECIPE_NAME}.json"
            first = path.read_bytes()
            self.assertFalse(builder.write_tts_lipsync_seed43_clone(output))
            self.assertEqual(path.read_bytes(), first)
            path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(RuntimeError, "Immutable generated recipe differs"):
                builder.write_tts_lipsync_seed43_clone(output)


if __name__ == "__main__":
    unittest.main()
