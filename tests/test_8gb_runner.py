import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from eightgb_bench import locks_4060
from eightgb_bench import runner_4060 as runner


def _source_graph():
    return json.loads((runner.REPO_ROOT / "recipes" / "h3_mime_i2v.json").read_text(encoding="utf-8"))["prompt"]


def _object_info_for_source_graph():
    graph = _source_graph()
    info = {}
    for node in graph.values():
        class_type = node["class_type"]
        if class_type in info:
            continue
        info[class_type] = {
            "input": {"required": {}, "optional": {}},
            "output": ["ANY", "ANY", "ANY", "ANY"],
        }
    for node in graph.values():
        required = info[node["class_type"]]["input"]["required"]
        for key in node["inputs"]:
            required[key] = ["ANY", {}]
    info["UNETLoader"]["input"]["required"]["unet_name"] = [
        ["minimax_h3_fl2va_pruned_int8_convrot.safetensors"],
        {},
    ]
    info["CLIPLoader"]["input"]["required"]["clip_name"] = [
        ["qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"],
        {},
    ]
    info["VAELoader"]["input"]["required"]["vae_name"] = [
        ["minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
        {},
    ]
    return info


class Physical4060RunnerPureTests(unittest.TestCase):
    def test_checked_in_text_hash_is_crlf_stable_and_rejects_a_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lf = root / "lf.json"
            crlf = root / "crlf.json"
            bom = root / "bom.json"
            lf.write_bytes(b'{"v":1}\n')
            crlf.write_bytes(b'{"v":1}\r\n')
            bom.write_bytes(b"\xef\xbb\xbf{}\n")
            self.assertEqual(runner.sha256_utf8_text_file(lf), runner.sha256_utf8_text_file(crlf))
            with self.assertRaisesRegex(runner.RunnerError, "BOM"):
                runner.sha256_utf8_text_file(bom)

    def test_direct_argv_is_fixed_to_loopback_and_has_no_shell_or_sage_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / "python.exe"
            comfy = root / "ComfyUI"
            main = comfy / "main.py"
            python.write_bytes(b"python")
            comfy.mkdir()
            main.write_text("print('main')\n", encoding="utf-8")
            cell = root / "cell"
            cell.mkdir()
            admission = {"python": python, "comfy_root": comfy}
            argv = runner.build_launch_argv(admission, cell)
        self.assertEqual(argv[:2], [str(python), str(main.resolve())])
        self.assertEqual(argv[argv.index("--listen") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--port") + 1], "18299")
        self.assertEqual(argv[argv.index("--base-directory") + 1], str(cell / "base"))
        self.assertIn("--disable-pinned-memory", argv)
        self.assertIn("--disable-all-custom-nodes", argv)
        self.assertNotIn("cmd.exe", [item.casefold() for item in argv])
        self.assertFalse(any("sage" in item.casefold() or "reserve" in item.casefold() for item in argv))

    def test_cell_is_created_before_children_and_stages_the_fixture_at_its_prompt_basename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "local"
            local.mkdir()
            with mock.patch.object(runner, "_safe_local_root", return_value=local):
                cell = runner.create_cell("run-a")
            roots = {}
            for category in ("diffusion_models", "text_encoders", "vae"):
                path = root / category
                path.mkdir()
                roots[category] = path
            comfy_root = root / "ComfyUI"
            (comfy_root / "custom_nodes").mkdir(parents=True)
            plan, _ = runner.load_plan()
            fixture_hashes = runner.prepare_cell(
                {"plan": plan, "model_roots": roots, "comfy_root": comfy_root}, cell
            )
            staged = cell / "input" / "scene_still.png"
            self.assertTrue(cell.is_dir())
            self.assertTrue(staged.is_file())
            self.assertTrue((cell / "base").is_dir())
            self.assertEqual(fixture_hashes, {"scene_still.png": plan["video_contract"]["fixture_sha256"]})
            self.assertFalse((cell / "input" / "fixtures").exists())
            yaml = (cell / "model_paths.yaml").read_text(encoding="utf-8")
            self.assertIn("custom_nodes:", yaml)
            self.assertIn(str(comfy_root / "custom_nodes").replace("\\", "/"), yaml)

    def test_sanitized_environment_strips_inherited_selectors_and_sets_only_the_enrolled_gpu(self):
        parent = {
            "PATH": "safe-path",
            "SYSTEMROOT": "C:\\Windows",
            "LAB_RESERVE_VRAM_GB": "12",
            "CUDA_VISIBLE_DEVICES": "0",
            "HF_TOKEN": "private",
            "HTTPS_PROXY": "private",
            "PYTHONPATH": "private",
        }
        with mock.patch.dict(os.environ, parent, clear=True):
            environment = runner.sanitized_environment(gpu_uuid="GPU-laptop-4060")
        self.assertEqual(environment["PATH"], "safe-path")
        self.assertEqual(environment["CUDA_VISIBLE_DEVICES"], "GPU-laptop-4060")
        for forbidden in ("LAB_RESERVE_VRAM_GB", "HF_TOKEN", "HTTPS_PROXY", "PYTHONPATH"):
            self.assertNotIn(forbidden, environment)
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
        self.assertEqual(environment["TRANSFORMERS_OFFLINE"], "1")

    def test_cache_nonce_preserves_seed_and_forces_the_sampler_output_branch(self):
        graph = _source_graph()
        original = json.loads(json.dumps(graph))
        queued, control = runner.apply_cache_nonce(graph, "warm-1-test")
        self.assertEqual(graph, original)
        self.assertEqual(queued["5"]["inputs"]["noise_seed"], 42)
        self.assertEqual(queued["5"]["inputs"][runner.CACHE_NONCE_INPUT], "warm-1-test")
        self.assertIn("8", control["fresh_node_ids"])
        self.assertIn("12", control["fresh_node_ids"])
        self.assertEqual(control["sampler_node_ids"], ["8"])
        self.assertEqual(control["fresh_output_node_ids"], ["12"])

    def test_cache_evidence_requires_an_event_and_rejects_cached_fresh_nodes(self):
        _, control = runner.apply_cache_nonce(_source_graph(), "warm-1-test")
        absent = runner.execution_cache_evidence([], control)
        self.assertFalse(absent["fresh_execution_proved"])
        unrelated = runner.execution_cache_evidence(
            [["execution_cached", {"nodes": ["1", "2"]}]], control
        )
        self.assertTrue(unrelated["fresh_execution_proved"])
        cached_sampler = runner.execution_cache_evidence(
            [["execution_cached", {"nodes": ["8"]}]], control
        )
        self.assertFalse(cached_sampler["fresh_execution_proved"])
        self.assertEqual(cached_sampler["cached_fresh_node_ids"], ["8"])

    def test_live_schema_requires_every_bound_model_option(self):
        plan, _ = runner.load_plan()
        proof = runner.validate_live_source_prompt(plan, _object_info_for_source_graph())
        self.assertEqual(proof["source_node_count"], 15)
        self.assertEqual(len(proof["model_option_proof"]), 4)
        invalid = _object_info_for_source_graph()
        invalid["UNETLoader"]["input"]["required"]["unet_name"][0] = []
        with self.assertRaisesRegex(runner.RunnerError, "did not expose admitted model"):
            runner.validate_live_source_prompt(plan, invalid)

    def test_live_schema_rejects_a_source_link_outside_the_live_output_range(self):
        plan, _ = runner.load_plan()
        invalid = _object_info_for_source_graph()
        invalid["MiniMaxH3ImageToVideo"]["output"] = ["CONDITIONING"]
        with self.assertRaisesRegex(runner.RunnerError, "invalid output 1"):
            runner.validate_live_source_prompt(plan, invalid)

    def test_listener_identity_allows_only_the_windows_launcher_substitution(self):
        expected = ["C:\\venv\\python.exe", "C:\\ComfyUI\\main.py", "--port", "18299"]
        self.assertTrue(runner._argv_matches_expected(expected, expected))
        self.assertTrue(
            runner._argv_matches_expected(
                ["C:\\Windows\\pythonw.exe", "C:\\ComfyUI\\main.py", "--port", "18299"],
                expected,
            )
        )
        self.assertFalse(
            runner._argv_matches_expected(expected + ["--use-sage-attention"], expected)
        )

    def test_media_contract_needs_both_streams_and_exact_shape(self):
        plan, _ = runner.load_plan()
        contract = plan["video_contract"]
        metrics = {
            "encoded_width": 864,
            "encoded_height": 480,
            "encoded_frame_count": 90,
            "encoded_fps": 24.0,
            "audio_present": True,
            "container_duration_s": 3.75,
            "video_duration_s": 3.75,
            "audio_duration_s": 3.75,
        }
        self.assertTrue(runner.media_matches_contract(metrics, contract))
        metrics["audio_present"] = False
        self.assertFalse(runner.media_matches_contract(metrics, contract))

    def test_resource_monitor_records_minimum_available_host_ram(self):
        monitor = runner.ResourceMonitor("GPU-laptop-4060")
        with mock.patch.object(monitor, "_sample_details", return_value=(0.2, 20.0, 12.0)), mock.patch.object(monitor, "_run"):
            baseline = monitor.start()
        self.assertEqual(baseline, (0.2, 20.0))
        monitor._stop.set()
        if monitor._thread is not None:
            monitor._thread.join(timeout=1)
        summary = monitor.stop()
        self.assertEqual(summary["min_host_ram_available_gib"], 12.0)
        self.assertEqual(summary["baseline_host_ram_available_gib"], 12.0)

    def test_resource_monitor_selects_the_enrolled_gpu_uuid_not_the_first_gpu(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout="GPU-other, 7100\nGPU-laptop-4060, 1024\n",
            stderr="",
        )
        monitor = runner.ResourceMonitor("GPU-laptop-4060")
        with mock.patch.object(runner.inventory, "_trusted_nvidia_smi_path", return_value=Path("C:/Windows/nvidia-smi.exe")), mock.patch.object(runner.subprocess, "run", return_value=completed), mock.patch.object(runner.inventory, "host_ram_snapshot", return_value={"total_gib": 32.0, "available_gib": 10.0}):
            vram, host = monitor._sample()
        self.assertEqual(vram, 1.0)
        self.assertEqual(host, 22.0)

    def test_system_stats_must_match_the_enrolled_gpu_identity(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout="GPU-laptop-4060, NVIDIA GeForce RTX 4060 Laptop GPU, 8188\n",
            stderr="",
        )
        stats = {
            "devices": [
                {
                    "name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "vram_total": 8188 * 1024 * 1024,
                }
            ]
        }
        with mock.patch.object(runner.inventory, "_trusted_nvidia_smi_path", return_value=Path("C:/Windows/nvidia-smi.exe")), mock.patch.object(runner.subprocess, "run", return_value=completed):
            identity = runner._verify_system_stats_device(stats, "GPU-laptop-4060")
        self.assertEqual(identity["vram_total_mib"], 8188)
        stats["devices"][0]["name"] = "NVIDIA GeForce RTX 5080 Laptop GPU"
        with mock.patch.object(runner.inventory, "_trusted_nvidia_smi_path", return_value=Path("C:/Windows/nvidia-smi.exe")), mock.patch.object(runner.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(runner.RunnerError, "does not match"):
                runner._verify_system_stats_device(stats, "GPU-laptop-4060")

    def test_preboot_gate_refuses_a_loaded_gpu_worker_or_low_host_headroom(self):
        idle_monitor = mock.Mock()
        idle_monitor._sample_details.return_value = (0.2, 20.0, 10.0)
        with mock.patch.object(runner, "ResourceMonitor", return_value=idle_monitor):
            ready = runner.verify_preboot_resources("GPU-laptop-4060")
        self.assertEqual(ready["vram_gib"], 0.2)
        busy_monitor = mock.Mock()
        busy_monitor._sample_details.return_value = (0.6, 20.0, 10.0)
        with mock.patch.object(runner, "ResourceMonitor", return_value=busy_monitor):
            with self.assertRaisesRegex(runner.RunnerError, "not idle"):
                runner.verify_preboot_resources("GPU-laptop-4060")
        ram_monitor = mock.Mock()
        ram_monitor._sample_details.return_value = (0.2, 25.0, 7.9)
        with mock.patch.object(runner, "ResourceMonitor", return_value=ram_monitor):
            with self.assertRaisesRegex(runner.RunnerError, "host RAM is too busy"):
                runner.verify_preboot_resources("GPU-laptop-4060")

    def test_model_manifest_is_hash_checked_before_and_after_an_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_root = root / "vae"
            model_root.mkdir()
            model = model_root / "asset.safetensors"
            model.write_bytes(b"ok")
            plan = {
                "engine": {
                    "required_assets": [
                        {"category": "vae", "filename": "asset.safetensors", "expected_bytes": 2}
                    ]
                }
            }
            expected = {"vae/asset.safetensors": runner.sha256_file(model)}
            manifest = runner.verify_model_manifest(plan, {"vae": model_root}, expected)
            self.assertEqual(manifest[0]["sha256"], expected["vae/asset.safetensors"])
            model.write_bytes(b"drift")
            with self.assertRaisesRegex(runner.RunnerError, "bytes drifted"):
                runner.verify_model_manifest(plan, {"vae": model_root}, expected)

    def test_runner_never_imports_or_mentions_the_5080_execution_surfaces(self):
        source = Path(runner.__file__).read_text(encoding="utf-8")
        for forbidden in ("import run_recipe", "from run_recipe", "import lab_locks", "from lab_locks", "import front_office", "from front_office", "import labctl", "from labctl"):
            self.assertNotIn(forbidden, source)


class Physical4060LeaseTests(unittest.TestCase):
    def test_local_leases_are_exclusive_and_release_only_their_matching_nonce(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "local"
            local.mkdir()
            with locks_4060.BenchLease(local):
                self.assertTrue((local / ".coordinator.mutex").is_file())
                self.assertTrue((local / ".gpu.lock").is_file())
                with self.assertRaisesRegex(locks_4060.LeaseError, "already exists"):
                    locks_4060.BenchLease(local).__enter__()
            self.assertFalse((local / ".coordinator.mutex").exists())
            self.assertFalse((local / ".gpu.lock").exists())

    def test_mismatched_nonce_is_never_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".gpu.lock"
            lease = locks_4060.LocalLease(path, "gpu")
            lease.acquire()
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["nonce"] = "other-owner"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(locks_4060.LeaseError, "nonmatching"):
                lease.release()
            self.assertTrue(path.exists())


class Physical4060TerminalReceiptTests(unittest.TestCase):
    def _payloads(self):
        admission = {"kind": "admission", "status": "ADMITTED_FOR_SEQUENCE"}
        run = {"kind": "run", "status": "MACHINE_GATE_FAILED"}
        shutdown = {"success": True, "listener_after": None, "post_shutdown_resources": {"vram_gib": 0.1}}
        return admission, run, shutdown

    def test_successful_run_receipts_bind_a_preexisting_shutdown_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = Path(directory) / "cell"
            cell.mkdir()
            admission, run, shutdown = self._payloads()
            result = runner.finalize_cell_receipts(
                cell=cell,
                run_id="run-a",
                caught=None,
                shutdown=shutdown,
                admission_payload=admission,
                run_payload=run,
                result={"status": "pending"},
                canonical_argv=["python", "main.py"],
                live={"listener_pid": 123},
            )
            shutdown_path = cell / "shutdown.json"
            admission_path = cell / "admission.json"
            run_path = cell / "run.json"
            self.assertEqual(result["run_sha256"], runner.sha256_file(run_path))
            self.assertEqual(json.loads(admission_path.read_text(encoding="utf-8"))["shutdown_sha256"], runner.sha256_file(shutdown_path))
            final_run = json.loads(run_path.read_text(encoding="utf-8"))
            self.assertEqual(final_run["admission_sha256"], runner.sha256_file(admission_path))
            self.assertEqual(final_run["shutdown_sha256"], runner.sha256_file(shutdown_path))

    def test_failed_shutdown_writes_only_a_failure_terminal_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = Path(directory) / "cell"
            cell.mkdir()
            admission, run, _ = self._payloads()
            result = runner.finalize_cell_receipts(
                cell=cell,
                run_id="run-b",
                caught=None,
                shutdown={"success": False, "error": "listener remains"},
                admission_payload=admission,
                run_payload=run,
                result={},
                canonical_argv=["python", "main.py"],
                live={"listener_pid": 123},
            )
            self.assertEqual(result["status"], "BLOCKED_OR_FAILED")
            self.assertTrue((cell / "shutdown.json").is_file())
            self.assertTrue((cell / "failure.json").is_file())
            self.assertFalse((cell / "admission.json").exists())
            self.assertFalse((cell / "run.json").exists())

    def test_shutdown_rejects_residual_gpu_allocation_after_the_owned_process_is_gone(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = Path(directory) / "cell"
            cell.mkdir()
            server = runner.OwnedServer(["python", "main.py"], cell, {}, "GPU-laptop-4060")
            monitor = mock.Mock()
            monitor._sample.return_value = (0.7, 20.0)
            with mock.patch.object(runner, "_listener_pid", return_value=None), mock.patch.object(runner, "ResourceMonitor", return_value=monitor):
                result = server.shutdown("test")
        self.assertFalse(result["success"])
        self.assertIn("cleanup is not proved", result["error"])

    def test_execute_shutdown_failure_never_leaves_an_admission_pass_receipt(self):
        class FailingShutdownServer:
            def __init__(self, *_args):
                pass

            def start(self):
                return {"listener_pid": 123}

            def shutdown(self, _reason):
                return {"success": False, "error": "simulated shutdown failure"}

        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "local"
            cell = local / "cells" / runner.PLAN_ID / "test-run"
            cell.mkdir(parents=True)
            admission = {
                "plan": {}, "gpu_uuid": "GPU-laptop-4060", "profile_sha256": "a" * 64,
                "plan_sha256": "b" * 64, "launch_sha256": "c" * 64,
                "model_roots": {}, "model_manifest": [],
                "profile": {"identity": {"model_sha256s": {}}},
            }
            with mock.patch.object(runner, "validate_admission_inputs", return_value=admission), mock.patch.object(runner, "_safe_local_root", return_value=local), mock.patch.object(runner, "create_cell", return_value=cell), mock.patch.object(runner, "prepare_cell", return_value={}), mock.patch.object(runner, "build_launch_argv", return_value=["python", "main.py"]), mock.patch.object(runner, "OwnedServer", FailingShutdownServer), mock.patch.object(runner, "_verify_fixture_readback"), mock.patch.object(runner, "_admission_receipt", return_value={"status": "ADMITTED_NO_PROMPT_QUEUED"}), mock.patch.object(runner, "verify_model_manifest", return_value=[]):
                with self.assertRaisesRegex(runner.RunnerError, "cleanup was not proved"):
                    runner.execute(runner.PROFILE_ID, run_sequence=False)
            failures = list(cell.glob("failure.json"))
            self.assertEqual(len(failures), 1)
            self.assertFalse((cell / "admission.json").exists())
            self.assertFalse((cell / "run.json").exists())

    def test_cell_setup_failure_has_a_terminal_failure_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "local"
            cell = local / "cells" / runner.PLAN_ID / "test-run"
            cell.mkdir(parents=True)
            admission = {"plan": {}, "gpu_uuid": "GPU-laptop-4060"}
            with mock.patch.object(runner, "validate_admission_inputs", return_value=admission), mock.patch.object(runner, "_safe_local_root", return_value=local), mock.patch.object(runner, "create_cell", return_value=cell), mock.patch.object(runner, "prepare_cell", side_effect=runner.RunnerError("simulated fixture staging failure")):
                with self.assertRaisesRegex(runner.RunnerError, "fixture staging failure"):
                    runner.execute(runner.PROFILE_ID, run_sequence=False)
            self.assertTrue((cell / "shutdown.json").is_file())
            self.assertTrue((cell / "failure.json").is_file())
            self.assertFalse((cell / "admission.json").exists())

    def test_post_shutdown_model_drift_prevents_a_pass_receipt(self):
        class CleanShutdownServer:
            def __init__(self, *_args):
                pass

            def start(self):
                return {"listener_pid": 123}

            def shutdown(self, _reason):
                return {"success": True, "listener_after": None}

        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "local"
            cell = local / "cells" / runner.PLAN_ID / "test-run"
            cell.mkdir(parents=True)
            admission = {
                "plan": {}, "gpu_uuid": "GPU-laptop-4060", "profile_sha256": "a" * 64,
                "plan_sha256": "b" * 64, "launch_sha256": "c" * 64,
                "model_roots": {}, "model_manifest": [],
                "profile": {"identity": {"model_sha256s": {}}},
            }
            with mock.patch.object(runner, "validate_admission_inputs", return_value=admission), mock.patch.object(runner, "_safe_local_root", return_value=local), mock.patch.object(runner, "create_cell", return_value=cell), mock.patch.object(runner, "prepare_cell", return_value={}), mock.patch.object(runner, "build_launch_argv", return_value=["python", "main.py"]), mock.patch.object(runner, "OwnedServer", CleanShutdownServer), mock.patch.object(runner, "_verify_fixture_readback"), mock.patch.object(runner, "_admission_receipt", return_value={"status": "ADMITTED_NO_PROMPT_QUEUED"}), mock.patch.object(runner, "verify_model_manifest", return_value=[{"sha256": "drift"}]):
                with self.assertRaisesRegex(runner.RunnerError, "manifest changed"):
                    runner.execute(runner.PROFILE_ID, run_sequence=False)
            self.assertTrue((cell / "shutdown.json").is_file())
            self.assertTrue((cell / "failure.json").is_file())
            self.assertFalse((cell / "admission.json").exists())

    def test_machine_gate_failure_keeps_its_receipt_but_returns_a_nonzero_runner_error(self):
        class CleanShutdownServer:
            def __init__(self, *_args):
                pass

            def start(self):
                return {"listener_pid": 123}

            def shutdown(self, _reason):
                return {"success": True, "listener_after": None}

        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "local"
            cell = local / "cells" / runner.PLAN_ID / "test-run"
            cell.mkdir(parents=True)
            admission = {
                "plan": {}, "gpu_uuid": "GPU-laptop-4060", "profile_sha256": "a" * 64,
                "plan_sha256": "b" * 64, "launch_sha256": "c" * 64,
                "model_roots": {}, "model_manifest": [],
                "profile": {"identity": {"model_sha256s": {}}},
                "preflight": {
                    "observed": {
                        "selected_gpu": {"memory_total_mib": 8188},
                        "host_ram": {"total_gib": 31.7},
                    }
                },
            }
            failed_leg = {"machine_gate_pass": False, "comfortable_target_met": False}
            with mock.patch.object(runner, "validate_admission_inputs", return_value=admission), mock.patch.object(runner, "_safe_local_root", return_value=local), mock.patch.object(runner, "create_cell", return_value=cell), mock.patch.object(runner, "prepare_cell", return_value={}), mock.patch.object(runner, "build_launch_argv", return_value=["python", "main.py"]), mock.patch.object(runner, "OwnedServer", CleanShutdownServer), mock.patch.object(runner, "_verify_fixture_readback"), mock.patch.object(runner, "_admission_receipt", return_value={"status": "ADMITTED_FOR_SEQUENCE"}), mock.patch.object(runner, "verify_model_manifest", return_value=[]), mock.patch.object(runner, "_run_leg", return_value=failed_leg):
                with self.assertRaisesRegex(runner.RunnerError, "sequence failed a machine gate"):
                    runner.execute(runner.PROFILE_ID, run_sequence=True)
            run = json.loads((cell / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["status"], "MACHINE_GATE_FAILED")
            self.assertTrue((cell / "admission.json").is_file())


if __name__ == "__main__":
    unittest.main()
