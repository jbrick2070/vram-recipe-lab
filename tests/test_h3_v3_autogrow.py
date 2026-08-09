import copy
import json
import tempfile
import unittest
from pathlib import Path

import run_recipe
import validate_recipes


class MiniMaxH3V3AutogrowContractTests(unittest.TestCase):
    def setUp(self):
        self.prompt = {
            "1": {"class_type": "ImageSource", "inputs": {}},
            "2": {"class_type": "VideoSource", "inputs": {}},
            "3": {"class_type": "AudioSource", "inputs": {}},
            "7": {
                "class_type": "MiniMaxH3ReferenceToVideo",
                "inputs": {
                    "ref_images.ref_image_0": ["1", 0],
                    "ref_videos.ref_video_2": ["2", 0],
                    "ref_video_audios.ref_video_audio_1": ["3", 0],
                    "ref_audios.ref_audio_2": ["3", 0],
                },
            },
        }

    def assert_guard_parity(self, prompt, expected_fragment=None):
        runtime_errors = run_recipe.minimax_h3_autogrow_input_errors(prompt)
        paper_errors = validate_recipes.minimax_h3_autogrow_input_errors(prompt)
        self.assertEqual(runtime_errors, paper_errors)
        if expected_fragment is None:
            self.assertEqual(runtime_errors, [])
        else:
            self.assertTrue(
                any(expected_fragment in error for error in runtime_errors),
                runtime_errors,
            )

    def test_valid_flat_socket_names_and_direct_links_pass_both_guards(self):
        self.assert_guard_parity(self.prompt)

    def test_every_nested_autogrow_container_is_rejected(self):
        members = {
            "ref_images": "ref_image_0",
            "ref_videos": "ref_video_0",
            "ref_video_audios": "ref_video_audio_0",
            "ref_audios": "ref_audio_0",
        }
        for container, member in members.items():
            with self.subTest(container=container):
                prompt = copy.deepcopy(self.prompt)
                prompt["7"]["inputs"] = {container: {member: ["1", 0]}}
                self.assert_guard_parity(prompt, "nested V3 autogrow container")

    def test_malformed_flat_names_and_values_are_rejected(self):
        cases = {
            "ref_images.ref_image_9": ["1", 0],
            "ref_images.ref_image_00": ["1", 0],
            "ref_videos.ref_image_0": ["2", 0],
            "ref_audios.ref_audio_0": {"source": ["3", 0]},
            "ref_video_audios.ref_video_audio_0": ["3", True],
        }
        for socket, value in cases.items():
            with self.subTest(socket=socket):
                prompt = copy.deepcopy(self.prompt)
                prompt["7"]["inputs"] = {socket: value}
                self.assert_guard_parity(prompt, f"input '{socket}'")

    @staticmethod
    def object_info():
        return {
            "ImageSource": {
                "input": {"required": {}, "optional": {}},
                "output": ["IMAGE"],
            },
            "VideoSource": {
                "input": {"required": {}, "optional": {}},
                "output": ["IMAGE"],
            },
            "AudioSource": {
                "input": {"required": {}, "optional": {}},
                "output": ["AUDIO"],
            },
            "MiniMaxH3ReferenceToVideo": {
                "input": {
                    "required": {},
                    "optional": {
                        "ref_images": ["COMFY_AUTOGROW_V3", {}],
                        "ref_videos": ["COMFY_AUTOGROW_V3", {}],
                        "ref_video_audios": ["COMFY_AUTOGROW_V3", {}],
                        "ref_audios": ["COMFY_AUTOGROW_V3", {}],
                    },
                },
                "output": ["CONDITIONING", "LATENT"],
            },
        }

    def test_runtime_widget_gate_accepts_flat_and_rejects_nested(self):
        run_recipe.check_widget_integrity(
            {"prompt": self.prompt}, self.object_info()
        )
        nested = copy.deepcopy(self.prompt)
        nested["7"]["inputs"] = {
            "ref_images": {"ref_image_0": ["1", 0]}
        }
        with self.assertRaisesRegex(
            run_recipe.PreflightError, "nested V3 autogrow container"
        ):
            run_recipe.check_widget_integrity(
                {"prompt": nested}, self.object_info()
            )

    def test_paper_validator_rejects_nested_recipe(self):
        recipe = {
            "name": "h3_r2v_guard_case",
            "contract": {
                "width": 832,
                "height": 480,
                "frames": 124,
                "fps": 24,
                "target_s": 5.167,
                "vram_ceiling_gb": 14.5,
            },
            "prompt": {
                "1": {"class_type": "LoadImage", "inputs": {}},
                "7": {
                    "class_type": "MiniMaxH3ReferenceToVideo",
                    "inputs": {
                        "ref_images": {"ref_image_0": ["1", 0]}
                    },
                },
                "9": {
                    "class_type": "SaveVideo",
                    "inputs": {"video": ["7", 1]},
                },
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            recipe_path = Path(temporary_directory) / "h3_r2v_guard_case.json"
            recipe_path.write_text(json.dumps(recipe), encoding="utf-8")
            result = validate_recipes.validate_recipe_file(recipe_path)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("nested V3 autogrow container" in error for error in result["errors"]),
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
