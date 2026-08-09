import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scratch import build_clean_h3_recipes as builder
from validate_recipes import (
    minimax_h3_autogrow_input_errors,
    topology_contract_errors,
    validate_recipe_file,
)


REPO_ROOT = Path(__file__).parent.parent.resolve()
RECIPE_PATH = REPO_ROOT / "recipes" / "h3_mime_r2v.json"
BASE_RECIPE_PATH = REPO_ROOT / "recipes" / "h3_r2v_low.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class H3MimeR2VTests(unittest.TestCase):
    def setUp(self):
        self.raw = RECIPE_PATH.read_bytes()
        self.recipe = json.loads(self.raw.decode("utf-8"))
        self.prompt = self.recipe["prompt"]

    def test_generator_matches_committed_canonical_recipe(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.raw.endswith(b"\n"))
        self.assertNotIn(b"\r\n", self.raw)
        self.assertEqual(self.recipe, builder.make_h3_mime_r2v_recipe())

        other_prefixes = {
            node.get("inputs", {}).get("filename_prefix")
            for path in (REPO_ROOT / "recipes").glob("*.json")
            if path != RECIPE_PATH
            for node in json.loads(path.read_text(encoding="utf-8"))
            .get("prompt", {})
            .values()
            if node.get("class_type") == "SaveVideo"
        }
        self.assertNotIn(builder.H3_MIME_R2V_PREFIX, other_prefixes)

    def test_immutable_writer_is_idempotent_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.assertTrue(builder.write_h3_mime_r2v(output))
            generated = output / "h3_mime_r2v.json"
            first = generated.read_bytes()
            self.assertFalse(builder.write_h3_mime_r2v(output))
            self.assertEqual(generated.read_bytes(), first)
            generated.write_bytes(b"{}\n")
            with self.assertRaisesRegex(RuntimeError, "Immutable generated recipe differs"):
                builder.write_h3_mime_r2v(output)

    def test_graph_is_low_r2v_with_only_mime_payload_changes(self):
        low_prompt = json.loads(BASE_RECIPE_PATH.read_text(encoding="utf-8"))["prompt"]
        expected = deepcopy(low_prompt)
        expected["7"]["inputs"]["prompt"] = builder.MIME_R2V_PROMPT
        expected["7"]["inputs"]["length"] = 90
        expected["12"]["inputs"]["filename_prefix"] = builder.H3_MIME_R2V_PREFIX
        self.assertEqual(self.prompt, expected)

    def test_portrait_is_the_only_flat_v3_reference(self):
        inputs = self.prompt["7"]["inputs"]
        self.assertEqual(self.prompt["7"]["class_type"], "MiniMaxH3ReferenceToVideo")
        self.assertEqual(inputs["ref_images.ref_image_0"], ["11", 0])
        self.assertEqual(self.prompt["11"]["inputs"]["image"], "portrait.png")
        self.assertEqual(
            {key for key in inputs if key.startswith("ref_")},
            {"ref_image_size", "ref_images.ref_image_0"},
        )
        self.assertFalse(
            {"ref_images", "ref_videos", "ref_video_audios", "ref_audios"}
            & set(inputs)
        )
        self.assertEqual(minimax_h3_autogrow_input_errors(self.prompt), [])
        self.assertEqual(
            [
                node_id
                for node_id, node in self.prompt.items()
                if node["class_type"] == "LoadImage"
            ],
            ["11"],
        )
        self.assertIn("<Picture 1>", builder.MIME_R2V_PROMPT)
        for forbidden_tag in ("<Picture 2>", "<Audio 1>", "<Video 1>"):
            self.assertNotIn(forbidden_tag, builder.MIME_R2V_PROMPT)

    def test_native_joint_audio_is_the_only_delivered_soundtrack(self):
        classes = {node["class_type"] for node in self.prompt.values()}
        self.assertNotIn("LoadAudio", classes)
        self.assertEqual(self.prompt["15"]["class_type"], "VAEDecodeAudio")
        self.assertEqual(self.prompt["15"]["inputs"], {"samples": ["8", 0], "vae": ["4", 0]})
        self.assertEqual(self.prompt["10"]["inputs"]["audio"], ["15", 0])
        audio_policy = self.recipe["topology_contract"]["audio_path_contract"]
        self.assertFalse(audio_policy["external_audio_conditioning"])
        self.assertFalse(audio_policy["external_source_mux"])

    def test_prompt_and_metadata_enforce_the_inverted_audio_policy(self):
        lowered = builder.MIME_R2V_PROMPT.lower()
        self.assertIn("coherent diegetic soundscape", lowered)
        self.assertIn("is alone", lowered)
        for prohibition in (
            "no dialogue",
            "no intelligible speech",
            "no voices",
            "no vocals",
            "no humming",
            "no music",
        ):
            self.assertIn(prohibition, lowered)
        soundtrack = self.recipe["experiment"]["soundtrack_policy"]
        self.assertFalse(soundtrack["external_mux"])
        self.assertEqual(
            soundtrack["forbidden"],
            ["dialogue", "intelligible speech", "voices", "vocals", "humming", "music"],
        )

    def test_exact_topology_fixture_schema_and_base_pins(self):
        topology = self.recipe["topology_contract"]
        self.assertTrue(topology["exact_node_set"])
        self.assertEqual(topology, builder.make_mime_r2v_topology_contract())
        self.assertEqual(
            topology["installed_schema"],
            {
                "comfyui_version": builder.COMFYUI_SCHEMA_VERSION,
                "git_commit": builder.COMFYUI_SCHEMA_COMMIT,
                "node_source": builder.H3_NODE_SOURCE,
                "node_source_sha256": builder.H3_NODE_SOURCE_SHA256,
            },
        )
        self.assertEqual(sha256_file(BASE_RECIPE_PATH), builder.H3_R2V_LOW_BASE_SHA256)
        self.assertEqual(
            topology["origin"]["base_recipe_sha256"],
            builder.H3_R2V_LOW_BASE_SHA256,
        )
        portrait = REPO_ROOT / "fixtures" / "portrait.png"
        self.assertEqual(sha256_file(portrait), builder.PORTRAIT_SHA256)
        self.assertEqual(topology["fixture_hashes"], {"portrait.png": builder.PORTRAIT_SHA256})
        self.assertEqual(topology_contract_errors(self.recipe, self.prompt), [])
        self.assertTrue(validate_recipe_file(RECIPE_PATH)["valid"])

    def test_unused_flat_reference_sockets_are_enforced_absent(self):
        topology = self.recipe["topology_contract"]
        absent = set(topology["required_absent_inputs"])
        expected = {
            *(f"7.ref_images.ref_image_{index}" for index in range(1, 9)),
            *(f"7.ref_videos.ref_video_{index}" for index in range(3)),
            *(
                f"7.ref_video_audios.ref_video_audio_{index}"
                for index in range(3)
            ),
            *(f"7.ref_audios.ref_audio_{index}" for index in range(3)),
        }
        self.assertTrue(expected <= absent)

        mutated = deepcopy(self.recipe)
        mutated["prompt"]["7"]["inputs"]["ref_audios.ref_audio_0"] = ["11", 0]
        errors = topology_contract_errors(mutated, mutated["prompt"])
        self.assertTrue(
            any("7.ref_audios.ref_audio_0 must be absent" in error for error in errors),
            errors,
        )
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "h3_mime_r2v.json"
            candidate.write_bytes((json.dumps(mutated, indent=2) + "\n").encode("utf-8"))
            result = validate_recipe_file(candidate)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("7.ref_audios.ref_audio_0 must be absent" in error for error in result["errors"]),
            result,
        )

    def test_timing_and_pending_human_receipt_contract_are_exact(self):
        contract = self.recipe["contract"]
        self.assertEqual(
            (contract["width"], contract["height"], contract["frames"], contract["fps"]),
            (864, 480, 90, 24.0),
        )
        self.assertEqual(contract["target_s"], 3.75)
        self.assertEqual(contract["duration_s"], 3.75)
        self.assertEqual(contract["delivered_s"], 3.75)
        self.assertEqual(contract["trim_frames"], 0)
        self.assertTrue(contract["requires_audio"])
        self.assertEqual(contract["required_boot_lane"], "lab-8199, sage-free")

        requirements = self.recipe["receipt_requirements"]
        timing = requirements["timing"]
        self.assertTrue(timing["ffprobe_required"])
        self.assertEqual(timing["absolute_duration_error_lte_s"], 1 / 24)
        self.assertEqual(timing["target_s"], 3.75)
        ear = requirements["inverted_ear_gate"]
        self.assertEqual(ear["status"], "pending_human")
        self.assertIn("soundscape_description", ear["required_fields"])
        self.assertEqual(ear["pass_values"]["audio_ear_source"], "human")


if __name__ == "__main__":
    unittest.main()
