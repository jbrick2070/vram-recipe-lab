import json
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
        self.assertEqual(result["orientation_only_source"]["measurement"]["peak_vram_gib"], 7.28)
        self.assertFalse(result["orientation_only_source"]["measurement"]["pass"])
        self.assertFalse(result["orientation_only_source"]["measurement"]["warm_pass"])

    def test_hardware_inventory_needs_no_profile_or_comfyui_path(self):
        gpu = {"uuid": "GPU-laptop", "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "memory_total_mib": 8188, "driver_version": "999.0", "driver_model_current": "WDDM"}
        with mock.patch.object(bench, "query_nvidia_smi", return_value=[gpu]), mock.patch.object(bench, "host_ram_snapshot", return_value={"total_gib": 31.7, "available_gib": 12.0}):
            result = bench.hardware_inventory()
        self.assertEqual(result["status"], "HARDWARE_OBSERVED_NOT_ENROLLED")
        self.assertEqual(result["receipt_schema_version"], 1)
        self.assertEqual(result["gpus"], [gpu])
        self.assertEqual(result["network_or_gpu_actions"], bench.READ_ONLY_GPU_INVENTORY_ACTIONS)
        self.assertIn("commit only", result["next_action"])
        self.assertNotIn("profile", result["next_action"].casefold())

    def test_hardware_inventory_cli_can_write_only_an_isolated_local_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bench_root = root / "eightgb_bench"
            bench_root.mkdir()
            local_root = bench_root / "local"
            gpu = {"uuid": "GPU-laptop", "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "memory_total_mib": 8188, "driver_version": "999.0", "driver_model_current": "WDDM"}
            payload = {"receipt_schema_version": 1, "status": "HARDWARE_OBSERVED_NOT_ENROLLED", "scope": bench.SCOPE}
            output = []
            with mock.patch.object(bench, "BENCH_ROOT", bench_root), mock.patch.object(bench, "LOCAL_ROOT", local_root), mock.patch.object(bench, "hardware_inventory", return_value=payload), mock.patch.object(bench, "format_json", side_effect=lambda value: output.append(value) or ""):
                self.assertEqual(bench.main(["hardware-inventory", "--write-receipt"]), 0)
            self.assertEqual(len(output), 1)
            self.assertIn("receipt_path", output[0])
            receipt = Path(output[0]["receipt_path"])
            self.assertTrue(receipt.is_relative_to(local_root))
            self.assertTrue(receipt.is_file())

    def test_hardware_inventory_can_publish_one_redacted_commit_ready_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bench_root = root / "eightgb_bench"
            reports_root = bench_root / "reports"
            reports_root.mkdir(parents=True)
            local_root = bench_root / "local"
            raw_uuid = "GPU-laptop-private-uuid"
            payload = {
                "receipt_schema_version": 1,
                "kind": "physical_4060_8gb_hardware_inventory",
                "checked_at_utc": "2026-08-13T16:00:00Z",
                "status": "HARDWARE_OBSERVED_NOT_ENROLLED",
                "scope": bench.SCOPE,
                "contract_sha256": "a" * 64,
                "preflight_script_sha256": "b" * 64,
                "gpus": [{
                    "uuid": raw_uuid,
                    "name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "memory_total_mib": 8188,
                    "driver_version": "999.0",
                    "driver_model_current": "WDDM",
                }],
                "host_ram": {"total_gib": 31.7, "available_gib": 12.0},
                "next_action": "local only",
                "network_or_gpu_actions": bench.READ_ONLY_GPU_INVENTORY_ACTIONS,
            }
            output = []
            with mock.patch.object(bench, "BENCH_ROOT", bench_root), mock.patch.object(bench, "LOCAL_ROOT", local_root), mock.patch.object(bench, "REPORTS_ROOT", reports_root), mock.patch.object(bench, "hardware_inventory", return_value=payload), mock.patch.object(bench, "format_json", side_effect=lambda value: output.append(value) or ""):
                self.assertEqual(bench.main(["hardware-inventory", "--write-public-report"]), 0)
                self.assertEqual(bench.main(["hardware-inventory", "--write-public-report"]), 0)
            self.assertEqual(len(output), 2)
            report_path = reports_root / "physical-rtx4060-8gb-hardware.json"
            self.assertEqual(output[0]["public_report_path"], bench.PUBLIC_REPORT_REPO_PATH.as_posix())
            self.assertTrue(report_path.is_file())
            report_bytes = report_path.read_bytes()
            report = json.loads(report_bytes)
            self.assertNotIn(raw_uuid.encode("utf-8"), report_bytes)
            self.assertNotIn(b"999.0", report_bytes)
            self.assertNotIn(b"WDDM", report_bytes)
            self.assertNotIn(b"available_gib", report_bytes)
            self.assertNotIn(b"checked_at_utc", report_bytes)
            self.assertNotIn(str(local_root).encode("utf-8"), report_bytes)
            self.assertNotIn("receipt_path", report)
            self.assertNotIn("available_gib", report["hardware"])
            self.assertNotIn("gpu_uuid_sha256", report["hardware"])
            receipt_paths = sorted((local_root / "receipts").glob("*.json"))
            self.assertEqual(len(receipt_paths), 2)
            self.assertEqual(
                report["source_local_receipt_sha256"],
                bench.sha256_file(receipt_paths[0]),
            )
            self.assertNotIn(b"GPU-laptop-private-uuid", bench.canonical_bytes(output[0]))
            self.assertNotIn(b"999.0", bench.canonical_bytes(output[0]))
            self.assertNotIn(b"WDDM", bench.canonical_bytes(output[0]))
            self.assertNotIn(b"available_gib", bench.canonical_bytes(output[0]))
            self.assertNotIn(b"checked_at_utc", bench.canonical_bytes(output[0]))
            self.assertNotIn(str(local_root).encode("utf-8"), bench.canonical_bytes(output[0]))
            self.assertEqual(output[1]["public_report_path"], bench.PUBLIC_REPORT_REPO_PATH.as_posix())

    def test_public_hardware_report_rejects_a_redirected_reports_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bench_root = root / "eightgb_bench"
            bench_root.mkdir()
            redirected = root / "somewhere-else"
            redirected.mkdir()
            payload = {
                "receipt_schema_version": 1,
                "kind": "physical_4060_8gb_hardware_inventory",
                "checked_at_utc": "2026-08-13T16:00:00Z",
                "status": "HARDWARE_OBSERVED_NOT_ENROLLED",
                "scope": bench.SCOPE,
                "contract_sha256": "a" * 64,
                "preflight_script_sha256": "b" * 64,
                "gpus": [{
                    "uuid": "GPU-laptop",
                    "name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "memory_total_mib": 8188,
                    "driver_version": "999.0",
                    "driver_model_current": "WDDM",
                }],
                "host_ram": {"total_gib": 31.7, "available_gib": 12.0},
                "next_action": "local only",
                "network_or_gpu_actions": bench.READ_ONLY_GPU_INVENTORY_ACTIONS,
            }
            local_root = bench_root / "local"
            local_root.mkdir()
            receipt_dir = local_root / "receipts"
            receipt_dir.mkdir()
            receipt_path = receipt_dir / "preflight.json"
            receipt_path.write_bytes(bench.canonical_bytes(payload))
            with mock.patch.object(bench, "BENCH_ROOT", bench_root), mock.patch.object(bench, "LOCAL_ROOT", local_root), mock.patch.object(bench, "REPORTS_ROOT", redirected):
                with self.assertRaisesRegex(bench.PreflightError, "report root drifted"):
                    bench.write_public_hardware_report(receipt_path)

    def test_first_candidate_is_the_measured_short_native_audio_h3_cell(self):
        plan = json.loads(bench.PLAN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(plan["id"], "h3-mime-i2v-864x480-f90")
        self.assertEqual(plan["video_contract"]["frames"], 90)
        self.assertTrue(plan["video_contract"]["audio"])
        self.assertEqual(plan["orientation_only_source"]["observed_on_other_machine"]["peak_vram_gib"], 7.28)
        self.assertEqual(plan["orientation_only_source"]["observed_on_other_machine"]["peak_host_ram_gib"], 27.56)

    def test_profile_template_declares_each_h3_model_root_required_by_the_plan(self):
        profile = json.loads((bench.BENCH_ROOT / "profile-template.json").read_text(encoding="utf-8"))
        self.assertEqual(set(profile["paths"]["model_roots"]), {"diffusion_models", "text_encoders", "vae"})

    def test_static_check_rejects_a_decorative_or_drifted_orientation_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            mutated_path = Path(directory) / "plan.json"
            plan = json.loads(bench.PLAN_PATH.read_text(encoding="utf-8"))
            plan["orientation_only_source"]["receipt_sha256"] = "0" * 64
            mutated_path.write_text(json.dumps(plan), encoding="utf-8")
            with mock.patch.object(bench, "PLAN_PATH", mutated_path):
                with self.assertRaisesRegex(bench.PreflightError, "orientation receipt SHA"):
                    bench.static_check()

    def test_contract_keeps_real_headroom_and_no_sage_policy(self):
        contract = json.loads(bench.CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["acceptance_gates"]["absolute_peak_vram_gib_lte"], 7.5)
        self.assertEqual(contract["acceptance_gates"]["absolute_peak_host_ram_gib_lte"], 28)
        self.assertEqual(contract["future_boot_policy"]["sage_attention"], "forbidden")
        self.assertEqual(contract["future_boot_policy"]["reserve_vram"], "forbidden")
        self.assertTrue(any("run_recipe.py" in value for value in contract["explicitly_not_used"]))

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
                "PROGRAMFILES": "C:\\Program Files",
                "HF_TOKEN": "must-not-leak",
                "HTTPS_PROXY": "must-not-leak",
                "OPENAI_API_KEY": "must-not-leak",
                "LAB_RESERVE_VRAM_GB": "12",
                "CUDA_VISIBLE_DEVICES": "0",
            }
        )
        self.assertEqual(environment["PATH"], "safe-path")
        self.assertEqual(environment["PROGRAMFILES"], "C:\\Program Files")
        self.assertNotIn("HF_TOKEN", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("HTTPS_PROXY", environment)
        self.assertNotIn("LAB_RESERVE_VRAM_GB", environment)
        self.assertNotIn("CUDA_VISIBLE_DEVICES", environment)
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")

    def test_git_identity_scopes_git_calls_with_a_per_command_safe_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            comfy_root = Path(directory) / "ComfyUI"
            comfy_root.mkdir()
            trusted_git = Path("C:\\Program Files\\Git\\cmd\\git.exe")
            with (
                mock.patch.object(bench, "_trusted_git_path", return_value=trusted_git),
                mock.patch.object(bench, "_run_readonly") as run_readonly,
            ):
                run_readonly.side_effect = ["b" * 40, ""]
                bench._git_identity(comfy_root)

        calls = run_readonly.call_args_list
        self.assertEqual(len(calls), 2)
        first = calls[0].args[0]
        second = calls[1].args[0]
        expected_prefix = [str(trusted_git), "-c", f"safe.directory={comfy_root}", "-C", str(comfy_root)]
        self.assertEqual(first[:5], expected_prefix)
        self.assertEqual(second[:5], expected_prefix)
        self.assertEqual(first[-2:], ["rev-parse", "HEAD"])
        self.assertEqual(second[-2:], ["status", "--porcelain"])

    def test_readonly_subprocesses_have_a_fixed_timeout(self):
        with mock.patch.object(bench.subprocess, "run", side_effect=bench.subprocess.TimeoutExpired("probe", 20)):
            with self.assertRaisesRegex(bench.PreflightError, "timed out"):
                bench._run_readonly(["not-run"], "test probe")


class Physical4060ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bench_root = self.root / "eightgb_bench"
        self.local = self.bench_root / "local"
        self.local.mkdir(parents=True)
        self.comfy_root = self.root / "ComfyUI"
        self.comfy_root.mkdir()
        (self.comfy_root / "main.py").write_text("print('main')\n", encoding="utf-8")
        self.python = self.root / "python.exe"
        self.python.write_bytes(b"python")
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
                "model_roots": {key: str(value) for key, value in self.roots.items()},
            },
            "identity": {
                "python_sha256": "a" * 64,
                "python_major_minor": "3.12",
                "comfyui_git_commit": "b" * 40,
                "comfyui_main_py_sha256": "c" * 64,
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
        }
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": hashes.get(path, "e" * 64)}

    def _preflight_patches(self):
        return (
            mock.patch.object(bench, "LOCAL_ROOT", self.local),
            mock.patch.object(bench, "BENCH_ROOT", self.bench_root),
            mock.patch.object(bench, "static_check", return_value={"contract_sha256": "e" * 64, "plan_sha256": "f" * 64}),
            mock.patch.object(bench, "query_nvidia_smi", return_value=[{"uuid": "GPU-test-4060", "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "memory_total_mib": 8188, "driver_version": "999.0", "driver_model_current": "WDDM"}]),
            mock.patch.object(bench, "host_ram_snapshot", return_value={"total_gib": 31.7, "available_gib": 12.0}),
            mock.patch.object(bench, "_observed_file", side_effect=self._fake_file_observed),
            mock.patch.object(bench, "_git_identity", return_value={"commit": "b" * 40, "dirty": False}),
            mock.patch.object(bench.sys, "executable", str(self.python)),
            mock.patch.object(bench, "_running_python_major_minor", return_value="3.12"),
        )

    def test_ready_inventory_is_hardware_bound_but_never_a_render_pass(self):
        patches = self._preflight_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], bench.READY_STATUS)
        self.assertEqual(payload["scope"], bench.SCOPE)
        self.assertEqual(payload["network_or_gpu_actions"], bench.READ_ONLY_GPU_INVENTORY_ACTIONS)
        self.assertIn("separately reviewed", payload["next_action"])
        self.assertEqual(payload["observed"]["selected_gpu"]["uuid"], "GPU-test-4060")

    def test_unpinned_uuid_fails_closed_and_reports_the_observed_laptop_uuid(self):
        self.profile["expected_gpu"]["uuid"] = ""
        self._write_profile()
        patches = self._preflight_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], "BLOCKED_GPU_UUID_UNPINNED")
        self.assertEqual(payload["blockers"][0]["detail"], "observed GPU-test-4060")

    def test_gpu_memory_outside_the_physical_8gb_range_fails_closed(self):
        patches = self._preflight_patches()
        bad_gpu = [{"uuid": "GPU-test-4060", "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "memory_total_mib": 16303, "driver_version": "999.0", "driver_model_current": "WDDM"}]
        with patches[0], patches[1], patches[2], mock.patch.object(bench, "query_nvidia_smi", return_value=bad_gpu), patches[4], patches[5], patches[6], patches[7], patches[8]:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], "BLOCKED_GPU_VRAM_RANGE")

    def test_missing_model_blocks_without_a_server_or_prompt(self):
        first_asset = self.plan["engine"]["required_assets"][0]
        (self.roots[first_asset["category"]] / first_asset["filename"]).unlink()
        patches = self._preflight_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], "BLOCKED_MODEL_MISSING")
        self.assertEqual(payload["network_or_gpu_actions"], bench.READ_ONLY_GPU_INVENTORY_ACTIONS)

    def test_arbitrary_profile_id_is_rejected_before_any_inventory_probe(self):
        with mock.patch.object(bench, "query_nvidia_smi") as nvidia:
            with self.assertRaisesRegex(bench.PreflightError, "not enrolled"):
                bench.preflight("anything-else")
        nvidia.assert_not_called()

    def test_local_receipt_is_exclusive_and_stays_below_the_ignored_local_root(self):
        payload = {"status": "BLOCKED_MODEL_MISSING", "scope": bench.SCOPE}
        with mock.patch.object(bench, "LOCAL_ROOT", self.local), mock.patch.object(bench, "BENCH_ROOT", self.bench_root):
            path = bench.write_receipt(payload)
        self.assertTrue(path.is_file())
        self.assertTrue(path.is_relative_to(self.local))
        self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_local_receipt_rejects_a_redirected_state_root(self):
        payload = {"status": "BLOCKED_MODEL_MISSING", "scope": bench.SCOPE}
        redirected = self.root / "somewhere-else"
        redirected.mkdir()
        with mock.patch.object(bench, "LOCAL_ROOT", redirected), mock.patch.object(bench, "BENCH_ROOT", self.bench_root):
            with self.assertRaisesRegex(bench.PreflightError, "state root drifted"):
                bench.write_receipt(payload)

    def test_derived_child_file_rejects_a_reparse_leaf(self):
        with mock.patch.object(bench, "_is_reparse_point", side_effect=lambda path: Path(path).name == "main.py"):
            with self.assertRaisesRegex(bench.PreflightError, "reparse"):
                bench._validated_child_file(self.comfy_root, "main.py", "test main")

    def test_hardware_identity_failure_does_not_enter_profile_roots_or_hash_models(self):
        self.profile["expected_gpu"]["uuid"] = ""
        self._write_profile()
        patches = self._preflight_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], mock.patch.object(bench, "_profile_paths") as profile_paths:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], "BLOCKED_GPU_UUID_UNPINNED")
        profile_paths.assert_not_called()

    def test_wrong_executing_python_fails_before_comfy_or_model_identity_probes(self):
        patches = self._preflight_patches()
        other_python = self.root / "other-python.exe"
        other_python.write_bytes(b"other")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], mock.patch.object(bench.sys, "executable", str(other_python)), mock.patch.object(bench, "_profile_paths") as profile_paths:
            payload = bench.preflight("physical-rtx4060-8gb")
        self.assertEqual(payload["status"], "BLOCKED_EXECUTING_PYTHON_PATH_DRIFT")
        profile_paths.assert_not_called()


if __name__ == "__main__":
    unittest.main()
