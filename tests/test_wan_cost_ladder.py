from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRATCH / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FIXTURES = load("wan_cost_fixture_test", "build_wan_cost_ladder_fixtures.py")
BASELINE = load("wan_cost_baseline_test", "capture_wan_cost_baseline.py")
MANAGER = load("wan_cost_manager_guard_test", "manager_offline_guard.py")
REPLAY = load("wan_cost_replay_test", "otr_visual_smoke_cachebust.py")
SIDECAR = load("wan_cost_sidecar_test", "wan_cost_ladder_sidecar.py")
REDUCE = load("wan_cost_reduce_test", "reduce_wan_cost_ladder.py")
CAMPAIGN = load("wan_cost_campaign_test", "run_wan_cost_ladder_campaign.py")
OWNERSHIP = load("wan_cost_ownership_test", "wan_cost_ownership.py")


class WanCostFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = FIXTURES._source_ledger()

    def test_declared_ladders_are_exact_and_legal(self):
        self.assertEqual(FIXTURES.LADDERS["wan_ti2v"], (25, 65, 93, 129, 177))
        self.assertEqual(FIXTURES.LADDERS["fastwan_8gb"], (25, 93, 177))
        for lengths in FIXTURES.LADDERS.values():
            for frames in lengths:
                self.assertEqual((frames - 1) % 4, 0)
                self.assertGreaterEqual(frames, 17)

    def test_every_fixture_renders_n_and_trims_only_at_assembly(self):
        for engine, lengths in FIXTURES.LADDERS.items():
            for frames in lengths:
                ledger = FIXTURES.derive_ledger(self.source, engine, frames)
                shot = ledger["video"]["shots"][0]
                self.assertEqual(shot["engine_id"], engine)
                self.assertEqual(shot["request_seed"], 0)
                self.assertEqual(FIXTURES.EFFECTIVE_VIDEO_SEED, 944021193)
                self.assertEqual(shot["target_frame_count"], frames - 1)
                self.assertEqual(
                    shot["coverage_plan"],
                    {
                        "target_visible_frames": frames - 1,
                        "join_mode": "single",
                        "segments": [
                            {
                                "index": 0,
                                "render_frames": frames,
                                "drop_head": 0,
                                "trim_tail": 1,
                            }
                        ],
                    },
                )

    def test_frame_count_is_only_within_engine_generation_variable(self):
        ignored = {
            "episode_id",
            "target_frame_count",
            "coverage_plan",
            "clip_budget",
            "wan_cost_ladder_measurement",
        }

        def normalized(ledger):
            value = copy.deepcopy(ledger)
            value.pop("episode_id", None)
            value.get("meta", {}).pop("wan_cost_ladder_measurement", None)
            value.get("video", {}).pop("clip_budget", None)
            shot = value["video"]["shots"][0]
            shot.pop("target_frame_count", None)
            shot.pop("coverage_plan", None)
            return value

        self.assertEqual(ignored, ignored)  # documents the normalization surface
        for engine, lengths in FIXTURES.LADDERS.items():
            rows = [normalized(FIXTURES.derive_ledger(self.source, engine, n)) for n in lengths]
            for row in rows[1:]:
                self.assertEqual(row, rows[0])

    def test_production_settings_pin_wan_and_exact_fastwan_sampler(self):
        wan = FIXTURES.PRODUCTION_SETTINGS["wan_ti2v"]
        self.assertEqual((wan["steps"], wan["cfg"], wan["shift"]), (30, 5.0, 5.0))
        self.assertEqual((wan["sampler"], wan["scheduler"]), ("euler", "simple"))
        self.assertEqual(wan["clip"], "umt5-xxl-encoder-Q5_K_M.gguf")
        fast = FIXTURES.PRODUCTION_SETTINGS["fastwan_8gb"]
        self.assertEqual(fast["inherits"], "wan_ti2v")
        self.assertEqual(fast["steps"], 3)
        self.assertEqual(fast["sampler"], "OTR_DMDRestartSamplerSelect")
        self.assertEqual(fast["sigmas"], "1.0, 0.757, 0.522, 0.0")
        self.assertEqual(fast["lora_strength"], 1.0)
        for engine in FIXTURES.LADDERS:
            proof = FIXTURES.verify_production_source(engine)
            self.assertEqual(proof["status"], "VERIFIED_FROM_LOCAL_SOURCE")
            self.assertTrue(all(count > 0 for count in proof["tokens_checked"].values()))

    def test_lab_manifest_blocks_exact_default_clip_until_live_refresh(self):
        status = FIXTURES.inventory_status()
        self.assertEqual(status["status"], "BLOCKED_MANIFEST_REFRESH_REQUIRED")
        self.assertIn("umt5-xxl-encoder-Q5_K_M.gguf", status["missing"])
        self.assertNotIn("Wan2.2-TI2V-5B-Q5_K_M.gguf", status["missing"])
        self.assertNotIn("wan2.2_vae.safetensors", status["missing"])
        self.assertNotIn(
            "Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors",
            status["missing"],
        )
        disk = FIXTURES.physical_asset_status()
        self.assertEqual(disk["status"], "AVAILABLE")
        self.assertTrue(all(row["bytes"] > 0 for row in disk["assets"].values()))

    def test_execution_plan_is_sequential_and_warm_receipt_bound(self):
        plan = FIXTURES.execution_plan()
        self.assertEqual(len(plan["pairs_in_required_sequence"]), 8)
        self.assertEqual(plan["boot_existing_otr_lane_via_start_process"]["ArgumentList"][-1], "WAN")
        for pair in plan["pairs_in_required_sequence"]:
            first = pair["pair_first_argv"]
            warm = pair["warm_second_argv"]
            self.assertIn("pair_first", first)
            self.assertIn("warm_second", warm)
            self.assertNotIn("--previous-receipt", first)
            self.assertIn("--previous-receipt", warm)
            previous = warm[warm.index("--previous-receipt") + 1]
            first_output = first[first.index("--output") + 1]
            self.assertEqual(previous, first_output)
            self.assertIn("0.2", first)
            self.assertIn("0.2", warm)


