import json
import unittest
import tempfile
from pathlib import Path
from unittest import mock

import mux_source_delivery
import run_recipe


class TestSourceDelivery(unittest.TestCase):
    @staticmethod
    def write_binding_fixture(root: Path, alias: dict, archive: dict | None = None) -> None:
        recipes = root / "recipes"
        results = root / "results"
        recipes.mkdir()
        results.mkdir()
        recipe = {
            "experiment": {"campaign": "audio_conditioning_matrix_v1"},
            "contract": {"duration_s": 3.88, "fps": 25.0},
        }
        recipe_bytes = (json.dumps(recipe) + "\n").encode("utf-8")
        (recipes / "cell.json").write_bytes(recipe_bytes)
        alias = {
            "receipt_schema_version": run_recipe.RECEIPT_SCHEMA_VERSION,
            "recipe": "cell",
            "run_number": 1,
            "recipe_sha256": run_recipe.sha256_bytes(recipe_bytes),
            "provenance_unchanged": True,
            "gate_pass": True,
            **alias,
        }
        (results / "cell.json").write_text(json.dumps(alias), encoding="utf-8")
        if archive is not None:
            archive = {**alias, **archive}
            (results / "cell_run1.json").write_text(
                json.dumps(archive), encoding="utf-8"
            )

    def test_elementary_hash_muxers_are_explicit(self):
        self.assertEqual(mux_source_delivery.elementary_muxer("h264"), "h264")
        self.assertEqual(mux_source_delivery.elementary_muxer("hevc"), "hevc")
        self.assertEqual(mux_source_delivery.elementary_muxer("av1"), "obu")
        with self.assertRaises(mux_source_delivery.DeliveryError):
            mux_source_delivery.elementary_muxer("vp9")

    def test_mux_command_stream_copies_video_and_uses_original_audio(self):
        command = mux_source_delivery.build_mux_command(
            Path("diagnostic.mp4"), Path("tts_dialogue.wav"), Path("delivery.mp4"), 0.0, 3.88
        )
        self.assertIn("tts_dialogue.wav", command)
        self.assertEqual(command[command.index("-c:v") + 1], "copy")
        self.assertEqual(command[command.index("-c:a") + 1], "aac")
        self.assertEqual(command[-1], "delivery.mp4")

    def test_duration_tolerance_is_inclusive_at_one_frame(self):
        self.assertTrue(mux_source_delivery.duration_within_one_frame(3.92, 3.88, 25.0))
        self.assertFalse(mux_source_delivery.duration_within_one_frame(3.92001, 3.88, 25.0))

    def test_delivery_lease_refuses_concurrent_same_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(mux_source_delivery, "DELIVERY_RESULTS", Path(tmp)):
                with mux_source_delivery.DeliveryLease("sample"):
                    with self.assertRaises(mux_source_delivery.DeliveryError):
                        with mux_source_delivery.DeliveryLease("sample"):
                            pass

    def test_delivery_rejects_modern_gate_alias_without_immutable_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_binding_fixture(root, {})
            with (
                mock.patch.object(mux_source_delivery, "REPO_ROOT", root),
                mock.patch.object(mux_source_delivery.run_recipe, "RESULTS_DIR", root / "results"),
            ):
                with self.assertRaisesRegex(
                    mux_source_delivery.DeliveryError, "matching immutable archive"
                ):
                    mux_source_delivery.create_delivery("cell")

    def test_delivery_rejects_failed_archive_promoted_by_current_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_binding_fixture(
                root,
                {"gate_pass": True},
                {"gate_pass": False, "status": "FAIL"},
            )
            with (
                mock.patch.object(mux_source_delivery, "REPO_ROOT", root),
                mock.patch.object(mux_source_delivery.run_recipe, "RESULTS_DIR", root / "results"),
            ):
                with self.assertRaisesRegex(
                    mux_source_delivery.DeliveryError, "machine field: gate_pass"
                ):
                    mux_source_delivery.create_delivery("cell")

    def test_mime_timing_fields_use_ffprobe_delivery_measurement(self):
        recipe = {
            "contract": {"fps": 24.0, "frames": 90, "target_s": 3.75},
            "experiment": {
                "timing_plan": {
                    "target_s": 3.75,
                    "frame_count": 90,
                    "trim_frames": 0,
                    "rendered_s": 3.75,
                    "delivered_s": 3.75,
                    "tail_trim_s": 0.0,
                }
            },
            "receipt_requirements": {
                "timing": {"absolute_duration_error_lte_s": 1.0 / 24.0},
                "inverted_ear_gate": {"status": "pending_human"},
            },
        }
        fields = run_recipe.timing_receipt_fields(
            recipe,
            {
                "container_duration_s": 3.76,
                "video_duration_s": 3.76,
                "audio_duration_s": 3.76,
            },
        )
        self.assertEqual(fields["target_s"], 3.75)
        self.assertEqual(fields["delivered_s"], 3.76)
        self.assertTrue(fields["duration_within_tolerance"])
        pending = run_recipe.pending_human_audio_fields(recipe)
        self.assertEqual(pending["audio_ear_source"], "pending_human")
        self.assertFalse(pending["inverted_ear_gate_pass"])

    def test_media_gate_enforces_contract_duration_within_one_frame(self):
        contract = {
            "frames": 90,
            "width": 864,
            "height": 480,
            "fps": 24.0,
            "target_s": 3.75,
        }
        metrics = {
            "encoded_frame_count": 90,
            "video_stream_bytes": 1000,
            "encoded_width": 864,
            "encoded_height": 480,
            "encoded_fps": 24.0,
            "container_duration_s": 3.75,
            "video_duration_s": 3.75,
        }
        self.assertTrue(run_recipe.media_artifact_is_valid(metrics, contract))
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {**metrics, "container_duration_s": 3.80}, contract
            )
        )
        audio_metrics = {
            **metrics,
            "audio_present": True,
            "audio_stream_bytes": 500,
            "audio_duration_s": 1.0,
        }
        self.assertFalse(
            run_recipe.media_artifact_is_valid(audio_metrics, contract, requires_audio=True)
        )


if __name__ == "__main__":
    unittest.main()
