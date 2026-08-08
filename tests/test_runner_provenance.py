import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run_recipe
import validate_recipes
from scratch import build_clean_h3_recipes


class TestRunnerProvenance(unittest.TestCase):
    def test_h3_generator_preserves_bytes_for_semantic_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recipe.json"
            original = b'{\r\n  "name": "sample",\r\n  "value": 1\r\n}'
            path.write_bytes(original)

            changed = build_clean_h3_recipes.write_recipe_if_changed(
                path, {"name": "sample", "value": 1}
            )

            self.assertFalse(changed)
            self.assertEqual(path.read_bytes(), original)

            changed = build_clean_h3_recipes.write_recipe_if_changed(
                path, {"name": "sample", "value": 2}
            )

            self.assertTrue(changed)
            self.assertEqual(path.read_bytes(), b'{\n  "name": "sample",\n  "value": 2\n}\n')

    def test_identity_change_resets_configuration_count_but_not_run_number(self):
        previous = {
            "run_count": 7,
            "config_run_count": 2,
            "run_identity_sha256": "old",
            "gate_pass": True,
        }

        state = run_recipe.next_run_state(previous, "new")

        self.assertEqual(state["run_count"], 8)
        self.assertEqual(state["config_run_count"], 1)
        self.assertFalse(state["same_identity"])
        self.assertFalse(state["previous_gate_pass"])

    def test_identical_passing_configuration_can_become_warm(self):
        previous = {
            "run_count": 7,
            "config_run_count": 1,
            "run_identity_sha256": "same",
            "gate_pass": True,
        }

        state = run_recipe.next_run_state(previous, "same")

        self.assertEqual(state["run_count"], 8)
        self.assertEqual(state["config_run_count"], 2)
        self.assertTrue(state["same_identity"])
        self.assertTrue(state["previous_gate_pass"])

    def test_legacy_receipt_without_identity_restarts_cold(self):
        state = run_recipe.next_run_state({"run_count": 3, "pass": True}, "new")
        self.assertEqual(state["run_count"], 4)
        self.assertEqual(state["config_run_count"], 1)
        self.assertFalse(state["previous_gate_pass"])

    def test_fixture_discovery_uses_literal_loader_inputs(self):
        recipe = {
            "prompt": {
                "1": {"class_type": "LoadImage", "inputs": {"image": "scene_still.png"}},
                "2": {"class_type": "LoadAudio", "inputs": {"audio": "music_opening.wav"}},
                "3": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "narration.wav"}},
            }
        }
        self.assertEqual(
            run_recipe.referenced_fixtures(recipe),
            ["music_opening.wav", "scene_still.png"],
        )

    def test_fixture_discovery_rejects_paths_outside_fixture_root(self):
        recipe = {
            "prompt": {
                "1": {"class_type": "LoadImage", "inputs": {"image": "../secret.png"}},
            }
        }
        with self.assertRaises(ValueError):
            run_recipe.referenced_fixtures(recipe)

    def test_fixture_upload_forces_exact_name_and_verifies_readback_hash(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return self.payload

        content = b"frozen-fixture-bytes"
        upload_response = json.dumps(
            {"name": "scene.png", "subfolder": "", "type": "input"}
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            fixture_root = Path(tmp)
            with (
                mock.patch.object(run_recipe, "FIXTURES_DIR", fixture_root),
                mock.patch.object(
                    run_recipe.urllib.request,
                    "urlopen",
                    side_effect=[FakeResponse(upload_response), FakeResponse(content)],
                ) as mock_urlopen,
            ):
                run_recipe.upload_fixtures({"scene.png": content})

            upload_request = mock_urlopen.call_args_list[0].args[0]
            self.assertIn(b'name="overwrite"\r\n\r\ntrue', upload_request.data)
            self.assertIn(b'name="type"\r\n\r\ninput', upload_request.data)
            self.assertIn(b'filename="scene.png"', upload_request.data)
            view_request = mock_urlopen.call_args_list[1].args[0]
            self.assertIn("filename=scene.png", view_request.full_url)
            self.assertIn("type=input", view_request.full_url)

    def test_sha256_file_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_bytes(b"recipe")
            self.assertEqual(
                run_recipe.sha256_file(path),
                "e1d8e552330911f9f779f85b6f2c00a15e790dcc3fbb3b28f5da1d660a30c5b8",
            )

    def test_schema_v2_receipt_cannot_drop_runner_field_to_look_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_file = root / "sample.json"
            output_dir = root / "outputs"
            output_dir.mkdir()
            recipe_file.write_text('{"name":"sample"}', encoding="utf-8")
            output_file = output_dir / "sample.mp4"
            output_file.write_bytes(b"video")
            identity = {
                "recipe_sha256": run_recipe.sha256_file(recipe_file),
                "runner_sha256": "runner-hash",
                "fixture_sha256s": {},
                "boot_lane": "lab-8199, sage-free",
                "server_argv": ["main.py", "--port", "8199"],
                "comfyui_git_commit": "commit",
            }
            receipt = {
                "receipt_schema_version": 2,
                "recipe": "sample",
                **identity,
                "identity": identity,
                "run_identity_sha256": run_recipe.stable_identity(identity),
                "gate_pass": True,
                "warm_pass": True,
                "pass": True,
                "config_run_count": 2,
                "provenance_unchanged": True,
                "output_path": output_file.name,
                "artifact_sha256": run_recipe.sha256_file(output_file),
            }

            self.assertEqual(
                validate_recipes.current_certification_errors(receipt, recipe_file, root),
                [],
            )
            receipt.pop("runner_sha256")
            errors = validate_recipes.current_certification_errors(receipt, recipe_file, root)
            self.assertTrue(any("runner_sha256" in error for error in errors))

    def test_clamp_target_translates_to_reserve(self):
        self.assertAlmostEqual(run_recipe.reserve_for_target_gib(16.0, 12.0), 4.0)
        self.assertAlmostEqual(run_recipe.reserve_for_target_gib(16.0, 8.0), 8.0)

    def test_clamp_rejects_impossible_target(self):
        with self.assertRaises(ValueError):
            run_recipe.reserve_for_target_gib(16.0, 17.0)
        with self.assertRaises(ValueError):
            run_recipe.reserve_for_target_gib(16.0, 0.0)
        with self.assertRaises(ValueError):
            run_recipe.reserve_for_target_gib(16.0, float("nan"))

    def test_direct_reserve_requires_finite_nonnegative_value_below_physical(self):
        self.assertEqual(run_recipe.validate_reserve_gib(12.0, 16.0), 12.0)
        for invalid in [-1.0, float("nan"), float("inf"), 16.0]:
            with self.assertRaises(ValueError):
                run_recipe.validate_reserve_gib(invalid, 16.0)

    def test_boot_lane_requires_exact_reserve_argv(self):
        with mock.patch.dict(os.environ, {"LAB_RESERVE_VRAM_GB": "4"}, clear=False):
            run_recipe.check_boot_lane(
                "recipe",
                {"system": {"argv": ["main.py", "--reserve-vram", "4"]}},
            )
            with self.assertRaises(run_recipe.PreflightError):
                run_recipe.check_boot_lane(
                    "recipe",
                    {"system": {"argv": ["main.py", "--reserve-vram", "12"]}},
                )

    def test_expected_lab_pid_requires_main_port_and_output_directory(self):
        valid_argv = [
            "python.exe",
            str(run_recipe.COMFYUI_ROOT / "main.py"),
            "--port",
            str(run_recipe.LAB_PORT),
            "--output-directory",
            str(run_recipe.REPO_ROOT / "outputs"),
        ]
        process = mock.Mock()
        process.cmdline.return_value = valid_argv
        with mock.patch.object(run_recipe.psutil, "Process", return_value=process):
            self.assertTrue(run_recipe.is_expected_lab_server_pid(123))
            process.cmdline.return_value = [*valid_argv[:-1], "C:\\other\\outputs"]
            self.assertFalse(run_recipe.is_expected_lab_server_pid(123))

    def test_shutdown_retains_receipt_when_pid_identity_is_untrusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "get_recorded_pid", return_value=123),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=False),
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                run_recipe.shutdown_lab_server()

            self.assertTrue(receipt.exists())
            terminate.assert_not_called()

    def test_shutdown_removes_receipt_only_after_verified_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "get_recorded_pid", return_value=123),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(run_recipe, "terminate_owned_process_tree", return_value=True),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
            ):
                run_recipe.shutdown_lab_server()

            self.assertFalse(receipt.exists())

    def test_preflight_refuses_to_overwrite_live_orphan_receipt(self):
        with (
            mock.patch.object(run_recipe, "cleanup_stale_pid_receipt"),
            mock.patch.object(run_recipe, "query_server_stats", return_value=None),
            mock.patch.object(run_recipe, "get_recorded_pid", return_value=123),
            mock.patch.object(run_recipe, "check_gpu_idle") as check_idle,
        ):
            with self.assertRaises(run_recipe.PreflightError):
                run_recipe.check_server_up_and_ownership()
        check_idle.assert_not_called()

    def test_affordability_blocks_same_lane_net_clamp_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            (results / "sample.json").write_text(
                json.dumps(
                    {
                        "recipe_sha256": "same",
                        "boot_lane": "clamp-8gb (reserve-8gb)",
                        "peak_vram_gb": 12.0,
                        "gate_pass": False,
                        "status": "FAIL (net VRAM 9.00 GB > clamp 8.0 GB)",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(run_recipe, "RESULTS_DIR", results):
                with self.assertRaises(run_recipe.PreflightError):
                    run_recipe.check_affordability(
                        "sample", "same", "clamp-8gb (reserve-8gb)"
                    )

    def test_matrix_writer_matches_current_header_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            matrix = Path(tmp) / "matrix.md"
            matrix.write_text(
                "| recipe | tier | status | peak VRAM (GB) | wall clock (s) | gated | pass consecutive | boot lane | last run | notes |\n"
                "|---|---|---|---|---|---|---|---|---|---|\n",
                encoding="utf-8",
            )
            with mock.patch.object(run_recipe, "ENGINE_MATRIX_BETA", matrix):
                run_recipe.update_engine_matrix_beta(
                    "sample", "smoke", "PASS", 6.5, 200.0, "yes", "2/2", "lane", "note"
                )
            row = matrix.read_text(encoding="utf-8").splitlines()[-1]
            columns = [part.strip() for part in row.strip("|").split("|")]
            self.assertEqual(len(columns), 10)
            self.assertEqual(columns[4], "200.0")
            self.assertEqual(columns[6], "2/2")

    def test_media_gate_requires_frames_and_video_packets(self):
        valid_metrics = {
            "encoded_frame_count": 97,
            "video_stream_bytes": 1000,
            "encoded_width": 832,
            "encoded_height": 480,
            "encoded_fps": 25.0,
            "audio_present": True,
            "audio_stream_bytes": 500,
        }
        contract = {"frames": 97, "width": 832, "height": 480, "fps": 25.0}
        self.assertTrue(
            run_recipe.media_artifact_is_valid(valid_metrics, contract, requires_audio=True)
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {"encoded_frame_count": 0, "video_stream_bytes": 1000}
            )
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {
                    "encoded_frame_count": 97,
                    "video_stream_bytes": 1000,
                    "media_probe_error": "invalid data",
                }
            )
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {**valid_metrics, "encoded_frame_count": 1}, contract
            )
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {**valid_metrics, "encoded_width": 640}, contract
            )
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {**valid_metrics, "audio_present": False, "audio_stream_bytes": 0},
                contract,
                requires_audio=True,
            )
        )

    def test_video_fingerprint_uses_frame_count_not_measured_audio_bitrate(self):
        left = {
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "encoded_width": 832,
            "encoded_height": 480,
            "encoded_fps": 25.0,
            "encoded_frame_count": 97,
            "audio_bitrate": 127000,
        }
        right = {**left, "audio_bitrate": 129000}
        self.assertEqual(run_recipe.media_fingerprint(left), run_recipe.media_fingerprint(right))
        right["encoded_frame_count"] = 121
        self.assertNotEqual(run_recipe.media_fingerprint(left), run_recipe.media_fingerprint(right))

    def test_bitrate_anomaly_is_strictly_over_twice_same_lane_clean_median(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            outputs = root / "outputs"
            results.mkdir()
            outputs.mkdir()
            base_metrics = {
                "video_codec": "h264",
                "pixel_format": "yuv420p",
                "encoded_width": 832,
                "encoded_height": 480,
                "encoded_fps": 25.0,
                "encoded_frame_count": 97,
            }
            for index, value in enumerate([90.0, 100.0, 110.0], start=1):
                output_name = f"clean{index}.mp4"
                output_file = outputs / output_name
                output_file.write_bytes(f"artifact-{index}".encode("ascii"))
                receipt = {
                    **base_metrics,
                    "video_stream_bytes_per_frame": value,
                    "boot_lane": "lane-a",
                    "eyeball": "ok",
                    "eyeball_source": "human",
                    "eyeball_reviewed_at": "2026-08-08T00:00:00Z",
                    "output_path": output_name,
                    "artifact_sha256": run_recipe.sha256_file(output_file),
                }
                (results / f"sample_run{index}.json").write_text(
                    json.dumps(receipt), encoding="utf-8"
                )

            with (
                mock.patch.object(run_recipe, "RESULTS_DIR", results),
                mock.patch.object(run_recipe, "REPO_ROOT", root),
            ):
                at_two = run_recipe.bitrate_anomaly_fields(
                    "sample", {**base_metrics, "video_stream_bytes_per_frame": 200.0}, "lane-a"
                )
                above_two = run_recipe.bitrate_anomaly_fields(
                    "sample", {**base_metrics, "video_stream_bytes_per_frame": 200.01}, "lane-a"
                )
                other_lane = run_recipe.bitrate_anomaly_fields(
                    "sample", {**base_metrics, "video_stream_bytes_per_frame": 300.0}, "lane-b"
                )

            self.assertFalse(at_two["bitrate_anomaly"])
            self.assertTrue(above_two["bitrate_anomaly"])
            self.assertEqual(other_lane["bitrate_baseline_status"], "provisional:0-of-3-clean-artifacts")


if __name__ == "__main__":
    unittest.main()