class WanCostReplayTests(unittest.TestCase):
    def test_replay_endpoint_is_exact_and_fail_closed(self):
        required = "http://127.0.0.1:8000"
        self.assertEqual(
            REPLAY.validate_comfyui_endpoint({"COMFYUI_URL": required}), required
        )
        for value in ("", "http://127.0.0.1:8188", "https://remote.example"):
            with self.assertRaises(REPLAY.ReplayError):
                REPLAY.validate_comfyui_endpoint({"COMFYUI_URL": value})

    def test_replay_self_attests_only_offline_nonsecret_credentials(self):
        environment = dict(MANAGER.OFFLINE_CREDENTIAL_ENVIRONMENT)
        proof = REPLAY.validate_offline_credential_environment(environment)
        self.assertTrue(proof["validated"])
        self.assertEqual(
            proof["nonsecret_sentinel_length"], len(MANAGER.OFFLINE_TOKEN_SENTINEL)
        )
        for bad in (
            {**environment, "HF_TOKEN": "real-secret"},
            {**environment, "HF_API_TOKEN": "real-secret"},
            {**environment, "hf_token": "case-variant-secret"},
        ):
            with self.assertRaises(REPLAY.ReplayError):
                REPLAY.validate_offline_credential_environment(bad)

    def test_sidecar_overrides_and_redacts_ambient_endpoint(self):
        secrets = {
            "HF_TOKEN": "real-secret-a",
            "HUGGING_FACE_HUB_TOKEN": "real-secret-b",
            "HUGGINGFACE_HUB_TOKEN": "real-secret-c",
            "HF_API_TOKEN": "real-secret-d",
            "hf_token": "real-secret-case-variant",
        }
        environment, evidence = SIDECAR.pinned_replay_environment(
            {
                "COMFYUI_URL": "https://user:secret@remote.example",
                "KEEP": "yes",
                **secrets,
            }
        )
        self.assertEqual(environment["COMFYUI_URL"], "http://127.0.0.1:8000")
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["KEEP"], "yes")
        self.assertTrue(evidence["conflicting_ambient_cleared"])
        self.assertTrue(evidence["ambient_value_redacted"])
        self.assertNotIn("remote.example", json.dumps(evidence))
        for key, expected in MANAGER.OFFLINE_CREDENTIAL_ENVIRONMENT.items():
            self.assertEqual(environment[key], expected)
        for key in MANAGER.SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS:
            self.assertNotIn(key, environment)
        serialized = json.dumps(evidence)
        for secret in secrets.values():
            self.assertNotIn(secret, serialized)
        self.assertNotIn("hf_token", environment)
        self.assertEqual(
            MANAGER.validate_offline_credential_environment_evidence(
                evidence["offline_credentials"]
            ),
            [],
        )

    def test_endpoint_binding_requires_owned_loopback_listener(self):
        server = {
            "serving_pid": 123,
            "process_create_time": 10.0,
            "listeners": [
                {"address": "127.0.0.1", "port": 8000, "pid": 123}
            ],
        }
        _child_environment, credential_evidence = (
            MANAGER.pin_offline_credential_environment({})
        )
        environment = {
            "required": "http://127.0.0.1:8000",
            "pinned_child_value": "http://127.0.0.1:8000",
            "python_dont_write_bytecode": "1",
            "offline_credentials": credential_evidence,
        }
        child_credential = {
            "validated": True,
            "nonsecret_sentinel_length": len(MANAGER.OFFLINE_TOKEN_SENTINEL),
            "set_key_names": sorted(MANAGER.OFFLINE_CREDENTIAL_ENVIRONMENT),
            "scrubbed_key_names_absent": list(
                MANAGER.SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS
            ),
            "ambient_values_never_read_or_returned": True,
        }
        binding, errors = SIDECAR.validate_replay_endpoint_binding(
            server,
            environment,
            {
                "comfyui_url": "http://127.0.0.1:8000",
                "python_dont_write_bytecode": True,
                "offline_credential_environment": child_credential,
            },
        )
        self.assertEqual(errors, [])
        self.assertTrue(binding["validated"])
        server["listeners"][0]["pid"] = 999
        binding, errors = SIDECAR.validate_replay_endpoint_binding(
            server,
            environment,
            {
                "comfyui_url": "http://127.0.0.1:8000",
                "python_dont_write_bytecode": True,
                "offline_credential_environment": child_credential,
            },
        )
        self.assertTrue(errors)
        self.assertFalse(binding["validated"])

    def test_rendered_clip_copy_is_fresh_hash_bound_lab_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            evidence = root / "evidence"
            output.mkdir()
            source = output / "clip.mp4"
            source.write_bytes(b"fresh-video-bytes")
            started_ns = source.stat().st_mtime_ns - 1
            now_ns = source.stat().st_mtime_ns
            report_snapshot = {
                "path": str(root / "report.json"),
                "exists": True,
                "bytes": 2,
                "mtime_ns": now_ns,
                "device": 1,
                "inode": 2,
                "sha256": "a" * 64,
            }
            manifest_snapshot = {
                "path": str(root / "manifest.json"),
                "exists": True,
                "bytes": 2,
                "mtime_ns": now_ns,
                "device": 1,
                "inode": 3,
                "sha256": "b" * 64,
            }
            old_root = SIDECAR.EVIDENCE_CLIP_ROOT
            SIDECAR.EVIDENCE_CLIP_ROOT = evidence
            try:
                binding = SIDECAR.capture_rendered_clip(
                    {
                        "clips": [
                            {
                                "exists": True,
                                "type": "video",
                                "path": str(source),
                            }
                        ]
                    },
                    label="wan_ti2v_f025_run1",
                    started_ns=started_ns,
                    server_output=output,
                    report_snapshot=report_snapshot,
                    manifest_snapshot=manifest_snapshot,
                )
            finally:
                SIDECAR.EVIDENCE_CLIP_ROOT = old_root
            copied = Path(binding["evidence"]["path"])
            self.assertEqual(copied.read_bytes(), source.read_bytes())
            self.assertEqual(
                binding["evidence"]["sha256"], binding["source_before"]["sha256"]
            )
            self.assertTrue(binding["freshness_window"]["within_window"])
            self.assertEqual(
                binding["fresh_state_files"]["node_episode_report"],
                report_snapshot,
            )

    def test_cache_buster_changes_only_inert_oom_index(self):
        base = {
            "92": {
                "class_type": "OTR_VideoRenderBatch",
                "inputs": {
                    "mode": "episode",
                    "oom_index": 0,
                    "patched_ledger_json": "{}",
                    "master_audio_path": "master.wav",
                    "image_done": "done",
                },
            }
        }
        changed = REPLAY.inject_cache_buster(base, 37)
        self.assertEqual(base["92"]["inputs"]["oom_index"], 0)
        self.assertEqual(changed["92"]["inputs"]["oom_index"], 37)
        changed["92"]["inputs"]["oom_index"] = 0
        self.assertEqual(changed, base)

    def test_cache_buster_refuses_non_episode_and_out_of_range(self):
        prompt = {
            "92": {
                "class_type": "OTR_VideoRenderBatch",
                "inputs": {"mode": "single", "oom_index": 0},
            }
        }
        with self.assertRaises(REPLAY.ReplayError):
            REPLAY.inject_cache_buster(prompt, 1)
        prompt["92"]["inputs"]["mode"] = "episode"
        for value in (0, 400):
            with self.assertRaises(REPLAY.ReplayError):
                REPLAY.inject_cache_buster(prompt, value)

    def test_pair_cache_busters_are_unique_and_deterministic(self):
        seen = set()
        for engine, lengths in SIDECAR.LADDERS.items():
            for frames in lengths:
                first = SIDECAR.canonical_cache_buster(engine, frames, "pair_first")
                warm = SIDECAR.canonical_cache_buster(engine, frames, "warm_second")
                self.assertEqual(warm, first + 1)
                self.assertNotIn(first, seen)
                self.assertNotIn(warm, seen)
                seen.update((first, warm))
                self.assertEqual(
                    SIDECAR.canonical_label(engine, frames, "warm_second"),
                    f"{engine}_f{frames:03d}_run2",
                )

    def test_manifest_validator_proves_exact_rendered_length(self):
        manifest = {
            "canvas": {"w": 832, "h": 480},
            "clips": [
                {
                    "engine_id": "wan_ti2v",
                    "recipe": "wan22_ti2v_5b_i2v_single_pass_v1",
                    "quant": "Q5_K_M",
                    "use_lora": False,
                    "render_canvas": "832x480",
                    "vram_peak_mb": 8192,
                    "frame_count": 64,
                    "target_frame_count": 64,
                    "segments": [
                        {
                            "segment_index": 0,
                            "render_frames": 65,
                            "drop_head": 0,
                            "trim_tail": 1,
                            "native_frame_count": 65,
                        }
                    ],
                }
            ],
        }
        report = {
            "ok": True,
            "mode": "episode",
            "engine_histogram": {"wan_ti2v": 1},
            "trace": [
                {
                    "shot_id": "shot_b001",
                    "video_seed": 944021193,
                    "final_engine": "wan_ti2v",
                }
            ],
        }
        self.assertEqual(
            SIDECAR._validate_episode_payload(manifest, report, "wan_ti2v", 65), []
        )
        manifest["clips"][0]["segments"][0]["native_frame_count"] = 64
        self.assertTrue(
            SIDECAR._validate_episode_payload(manifest, report, "wan_ti2v", 65)
        )

    def test_manifest_validator_requires_adapter_render_peak(self):
        manifest = {
            "canvas": {"w": 832, "h": 480},
            "clips": [
                {
                    "engine_id": "wan_ti2v",
                    "recipe": "wan22_ti2v_5b_i2v_single_pass_v1",
                    "quant": "Q5_K_M",
                    "use_lora": False,
                    "render_canvas": "832x480",
                    "vram_peak_mb": None,
                    "frame_count": 64,
                    "target_frame_count": 64,
                    "segments": [
                        {
                            "segment_index": 0,
                            "render_frames": 65,
                            "drop_head": 0,
                            "trim_tail": 1,
                            "native_frame_count": 65,
                        }
                    ],
                }
            ],
        }
        report = {
            "ok": True,
            "mode": "episode",
            "engine_histogram": {"wan_ti2v": 1},
            "trace": [
                {
                    "shot_id": "shot_b001",
                    "video_seed": 944021193,
                    "final_engine": "wan_ti2v",
                }
            ],
        }
        errors = SIDECAR._validate_episode_payload(
            manifest, report, "wan_ti2v", 65
        )
        self.assertTrue(any("render-window VRAM peak" in error for error in errors))


