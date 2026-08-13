import hashlib
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from scratch import build_h3_canonical_canvas_ladders as builder
from scratch import package_h3_25fps_lipsync_proof as packager
from validate_recipes import topology_contract_errors, validate_recipe_file


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "models_manifest.md"


class H3CanonicalCanvasLadderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = builder.build_recipes()
        cls.paths = {
            name: ROOT / "recipes" / f"{name}.json" for name in cls.expected
        }
        cls.actual = {
            name: json.loads(path.read_text(encoding="utf-8"))
            for name, path in cls.paths.items()
        }

    def test_hash_pinned_sources_and_fixtures(self):
        pins = {
            builder.I2V_SOURCE: builder.I2V_SOURCE_SHA256,
            builder.REF2VA_SOURCE: builder.REF2VA_SOURCE_SHA256,
            builder.SCENE_FIXTURE: builder.SCENE_SHA256,
            builder.PORTRAIT_FIXTURE: builder.PORTRAIT_SHA256,
            builder.TTS_FIXTURE: builder.TTS_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_generated_recipes_are_canonical_immutable_builder_output(self):
        self.assertEqual(self.actual, self.expected)
        self.assertEqual(len(self.actual), 6)
        for path in self.paths.values():
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
            self.assertNotIn(b"\r\n", raw, path)
            self.assertTrue(raw.endswith(b"\n"), path)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = builder.write_recipes(output)
            self.assertEqual(set(first), set(self.expected))
            self.assertTrue(all(first.values()))
            second = builder.write_recipes(output)
            self.assertTrue(not any(second.values()))
            drifted = output / f"{builder.i2v_name(107)}.json"
            drifted.write_bytes(b"{}\n")
            with self.assertRaisesRegex(
                RuntimeError, "Immutable generated recipe differs"
            ):
                builder.write_recipes(output)

    def test_canvas_frame_grid_duration_and_lane_contracts(self):
        for mode, name_fn in (
            ("i2v", builder.i2v_name),
            ("r2v_refaudio", builder.ref2va_name),
        ):
            for frames in builder.FRAME_RUNGS:
                recipe = self.actual[name_fn(frames)]
                contract = recipe["contract"]
                self.assertEqual(contract["mode"], mode)
                self.assertEqual(
                    (contract["width"], contract["height"]),
                    (832, 480),
                )
                self.assertEqual(contract["frames"], frames)
                self.assertEqual(contract["fps"], 24.0)
                self.assertEqual(contract["duration_s"], round(frames / 24, 6))
                self.assertEqual((frames - 5) % 17, 0)
                self.assertEqual(contract["h3_grid_k"], (frames - 5) // 17)
                self.assertTrue(contract["requires_disable_pinned_memory"])
                self.assertEqual(
                    contract["required_boot_lane"],
                    "lab-8199, sage-free, manager-offline-test, no-pinned",
                )
                warm = recipe["receipt_requirements"]["warm_gate"]
                self.assertEqual(warm["required_consecutive_runs"], 2)
                self.assertEqual(warm["passing_run"], "second consecutive run")
                self.assertEqual(warm["required_lane"], "--disable-pinned-memory")
                self.assertTrue(warm["executor_cache_nonce_required"])
                manager = recipe["receipt_requirements"]["manager_offline_gate"]
                self.assertTrue(manager["required"])
                self.assertEqual(
                    manager["authoritative_source"], "pair-unique server log"
                )
                self.assertEqual(manager["required_announcement_count"], 1)
                self.assertTrue(manager["must_precede_first_prompt"])
                idle = recipe["receipt_requirements"]["preboot_gpu_idle_gate"]
                self.assertTrue(idle["cold_required"])
                self.assertEqual(idle["sample_count"], 5)
                self.assertTrue(idle["vram_used_recorded_non_gating"])
                self.assertTrue(idle["gpu_utilization_recorded_non_gating"])
                self.assertTrue(
                    idle["desktop_graphics_signals_retained_but_not_required"]
                )
                self.assertTrue(idle["display_active_recorded_non_gating"])
                self.assertEqual(
                    idle["display_active_allowed_measured_states"],
                    ["Disabled", "Enabled"],
                )
                self.assertNotIn("required_display_active", idle)
                self.assertTrue(
                    idle["advisory_unreadable_processes_retained_non_gating"]
                )
                self.assertTrue(idle["shared_positive_workload_classifier_required"])
                self.assertTrue(
                    idle[
                        "optional_verified_direct_windows_venv_launcher_exclusion"
                    ]
                )
                self.assertEqual(
                    idle["windows_venv_launcher_exclusion_max_count"], 1
                )
                self.assertTrue(idle["redacted_process_evidence_required"])
                self.assertEqual(
                    idle["process_scan_result_fields"],
                    ["blocking_processes", "advisory_unreadable_processes"],
                )
                self.assertEqual(
                    idle["redacted_process_schema"],
                    builder.REDACTED_WORKLOAD_PROCESS_SCHEMA,
                )
                self.assertIn("no fresh idle sampling claimed", idle["warm_policy"])
                operator_policy = recipe["receipt_requirements"][
                    "operator_idle_policy"
                ]
                self.assertTrue(operator_policy["baseline_vram_recorded_advisory"])
                self.assertFalse(operator_policy["baseline_numeric_rejection"])
                self.assertTrue(
                    operator_policy[
                        "pair_cold_warm_baseline_drift_recorded_advisory"
                    ]
                )
                self.assertFalse(
                    operator_policy["pair_baseline_drift_numeric_rejection"]
                )
                self.assertEqual(
                    operator_policy["elevated_baseline_stamp"],
                    "elevated-baseline lane, operator-authorized 2026-08-10",
                )
                self.assertTrue(
                    operator_policy[
                        "per_leg_immediate_prequeue_known_workload_scan_required"
                    ]
                )
                self.assertTrue(
                    operator_policy[
                        "unreadable_unknown_python_advisory_non_gating"
                    ]
                )
                self.assertTrue(
                    operator_policy[
                        "optional_verified_direct_owned_server_windows_venv_launcher_exclusion"
                    ]
                )
                self.assertEqual(
                    operator_policy[
                        "owned_server_windows_venv_launcher_exclusion_max_count"
                    ],
                    1,
                )
                self.assertEqual(
                    operator_policy["owned_server_excluded_process_count_allowed"],
                    [1, 2],
                )
                self.assertEqual(
                    operator_policy["owned_lab_server_exclusion_schema"],
                    builder.OWNED_LAB_SERVER_EXCLUSION_SCHEMA,
                )
                self.assertEqual(
                    operator_policy[
                        "verified_owned_server_windows_venv_launcher_schema"
                    ],
                    builder.VERIFIED_OWNED_SERVER_WINDOWS_VENV_LAUNCHER_SCHEMA,
                )
                self.assertEqual(
                    operator_policy["excluded_owned_lab_server_row_schema"],
                    builder.EXCLUDED_OWNED_LAB_SERVER_ROW_SCHEMA,
                )
                self.assertTrue(
                    operator_policy["redacted_positive_workload_evidence_required"]
                )
                required_fields = recipe["receipt_requirements"][
                    "required_measured_fields"
                ]
                self.assertIn("absolute_peak_vram_gb", required_fields)
                self.assertIn("net_peak_vram_gb", required_fields)
                self.assertIn("baseline_lane_stamp", required_fields)
                self.assertEqual(
                    recipe["receipt_requirements"]["completion_timeout_s"],
                    builder.completion_timeout_seconds(frames),
                )

    def test_each_mode_ladder_changes_only_length_and_artifact_identity(self):
        expected_diff = {"7.inputs.length", "12.inputs.filename_prefix"}
        for name_fn in (builder.i2v_name, builder.ref2va_name):
            prompts = [
                self.actual[name_fn(frames)]["prompt"]
                for frames in builder.FRAME_RUNGS
            ]
            for left, right in zip(prompts, prompts[1:]):
                self.assertEqual(
                    builder.prompt_difference_paths(left, right), expected_diff
                )

    def test_i2v_retains_official_av_complete_topology(self):
        for frames in builder.FRAME_RUNGS:
            prompt = self.actual[builder.i2v_name(frames)]["prompt"]
            self.assertEqual(
                prompt["1"]["inputs"],
                {
                    "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                    "weight_dtype": "default",
                },
            )
            self.assertEqual(prompt["5"]["inputs"], {"noise_seed": 42})
            self.assertEqual(prompt["7"]["class_type"], "MiniMaxH3ImageToVideo")
            self.assertEqual(prompt["7"]["inputs"]["first_frame"], ["11", 0])
            self.assertNotIn("last_frame", prompt["7"]["inputs"])
            self.assertEqual(prompt["11"]["inputs"], {"image": "scene_still.png"})
            self.assertFalse(
                any(node["class_type"] == "LoadAudio" for node in prompt.values())
            )
            self.assertEqual(
                prompt["15"]["inputs"],
                {"samples": ["8", 0], "vae": ["4", 0]},
            )
            self.assertEqual(prompt["10"]["inputs"]["audio"], ["15", 0])

    def test_ref2va_retains_flat_v3_sockets_and_exact_fixture_path(self):
        for frames in builder.FRAME_RUNGS:
            prompt = self.actual[builder.ref2va_name(frames)]["prompt"]
            self.assertEqual(
                prompt["1"]["inputs"],
                {
                    "unet_name": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
                    "weight_dtype": "default",
                },
            )
            self.assertEqual(prompt["5"]["inputs"], {"noise_seed": 43})
            inputs = prompt["7"]["inputs"]
            references = {
                key: value
                for key, value in inputs.items()
                if key.startswith(
                    (
                        "ref_images.",
                        "ref_audios.",
                        "ref_videos.",
                        "ref_video_audios.",
                    )
                )
            }
            self.assertEqual(
                references,
                {
                    "ref_images.ref_image_0": ["11", 0],
                    "ref_audios.ref_audio_0": ["16", 0],
                },
            )
            self.assertEqual(inputs["ref_image_size"], "match")
            self.assertEqual(inputs["prompt"], builder.ACTION_PROMPT)
            self.assertEqual(prompt["11"]["inputs"], {"image": "portrait.png"})
            self.assertEqual(prompt["16"]["inputs"], {"audio": "tts_dialogue.wav"})
            consumers = {
                (node_id, input_name)
                for node_id, node in prompt.items()
                for input_name, value in node["inputs"].items()
                if value == ["16", 0]
            }
            self.assertEqual(consumers, {("7", "ref_audios.ref_audio_0")})
            self.assertEqual(prompt["10"]["inputs"]["audio"], ["15", 0])

    def test_sampler_scheduler_and_native_delivery_are_fixed(self):
        for recipe in self.actual.values():
            prompt = recipe["prompt"]
            self.assertEqual(prompt["13"]["inputs"], {"sampler_name": "res_multistep"})
            self.assertEqual(
                prompt["14"]["inputs"],
                {
                    "model": ["1", 0],
                    "scheduler": "simple",
                    "steps": 20,
                    "denoise": 1.0,
                },
            )
            self.assertEqual(prompt["10"]["inputs"]["fps"], 24.0)
            self.assertEqual(prompt["10"]["inputs"]["audio"], ["15", 0])

    def test_offline_validator_accepts_every_recipe(self):
        for name, path in self.paths.items():
            recipe = self.actual[name]
            self.assertEqual(topology_contract_errors(recipe, recipe["prompt"]), [])
            report = validate_recipe_file(path)
            self.assertTrue(report["valid"], (name, report["errors"]))
            self.assertEqual(report["warnings"], [], name)

    def test_models_are_manifested_and_prefixes_are_globally_unique(self):
        manifest = MANIFEST.read_text(encoding="utf-8")
        for model in (
            "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
            "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            "minimax_h3_video_vae_fp16.safetensors",
            "minimax_h3_audio_vae_fp32.safetensors",
        ):
            self.assertIn(f"`{model}`", manifest)

        all_prefixes: list[str] = []
        for path in (ROOT / "recipes").glob("*.json"):
            recipe = json.loads(path.read_text(encoding="utf-8"))
            all_prefixes.extend(
                node["inputs"]["filename_prefix"]
                for node in recipe.get("prompt", {}).values()
                if node.get("class_type") == "SaveVideo"
                and isinstance(node.get("inputs", {}).get("filename_prefix"), str)
            )
        for recipe in self.actual.values():
            prefix = recipe["prompt"]["12"]["inputs"]["filename_prefix"]
            self.assertEqual(all_prefixes.count(prefix), 1, prefix)


class H3LipSyncPackagingPlanTests(unittest.TestCase):
    @staticmethod
    def _valid_source_receipt(source: Path) -> dict:
        return {
            "recipe": packager.SOURCE_RECIPE_NAME,
            "recipe_sha256": packager.SOURCE_RECIPE_SHA256,
            "artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "artifact_bytes": source.stat().st_size,
            "gate_pass": True,
            "pass": False,
            "warm_pass": False,
            "run_number": 1,
            "run_count": 1,
            "config_run_count": 1,
            "output_path": source.name,
            "boot_lane": packager.SOURCE_BOOT_LANE,
            "fixture_sha256s": {
                "portrait.png": packager.PORTRAIT_SHA256,
                "tts_dialogue.wav": packager.TTS_SHA256,
            },
            "encoded_width": 832,
            "encoded_height": 480,
            "encoded_frame_count": 192,
            "encoded_fps": 24.0,
            "audio_present": True,
            "audio_duration_s": 8.0,
            "manager_offline_probe": {
                "pre_queue": {
                    "valid": True,
                    "verified_before_this_prompt": True,
                    "require_no_prior_prompt": True,
                    "log_scan": {
                        "authoritative_server_reported_mode": {
                            "resolved_mode": "offline",
                            "mode_precedes_first_execution": True,
                        }
                    },
                }
            },
            "server_argv": [
                "main.py",
                "--port",
                "8199",
                "--reserve-vram",
                "12",
                "--disable-pinned-memory",
                "--cache-classic",
            ],
        }

    def test_packager_is_pinned_to_the_seed43_192_frame_recipe(self):
        self.assertEqual(
            hashlib.sha256(packager.SOURCE_RECIPE.read_bytes()).hexdigest(),
            packager.SOURCE_RECIPE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(packager.TTS_FIXTURE.read_bytes()).hexdigest(),
            packager.TTS_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(packager.PORTRAIT_FIXTURE.read_bytes()).hexdigest(),
            packager.PORTRAIT_SHA256,
        )
        recipe = json.loads(packager.SOURCE_RECIPE.read_text(encoding="utf-8"))
        self.assertEqual(recipe["name"], packager.SOURCE_RECIPE_NAME)
        self.assertEqual(recipe["prompt"]["5"]["inputs"], {"noise_seed": 43})
        self.assertEqual(recipe["contract"]["frames"], 192)
        self.assertEqual(recipe["contract"]["fps"], 24.0)
        self.assertEqual(
            recipe["contract"]["required_boot_lane"], packager.SOURCE_BOOT_LANE
        )
        self.assertEqual(
            recipe["prompt"]["12"]["inputs"]["filename_prefix"],
            f"{packager.SOURCE_RECIPE_NAME}_out",
        )

    def test_plan_makes_the_intentional_drift_and_duration_fix_explicit(self):
        source = Path("C:/proof/source.mp4")
        source_receipt = Path("C:/proof/source_run1.json")
        output = Path("C:/proof/out")
        plan = packager.build_plan(source, source_receipt, output)
        self.assertEqual(plan["source_run_receipt"], str(source_receipt))
        self.assertEqual(plan["delivery_contract"]["raw_frames"], 192)
        self.assertEqual(plan["delivery_contract"]["raw_duration_s"], 7.68)
        self.assertEqual(plan["delivery_contract"]["fixed_frames"], 200)
        self.assertEqual(plan["delivery_contract"]["fixed_duration_s"], 8.0)
        self.assertEqual(plan["delivery_contract"]["human_review"], "PENDING_HUMAN")
        self.assertEqual(
            plan["delivery_contract"]["certification_status"],
            "NONCERTIFYING_REVIEW_COPIES",
        )
        self.assertEqual(
            plan["source_contract"]["evidence_role"],
            "authorized cold review source only; noncertifying",
        )
        self.assertFalse(plan["source_contract"]["expected_pass"])
        self.assertFalse(plan["source_contract"]["expected_warm_pass"])
        self.assertEqual(plan["delivery_contract"]["judgment_policy"], "packager makes no lip-sync judgment")

        raw, fixed = plan["variants"]
        self.assertEqual(raw["video_filter"], "settb=AVTB,setpts=N/(25*TB)")
        self.assertEqual(fixed["video_filter"], "fps=fps=25:start_time=0:round=near")
        for variant in (raw, fixed):
            command = variant["command"]
            self.assertEqual(command.count("-i"), 2)
            self.assertIn(str(packager.TTS_FIXTURE), command)
            self.assertEqual(command[command.index("-map") + 1], "0:v:0")
            second_map = command.index("-map", command.index("-map") + 1)
            self.assertEqual(command[second_map + 1], "1:a:0")
            self.assertIn("asetpts=PTS-STARTPTS", command[command.index("-af") + 1])
            self.assertEqual(command[command.index("-r") + 1], "25")
            self.assertIn("-n", command)

    def test_output_probe_validator_enforces_exact_frames_and_25fps(self):
        def probe(frames: int, duration: float) -> dict:
            return {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "pix_fmt": "yuv420p",
                        "width": 832,
                        "height": 480,
                        "nb_read_frames": str(frames),
                        "avg_frame_rate": "25/1",
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "sample_rate": "48000",
                        "channels": 2,
                        "start_time": "0.000000",
                        "duration": f"{duration:.6f}",
                    },
                ],
                "format": {"duration": f"{duration:.6f}"},
            }

        raw = packager.validate_output(probe(192, 7.68), packager.VARIANTS[0])
        fixed = packager.validate_output(probe(200, 8.0), packager.VARIANTS[1])
        self.assertEqual((raw["frames"], raw["fps"]), (192, 25.0))
        self.assertEqual((fixed["frames"], fixed["fps"]), (200, 25.0))
        with self.assertRaisesRegex(RuntimeError, "expected 200 frames"):
            packager.validate_output(probe(199, 8.0), packager.VARIANTS[1])
        bad_audio = probe(192, 7.68)
        bad_audio["streams"][1]["duration"] = "7.000000"
        with self.assertRaisesRegex(RuntimeError, "audio duration"):
            packager.validate_output(bad_audio, packager.VARIANTS[0])

    def test_raw_tts_probe_validator_pins_stream_shape_and_duration(self):
        probe = {
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "pcm_s16le",
                    "sample_rate": "44100",
                    "channels": 1,
                    "bits_per_sample": 16,
                    "duration": "10.000000",
                }
            ],
            "format": {"duration": "10.000000"},
        }
        evidence = packager.validate_tts_fixture(probe)
        self.assertEqual(evidence["duration_s"], 10.0)
        contaminated = json.loads(json.dumps(probe))
        contaminated["streams"].insert(
            0, {"codec_type": "video", "codec_name": "png"}
        )
        with self.assertRaisesRegex(RuntimeError, "exact stream types"):
            packager.validate_tts_fixture(contaminated)

    def test_source_validator_requires_native_audio_and_exact_media_shape(self):
        probe = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 832,
                    "height": 480,
                    "nb_read_frames": "192",
                    "avg_frame_rate": "24/1",
                    "duration": "8.000000",
                },
                {
                    "codec_type": "audio",
                    "start_time": "0.000000",
                    "duration": "8.000000",
                },
            ],
            "format": {"duration": "8.000000"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.mp4"
            source.write_bytes(b"source")
            packager.validate_source(source, packager.TTS_FIXTURE, probe)
            no_audio = json.loads(json.dumps(probe))
            no_audio["streams"] = no_audio["streams"][:1]
            with self.assertRaisesRegex(RuntimeError, "exact stream types"):
                packager.validate_source(source, packager.TTS_FIXTURE, no_audio)

    def test_source_receipt_must_hash_bind_the_render_and_recipe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = root / "outputs"
            outputs.mkdir()
            results = root / "results"
            results.mkdir()
            source = outputs / packager.SOURCE_ARTIFACT_BASENAME
            source.write_bytes(b"receipt-bound-source")
            receipt_path = results / packager.SOURCE_RECEIPT_BASENAME
            receipt = self._valid_source_receipt(source)
            receipt_path.write_bytes(
                (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
            )
            with mock.patch.object(packager, "ROOT", root):
                evidence = packager.validate_source_receipt(source, receipt_path)
            self.assertTrue(evidence["gate_pass"])
            self.assertFalse(evidence["pass"])
            self.assertFalse(evidence["warm_pass"])
            self.assertEqual(evidence["run_number"], 1)
            receipt["artifact_sha256"] = "0" * 64
            receipt_path.write_bytes(
                (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
            )
            with self.assertRaisesRegex(RuntimeError, "artifact SHA-256 mismatch"):
                with mock.patch.object(packager, "ROOT", root):
                    packager.validate_source_receipt(source, receipt_path)

    def test_source_receipt_rejects_certifying_or_wrong_h3_boot_lane(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = root / "outputs"
            outputs.mkdir()
            results = root / "results"
            results.mkdir()
            source = outputs / packager.SOURCE_ARTIFACT_BASENAME
            source.write_bytes(b"receipt-bound-source")
            receipt_path = results / packager.SOURCE_RECEIPT_BASENAME
            base = self._valid_source_receipt(source)
            certifying = dict(base)
            certifying.update({"pass": True, "warm_pass": True})
            receipt_path.write_bytes(
                (json.dumps(certifying, indent=2) + "\n").encode("utf-8")
            )
            with self.assertRaisesRegex(RuntimeError, "noncertifying cold review run"):
                with mock.patch.object(packager, "ROOT", root):
                    packager.validate_source_receipt(source, receipt_path)

            wrong_lane = dict(base)
            wrong_lane["boot_lane"] = "lab-8199, sage-free"
            receipt_path.write_bytes(
                (json.dumps(wrong_lane, indent=2) + "\n").encode("utf-8")
            )
            with self.assertRaisesRegex(RuntimeError, "exact Job-D lane"):
                with mock.patch.object(packager, "ROOT", root):
                    packager.validate_source_receipt(source, receipt_path)

    def test_source_receipt_rejects_fixture_offline_or_reserve_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = root / "outputs"
            results = root / "results"
            outputs.mkdir()
            results.mkdir()
            source = outputs / packager.SOURCE_ARTIFACT_BASENAME
            source.write_bytes(b"receipt-bound-source")
            receipt_path = results / packager.SOURCE_RECEIPT_BASENAME
            valid = self._valid_source_receipt(source)

            fixture_drift = json.loads(json.dumps(valid))
            fixture_drift["fixture_sha256s"]["tts_dialogue.wav"] = "0" * 64
            receipt_path.write_bytes(
                (json.dumps(fixture_drift, indent=2) + "\n").encode("utf-8")
            )
            with self.assertRaisesRegex(RuntimeError, r"exact portrait \+ TTS"):
                with mock.patch.object(packager, "ROOT", root):
                    packager.validate_source_receipt(source, receipt_path)

            offline_drift = json.loads(json.dumps(valid))
            mode = offline_drift["manager_offline_probe"]["pre_queue"]["log_scan"]
            mode["authoritative_server_reported_mode"]["resolved_mode"] = "public"
            receipt_path.write_bytes(
                (json.dumps(offline_drift, indent=2) + "\n").encode("utf-8")
            )
            with self.assertRaisesRegex(RuntimeError, "network_mode: offline"):
                with mock.patch.object(packager, "ROOT", root):
                    packager.validate_source_receipt(source, receipt_path)

            reserve_drift = json.loads(json.dumps(valid))
            argv = reserve_drift["server_argv"]
            argv[argv.index("--reserve-vram") + 1] = "11.5"
            receipt_path.write_bytes(
                (json.dumps(reserve_drift, indent=2) + "\n").encode("utf-8")
            )
            with self.assertRaisesRegex(RuntimeError, "reserve-12gb"):
                with mock.patch.object(packager, "ROOT", root):
                    packager.validate_source_receipt(source, receipt_path)

    def test_source_receipt_rejects_noncanonical_run_or_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = root / "outputs"
            results = root / "results"
            outputs.mkdir()
            results.mkdir()
            source = outputs / packager.SOURCE_ARTIFACT_BASENAME
            source.write_bytes(b"receipt-bound-source")
            receipt_path = results / packager.SOURCE_RECEIPT_BASENAME
            receipt = self._valid_source_receipt(source)
            receipt.update(
                {"run_number": 2, "run_count": 2, "config_run_count": 2}
            )
            receipt_path.write_bytes(
                (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
            )
            with self.assertRaisesRegex(RuntimeError, "exact authorized cold run-1"):
                with mock.patch.object(packager, "ROOT", root):
                    packager.validate_source_receipt(source, receipt_path)
            with self.assertRaisesRegex(RuntimeError, "exact authorized Job-D cold artifact"):
                with mock.patch.object(packager, "ROOT", root):
                    packager.validate_source_receipt(
                        outputs / "other.mp4", receipt_path
                    )

    def test_receipt_write_is_o_excl_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proof.json"
            first = b'{"first":true}\n'
            packager.immutable_write(path, first)
            with self.assertRaisesRegex(RuntimeError, "refusing to replace"):
                packager.immutable_write(path, b'{"second":true}\n')
            self.assertEqual(path.read_bytes(), first)

    def test_duration_arithmetic_matches_the_design_claim(self):
        self.assertEqual(packager.RAW_DURATION_S, Fraction(192, 25))
        self.assertEqual(packager.FIXED_DURATION_S, Fraction(200, 25))
        self.assertEqual(float(packager.FIXED_DURATION_S - packager.RAW_DURATION_S), 0.32)


if __name__ == "__main__":
    unittest.main()
