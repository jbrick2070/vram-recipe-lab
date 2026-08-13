import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eightgb_bench import preflight_4060 as bench


class Physical4060StaticContractTests(unittest.TestCase):
    def test_static_contract_is_valid_and_does_not_allocate_or_contact_a_server(self):
        result = bench.static_check()
        self.assertEqual(result["status"], "STATIC_CONTRACT_VALID")
        self.assertEqual(result["scope"], bench.SCOPE)
        self.assertEqual(result["network_or_gpu_actions"], "none")

    def test_hardware_inventory_needs_no_profile_or_comfyui_path(self):
        gpu = {"uuid": "GPU-laptop", "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "memory_total_mib": 8188, "driver_version": "999.0", "driver_model_current": "WDDM"}
        with mock.patch.object(bench, "query_nvidia_smi", return_value=[gpu]), mock.patch.object(bench, "host_ram_snapshot", return_value={"total_gib": 31.7, "available_gib": 12.0}):
            result = bench.hardware_inventory()
        self.assertEqual(result["status"], "HARDWARE_OBSERVED_NOT_ENROLLED")
        self.assertEqual(result["gpus"], [gpu])
        self.assertEqual(result["network_or_gpu_actions"], "none")

    def test_first_candidate_is_the_measured_short_native_audio_h3_cell(self):
        plan = json.loads(bench.PLAN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(plan["id"], "h3-mime-i2v-864x480-f90")
        self.assertEqual(plan["video_contract"]["frames"], 90)
        self.assertTrue(plan["video_contract"]["audio"])
        self.assertEqual(plan["orientation_only_source"]["observed_on_other_machine"]["peak_vram_gib"], 7.28)
        self.assertEqual(plan["orientation_only_source"]["observed_on_other_machine"]["peak_host_ram_gib"], 27.56)

    def test_contract_keeps_real_headroom_and_no_sage_policy(self):
        contract = json.loads(bench.CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["acceptance_gates"]["absolute_peak_vram_gib_lte"], 7.5)
        self.assertEqual(contract["acceptance_gates"]["absolute_peak_host_ram_gib_lte"], 28)
        self.assertEqual(contract["future_boot_policy"]["sage_attention"], "forbidden")
        self.assertEqual(contract["future_boot_policy"]["reserve_vram"], "forbidden")
        self.assertIn("run_recipe.py", contract["explicitly_not_used"])

    def test_source_has_no_launcher_or_network_client(self):
        source = Path(bench.__file__).read_text(encoding="utf-8")
        self.assertNotIn("Popen(", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("socket", source)
        self.assertNotIn("http://", source)
        self.assertNotIn("https://", source)

    def test_readonly_subprocess_environment_strips_tokens_proxies_and_lab_selectors(self):
        environment = bench.readonly_environment(
            {
                "PATH": "safe-path",
                "SYSTEMROOT": "C:\\Windows",
                "HF_TOKEN": "must-not-leak",
                "HTTPS_PROXY": "must-not-leak",
                "LAB_RESERVE_VRAM_GB": "12",
                "CUDA_VISIBLE_DEVICES": "0",
            }
        )
        self.assertEqual(environment["PATH"], "safe-path")
        self.assertNotIn("HF_TOKEN", environment)
        self.assertNotIn("HTTPS_PROXY", environment)
        self.assertNotIn("LAB_RESERVE_VRAM_GB", environment)
        self.assertNotIn("CUDA_VISIBLE_DEVICES", environment)
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")


class Physical4060ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / "eightgb_bench" / "local"
        self.local.mkdir(parents=True)
        self.comfy_root = self.root / "ComfyUI"
        self.comfy_root.mkdir()
        (self.comfy_root / "main.py").write_text("print('main')\n", encoding="utf-8")
        self.python = self.root / "python.exe"
        self.python.write_bytes(b"python")
        self.config = self.root / "model-paths.yaml"
        self.config.write_text("models: {}\n", encoding="utf-8")
        self.roots = {}
        for category in ("diffusion_models", "text_encoders", "vae"):
            path = self.root / category
            path.mkdir()
            self.roots[category] = path
        self.plan = json.loads(bench.PLAN_PATH.read_text(encoding="utf-8"))
        self.asset_hashes = {}
        for index, asset in enumerate(self.plan["engine"]["required_assets"], start=1):
            key = f"{asset['category']}/{asset['filename']}"
            path = self.roots[asset["category"]] / asset["filename"]
            path.write_bytes(b"x")
            self.asset_hashes[key] = f"{index:x}" * 64
        self.profile = {
            "schema_version": 1,
            "id": "physical-rtx4060-8gb",
            "scope": bench.SCOPE,
            "expected_gpu": {
                "name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                "uuid": "GPU-test-4060",
                "memory_total_mib_min": 7800,
                "memory_total_mib_max": 8192,
            },
            "paths": {
                "python": str(self.python),
                "comfyui_root": str(self.comfy_root),
                "model_paths_config": str(self.config),
                "model_roots": {key: str(value) for key, value in self.roots.items()},
            },
            "identity": {
                "python_sha256": "a" * 64,
                "python_major_minor": "3.12",
                "comfyui_git_commit": "b" * 40,
                "comfyui_main_py_sha256": "c" * 64,
                "model_paths_config_sha256": "d" * 64,
                "model_sha256s": self.asset_hashes,
            },
            "policy": {
                "require_clean_comfyui_git": True,
                "allowed_python_major_minors": ["3.10", "3.12"],
                "sage_attention": False,
                "manager": False,
                "reserve_vram": "forbidden",
                "network": "offline",
            },
        }
        self.profile_path = self.local / "physical-rtx4060-8gb.profile.json"
        self._write_profile()

    def _write_profile(self):
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")

    def _fake_file_observed(self, path):
        path = Path(path)
        asset_key = next(
            (
                key
                for key in self.asset_hashes
                if path.name == key.split("/", 1)[1]
            ),
            None,
        )
        if asset_key:
            asset = next(
                item
                for item in self.plan["engine"]["required_assets"]
                if f"{item['category']}/{item['filename']}" == asset_key
            )
            return {"path": str(path), "bytes": asset["expected_bytes"], "sha256": self.asset_hashes[asset_key]}
        hashes = {
            self.python: "a" * 64,
            self.comfy_root / "main.py": "c" * 64,
            self.config: "d" * 64,
        }
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": hashes[path]}

    def _preflight_patches(self):
        return (
            mock.patch.object(bench, "LOCAL_ROOT", self.local),
            mock.patch.object(bench, "static_check", return_value={"contract_sha256": "e" * 64, "plan_sha256": "f" * 64}),
            mock.patch.object(bench, "query_nvidia_smi", return_value=[{"uuid": "GPU-test-4060", "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "memory_total_mib": 8188, "driver_version": "999.0", "driver_model_current": "WDDM"}]),
            mock.patch.object(bench, "host_ram_snapshot", return_value={"total_gib": 31.7, "available_gib": 12.0}),
            mock.patch.object(bench, "_observed_file", side_effect=self._fake_file_observed),
            mock.patch.object(bench, "_git_identity", return_value={"commit": "b" * 40, "dirty": False}),
            mock.patch.object(bench, "_run_readonly", return_value="3.12"),
        )

    def test_ready_inventory_is_hardware_bound_but_never_a_render_pass(self):
        patches = self._preflight_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], bench.READY_STATUS)
        self.assertEqual(payload["scope"], bench.SCOPE)
        self.assertEqual(payload["network_or_gpu_actions"], "none")
        self.assertIn("separately reviewed", payload["next_action"])
        self.assertEqual(payload["observed"]["selected_gpu"]["uuid"], "GPU-test-4060")

    def test_unpinned_uuid_fails_closed_and_reports_the_observed_laptop_uuid(self):
        self.profile["expected_gpu"]["uuid"] = ""
        self._write_profile()
        patches = self._preflight_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], "BLOCKED_GPU_UUID_UNPINNED")
        self.assertEqual(payload["blockers"][0]["detail"], "observed GPU-test-4060")

    def test_gpu_memory_outside_the_physical_8gb_range_fails_closed(self):
        patches = self._preflight_patches()
        bad_gpu = [{"uuid": "GPU-test-4060", "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "memory_total_mib": 16303, "driver_version": "999.0", "driver_model_current": "WDDM"}]
        with patches[0], patches[1], mock.patch.object(bench, "query_nvidia_smi", return_value=bad_gpu), patches[3], patches[4], patches[5], patches[6]:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], "BLOCKED_GPU_VRAM_RANGE")

    def test_missing_model_blocks_without_a_server_or_prompt(self):
        first_asset = self.plan["engine"]["required_assets"][0]
        (self.roots[first_asset["category"]] / first_asset["filename"]).unlink()
        patches = self._preflight_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], "BLOCKED_MODEL_MISSING")
        self.assertEqual(payload["network_or_gpu_actions"], "none")

    def test_arbitrary_profile_id_is_rejected_before_any_inventory_probe(self):
        with mock.patch.object(bench, "query_nvidia_smi") as nvidia:
            with self.assertRaisesRegex(bench.PreflightError, "not enrolled"):
                bench.preflight("anything-else")
        nvidia.assert_not_called()

    def test_local_receipt_is_exclusive_and_stays_below_the_ignored_local_root(self):
        payload = {"status": "BLOCKED_MODEL_MISSING", "scope": bench.SCOPE}
        with mock.patch.object(bench, "LOCAL_ROOT", self.local):
            path = bench.write_receipt(payload)
        self.assertTrue(path.is_file())
        self.assertTrue(path.is_relative_to(self.local))
        self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    unittest.main()