class WanCostManagerOfflineGuardTests(unittest.TestCase):
    @staticmethod
    def clean_log(config_path: Path) -> str:
        return "\n".join(
            [
                f"** ComfyUI-Manager config path: {config_path}",
                "[ComfyUI-Manager] network_mode: offline",
                "Starting server",
                "To see the GUI go to: http://127.0.0.1:8000",
                "[ComfyUI-Manager] All startup tasks have been completed.",
                "",
            ]
        )

    def test_actual_manager_path_is_derived_from_launcher_and_serving_argv(self):
        preboot = MANAGER.launcher_offline_evidence(MANAGER.DEFAULT_LAUNCHER)
        expected_user = Path(r"C:\Users\jeffr\Documents\ComfyUI")
        expected_config = expected_user / "__manager" / "config.ini"
        self.assertEqual(
            Path(preboot["derivation"]["user_directory"]), expected_user
        )
        self.assertEqual(Path(preboot["config"]["path"]), expected_config)
        self.assertEqual(preboot["config"]["network_mode"], "offline")
        self.assertNotIn(r"\user\__manager", preboot["config"]["path"].lower())
        post = MANAGER.server_offline_evidence(
            ["python", "main.py", "--user-directory", str(expected_user)], preboot
        )
        self.assertTrue(post["matches_preboot_path_and_sha"])
        self.assertEqual(post["config"]["sha256"], preboot["config"]["sha256"])

    def test_relative_user_directories_fail_before_abspath(self):
        with self.assertRaises(MANAGER.ManagerOfflineError):
            MANAGER.manager_config_from_user_directory(Path("relative-user"))
        with self.assertRaises(MANAGER.ManagerOfflineError):
            MANAGER.argv_user_directory(
                ["python", "main.py", "--user-directory", "relative-user"]
            )

    def test_boot_gate_requires_offline_path_and_startup_completion(self):
        config = Path(r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "server.log"
            log.write_text(self.clean_log(config), encoding="utf-8", newline="\n")
            scan = MANAGER.scan_boot_log_prefix(log, config)
            self.assertEqual(scan["status"], "pass")
            self.assertEqual(scan["errors"], [])
            self.assertEqual(len(scan["startup_complete_markers"]), 1)
            authority = scan["authoritative_server_reported_mode"]
            self.assertEqual(authority["announcement_count"], 1)
            self.assertEqual(authority["observed_values"], ["offline"])
            self.assertEqual(authority["resolved_mode"], "offline")
            self.assertTrue(authority["mode_precedes_startup_completion"])
            self.assertTrue(authority["mode_precedes_first_execution"])
            self.assertTrue(authority["gate_evaluated_after_startup_tasks_complete"])
            self.assertEqual(MANAGER.validate_log_prefix_binding(scan, log), [])
            log.write_text(
                self.clean_log(config).replace(
                    "[ComfyUI-Manager] All startup tasks have been completed.\n", ""
                ),
                encoding="utf-8",
                newline="\n",
            )
            self.assertEqual(
                MANAGER.scan_boot_log_prefix(log, config)["status"], "fail"
            )

    def test_server_reported_mode_is_unique_authoritative_and_fail_closed(self):
        config = Path(r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "server.log"
            missing = self.clean_log(config).replace(
                "[ComfyUI-Manager] network_mode: offline\n", ""
            )
            duplicate = self.clean_log(config).replace(
                "[ComfyUI-Manager] network_mode: offline",
                "[ComfyUI-Manager] network_mode: offline\n"
                "[ComfyUI-Manager] network_mode: offline",
            )
            nonoffline = self.clean_log(config).replace(
                "network_mode: offline", "network_mode: public"
            )
            for text, values in (
                (missing, []),
                (duplicate, ["offline", "offline"]),
                (nonoffline, ["public"]),
            ):
                with self.subTest(values=values):
                    log.write_text(text, encoding="utf-8", newline="\n")
                    scan = MANAGER.scan_boot_log_prefix(log, config)
                    authority = scan["authoritative_server_reported_mode"]
                    self.assertEqual(scan["status"], "fail")
                    self.assertEqual(authority["observed_values"], values)
                    self.assertTrue(MANAGER.authoritative_mode_errors(scan))
            source = MANAGER.manager_source_proof()
            self.assertEqual(
                source["mode_authority_contract"]["manager_server_source_line"],
                29,
            )
            self.assertEqual(
                source["mode_authority_contract"][
                    "manager_core_default_source_line"
                ],
                1774,
            )
            self.assertIn(
                "'network_mode': 'public'",
                source["manager_core_required_tokens"][0],
            )

    def test_every_known_manager_network_marker_fails(self):
        config = Path(r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini")
        markers = [
            "[ComfyUI-Manager] default cache updated: https://example.invalid/cache.json",
            "FETCH DATA from: https://example.invalid/data.json",
            "FETCH ComfyRegistry Data: 5/170",
            "Start fetching...",
            "Fetching done.",
            "FETCH FAILED: timeout",
            "[ComfyUI-Manager] Downloading 'node-pack'",
            "[ComfyUI-Manager] Failed to perform initial fetching",
            "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/x.json",
        ]
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "server.log"
            for marker in markers:
                with self.subTest(marker=marker):
                    log.write_text(
                        self.clean_log(config) + marker + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                    scan = MANAGER.scan_boot_log_prefix(
                        log, config, require_pre_prompt=False
                    )
                    self.assertEqual(scan["status"], "fail")
                    self.assertTrue(scan["forbidden_network_markers"])
            for mode in ("public", "private"):
                with self.subTest(mode=mode):
                    log.write_text(
                        self.clean_log(config).replace(
                            "network_mode: offline", f"network_mode: {mode}"
                        ),
                        encoding="utf-8",
                        newline="\n",
                    )
                    self.assertEqual(
                        MANAGER.scan_boot_log_prefix(log, config)["status"], "fail"
                    )

    def test_local_downloader_route_names_do_not_false_block(self):
        config = Path(r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "server.log"
            log.write_text(
                self.clean_log(config)
                + "[ComfyUI-Manager] download_model_base local route registered\n"
                + "[ComfyUI-Manager] ModelDownloader Routes registered\n",
                encoding="utf-8",
                newline="\n",
            )
            scan = MANAGER.scan_boot_log_prefix(
                log, config, require_pre_prompt=False
            )
            self.assertEqual(scan["status"], "pass")
            self.assertEqual(scan["forbidden_network_markers"], [])

    def test_hf_resolution_allows_only_nonsecret_environment_sentinel(self):
        config = Path(r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini")
        expected = (
            "[hf_token] HF_TOKEN resolved from os.environ "
            f"(len={len(MANAGER.OFFLINE_TOKEN_SENTINEL)})"
        )
        forbidden = [
            "[hf_token] HF_TOKEN resolved from HKCU\\Environment (len=37)",
            "[hf_token] HF_TOKEN resolved from os.environ (len=37)",
            "[hf_token] No HF_TOKEN found in env or HKCU -- public repos only",
            "[hf_token] winreg lookup failed: denied",
        ]
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "server.log"
            log.write_text(
                self.clean_log(config) + expected + "\n",
                encoding="utf-8",
                newline="\n",
            )
            scan = MANAGER.scan_boot_log_prefix(
                log, config, require_pre_prompt=False
            )
            self.assertEqual(scan["status"], "pass")
            self.assertEqual(scan["forbidden_credential_markers"], [])
            self.assertEqual(
                scan["hf_token_resolution_markers"][0]["source"], "os.environ"
            )
            for marker in forbidden:
                with self.subTest(marker=marker):
                    log.write_text(
                        self.clean_log(config) + marker + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                    failed = MANAGER.scan_boot_log_prefix(
                        log, config, require_pre_prompt=False
                    )
                    self.assertEqual(failed["status"], "fail")
                    self.assertTrue(failed["forbidden_credential_markers"])

    def test_runtime_scan_allows_execution_but_rehashes_full_prefix(self):
        config = Path(r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "server.log"
            log.write_text(
                self.clean_log(config) + "got prompt\nPrompt executed in 1.0 seconds\n",
                encoding="utf-8",
                newline="\n",
            )
            self.assertEqual(
                MANAGER.scan_boot_log_prefix(log, config)["status"], "fail"
            )
            runtime = MANAGER.scan_boot_log_prefix(
                log, config, require_pre_prompt=False
            )
            self.assertEqual(runtime["status"], "pass")
            self.assertEqual(MANAGER.validate_runtime_log_binding(runtime, log), [])
            original = log.read_bytes()
            log.write_bytes(b"X" + original[1:])
            self.assertTrue(MANAGER.validate_runtime_log_binding(runtime, log))

    def test_sidecar_hash_binds_boot_guard_to_server_and_log_prefix(self):
        preboot = MANAGER.launcher_offline_evidence(MANAGER.DEFAULT_LAUNCHER)
        argv = [
            "python",
            "main.py",
            "--user-directory",
            preboot["derivation"]["user_directory"],
        ]
        postboot = MANAGER.server_offline_evidence(argv, preboot)
        server = {
            "serving_pid": 123,
            "process_create_time": 10.0,
            "parent_pid": 99,
            "executable": (
                OWNERSHIP.venv_base_interpreter_receipt()["base_interpreter"][
                    "path"
                ]
            ),
            "argv": argv,
        }
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "attempt-999"
            evidence.mkdir()
            log = evidence / "wan_cost_ladder.server.log"
            log.write_text(
                self.clean_log(Path(postboot["config"]["path"])),
                encoding="utf-8",
                newline="\n",
            )
            scan = MANAGER.scan_boot_log_prefix(
                log, Path(postboot["config"]["path"])
            )
            launcher_argv = [
                os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                "/d",
                "/c",
                str(SIDECAR.OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd"),
                str(log),
                "WAN",
            ]
            server["ownership_chain"] = {
                "validated": True,
                "policy": OWNERSHIP.POLICY_NAME,
                "validator_source": OWNERSHIP.validator_source_receipt(),
                "policy_precedent": OWNERSHIP.policy_precedent(),
                "venv_base_interpreter": (
                    OWNERSHIP.venv_base_interpreter_receipt()
                ),
                "chain_type": "direct-child",
                "launcher": {
                    "pid": 99,
                    "parent_pid": 1,
                    "process_create_time": 9.0,
                    "executable": launcher_argv[0],
                    "argv": launcher_argv,
                },
                "intermediary": None,
                "serving": {
                    "pid": 123,
                    "parent_pid": 99,
                    "process_create_time": 10.0,
                    "executable": server["executable"],
                    "argv": argv,
                },
                "expected_launcher_argv": launcher_argv,
            }
            source = (SCRATCH / "manager_offline_guard.py").resolve()
            payload = {
                "schema_version": 1,
                "kind": "wan-cost-ladder-manager-offline-boot-guard",
                "campaign_attempt_id": "attempt-999",
                "status": "pass",
                "server_instance": server,
                "preboot": preboot,
                "post_identification": postboot,
                "boot_log_scan": scan,
                "authoritative_server_reported_mode": scan[
                    "authoritative_server_reported_mode"
                ],
                "boot_environment": {
                    "set": {
                        "OTR_HEADLESS_PORT": "8000",
                        "COMFYUI_URL": "http://127.0.0.1:8000",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        **MANAGER.OFFLINE_CREDENTIAL_ENVIRONMENT,
                    },
                    "offline_credentials": (
                        MANAGER.pin_offline_credential_environment({})[1]
                    ),
                },
                "source": {
                    "path": str(source),
                    "sha256": SIDECAR.BASE.sha256_file(source),
                },
            }
            guard = evidence / "manager_boot_guard.json"
            guard.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            loaded, snapshot = SIDECAR.validate_manager_boot_guard(
                guard,
                attempt_id="attempt-999",
                attempt_evidence_root=evidence,
                server=server,
                server_log=log,
                baseline_manager=preboot,
            )
            self.assertEqual(loaded, payload)
            self.assertTrue(snapshot["sha256"])
            changed_server = dict(server)
            changed_server["serving_pid"] = 456
            with self.assertRaises(SIDECAR.SidecarError):
                SIDECAR.validate_manager_boot_guard(
                    guard,
                    attempt_id="attempt-999",
                    attempt_evidence_root=evidence,
                    server=changed_server,
                    server_log=log,
                    baseline_manager=preboot,
                )


class WanCostWddmBaselineTests(unittest.TestCase):
    @staticmethod
    def identity(*, command_line=None, name="chrome.exe", executable=None):
        return {
            "pid": 123,
            "exists": True,
            "name": name,
            "executable": executable or rf"C:\Program Files\{name}",
            "command_line": command_line or [name, "--type=gpu-process"],
            "process_create_time": 10.0,
            "identity_errors": [],
        }

    def test_unmetered_wddm_desktop_row_requires_live_desktop_identity(self):
        row = {
            "gpu_uuid": "GPU-test",
            "pid": 123,
            "nvidia_process_name": r"C:\Program Files\Chrome\chrome.exe",
            "used_gpu_memory_token": "[N/A]",
        }
        allowed = BASELINE.classify_process_row(
            row, "GPU-test", self.identity()
        )
        self.assertEqual(
            allowed["classification"], "allowed_unmetered_wddm_desktop_client"
        )
        self.assertEqual(allowed["blocking_reasons"], [])
        self.assertTrue(allowed["desktop_graphics_signals"])

        unknown = BASELINE.classify_process_row(
            row,
            "GPU-test",
            self.identity(
                name="python.exe",
                executable=r"C:\Python\python.exe",
                command_line=["python.exe", "unknown.py"],
            ),
        )
        self.assertEqual(unknown["classification"], "blocked")
        self.assertTrue(
            any("desktop-graphics" in reason for reason in unknown["blocking_reasons"])
        )

    def test_target_and_activity_queries_require_exact_active_wddm(self):
        identity_stdout = (
            "0, GPU-test, NVIDIA GeForce RTX 5080 Laptop GPU, 16303, WDDM, Enabled\n"
        )
        completed = mock.Mock(stdout=identity_stdout)
        with mock.patch.object(BASELINE, "_run_nvidia_smi", return_value=completed):
            identity = BASELINE.target_gpu_identity(0)
        self.assertEqual(identity["driver_model_current"], "WDDM")
        self.assertEqual(identity["display_active"], "Enabled")

        activity_stdout = (
            "0, GPU-test, NVIDIA GeForce RTX 5080 Laptop GPU, 1024, 16303, "
            "5, 2, P4, WDDM, Enabled\n"
        )
        completed = mock.Mock(stdout=activity_stdout)
        with mock.patch.object(BASELINE, "_run_nvidia_smi", return_value=completed):
            activity = BASELINE.query_gpu_activity(0, "GPU-test")
        self.assertEqual(activity["driver_model_current"], "WDDM")
        self.assertEqual(activity["display_active"], "Enabled")

        completed = mock.Mock(stdout=identity_stdout.replace("WDDM", "TCC"))
        with mock.patch.object(BASELINE, "_run_nvidia_smi", return_value=completed):
            with self.assertRaises(BASELINE.BaselineError):
                BASELINE.target_gpu_identity(0)

    def test_numeric_unknown_and_model_rows_fail_closed(self):
        base = {
            "gpu_uuid": "GPU-test",
            "pid": 123,
            "nvidia_process_name": "python.exe",
            "used_gpu_memory_token": "[N/A]",
        }
        identity = self.identity()
        for token in ("0", "512", "[Unknown]"):
            row = {**base, "used_gpu_memory_token": token}
            result = BASELINE.classify_process_row(row, "GPU-test", identity)
            self.assertEqual(result["classification"], "blocked")
            self.assertTrue(result["blocking_reasons"])
        model = BASELINE.classify_process_row(
            base,
            "GPU-test",
            self.identity(
                name="python.exe",
                executable=r"C:\Python\python.exe",
                command_line=["python.exe", "main.py", "--port", "8199"],
            ),
        )
        self.assertTrue(
            any("model/inference" in reason for reason in model["blocking_reasons"])
        )

    def test_exact_dwm_identity_is_not_generic_access_denied(self):
        identity = self.identity(
            name="dwm.exe",
            executable=r"C:\Windows\System32\dwm.exe",
            command_line=[],
        )
        signals = BASELINE._desktop_graphics_signals(identity)
        self.assertIn("windows_desktop_compositor", signals)
        identity["executable"] = r"C:\Temp\dwm.exe"
        self.assertNotIn(
            "windows_desktop_compositor",
            BASELINE._desktop_graphics_signals(identity),
        )

    def test_quiescence_is_conjunctive_not_process_name_only(self):
        activity = {
            "gpu_uuid": "GPU-test",
            "driver_model_current": "WDDM",
            "display_active": "Enabled",
            "vram_used_mib": 1024.0,
            "gpu_utilization_percent": 5.0,
            "memory_utilization_percent": 2.0,
        }
        processes = {"target_gpu_uuid": "GPU-test", "blocking_rows": []}
        lock = {"matches_acquired_owner": True}
        scan = {"blocking_processes": []}
        self.assertEqual(
            BASELINE.evaluate_sample(activity, processes, lock, [], scan), []
        )
        for field, value in (
            ("vram_used_mib", 2049.0),
            ("gpu_utilization_percent", 16.0),
            ("memory_utilization_percent", 11.0),
        ):
            changed = dict(activity)
            changed[field] = value
            self.assertTrue(
                BASELINE.evaluate_sample(changed, processes, lock, [], scan)
            )
        self.assertTrue(
            BASELINE.evaluate_sample(
                activity,
                {"target_gpu_uuid": "GPU-other", "blocking_rows": []},
                lock,
                [],
                scan,
            )
        )
        self.assertTrue(
            BASELINE.evaluate_sample(activity, processes, lock, [999], scan)
        )
        non_wddm = dict(activity)
        non_wddm["driver_model_current"] = "TCC"
        self.assertTrue(
            BASELINE.evaluate_sample(non_wddm, processes, lock, [], scan)
        )

    def test_schema_recomputes_all_five_wddm_samples(self):
        owner = {"pid": 1, "process_create_time": 1.0, "nonce": "n" * 64, "role": "standalone"}
        identity = self.identity()
        process_row = BASELINE.classify_process_row(
            {
                "gpu_uuid": "GPU-test",
                "pid": 123,
                "nvidia_process_name": "chrome.exe",
                "used_gpu_memory_token": "[N/A]",
            },
            "GPU-test",
            identity,
        )
        samples = []
        for index in range(5):
            samples.append(
                {
                    "sample_index": index,
                    "gpu_index": 0,
                    "gpu_uuid": "GPU-test",
                    "driver_model_current": "WDDM",
                    "display_active": "Enabled",
                    "vram_used_mib": 1000.0 + index,
                    "gpu_utilization_percent": 5.0,
                    "memory_utilization_percent": 2.0,
                    "port_8000_listener_pids": [],
                    "quiescent": True,
                    "quiescence_errors": [],
                    "gpu_lock": {
                        "matches_acquired_owner": True,
                        "owner": owner,
                    },
                    "nvidia_process_evidence": {
                        "target_gpu_index": 0,
                        "target_gpu_uuid": "GPU-test",
                        "row_count": 1,
                        "rows": [process_row],
                        "blocking_rows": [],
                    },
                    "forbidden_process_scan": {
                        "scanned_process_count": 10,
                        "blocking_processes": [],
                    },
                }
            )
        payload = {
            "schema_version": 2,
            "kind": "wan-cost-ladder-quiescent-desktop-baseline",
            "status": "measured",
            "gpu_index": 0,
            "target_gpu": {
                "gpu_index": 0,
                "gpu_uuid": "GPU-test",
                "driver_model_current": "WDDM",
                "display_active": "Enabled",
            },
            "sampling_interval_s": 0.2,
            "sample_count": 5,
            "vram_used_mib": 1004.0,
            "max_gpu_utilization_percent": 5.0,
            "max_memory_utilization_percent": 2.0,
            "quiescence_policy": {
                "max_vram_used_mib": 2048.0,
                "max_gpu_utilization_percent": 15.0,
                "max_memory_utilization_percent": 10.0,
                "recognized_unmetered_wddm_memory_token": "[N/A]",
                "numeric_or_unknown_process_memory_tokens_block": True,
                "process_identity_and_desktop_graphics_signal_required": True,
                "port_8000_listener_required_absent": True,
                "same_gpu_lease_required_each_sample": True,
                "required_driver_model": "WDDM",
                "required_display_active": "Enabled",
            },
            "port_8000_listener_pids_before": [],
            "port_8000_listener_pids_after": [],
            "blocking_nvidia_processes": [],
            "nvidia_process_observation_count": 5,
            "manager_config": MANAGER.launcher_offline_evidence(
                MANAGER.DEFAULT_LAUNCHER
            ),
            "gpu_lease_owner": owner,
            "gpu_lease_release": {"success": True},
            "samples": samples,
            "source": {
                "path": str(Path(BASELINE.__file__).resolve()),
                "sha256": BASELINE.BASE.sha256_file(Path(BASELINE.__file__).resolve()),
            },
        }
        self.assertEqual(BASELINE.receipt_validation_errors(payload, 0), [])
        payload["samples"][4]["nvidia_process_evidence"]["rows"][0][
            "used_gpu_memory_token"
        ] = "0"
        self.assertTrue(BASELINE.receipt_validation_errors(payload, 0))

    def test_reducer_uses_conservative_max_of_both_peak_instruments(self):
        receipt = {
            "sampler": {
                "coverage_errors": [],
                "interval_s": 0.2,
                "sample_count": 3,
                "peak_vram_mib": 9000.0,
                "samples": [
                    {"vram_used_mib": 7000.0},
                    {"vram_used_mib": 9000.0},
                    {"vram_used_mib": 8000.0},
                ],
            },
            "sidecar_peak_vram_mib": 9000.0,
            "adapter_render_peak_vram_mib": 9200.0,
            "warm_peak_vram_mib": 9200.0,
            "warm_peak_derivation": {
                "operation": "max",
                "inputs": [
                    "sidecar_peak_vram_mib",
                    "adapter_render_peak_vram_mib",
                ],
                "selected_source": "adapter_render_window_100ms",
            },
            "node_episode_manifest_payload": {
                "clips": [{"vram_peak_mb": 9200}]
            },
        }
        peaks = REDUCE._recompute_peaks(receipt)
        self.assertEqual(peaks["sidecar_peak_mib"], 9000.0)
        self.assertEqual(peaks["adapter_render_peak_mib"], 9200.0)
        self.assertEqual(peaks["conservative_peak_mib"], 9200.0)

    def test_inter_run_gap_allows_benign_append_but_refuses_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "server.log"
            path.write_bytes(b"boot complete\n")
            previous = SIDECAR.BASE.stable_file_snapshot(path)
            with path.open("ab") as handle:
                handle.write(b"benign idle note\n")
            current = SIDECAR.BASE.stable_file_snapshot(path)
            gap = SIDECAR.inter_run_log_gap(previous, current, path)
            self.assertEqual(gap["execution_markers_found"], [])
            self.assertTrue(gap["prefix_sha256_reverified"])
            previous = current
            with path.open("ab") as handle:
                handle.write(b"got prompt\n")
            current = SIDECAR.BASE.stable_file_snapshot(path)
            with self.assertRaises(SIDECAR.SidecarError):
                SIDECAR.inter_run_log_gap(previous, current, path)


class WanCostReducerTests(unittest.TestCase):
    def test_reducer_accepts_only_semantically_identical_windows_launcher_argv(self):
        server_log = (
            REDUCE.EVIDENCE_BASE
            / "attempt-004"
            / "wan_cost_ladder.server.log"
        )
        recorded = [
            r"C:\WINDOWS\system32\cmd.exe",
            "/d",
            "/c",
            str(REDUCE.OTR_ROOT / "scripts" / "_otr_soak_server_launch.cmd"),
            str(server_log),
            "WAN",
        ]
        self.assertEqual(
            REDUCE.validated_recorded_launcher_argv(recorded, server_log),
            recorded,
        )
        for index, replacement in (
            (2, "/k"),
            (3, str(REDUCE.OTR_ROOT / "scripts" / "other.cmd")),
            (4, str(server_log.with_name("other.log"))),
            (5, "HUMO"),
        ):
            changed = list(recorded)
            changed[index] = replacement
            with self.subTest(index=index):
                with self.assertRaises(REDUCE.ReductionError):
                    REDUCE.validated_recorded_launcher_argv(changed, server_log)

    def test_reducer_rehashes_clip_evidence_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip_root = root / "clips"
            clip_root.mkdir()
            label = "wan_ti2v_f025_run1"
            evidence_path = clip_root / f"{label}.mp4"
            evidence_path.write_bytes(b"measured-video")
            evidence = REDUCE.BASE.stable_file_snapshot(evidence_path)
            source = dict(evidence)
            source["path"] = str(root / "production.mp4")
            started_ns = int(evidence["mtime_ns"]) - 1
            captured_ns = int(evidence["mtime_ns"]) + 1
            report = {
                "path": str(root / "report.json"),
                "exists": True,
                "bytes": 2,
                "mtime_ns": int(evidence["mtime_ns"]),
                "device": 1,
                "inode": 2,
                "sha256": "a" * 64,
            }
            manifest = {
                "path": str(root / "manifest.json"),
                "exists": True,
                "bytes": 2,
                "mtime_ns": int(evidence["mtime_ns"]),
                "device": 1,
                "inode": 3,
                "sha256": "b" * 64,
            }
            receipt = {
                "started_at_ns": started_ns,
                "node_episode_report_after": report,
                "node_episode_manifest_after": manifest,
                "node_episode_manifest_payload": {
                    "clips": [{"path": source["path"]}]
                },
                "rendered_clip": {
                    "manifest_path": source["path"],
                    "source_before": source,
                    "source_after": dict(source),
                    "source_stable_during_copy": True,
                    "freshness_window": {
                        "replay_started_at_ns": started_ns,
                        "source_mtime_ns": int(evidence["mtime_ns"]),
                        "captured_at_ns": captured_ns,
                        "within_window": True,
                    },
                    "fresh_state_files": {
                        "node_episode_report": report,
                        "node_episode_manifest": manifest,
                    },
                    "evidence": evidence,
                },
            }
            old_root = REDUCE.EVIDENCE_CLIP_ROOT
            REDUCE.EVIDENCE_CLIP_ROOT = clip_root
            try:
                proof = REDUCE._rendered_clip_evidence(receipt, label)
                self.assertEqual(proof["sha256"], evidence["sha256"])
                evidence_path.write_bytes(b"tampered")
                with self.assertRaises(REDUCE.ReductionError):
                    REDUCE._rendered_clip_evidence(receipt, label)
            finally:
                REDUCE.EVIDENCE_CLIP_ROOT = old_root

    def test_fit_scales_per_frame_to_otr_reference_and_envelopes(self):
        scale = (832 * 480) / (1472 * 832)
        points = [(25, 1000.0 + 10.0 * 25), (65, 1000.0 + 10.0 * 65)]
        points += [(129, 1000.0 + 10.0 * 129), (177, 1000.0 + 10.0 * 177)]
        fit = REDUCE.fit_upper_envelope(points)
        self.assertAlmostEqual(
            fit["least_squares_measured_canvas"]["overhead_mb"], 1000.0
        )
        self.assertAlmostEqual(
            fit["least_squares_measured_canvas"]["per_frame_mb"], 10.0
        )
        self.assertAlmostEqual(
            fit["candidate_row_at_1472x832"]["per_frame_mb"],
            (int((10.0 / scale) * 1000 + 0.999999999) / 1000),
            places=3,
        )
        row = fit["candidate_row_at_1472x832"]
        for frames, demand in points:
            predicted = row["overhead_mb"] + row["per_frame_mb"] * frames * scale
            self.assertGreaterEqual(predicted + 1e-6, demand)

    def test_fit_preserves_residuals_and_negative_slope_clamp(self):
        fit = REDUCE.fit_upper_envelope([(25, 1300), (93, 1200), (177, 1100)])
        self.assertTrue(fit["slope_was_clamped_nonnegative"])
        self.assertEqual(fit["upper_envelope_measured_canvas"]["per_frame_mb"], 0.0)
        self.assertEqual(len(fit["residuals_mb"]), 3)
        self.assertGreater(fit["max_absolute_residual_mb"], 0)

    def test_non_monotonicity_is_explicit(self):
        rows = [
            {"model_render_frames": 25, "warm_peak_mib": 9000.0},
            {"model_render_frames": 93, "warm_peak_mib": 8800.0},
            {"model_render_frames": 177, "warm_peak_mib": 9100.0},
        ]
        findings = REDUCE.non_monotonic_rows(rows, "warm_peak_mib")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["from_frames"], 25)
        self.assertEqual(findings[0]["to_frames"], 93)
        self.assertEqual(findings[0]["decrease"], 200.0)

    def test_expected_receipt_surface_requires_two_runs_per_cell(self):
        paths = REDUCE.expected_paths()
        self.assertEqual(len(paths), 16)
        self.assertEqual(len(set(paths)), 16)
        self.assertTrue(all(path.parent == REDUCE.TELEMETRY_ROOT for path in paths))


class WanCostCampaignTests(unittest.TestCase):
    class FakeProcess:
        def __init__(self, *, pid, parent_pid, created, executable, argv):
            self.pid = pid
            self._parent_pid = parent_pid
            self._created = created
            self._executable = executable
            self._argv = list(argv)

        def ppid(self):
            return self._parent_pid

        def create_time(self):
            return self._created

        def exe(self):
            return self._executable

        def cmdline(self):
            return list(self._argv)

    def test_runbook_covers_all_16_legs_in_pair_order(self):
        plan = CAMPAIGN.runbook()
        self.assertEqual(len(plan["pairs_in_required_sequence"]), 8)
        self.assertEqual(len(plan["expected_raw_receipts"]), 16)
        self.assertTrue(plan["one_resident_server"]["allowed"])
        seen = set()
        for pair in plan["pairs_in_required_sequence"]:
            first = pair["pair_first_cache_buster"]
            warm = pair["warm_second_cache_buster"]
            self.assertEqual(warm, first + 1)
            self.assertNotIn(first, seen)
            self.assertNotIn(warm, seen)
            seen.update((first, warm))
            self.assertIn("pair_first", pair["pair_first_argv"])
            self.assertIn("warm_second", pair["warm_second_argv"])

    def test_default_campaign_invocation_is_read_only_plan(self):
        plan = CAMPAIGN.runbook()
        self.assertEqual(plan["execution_switch"][-1], "--run")
        self.assertEqual(plan["owned_boot"]["port"], 8000)
        self.assertIn("WAN", plan["owned_boot"]["argv"][-1])
        self.assertIn("one narrow Windows exception", plan["owned_boot"]["ownership_proof"])

    def test_owned_server_accepts_only_exact_windows_venv_one_hop(self):
        command = CAMPAIGN.owned_boot_command()
        server_argv = [
            (
                r"C:\Users\jeffr\AppData\Roaming\uv\python"
                r"\cpython-3.12.11-windows-x86_64-none\python.exe"
            ),
            r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI\main.py",
            "--port",
            "8000",
            "--cuda-malloc",
            "--user-directory",
            r"C:\Users\jeffr\Documents\ComfyUI",
            "--output-directory",
            r"C:\Users\jeffr\Documents\ComfyUI\output",
            "--extra-model-paths-config",
            (
                r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes"
                r"\ComfyUI-OldTimeRadio\scripts\_otr_headless_model_paths.yaml"
            ),
            "--disable-metadata",
        ]
        launcher = self.FakeProcess(
            pid=100,
            parent_pid=1,
            created=10.0,
            executable=command[0],
            argv=command,
        )
        shim = self.FakeProcess(
            pid=200,
            parent_pid=100,
            created=11.0,
            executable=str(CAMPAIGN.PYTHON),
            argv=[str(CAMPAIGN.PYTHON), *server_argv[1:]],
        )
        serving = self.FakeProcess(
            pid=300,
            parent_pid=200,
            created=12.0,
            executable=server_argv[0],
            argv=server_argv,
        )
        rows = {200: shim, 300: serving}
        server = {
            "serving_pid": 300,
            "parent_pid": 200,
            "process_create_time": 12.0,
            "executable": server_argv[0],
            "argv": server_argv,
        }
        chain = CAMPAIGN.verify_owned_server_chain(
            server, launcher, command, process_factory=rows.__getitem__
        )
        self.assertTrue(chain["validated"])
        self.assertEqual(chain["chain_type"], "windows-venv-one-hop")
        self.assertEqual(chain["intermediary"]["pid"], 200)
        self.assertEqual(chain["launcher"]["pid"], 100)

        adversarial = []
        wrong_parent = self.FakeProcess(
            pid=200,
            parent_pid=999,
            created=11.0,
            executable=str(CAMPAIGN.PYTHON),
            argv=[str(CAMPAIGN.PYTHON), *server_argv[1:]],
        )
        adversarial.append({200: wrong_parent, 300: serving})
        wrong_exe = self.FakeProcess(
            pid=200,
            parent_pid=100,
            created=11.0,
            executable=r"C:\Windows\System32\not-python.exe",
            argv=[str(CAMPAIGN.PYTHON), *server_argv[1:]],
        )
        adversarial.append({200: wrong_exe, 300: serving})
        wrong_argv = self.FakeProcess(
            pid=200,
            parent_pid=100,
            created=11.0,
            executable=str(CAMPAIGN.PYTHON),
            argv=[str(CAMPAIGN.PYTHON), "other.py"],
        )
        adversarial.append({200: wrong_argv, 300: serving})
        late_shim = self.FakeProcess(
            pid=200,
            parent_pid=100,
            created=16.0,
            executable=str(CAMPAIGN.PYTHON),
            argv=[str(CAMPAIGN.PYTHON), *server_argv[1:]],
        )
        late_serving = self.FakeProcess(
            pid=300,
            parent_pid=200,
            created=17.0,
            executable=server_argv[0],
            argv=server_argv,
        )
        adversarial.append({200: late_shim, 300: late_serving})
        for candidate in adversarial:
            with self.subTest(candidate=candidate[200]._executable):
                with self.assertRaises(CAMPAIGN.CampaignError):
                    CAMPAIGN.verify_owned_server_chain(
                        server,
                        launcher,
                        command,
                        process_factory=candidate.__getitem__,
                    )

        arbitrary_exe = r"C:\Windows\System32\not-the-venv-base.exe"
        arbitrary_serving = self.FakeProcess(
            pid=300,
            parent_pid=200,
            created=12.0,
            executable=arbitrary_exe,
            argv=[arbitrary_exe, *server_argv[1:]],
        )
        arbitrary_server = {
            **server,
            "executable": arbitrary_exe,
            "argv": [arbitrary_exe, *server_argv[1:]],
        }
        with self.assertRaises(CAMPAIGN.CampaignError):
            CAMPAIGN.verify_owned_server_chain(
                arbitrary_server,
                launcher,
                command,
                process_factory={200: shim, 300: arbitrary_serving}.__getitem__,
            )

    def test_pyvenv_base_derivation_is_unique_absolute_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "base-python"
            home.mkdir()
            (home / "python.exe").write_bytes(b"base-interpreter")
            config = root / "pyvenv.cfg"
            config.write_text(
                f"home = {home}\nversion_info = 3.12.11\n",
                encoding="utf-8",
                newline="\n",
            )
            receipt = OWNERSHIP.venv_base_interpreter_receipt(config)
            self.assertEqual(
                Path(receipt["base_interpreter"]["path"]), home / "python.exe"
            )
            original_sha = receipt["config"]["sha256"]
            config.write_text(
                f"home = {home}\nversion_info = 3.12.12\n",
                encoding="utf-8",
                newline="\n",
            )
            self.assertNotEqual(
                OWNERSHIP.venv_base_interpreter_receipt(config)["config"][
                    "sha256"
                ],
                original_sha,
            )
            config.write_text(
                f"home = {home}\nhome = {home}\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(OWNERSHIP.OwnershipError):
                OWNERSHIP.venv_base_interpreter_receipt(config)
            config.write_text(
                "home = relative-base\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(OWNERSHIP.OwnershipError):
                OWNERSHIP.venv_base_interpreter_receipt(config)

    def test_preidentification_post_shutdown_audit_does_not_invent_server_argv(self):
        preboot = MANAGER.launcher_offline_evidence(MANAGER.DEFAULT_LAUNCHER)
        audit, errors = CAMPAIGN.post_shutdown_manager_audit(
            None, preboot, {"exists": True, "sha256": "a" * 64}
        )
        self.assertEqual(errors, [])
        self.assertEqual(audit["status"], "not_applicable_pre_identification")
        self.assertIn("empty argv", audit["reason"])
        self.assertNotIn("config", audit)

    def test_identified_abort_receipts_observed_authoritative_mode_values(self):
        config = Path(r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini")
        server = {
            "argv": [
                "python",
                "main.py",
                "--user-directory",
                str(config.parents[1]),
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "server.log"
            text = WanCostManagerOfflineGuardTests.clean_log(config).replace(
                "[ComfyUI-Manager] network_mode: offline",
                "[ComfyUI-Manager] network_mode: offline\n"
                "[ComfyUI-Manager] network_mode: public",
            )
            log.write_text(text, encoding="utf-8", newline="\n")
            with mock.patch.object(CAMPAIGN, "SERVER_LOG", log):
                evidence = CAMPAIGN.authoritative_mode_failure_evidence(server)
            self.assertEqual(evidence["status"], "fail")
            self.assertEqual(evidence["announcement_count"], 2)
            self.assertEqual(evidence["observed_values"], ["offline", "public"])
            self.assertIsNone(evidence["resolved_mode"])

    def test_server_identity_includes_parent(self):
        base = {
            "serving_pid": 100,
            "process_create_time": 10.5,
            "parent_pid": 50,
            "argv": ["python", "main.py", "--port", "8000"],
        }
        self.assertTrue(CAMPAIGN._same_server(base, dict(base)))
        changed = dict(base)
        changed["parent_pid"] = 51
        self.assertFalse(CAMPAIGN._same_server(base, changed))

    def test_boot_environment_clears_stale_lane_and_recipe_overrides(self):
        source = {
            "PATH": "x",
            "OTR_HEADLESS_PORT": "8123",
            "OTR_HEADLESS_RESERVE_VRAM_GB": "8",
            "OTR_ENABLE_LTX_VIDEO": "1",
            "OTR_FORCE_ENGINE_MAP": "wan_ti2v=fastwan_8gb",
            "OTR_WAN_TI2V_CLIP_NAME": "wrong.gguf",
            "OTR_FASTWAN_8GB_PREQUALIFICATION": "1",
            "UNRELATED": "kept",
            "COMFYUI_URL": "http://127.0.0.1:8188",
        }
        source.update(
            {
                "HF_TOKEN": "real-secret-a",
                "HUGGING_FACE_HUB_TOKEN": "real-secret-b",
                "HUGGINGFACE_HUB_TOKEN": "real-secret-c",
                "HF_API_TOKEN": "real-secret-d",
            }
        )
        environment, removed, credential_evidence = (
            CAMPAIGN.production_boot_environment(source)
        )
        self.assertEqual(environment["OTR_HEADLESS_PORT"], "8000")
        self.assertEqual(environment["COMFYUI_URL"], "http://127.0.0.1:8000")
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["UNRELATED"], "kept")
        for key in (
            "OTR_HEADLESS_RESERVE_VRAM_GB",
            "OTR_ENABLE_LTX_VIDEO",
            "OTR_FORCE_ENGINE_MAP",
            "OTR_WAN_TI2V_CLIP_NAME",
            "OTR_FASTWAN_8GB_PREQUALIFICATION",
        ):
            self.assertNotIn(key, environment)
            self.assertIn(key, removed)
        self.assertIn("COMFYUI_URL", removed)
        for key, expected in MANAGER.OFFLINE_CREDENTIAL_ENVIRONMENT.items():
            self.assertEqual(environment[key], expected)
        for key in MANAGER.SCRUBBED_CREDENTIAL_ENVIRONMENT_KEYS:
            self.assertNotIn(key, environment)
            self.assertIn(key, removed)
        serialized = json.dumps(credential_evidence)
        for secret in ("real-secret-a", "real-secret-b", "real-secret-c", "real-secret-d"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(
            MANAGER.validate_offline_credential_environment_evidence(
                credential_evidence
            ),
            [],
        )

    def test_campaign_children_override_ambient_endpoint(self):
        environment = CAMPAIGN.campaign_child_environment(
            {
                "COMFYUI_URL": "https://remote.example",
                "KEEP": "yes",
                "HF_TOKEN": "real-secret",
                "HUGGINGFACE_HUB_TOKEN": "real-secret-alt",
            }
        )
        self.assertEqual(environment["COMFYUI_URL"], "http://127.0.0.1:8000")
        self.assertEqual(environment["KEEP"], "yes")
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["HF_TOKEN"], "offline-disabled")
        self.assertNotIn("HUGGINGFACE_HUB_TOKEN", environment)

    def test_campaign_plan_keeps_server_log_out_of_otr_repo(self):
        plan = CAMPAIGN.campaign_execution_plan()
        self.assertTrue(str(CAMPAIGN.SERVER_LOG).startswith(str(CAMPAIGN.LAB_ROOT)))
        self.assertFalse(str(CAMPAIGN.SERVER_LOG).startswith(str(CAMPAIGN.OTR_ROOT)))
        self.assertEqual(
            plan["boot_existing_otr_lane_via_start_process"]["ArgumentList"][0],
            str(CAMPAIGN.SERVER_LOG),
        )
        for pair in plan["pairs_in_required_sequence"]:
            for key in ("pair_first_argv", "warm_second_argv"):
                argv = pair[key]
                self.assertEqual(argv[argv.index("--server-log") + 1], str(CAMPAIGN.SERVER_LOG))
                self.assertEqual(
                    argv[argv.index("--manager-boot-guard") + 1],
                    str(CAMPAIGN.MANAGER_BOOT_GUARD),
                )
        self.assertEqual(len(CAMPAIGN.expected_clip_evidence()), 16)

    def test_campaign_manager_guard_uses_actual_user_directory(self):
        plan = CAMPAIGN.runbook()
        config = plan["manager_offline_check"]["config"]
        self.assertEqual(config["network_mode"], "offline")
        self.assertEqual(
            Path(config["path"]),
            Path(r"C:\Users\jeffr\Documents\ComfyUI\__manager\config.ini"),
        )
        self.assertIn(str(CAMPAIGN.MANAGER_BOOT_GUARD), plan["expected_final_receipts"])

    def test_failed_attempt_is_immutable_and_retry_is_namespaced(self):
        prior = CAMPAIGN.prior_failed_attempt_evidence()
        legacy = prior["legacy_attempt_001"]
        incident = prior["attempt_002_offline_incident"]
        ownership_incident = prior["attempt_003_ownership_incident"]
        self.assertEqual(legacy["attempt_id"], "legacy-attempt-001")
        self.assertEqual(legacy["disposition"], "immutable_in_place")
        self.assertEqual(
            legacy["receipt"]["sha256"],
            "442013facb8b261763a9d559270a6ca2302692c27629c94d29d4817b8c57c211",
        )
        self.assertEqual(
            incident["lifecycle"]["sha256"],
            "a0c0e2eda3b760b4387cee157898043fcfcebe9a16e4842997c2270fd4a07e99",
        )
        self.assertEqual(
            incident["recovery_receipt"]["sha256"],
            "77b42b7069e53b31d9694fabcbd54a0b6317b27b3a2d2a02cbf089390049fc4f",
        )
        self.assertEqual(
            incident["baseline"]["sha256"],
            "88f607f553a4f55c6d442c9b27f85748e84a15030a7e3522ac10918a1172ce10",
        )
        self.assertEqual(
            incident["server_log"]["sha256"],
            "7523896db30d08b4f7e0557a4ab5c5ce1f4be17b3c01294a99d3264362dde71c",
        )
        self.assertFalse(incident["measurement_accepted"])
        self.assertEqual(
            ownership_incident["lifecycle"]["sha256"],
            "f90ae20856f8c00c10163303fb8d28656db594069cda73c2b9735530111f61a3",
        )
        self.assertEqual(
            ownership_incident["baseline"]["sha256"],
            "5e7de2b54bb7b5431d2841b7e099902e9852512552a81be30b484ddebf86fbc5",
        )
        self.assertEqual(
            ownership_incident["server_log"]["sha256"],
            "a3b177447b58b6f050fd20d56f87e881cba8aa79c5d65408b8a1ffca81f52f97",
        )
        self.assertEqual(
            ownership_incident["recovery_receipt"]["sha256"],
            "ea625fe56a533853b4bb6b383f544152a5780799ae36073a73f0875bb3602bfd",
        )
        self.assertEqual(
            ownership_incident["verified_chain_roles"],
            ["serving-python", "windows-venv-python-shim", "owned-cmd-launcher"],
        )
        self.assertFalse(ownership_incident["measurement_accepted"])
        self.assertEqual(CAMPAIGN.ATTEMPT_ID, "attempt-004")
        plan = CAMPAIGN.campaign_execution_plan()
        self.assertIn("attempt-004", str(CAMPAIGN.BASELINE))
        self.assertIn("attempt-004", str(CAMPAIGN.LIFECYCLE_RECEIPT))
        self.assertNotEqual(
            CAMPAIGN.LIFECYCLE_RECEIPT.resolve(),
            CAMPAIGN.PRIOR_FAILED_LIFECYCLE.resolve(),
        )
        baseline_argv = plan["desktop_baseline_argv"]
        self.assertEqual(
            baseline_argv[baseline_argv.index("--output") + 1],
            str(CAMPAIGN.BASELINE),
        )
        for pair in plan["pairs_in_required_sequence"]:
            for key in ("pair_first_argv", "warm_second_argv"):
                argv = pair[key]
                self.assertTrue(
                    argv[argv.index("--output") + 1].startswith(
                        str(CAMPAIGN.TELEMETRY_ROOT)
                    )
                )
                self.assertEqual(
                    argv[argv.index("--desktop-baseline-receipt") + 1],
                    str(CAMPAIGN.BASELINE),
                )


if __name__ == "__main__":
    unittest.main()
