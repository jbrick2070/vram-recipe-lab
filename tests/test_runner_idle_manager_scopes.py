import copy
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_recipe  # noqa: E402


class ManagerProbeScopeTests(unittest.TestCase):
    def test_closed_scope_map_accepts_only_named_campaigns(self):
        mission1 = run_recipe.manager_probe_recipe_scope(
            "h3_unconditioned_music_scene_seed42_f124"
        )
        self.assertEqual(mission1["scope"], "h3-unconditioned-music-mission1")
        self.assertEqual(mission1["match_type"], "prefix")

        for recipe_name in run_recipe.MANAGER_PROBE_CANONICAL_JOB_C_RECIPES:
            with self.subTest(recipe_name=recipe_name):
                scope = run_recipe.manager_probe_recipe_scope(recipe_name)
                self.assertEqual(scope["scope"], "h3-canonical-canvas-job-c")
                self.assertEqual(scope["match_type"], "exact")
                self.assertEqual(scope["match_value"], recipe_name)

        for recipe_name in run_recipe.MANAGER_PROBE_SHORT_JOB_RECIPES:
            with self.subTest(recipe_name=recipe_name):
                scope = run_recipe.manager_probe_recipe_scope(recipe_name)
                self.assertEqual(scope["scope"], "h3-short-jobs")
                self.assertEqual(scope["match_type"], "exact")
                self.assertEqual(scope["match_value"], recipe_name)

        followup = run_recipe.manager_probe_recipe_scope(
            "h3_music_followup_score_seed43_f124"
        )
        self.assertEqual(followup["scope"], "h3-music-followup")
        self.assertEqual(followup["match_type"], "prefix")

        rejected = (
            "h3_i2v_canonical_832x480_f124",
            "h3_r2v_refaudio_canonical_832x480_f192_seed42",
            "h3_music_followup",
            "h3_unconditioned_music",
            "unrelated_recipe",
            "../h3_music_followup_escape",
        )
        for recipe_name in rejected:
            with self.subTest(recipe_name=recipe_name):
                with self.assertRaises(run_recipe.PreflightError):
                    run_recipe.manager_probe_recipe_scope(recipe_name)

    def test_log_path_is_contained_by_selected_recipe_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mission1 = root / "mission1"
            canonical = root / "canonical"
            followup = root / "followup"
            for path in (mission1, canonical, followup):
                path.mkdir()
            scopes = (
                ("mission1", frozenset(), "h3_unconditioned_music_", mission1),
                (
                    "canonical",
                    frozenset({"h3_i2v_canonical_832x480_f107"}),
                    None,
                    canonical,
                ),
                ("followup", frozenset(), "h3_music_followup_", followup),
            )
            canonical_log = canonical / "pair1.log"
            environment = {
                run_recipe.MANAGER_PROBE_ENV: "1",
                run_recipe.MANAGER_PROBE_LOG_ENV: str(canonical_log),
            }
            with (
                mock.patch.object(run_recipe, "MANAGER_PROBE_SCOPES", scopes),
                mock.patch.dict(os.environ, environment, clear=True),
            ):
                self.assertEqual(
                    run_recipe.manager_probe_log_path(
                        "h3_i2v_canonical_832x480_f107"
                    ),
                    canonical_log.resolve(),
                )
                with self.assertRaises(run_recipe.PreflightError):
                    run_recipe.manager_probe_log_path(
                        "h3_unconditioned_music_scene_seed42_f124"
                    )


class WddmIdleGateTests(unittest.TestCase):
    server_instance = {
        "serving_pid": 1234,
        "process_create_time": 5678.0,
    }

    @staticmethod
    def runner_exclusion():
        return {
            "pid": 100,
            "process_create_time": 50.0,
            "resolved_runner_path": str(Path(run_recipe.__file__).resolve()),
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": {
                "pid": 100,
                "exists": True,
                "name": "python.exe",
                "executable": sys.executable,
                "command_line": [sys.executable, str(Path(run_recipe.__file__).resolve())],
                "process_create_time": 50.0,
                "identity_errors": [],
            },
            "verified_windows_venv_launcher": None,
            "expected_excluded_process_count": 1,
        }

    @staticmethod
    def runner_exclusion_with_launcher(venv_prefix=None):
        exclusion = WddmIdleGateTests.runner_exclusion()
        prefix = Path(venv_prefix or sys.prefix).resolve()
        launcher_exe = str((prefix / "Scripts" / "python.exe").resolve())
        child_exe_path = (Path(sys.base_prefix) / "python.exe").resolve()
        if os.path.normcase(str(child_exe_path)) == os.path.normcase(launcher_exe):
            child_exe_path = (prefix / "base-runtime" / "python.exe").resolve()
        child_exe = str(child_exe_path)
        runner_path = str(Path(run_recipe.__file__).resolve())
        child_argv = [child_exe, runner_path]
        launcher_argv = [launcher_exe, runner_path]
        exclusion["process_identity"]["executable"] = child_exe
        exclusion["process_identity"]["command_line"] = child_argv
        exclusion["verified_windows_venv_launcher"] = {
            "pid": 228,
            "process_create_time": 49.0,
            "expected_launcher_path": launcher_exe,
            "direct_child_pid": 100,
            "direct_parent_verified": True,
            "launcher_identity_live": True,
            "child_identity_live": True,
            "argv_tail_matches_child": True,
            "both_exact_runner_target": True,
            "child_executable_differs": True,
            "creation_delta_s": 1.0,
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": {
                "pid": 228,
                "exists": True,
                "name": "python.exe",
                "executable": launcher_exe,
                "command_line": launcher_argv,
                "process_create_time": 49.0,
                "identity_errors": [],
            },
        }
        exclusion["expected_excluded_process_count"] = 2
        return exclusion

    @staticmethod
    def listener_evidence():
        return {
            "port": 8199,
            "listeners": [],
            "listener_pids": [],
            "unknown_owner_count": 0,
        }

    @staticmethod
    def target_gpu():
        return {
            "gpu_index": 0,
            "gpu_uuid": "GPU-TEST",
            "gpu_name": "Test GPU",
            "vram_total_mib": 16384.0,
            "driver_model_current": "WDDM",
            "display_active": "Enabled",
            "query_argv": ["nvidia-smi", "identity"],
            "raw_stdout_sha256": "a" * 64,
        }

    @staticmethod
    def activity():
        return {
            "gpu_index": 0,
            "gpu_uuid": "GPU-TEST",
            "gpu_name": "Test GPU",
            "vram_used_mib": 1200.0,
            "vram_total_mib": 16384.0,
            "gpu_utilization_percent": 2.0,
            "memory_utilization_percent": 1.0,
            "performance_state": "P8",
            "driver_model_current": "WDDM",
            "display_active": "Enabled",
            "query_argv": ["nvidia-smi", "activity"],
            "raw_stdout_sha256": "b" * 64,
        }

    @staticmethod
    def process_evidence():
        return {
            "target_gpu_index": 0,
            "target_gpu_uuid": "GPU-TEST",
            "query_argv": ["nvidia-smi", "processes"],
            "raw_stdout_sha256": "c" * 64,
            "row_count": 0,
            "rows": [],
            "blocking_rows": [],
        }

    @staticmethod
    def lock_evidence():
        return {
            "path": str(ROOT / ".gpu.lock"),
            "receipt": {
                "lock_schema_version": 1,
                "role": "standalone",
                "pid": 100,
                "process_create_time": 50.0,
                "nonce": "d" * 64,
                "created_at_unix": 49.0,
            },
            "receipt_sha256": "d" * 64,
            "authorization": "current standalone owner",
            "matches_expected_owner": True,
            "matches_acquired_owner": True,
        }

    def forbidden_scan(self):
        return {
            "scanned_process_count": 10,
            "model_workload_markers": list(
                run_recipe.GPU_IDLE_MODEL_WORKLOAD_MARKERS
            ),
            "classifier_contract": run_recipe.known_workload_classifier_contract(),
            "current_runner_exclusion": self.runner_exclusion(),
            "excluded_current_runner": [
                {
                    "pid": 100,
                    "process_create_time": 50.0,
                    "reason": "exact current run_recipe process",
                }
            ],
            "blocking_processes": [],
            "advisory_unreadable_processes": [],
        }

    @staticmethod
    def server_argv():
        return [
            str(run_recipe.COMFYUI_ROOT / "main.py"),
            "--port",
            "8199",
            "--output-directory",
            str(run_recipe.REPO_ROOT / "outputs"),
        ]

    @staticmethod
    def server_exclusion_with_launcher(venv_prefix=None):
        prefix = Path(venv_prefix or sys.prefix).resolve()
        launcher_exe = str((prefix / "Scripts" / "python.exe").resolve())
        child_exe_path = (Path(sys.base_prefix) / "python.exe").resolve()
        if os.path.normcase(str(child_exe_path)) == os.path.normcase(launcher_exe):
            child_exe_path = (prefix / "base-runtime" / "python.exe").resolve()
        child_exe = str(child_exe_path)
        server_argv = WddmIdleGateTests.server_argv()
        child_argv = [child_exe, *server_argv]
        launcher_argv = [launcher_exe, *server_argv]
        return {
            "pid": 1234,
            "process_create_time": 5678.0,
            "server_instance": copy.deepcopy(WddmIdleGateTests.server_instance),
            "process_identity": {
                "pid": 1234,
                "exists": True,
                "name": "python.exe",
                "executable": child_exe,
                "command_line": child_argv,
                "process_create_time": 5678.0,
                "identity_errors": [],
            },
            "argv_match": run_recipe._prequeue_server_argv_match(
                child_argv, server_argv, child_exe
            ),
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "verified_windows_venv_launcher": {
                "pid": 37248,
                "process_create_time": 5677.0,
                "expected_launcher_path": launcher_exe,
                "direct_child_pid": 1234,
                "direct_parent_verified": True,
                "launcher_identity_live": True,
                "child_identity_live": True,
                "argv_tail_matches_child": True,
                "both_exact_validated_server_argv": True,
                "child_executable_differs": True,
                "creation_delta_s": 1.0,
                "narrowly_verified": True,
                "excluded_pid_only": True,
                "process_identity": {
                    "pid": 37248,
                    "exists": True,
                    "name": "python.exe",
                    "executable": launcher_exe,
                    "command_line": launcher_argv,
                    "process_create_time": 5677.0,
                    "identity_errors": [],
                },
                "argv_match": run_recipe._prequeue_server_argv_match(
                    launcher_argv, server_argv, launcher_exe
                ),
            },
            "expected_excluded_process_count": 2,
        }

    def prequeue_processes(self, extra=()):
        current = SimpleNamespace(
            info={
                "pid": 100,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [
                    sys.executable,
                    str(Path(run_recipe.__file__).resolve()),
                ],
                "create_time": 50.0,
            }
        )
        server = SimpleNamespace(
            info={
                "pid": self.server_instance["serving_pid"],
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [sys.executable, *self.server_argv()],
                "create_time": self.server_instance["process_create_time"],
            }
        )
        return [current, server, *extra]

    def collect_prequeue_scan(self, extra=()):
        server_identity = {
            "pid": self.server_instance["serving_pid"],
            "exists": True,
            "name": "python.exe",
            "executable": sys.executable,
            "command_line": [sys.executable, *self.server_argv()],
            "process_create_time": self.server_instance["process_create_time"],
            "identity_errors": [],
        }
        with (
            mock.patch.object(
                run_recipe,
                "_idle_current_runner_exclusion",
                return_value=self.runner_exclusion(),
            ),
            mock.patch.object(
                run_recipe, "_idle_process_identity", return_value=server_identity
            ),
            mock.patch.object(
                run_recipe,
                "_prequeue_verified_owned_server_windows_venv_launcher",
                return_value=None,
            ),
            mock.patch.object(
                run_recipe.psutil,
                "process_iter",
                return_value=self.prequeue_processes(extra),
            ),
            mock.patch.object(
                run_recipe, "listener_pid", side_effect=[1234, 1234]
            ),
        ):
            return run_recipe.collect_prequeue_known_workload_scan(
                self.server_instance, self.server_argv()
            )

    def collect_prequeue_scan_with_runner(self, exclusion, extra=()):
        def process_row(identity):
            return SimpleNamespace(
                info={
                    "pid": identity["pid"],
                    "name": identity["name"],
                    "exe": identity["executable"],
                    "cmdline": list(identity["command_line"]),
                    "create_time": identity["process_create_time"],
                }
            )

        server_identity = {
            "pid": self.server_instance["serving_pid"],
            "exists": True,
            "name": "python.exe",
            "executable": sys.executable,
            "command_line": [sys.executable, *self.server_argv()],
            "process_create_time": self.server_instance["process_create_time"],
            "identity_errors": [],
        }
        rows = [process_row(exclusion["process_identity"])]
        launcher = exclusion.get("verified_windows_venv_launcher")
        if isinstance(launcher, dict):
            rows.append(process_row(launcher["process_identity"]))
        rows.extend((process_row(server_identity), *extra))
        child_process = SimpleNamespace(ppid=lambda: int(launcher["pid"]))
        with (
            mock.patch.object(
                run_recipe, "_idle_current_runner_exclusion", return_value=exclusion
            ),
            mock.patch.object(
                run_recipe, "_idle_process_identity", return_value=server_identity
            ),
            mock.patch.object(
                run_recipe,
                "_prequeue_verified_owned_server_windows_venv_launcher",
                return_value=None,
            ),
            mock.patch.object(run_recipe.psutil, "process_iter", return_value=rows),
            mock.patch.object(run_recipe.psutil, "Process", return_value=child_process),
            mock.patch.object(
                run_recipe.lab_locks, "process_identity_is_live", return_value=True
            ),
            mock.patch.object(
                run_recipe, "listener_pid", side_effect=[1234, 1234]
            ),
        ):
            return run_recipe.collect_prequeue_known_workload_scan(
                self.server_instance, self.server_argv()
            )

    def collect_prequeue_scan_with_server(self, server_exclusion, extra=()):
        def process_row(identity):
            return SimpleNamespace(
                info={
                    "pid": identity["pid"],
                    "name": identity["name"],
                    "exe": identity["executable"],
                    "cmdline": list(identity["command_line"]),
                    "create_time": identity["process_create_time"],
                }
            )

        current = self.runner_exclusion()
        launcher = server_exclusion["verified_windows_venv_launcher"]
        rows = [
            process_row(current["process_identity"]),
            process_row(server_exclusion["process_identity"]),
            process_row(launcher["process_identity"]),
            *extra,
        ]
        serving_process = SimpleNamespace(ppid=lambda: int(launcher["pid"]))
        with (
            mock.patch.object(
                run_recipe, "_idle_current_runner_exclusion", return_value=current
            ),
            mock.patch.object(
                run_recipe,
                "_prequeue_owned_server_exclusion",
                return_value=server_exclusion,
            ),
            mock.patch.object(run_recipe.psutil, "process_iter", return_value=rows),
            mock.patch.object(
                run_recipe.psutil, "Process", return_value=serving_process
            ),
            mock.patch.object(
                run_recipe.lab_locks, "process_identity_is_live", return_value=True
            ),
            mock.patch.object(
                run_recipe, "listener_pid", side_effect=[1234, 1234]
            ),
        ):
            return run_recipe.collect_prequeue_known_workload_scan(
                self.server_instance, self.server_argv()
            )

    def measured_evidence(self):
        memory = SimpleNamespace(used=1024, total=4096)
        with (
            mock.patch.object(
                run_recipe,
                "_idle_current_runner_exclusion",
                return_value=self.runner_exclusion(),
            ),
            mock.patch.object(
                run_recipe,
                "_idle_listener_evidence",
                side_effect=[self.listener_evidence() for _ in range(7)],
            ),
            mock.patch.object(
                run_recipe, "_idle_target_gpu_identity", return_value=self.target_gpu()
            ),
            mock.patch.object(
                run_recipe,
                "_idle_query_gpu_activity",
                side_effect=[self.activity() for _ in range(5)],
            ),
            mock.patch.object(
                run_recipe,
                "_idle_query_process_evidence",
                side_effect=[self.process_evidence() for _ in range(5)],
            ),
            mock.patch.object(
                run_recipe,
                "_idle_lock_evidence",
                side_effect=[self.lock_evidence() for _ in range(5)],
            ),
            mock.patch.object(
                run_recipe,
                "_idle_forbidden_process_scan",
                side_effect=[self.forbidden_scan() for _ in range(5)],
            ),
            mock.patch.object(run_recipe.psutil, "virtual_memory", return_value=memory),
            mock.patch.object(run_recipe.time, "sleep") as sleep,
        ):
            evidence = run_recipe.check_gpu_idle()
        self.assertEqual(sleep.call_count, 4)
        return run_recipe._idle_finalize_evidence(evidence, self.server_instance)

    def test_five_sample_gate_retains_and_validates_immutable_evidence(self):
        evidence = self.measured_evidence()
        self.assertEqual(evidence["status"], "measured")
        self.assertTrue(evidence["gate_ran"])
        self.assertEqual(evidence["sample_count"], 5)
        self.assertEqual(len(evidence["samples"]), 5)
        self.assertEqual(evidence["server_instance"], self.server_instance)
        self.assertEqual(
            evidence["evidence_sha256"],
            run_recipe.stable_identity(
                {key: value for key, value in evidence.items() if key != "evidence_sha256"}
            ),
        )
        self.assertEqual(
            run_recipe.gpu_idle_gate_validation_errors(
                evidence, self.server_instance
            ),
            [],
        )

        tampered = copy.deepcopy(evidence)
        tampered["samples"][0]["vram_used_mib"] = 2000.0
        errors = run_recipe.gpu_idle_gate_validation_errors(
            tampered, self.server_instance
        )
        self.assertIn("idle gate evidence SHA-256 is invalid", errors)
        self.assertIn("cold idle gate summary was not recomputed", errors)

    def test_warm_marker_explicitly_disclaims_fresh_sampling(self):
        evidence = run_recipe._idle_owned_server_reuse_evidence(self.server_instance)
        self.assertEqual(evidence["status"], "not-rerun-owned-server-reuse")
        self.assertFalse(evidence["gate_ran"])
        self.assertNotIn("samples", evidence)
        self.assertEqual(
            run_recipe.gpu_idle_gate_validation_errors(
                evidence, self.server_instance
            ),
            [],
        )

        extra = copy.deepcopy(evidence)
        extra["summary"] = {}
        extra.pop("evidence_sha256")
        extra["evidence_sha256"] = run_recipe.stable_identity(extra)
        self.assertIn(
            "owned-server reuse marker contains missing/extra fields",
            run_recipe.gpu_idle_gate_validation_errors(
                extra, self.server_instance
            ),
        )

        wrong_reason = copy.deepcopy(evidence)
        wrong_reason["reason"] = "fresh gate ran"
        wrong_reason.pop("evidence_sha256")
        wrong_reason["evidence_sha256"] = run_recipe.stable_identity(wrong_reason)
        self.assertIn(
            "owned-server reuse reason is not exact",
            run_recipe.gpu_idle_gate_validation_errors(
                wrong_reason, self.server_instance
            ),
        )

    def test_idle_vram_threshold_is_inclusive_and_gating(self):
        activity = self.activity()
        activity["vram_used_mib"] = 3072.0
        errors = run_recipe._idle_evaluate_sample(
            activity,
            self.process_evidence(),
            self.lock_evidence(),
            self.listener_evidence(),
            self.forbidden_scan(),
        )
        self.assertEqual(errors, [])

        activity["vram_used_mib"] = 3072.1
        errors = run_recipe._idle_evaluate_sample(
            activity,
            self.process_evidence(),
            self.lock_evidence(),
            self.listener_evidence(),
            self.forbidden_scan(),
        )
        self.assertIn(
            "selected GPU absolute baseline exceeds 3072 MiB", errors
        )

        contract = run_recipe.gpu_idle_gate_contract()
        self.assertEqual(contract["policy"]["maximum_vram_used_mib"], 3072.0)
        self.assertTrue(contract["policy"]["vram_used_mib_threshold_gating"])
        self.assertEqual(
            contract["policy"]["operator_idle_policy"],
            run_recipe.operator_idle_policy_contract(),
        )

        evidence = self.measured_evidence()
        evidence["samples"][-1]["vram_used_mib"] = 4096.0
        evidence["summary"]["max_vram_used_mib"] = 4096.0
        evidence.pop("evidence_sha256")
        evidence["evidence_sha256"] = run_recipe.stable_identity(evidence)
        self.assertIn(
            "sample 4 exceeds the 3072 MiB absolute baseline gate",
            run_recipe.gpu_idle_gate_validation_errors(
                evidence, self.server_instance
            ),
        )

    def test_wddm_display_disabled_is_recorded_and_non_gating(self):
        activity = self.activity()
        activity["display_active"] = "Disabled"
        self.assertEqual(
            run_recipe._idle_evaluate_sample(
                activity,
                self.process_evidence(),
                self.lock_evidence(),
                self.listener_evidence(),
                self.forbidden_scan(),
            ),
            [],
        )
        evidence = self.measured_evidence()
        evidence["target_gpu"]["display_active"] = "Disabled"
        for sample in evidence["samples"]:
            sample["display_active"] = "Disabled"
        evidence.pop("evidence_sha256")
        evidence["evidence_sha256"] = run_recipe.stable_identity(evidence)
        self.assertEqual(
            run_recipe.gpu_idle_gate_validation_errors(
                evidence, self.server_instance
            ),
            [],
        )
        policy = run_recipe.gpu_idle_gate_contract()["policy"]
        self.assertEqual(
            policy["display_active_allowed_measured_states"],
            ["Disabled", "Enabled"],
        )
        self.assertTrue(policy["display_active_recorded_non_gating"])

    def test_validator_rejects_lock_nonce_and_runner_exclusion_drift(self):
        evidence = self.measured_evidence()
        lock_drift = copy.deepcopy(evidence)
        lock_drift["samples"][3]["gpu_lock"]["receipt"]["nonce"] = "e" * 64
        lock_drift.pop("evidence_sha256")
        lock_drift["evidence_sha256"] = run_recipe.stable_identity(lock_drift)
        self.assertIn(
            "sample 3 GPU lease owner/nonce drifted",
            run_recipe.gpu_idle_gate_validation_errors(
                lock_drift, self.server_instance
            ),
        )

        runner_drift = copy.deepcopy(evidence)
        runner_drift["samples"][2]["forbidden_process_scan"][
            "current_runner_exclusion"
        ]["pid"] = 999
        runner_drift.pop("evidence_sha256")
        runner_drift["evidence_sha256"] = run_recipe.stable_identity(runner_drift)
        self.assertIn(
            "sample 2 current runner exclusion binding drifted",
            run_recipe.gpu_idle_gate_validation_errors(
                runner_drift, self.server_instance
            ),
        )

    def test_gate_retains_utilization_descriptors_without_using_them_as_blockers(self):
        memory = SimpleNamespace(used=1024, total=4096)
        activities = [self.activity() for _ in range(5)]
        activities[2]["gpu_utilization_percent"] = 50.0
        with (
            mock.patch.object(
                run_recipe,
                "_idle_current_runner_exclusion",
                return_value=self.runner_exclusion(),
            ),
            mock.patch.object(
                run_recipe,
                "_idle_listener_evidence",
                side_effect=[self.listener_evidence() for _ in range(7)],
            ),
            mock.patch.object(
                run_recipe, "_idle_target_gpu_identity", return_value=self.target_gpu()
            ),
            mock.patch.object(
                run_recipe, "_idle_query_gpu_activity", side_effect=activities
            ) as activity,
            mock.patch.object(
                run_recipe,
                "_idle_query_process_evidence",
                side_effect=[self.process_evidence() for _ in range(5)],
            ),
            mock.patch.object(
                run_recipe,
                "_idle_lock_evidence",
                side_effect=[self.lock_evidence() for _ in range(5)],
            ),
            mock.patch.object(
                run_recipe,
                "_idle_forbidden_process_scan",
                side_effect=[self.forbidden_scan() for _ in range(5)],
            ),
            mock.patch.object(run_recipe.psutil, "virtual_memory", return_value=memory),
            mock.patch.object(run_recipe.time, "sleep"),
        ):
            evidence = run_recipe.check_gpu_idle()
        self.assertEqual(activity.call_count, 5)
        self.assertEqual(evidence["summary"]["max_gpu_utilization_percent"], 50.0)
        self.assertTrue(all(row["quiescent"] for row in evidence["samples"]))

    def test_cold_gate_error_deduplicates_redacted_diagnostic_blocker(self):
        memory = SimpleNamespace(used=1024, total=4096)
        blocker = run_recipe.classify_known_workload_process(
            {
                "pid": 777,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [
                    sys.executable,
                    r"C:\foreign\run_recipe.py",
                    "--token",
                    "SECRET_VALUE",
                ],
                "create_time": 3.0,
            }
        )["redacted_process"]
        blocked_scan = self.forbidden_scan()
        blocked_scan["blocking_processes"] = [blocker]
        with (
            mock.patch.object(
                run_recipe,
                "_idle_current_runner_exclusion",
                return_value=self.runner_exclusion(),
            ),
            mock.patch.object(
                run_recipe,
                "_idle_listener_evidence",
                side_effect=[self.listener_evidence() for _ in range(7)],
            ),
            mock.patch.object(
                run_recipe, "_idle_target_gpu_identity", return_value=self.target_gpu()
            ),
            mock.patch.object(
                run_recipe,
                "_idle_query_gpu_activity",
                side_effect=[self.activity() for _ in range(5)],
            ),
            mock.patch.object(
                run_recipe,
                "_idle_query_process_evidence",
                side_effect=[self.process_evidence() for _ in range(5)],
            ),
            mock.patch.object(
                run_recipe,
                "_idle_lock_evidence",
                side_effect=[self.lock_evidence() for _ in range(5)],
            ),
            mock.patch.object(
                run_recipe,
                "_idle_forbidden_process_scan",
                side_effect=[copy.deepcopy(blocked_scan) for _ in range(5)],
            ),
            mock.patch.object(run_recipe.psutil, "virtual_memory", return_value=memory),
            mock.patch.object(run_recipe.time, "sleep"),
        ):
            with self.assertRaises(run_recipe.PreflightError) as caught:
                run_recipe.check_gpu_idle()
        message = str(caught.exception)
        self.assertIn("redacted_blocking_processes", message)
        self.assertIn('"matched_markers":["run_recipe.py"]', message)
        self.assertIn('"argv_sha256":"', message)
        self.assertNotIn("SECRET_VALUE", message)
        self.assertEqual(message.count('"pid":777'), 1)

    def test_process_scan_excludes_only_exact_current_runner_pid(self):
        runner_path = str(Path(run_recipe.__file__).resolve())
        exclusion = self.runner_exclusion()
        current = SimpleNamespace(
            info={
                "pid": 100,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [sys.executable, runner_path],
                "create_time": 50.0,
            }
        )
        duplicate = SimpleNamespace(
            info={
                "pid": 101,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [sys.executable, runner_path],
                "create_time": 51.0,
            }
        )
        with mock.patch.object(
            run_recipe.psutil, "process_iter", return_value=[current, duplicate]
        ):
            scan = run_recipe._idle_forbidden_process_scan(exclusion)
        self.assertEqual([row["pid"] for row in scan["excluded_current_runner"]], [100])
        self.assertEqual([row["pid"] for row in scan["blocking_processes"]], [101])
        self.assertEqual(
            scan["blocking_processes"][0]["matched_markers"], ["run_recipe.py"]
        )
        self.assertNotIn("command_line", scan["blocking_processes"][0])

    def test_windows_venv_launcher_proof_and_retained_validator_are_narrow(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "venv"
            prefix.mkdir()
            (prefix / "pyvenv.cfg").write_text("home = mocked\n", encoding="utf-8")
            exclusion = self.runner_exclusion_with_launcher(prefix)
            child_identity = copy.deepcopy(exclusion["process_identity"])
            launcher_identity = copy.deepcopy(
                exclusion["verified_windows_venv_launcher"]["process_identity"]
            )
            child_process = SimpleNamespace(ppid=lambda: 228)
            with (
                mock.patch.object(run_recipe.os, "name", "nt"),
                mock.patch.object(run_recipe.sys, "prefix", str(prefix)),
                mock.patch.object(
                    run_recipe.sys, "base_prefix", str(prefix / "base-runtime")
                ),
                mock.patch.object(run_recipe.os, "getppid", return_value=228),
                mock.patch.object(
                    run_recipe,
                    "_idle_process_identity",
                    return_value=launcher_identity,
                ),
                mock.patch.object(
                    run_recipe.psutil, "Process", return_value=child_process
                ),
                mock.patch.object(
                    run_recipe.lab_locks,
                    "process_identity_is_live",
                    return_value=True,
                ),
            ):
                observed = run_recipe._idle_verified_current_windows_venv_launcher(
                    child_identity
                )
                self.assertEqual(
                    observed, exclusion["verified_windows_venv_launcher"]
                )
                excluded_rows = [
                    {
                        "pid": 100,
                        "process_create_time": 50.0,
                        "reason": "exact current run_recipe process",
                    },
                    {
                        "pid": 228,
                        "process_create_time": 49.0,
                        "reason": (
                            "exact verified direct Windows venv launcher stub"
                        ),
                    },
                ]
                self.assertEqual(
                    run_recipe.current_runner_exclusion_validation_errors(
                        exclusion, excluded_rows
                    ),
                    [],
                )

                wrong_child = copy.deepcopy(exclusion)
                wrong_child["verified_windows_venv_launcher"][
                    "direct_child_pid"
                ] = 999
                self.assertTrue(
                    run_recipe.current_runner_exclusion_validation_errors(wrong_child)
                )
                forged_row = copy.deepcopy(excluded_rows)
                forged_row[1]["reason"] = "arbitrary ancestor"
                self.assertIn(
                    "excluded current runner rows are not exact",
                    run_recipe.current_runner_exclusion_validation_errors(
                        exclusion, forged_row
                    ),
                )

    @unittest.skipUnless(os.name == "nt", "Windows venv launcher behavior")
    def test_cold_scan_excludes_one_verified_launcher_but_blocks_other_ancestor(self):
        if sys.prefix == sys.base_prefix:
            self.skipTest("test interpreter is not running from a virtual environment")
        exclusion = self.runner_exclusion_with_launcher()

        def process_row(identity):
            return SimpleNamespace(
                info={
                    "pid": identity["pid"],
                    "name": identity["name"],
                    "exe": identity["executable"],
                    "cmdline": list(identity["command_line"]),
                    "create_time": identity["process_create_time"],
                }
            )

        unrelated_ancestor = SimpleNamespace(
            info={
                "pid": 227,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [
                    sys.executable,
                    str(Path(run_recipe.__file__).resolve()),
                ],
                "create_time": 48.0,
            }
        )
        child_process = SimpleNamespace(ppid=lambda: 228)
        with (
            mock.patch.object(
                run_recipe.psutil,
                "process_iter",
                return_value=[
                    process_row(exclusion["process_identity"]),
                    process_row(
                        exclusion["verified_windows_venv_launcher"][
                            "process_identity"
                        ]
                    ),
                    unrelated_ancestor,
                ],
            ),
            mock.patch.object(
                run_recipe.psutil, "Process", return_value=child_process
            ),
            mock.patch.object(
                run_recipe.lab_locks,
                "process_identity_is_live",
                return_value=True,
            ),
        ):
            scan = run_recipe._idle_forbidden_process_scan(exclusion)
        self.assertEqual(
            {row["pid"] for row in scan["excluded_current_runner"]}, {100, 228}
        )
        self.assertEqual([row["pid"] for row in scan["blocking_processes"]], [227])
        self.assertEqual(
            scan["blocking_processes"][0]["matched_markers"], ["run_recipe.py"]
        )

    @unittest.skipUnless(os.name == "nt", "Windows venv launcher behavior")
    def test_prequeue_scan_reproves_exact_launcher_and_rejects_other_ancestor(self):
        if sys.prefix == sys.base_prefix:
            self.skipTest("test interpreter is not running from a virtual environment")
        exclusion = self.runner_exclusion_with_launcher()
        evidence = self.collect_prequeue_scan_with_runner(exclusion)
        self.assertEqual(evidence["status"], "clean")
        self.assertEqual(
            {row["pid"] for row in evidence["excluded_current_runner"]}, {100, 228}
        )
        self.assertEqual(
            run_recipe.prequeue_known_workload_scan_validation_errors(
                evidence, self.server_instance, self.server_argv()
            ),
            [],
        )

        unrelated_ancestor = SimpleNamespace(
            info={
                "pid": 227,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [
                    sys.executable,
                    str(Path(run_recipe.__file__).resolve()),
                ],
                "create_time": 48.0,
            }
        )
        with self.assertRaises(run_recipe.PreflightError) as caught:
            self.collect_prequeue_scan_with_runner(exclusion, [unrelated_ancestor])
        self.assertIn('"pid":227', str(caught.exception))
        self.assertNotIn("cmdline", str(caught.exception))

    def test_owned_server_venv_launcher_proof_and_validator_are_narrow(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "venv"
            prefix.mkdir()
            (prefix / "pyvenv.cfg").write_text("home = mocked\n", encoding="utf-8")
            exclusion = self.server_exclusion_with_launcher(prefix)
            child_identity = copy.deepcopy(exclusion["process_identity"])
            launcher_identity = copy.deepcopy(
                exclusion["verified_windows_venv_launcher"]["process_identity"]
            )

            def identity_for(pid):
                if int(pid) == 1234:
                    return copy.deepcopy(child_identity)
                if int(pid) == 37248:
                    return copy.deepcopy(launcher_identity)
                raise AssertionError(f"unexpected mocked identity PID {pid}")

            serving_process = SimpleNamespace(ppid=lambda: 37248)
            with (
                mock.patch.object(run_recipe.os, "name", "nt"),
                mock.patch.object(run_recipe.sys, "prefix", str(prefix)),
                mock.patch.object(
                    run_recipe.sys, "base_prefix", str(prefix / "base-runtime")
                ),
                mock.patch.object(run_recipe.os, "getpid", return_value=100),
                mock.patch.object(
                    run_recipe, "_idle_process_identity", side_effect=identity_for
                ),
                mock.patch.object(
                    run_recipe.psutil, "Process", return_value=serving_process
                ),
                mock.patch.object(
                    run_recipe.lab_locks,
                    "process_identity_is_live",
                    return_value=True,
                ),
            ):
                observed_launcher = (
                    run_recipe._prequeue_verified_owned_server_windows_venv_launcher(
                        child_identity, self.server_argv()
                    )
                )
                self.assertEqual(
                    observed_launcher,
                    exclusion["verified_windows_venv_launcher"],
                )
                observed_exclusion = run_recipe._prequeue_owned_server_exclusion(
                    self.server_instance, self.server_argv()
                )
                self.assertEqual(observed_exclusion, exclusion)
                excluded_rows = [
                    {
                        "pid": 1234,
                        "process_create_time": 5678.0,
                        "reason": (
                            "exact owned port-8199 server PID/create-time/argv"
                        ),
                    },
                    {
                        "pid": 37248,
                        "process_create_time": 5677.0,
                        "reason": (
                            "exact verified direct Windows venv owned-server "
                            "launcher stub"
                        ),
                    },
                ]
                self.assertEqual(
                    run_recipe.owned_lab_server_exclusion_validation_errors(
                        exclusion,
                        self.server_instance,
                        self.server_argv(),
                        excluded_rows,
                    ),
                    [],
                )

                wrong_child = copy.deepcopy(exclusion)
                wrong_child["verified_windows_venv_launcher"][
                    "direct_child_pid"
                ] = 999
                self.assertTrue(
                    run_recipe.owned_lab_server_exclusion_validation_errors(
                        wrong_child, self.server_instance, self.server_argv()
                    )
                )
                wrong_path = copy.deepcopy(exclusion)
                wrong_path["verified_windows_venv_launcher"][
                    "expected_launcher_path"
                ] = str(prefix / "Scripts" / "other-python.exe")
                self.assertIn(
                    "owned-server Windows venv launcher path is wrong",
                    run_recipe.owned_lab_server_exclusion_validation_errors(
                        wrong_path, self.server_instance, self.server_argv()
                    ),
                )
                wrong_tail = copy.deepcopy(exclusion)
                wrong_tail["verified_windows_venv_launcher"]["process_identity"][
                    "command_line"
                ][-1] = str(ROOT / "wrong-output")
                self.assertIn(
                    "owned-server Windows venv launcher argv tail differs from child",
                    run_recipe.owned_lab_server_exclusion_validation_errors(
                        wrong_tail, self.server_instance, self.server_argv()
                    ),
                )
                wrong_delta = copy.deepcopy(exclusion)
                wrong_delta["verified_windows_venv_launcher"][
                    "creation_delta_s"
                ] = 4.0
                self.assertIn(
                    "owned-server Windows venv launcher creation delta is invalid",
                    run_recipe.owned_lab_server_exclusion_validation_errors(
                        wrong_delta, self.server_instance, self.server_argv()
                    ),
                )
                forged_rows = copy.deepcopy(excluded_rows)
                forged_rows[1]["reason"] = "arbitrary main.py ancestor"
                self.assertIn(
                    "excluded owned lab server rows are not exact",
                    run_recipe.owned_lab_server_exclusion_validation_errors(
                        exclusion,
                        self.server_instance,
                        self.server_argv(),
                        forged_rows,
                    ),
                )
                contract = run_recipe.prequeue_known_workload_scan_contract()
                self.assertEqual(
                    contract["owned_lab_server_exclusion_schema"],
                    list(run_recipe.PREQUEUE_OWNED_SERVER_EXCLUSION_SCHEMA),
                )
                self.assertEqual(
                    contract[
                        "verified_owned_server_windows_venv_launcher_schema"
                    ],
                    list(
                        run_recipe.PREQUEUE_VERIFIED_SERVER_VENV_LAUNCHER_SCHEMA
                    ),
                )

    @unittest.skipUnless(os.name == "nt", "Windows venv launcher behavior")
    def test_prequeue_excludes_owned_server_launcher_but_blocks_other_main_ancestor(self):
        if sys.prefix == sys.base_prefix:
            self.skipTest("test interpreter is not running from a virtual environment")
        exclusion = self.server_exclusion_with_launcher()
        evidence = self.collect_prequeue_scan_with_server(exclusion)
        self.assertEqual(evidence["status"], "clean")
        self.assertEqual(
            {row["pid"] for row in evidence["excluded_owned_lab_server"]},
            {1234, 37248},
        )
        self.assertEqual(
            run_recipe.prequeue_known_workload_scan_validation_errors(
                evidence, self.server_instance, self.server_argv()
            ),
            [],
        )

        unrelated_ancestor = SimpleNamespace(
            info={
                "pid": 37247,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [sys.executable, *self.server_argv()],
                "create_time": 5676.0,
            }
        )
        with self.assertRaises(run_recipe.PreflightError) as caught:
            self.collect_prequeue_scan_with_server(exclusion, [unrelated_ancestor])
        message = str(caught.exception)
        self.assertIn('"pid":37247', message)
        self.assertIn('"matched_markers":["main.py"]', message)
        self.assertNotIn("cmdline", message)

    def test_shared_classifier_matches_only_positive_targets(self):
        for target, marker in (
            (r"C:\foreign\run_recipe.py", "run_recipe.py"),
            (r"C:\foreign\main.py", "main.py"),
            (r"C:\tools\eng_wan_cost_probe.py", "eng_wan_"),
        ):
            with self.subTest(target=target):
                result = run_recipe.classify_known_workload_process(
                    {
                        "pid": 700,
                        "name": "python.exe",
                        "exe": sys.executable,
                        "cmdline": [sys.executable, "-I", "-X", "dev", target],
                        "create_time": 1.0,
                    }
                )
                self.assertEqual(
                    result["classification"], "blocking_positive_known_workload"
                )
                self.assertIn(marker, result["redacted_process"]["matched_markers"])
                self.assertEqual(
                    len(result["redacted_process"]["argv_sha256"]), 64
                )
                self.assertNotIn("command_line", result["redacted_process"])

        module = run_recipe.classify_known_workload_process(
            {
                "pid": 701,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [sys.executable, "-m", "vllm.entrypoints.api_server"],
                "create_time": 1.0,
            }
        )
        self.assertIn("vllm", module["redacted_process"]["matched_markers"])

    def test_shared_classifier_ignores_marker_text_in_later_data_arguments(self):
        python_review = run_recipe.classify_known_workload_process(
            {
                "pid": 702,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [
                    sys.executable,
                    r"C:\tools\harmless.py",
                    "--review",
                    r"C:\foreign\run_recipe.py",
                    "--prompt",
                    "minimax",
                ],
                "create_time": 1.0,
            }
        )
        self.assertEqual(
            python_review["classification"],
            "advisory_unreadable_or_unmatched_python",
        )
        self.assertEqual(python_review["redacted_process"]["matched_markers"], [])
        self.assertFalse(
            run_recipe._idle_command_line_has_exact_runner(
                [
                    sys.executable,
                    r"C:\tools\harmless.py",
                    str(Path(run_recipe.__file__).resolve()),
                ]
            )
        )
        self.assertTrue(
            run_recipe._idle_command_line_has_exact_runner(
                [sys.executable, str(Path(run_recipe.__file__).resolve())]
            )
        )
        nonpython_review = run_recipe.classify_known_workload_process(
            {
                "pid": 703,
                "name": "reviewer.exe",
                "exe": r"C:\tools\reviewer.exe",
                "cmdline": ["reviewer.exe", "--text", "vllm minimax run_recipe.py"],
                "create_time": 1.0,
            }
        )
        self.assertEqual(nonpython_review["classification"], "clear")

    def test_unreadable_python_is_retained_as_non_gating_advisory(self):
        current = SimpleNamespace(
            info={
                "pid": 100,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [sys.executable, str(Path(run_recipe.__file__).resolve())],
                "create_time": 50.0,
            }
        )
        unreadable = SimpleNamespace(
            info={
                "pid": 704,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": None,
                "create_time": 2.0,
            }
        )
        with mock.patch.object(
            run_recipe.psutil, "process_iter", return_value=[current, unreadable]
        ):
            scan = run_recipe._idle_forbidden_process_scan(self.runner_exclusion())
        self.assertEqual(scan["blocking_processes"], [])
        self.assertEqual(len(scan["advisory_unreadable_processes"]), 1)
        advisory = scan["advisory_unreadable_processes"][0]
        self.assertEqual(advisory["matched_markers"], [])
        self.assertNotIn("command_line", advisory)
        self.assertFalse(
            run_recipe.prequeue_known_workload_scan_contract()[
                "python_without_readable_argv_blocks"
            ]
        )
        positive_advisory = copy.deepcopy(advisory)
        positive_advisory["matched_markers"] = ["main.py"]
        self.assertTrue(
            run_recipe.redacted_workload_process_validation_errors(
                positive_advisory, "advisory"
            )
        )
        leaked_path = copy.deepcopy(advisory)
        leaked_path["target_basename"] = r"C:\secret\harmless.py"
        self.assertTrue(
            any(
                "leaks a path" in error
                for error in run_recipe.redacted_workload_process_validation_errors(
                    leaked_path, "advisory"
                )
            )
        )

    def test_wddm_process_row_requires_unmetered_desktop_identity(self):
        row = {
            "gpu_uuid": "GPU-TEST",
            "pid": 10,
            "nvidia_process_name": "dwm.exe",
            "used_gpu_memory_token": "[N/A]",
        }
        identity = {
            "pid": 10,
            "exists": True,
            "name": "dwm.exe",
            "executable": r"C:\Windows\System32\dwm.exe",
            "command_line": [r"C:\Windows\System32\dwm.exe"],
            "process_create_time": 1.0,
            "identity_errors": [],
        }
        allowed = run_recipe._idle_classify_process_row(row, "GPU-TEST", identity)
        self.assertEqual(
            allowed["classification"], "allowed_unmetered_wddm_desktop_client"
        )
        numeric = run_recipe._idle_classify_process_row(
            {**row, "used_gpu_memory_token": "25"}, "GPU-TEST", identity
        )
        self.assertEqual(numeric["classification"], "blocked")

    def test_unmetered_streamdeck_style_client_without_signal_is_allowed(self):
        row = {
            "gpu_uuid": "GPU-TEST",
            "pid": 20,
            "nvidia_process_name": "StreamDeck.exe",
            "used_gpu_memory_token": "[N/A]",
        }
        identity = {
            "pid": 20,
            "exists": True,
            "name": "StreamDeck.exe",
            "executable": r"C:\Program Files\Elgato\StreamDeck\StreamDeck.exe",
            "command_line": [
                r"C:\Program Files\Elgato\StreamDeck\StreamDeck.exe"
            ],
            "process_create_time": 123.0,
            "identity_errors": [],
        }
        allowed = run_recipe._idle_classify_process_row(row, "GPU-TEST", identity)
        self.assertEqual(allowed["desktop_graphics_signals"], [])
        self.assertEqual(
            allowed["desktop_signal_status"], "unrecognized-non-workload-client"
        )
        self.assertEqual(
            allowed["classification"], "allowed_unmetered_wddm_desktop_client"
        )
        self.assertEqual(allowed["blocking_reasons"], [])

    def test_unmetered_known_workload_and_missing_live_identity_still_block(self):
        row = {
            "gpu_uuid": "GPU-TEST",
            "pid": 21,
            "nvidia_process_name": "python.exe",
            "used_gpu_memory_token": "[N/A]",
        }
        known_workload = {
            "pid": 21,
            "exists": True,
            "name": "python.exe",
            "executable": sys.executable,
            "command_line": [sys.executable, "minimax_worker.py"],
            "process_create_time": 124.0,
            "identity_errors": [],
        }
        blocked = run_recipe._idle_classify_process_row(
            row, "GPU-TEST", known_workload
        )
        self.assertEqual(blocked["classification"], "blocked")
        self.assertTrue(
            any("positive known workload" in reason for reason in blocked["blocking_reasons"])
        )

        missing_create_time = copy.deepcopy(known_workload)
        missing_create_time["command_line"] = [sys.executable, "desktop_helper.py"]
        missing_create_time["process_create_time"] = None
        blocked = run_recipe._idle_classify_process_row(
            row, "GPU-TEST", missing_create_time
        )
        self.assertEqual(blocked["classification"], "blocked")
        self.assertIn(
            "NVIDIA process create time is unavailable", blocked["blocking_reasons"]
        )

    def test_vram_receipt_fields_stamp_strict_boundary_and_compute_net(self):
        standard = run_recipe.vram_receipt_fields(2.0, 12.125)
        self.assertFalse(standard["elevated_baseline_lane"])
        self.assertIsNone(standard["baseline_lane_stamp"])
        self.assertEqual(standard["absolute_peak_vram_gb"], 12.125)
        self.assertEqual(standard["net_peak_vram_gb"], 10.125)

        elevated = run_recipe.vram_receipt_fields(2.001, 12.126)
        self.assertTrue(elevated["elevated_baseline_lane"])
        self.assertEqual(
            elevated["baseline_lane_stamp"],
            "elevated-baseline lane, operator-authorized 2026-08-10",
        )
        self.assertEqual(elevated["net_peak_vram_gb"], 10.125)
        self.assertEqual(
            elevated["vram_measurement"]["net_peak_gib"],
            elevated["absolute_peak_vram_gb"] - elevated["baseline_vram_gb"],
        )
        self.assertEqual(
            run_recipe.operator_idle_policy_contract()[
                "preboot_baseline_maximum_mib"
            ],
            3072.0,
        )

    def test_prequeue_baseline_is_gating_while_pair_drift_is_advisory(self):
        at_threshold = run_recipe.prompt_baseline_advisory(3.0)
        self.assertFalse(at_threshold["threshold_exceeded"])
        self.assertTrue(at_threshold["gating"])
        over_threshold = run_recipe.prompt_baseline_advisory(3.001)
        self.assertTrue(over_threshold["threshold_exceeded"])
        self.assertTrue(over_threshold["gating"])
        self.assertEqual(over_threshold["disposition"], "abort before prompt")

        previous = {"baseline_vram_gb": 2.0}
        at_drift = run_recipe.pair_baseline_drift_advisory(2.5, previous, 2)
        self.assertEqual(at_drift["absolute_drift_gb"], 0.5)
        self.assertFalse(at_drift["threshold_exceeded"])
        over_drift = run_recipe.pair_baseline_drift_advisory(2.501, previous, 2)
        self.assertEqual(over_drift["absolute_drift_gb"], 0.501)
        self.assertTrue(over_drift["threshold_exceeded"])
        self.assertFalse(over_drift["gating"])
        # Cold/config-reset legs have no prior same-identity baseline to compare.
        cold = run_recipe.pair_baseline_drift_advisory(3.9, {}, 1)
        self.assertFalse(cold["applicable"])
        self.assertFalse(cold["gating"])

        policy = run_recipe.operator_idle_policy_contract()
        self.assertTrue(policy["preboot_baseline_threshold_gating"])
        self.assertFalse(policy["pair_drift_threshold_gating"])

    def test_cold_race_prequeue_scan_blocks_workload_started_after_preboot(self):
        raced_workload = SimpleNamespace(
            info={
                "pid": 300,
                "name": "python.exe",
                "exe": sys.executable,
                "cmdline": [
                    sys.executable,
                    "minimax_worker.py",
                    "--token",
                    "PREQUEUE_SECRET",
                ],
                "create_time": 200.0,
            }
        )
        with self.assertRaises(run_recipe.PreflightError) as caught:
            self.collect_prequeue_scan([raced_workload])
        message = str(caught.exception)
        self.assertIn("redacted_blocking_processes", message)
        self.assertNotIn("PREQUEUE_SECRET", message)
        self.assertRegex(message, r'"argv_sha256":"[0-9a-f]{64}"')
        source = inspect.getsource(run_recipe.main)
        self.assertLess(
            source.index("collect_prequeue_known_workload_scan"),
            source.index("urllib.request.urlopen(req)"),
        )

    def test_warm_leg_prequeue_scan_reproves_exclusions_and_retains_evidence(self):
        desktop_client = SimpleNamespace(
            info={
                "pid": 301,
                "name": "StreamDeck.exe",
                "exe": r"C:\Program Files\Elgato\StreamDeck\StreamDeck.exe",
                "cmdline": [
                    r"C:\Program Files\Elgato\StreamDeck\StreamDeck.exe"
                ],
                "create_time": 201.0,
            }
        )
        evidence = self.collect_prequeue_scan([desktop_client])
        self.assertEqual(evidence["status"], "clean")
        self.assertTrue(evidence["scan_ran"])
        self.assertEqual(evidence["blocking_processes"], [])
        self.assertEqual(len(evidence["excluded_current_runner"]), 1)
        self.assertEqual(len(evidence["excluded_owned_lab_server"]), 1)
        self.assertTrue(evidence["contract"]["warm_leg_scan_required"])
        self.assertEqual(
            run_recipe.prequeue_known_workload_scan_validation_errors(
                evidence, self.server_instance, self.server_argv()
            ),
            [],
        )

        tampered = copy.deepcopy(evidence)
        tampered["excluded_owned_lab_server"][0]["pid"] = 999
        self.assertIn(
            "prequeue workload scan evidence SHA-256 is invalid",
            run_recipe.prequeue_known_workload_scan_validation_errors(
                tampered, self.server_instance, self.server_argv()
            ),
        )


class IdleGatePlumbingTests(unittest.TestCase):
    server_instance = WddmIdleGateTests.server_instance
    runner_exclusion = staticmethod(WddmIdleGateTests.runner_exclusion)
    listener_evidence = staticmethod(WddmIdleGateTests.listener_evidence)
    target_gpu = staticmethod(WddmIdleGateTests.target_gpu)
    activity = staticmethod(WddmIdleGateTests.activity)
    process_evidence = staticmethod(WddmIdleGateTests.process_evidence)
    lock_evidence = staticmethod(WddmIdleGateTests.lock_evidence)
    forbidden_scan = WddmIdleGateTests.forbidden_scan
    measured_evidence = WddmIdleGateTests.measured_evidence

    def test_run_all_preflights_returns_receipt_idle_evidence_separately(self):
        marker = run_recipe._idle_owned_server_reuse_evidence(self.server_instance)
        sidecar = {
            "path": str(run_recipe.SERVER_IDLE_GATE_FILE.resolve()),
            "bytes": 1,
            "sha256": "e" * 64,
            "identity": [1, 2, 3, 1, 1, 4],
            "evidence_sha256": "f" * 64,
            "server_instance": copy.deepcopy(self.server_instance),
        }
        stats = {
            "system": {"argv": ["main.py", "--port", "8199"]},
            run_recipe.GPU_IDLE_INTERNAL_STATS_KEY: marker,
            run_recipe.GPU_IDLE_SIDECAR_INTERNAL_STATS_KEY: sidecar,
        }
        with (
            mock.patch.object(
                run_recipe, "check_server_up_and_ownership", return_value=stats
            ),
            mock.patch.object(run_recipe, "fetch_object_info", return_value={}),
            mock.patch.object(run_recipe, "check_nodes_exist"),
            mock.patch.object(run_recipe, "check_models_exist"),
            mock.patch.object(run_recipe, "check_installed_schema_contract"),
            mock.patch.object(run_recipe, "check_widget_integrity"),
            mock.patch.object(run_recipe, "check_affordability"),
            mock.patch.object(
                run_recipe, "check_fixtures_uploaded", return_value=({}, {})
            ),
            mock.patch.object(
                run_recipe,
                "check_boot_lane",
                return_value={"enabled": False, "default_manager_disabled": True},
            ),
            mock.patch.object(run_recipe, "check_disk_space"),
        ):
            returned = run_recipe.run_all_preflights(
                ROOT / "recipes" / "placeholder.json",
                {"prompt": {}},
                "placeholder",
                "a" * 64,
                "lab-8199, sage-free",
            )
        self.assertEqual(returned[4], marker)
        self.assertEqual(returned[5], sidecar)
        self.assertNotIn(run_recipe.GPU_IDLE_INTERNAL_STATS_KEY, returned[0])
        self.assertNotIn(run_recipe.GPU_IDLE_SIDECAR_INTERNAL_STATS_KEY, returned[0])

    def test_existing_owned_server_returns_reuse_marker_without_resampling(self):
        stats = {"system": {"argv": ["main.py", "--port", "8199"]}}
        sidecar = {
            "metadata": {
                "path": str(run_recipe.SERVER_IDLE_GATE_FILE.resolve()),
                "server_instance": copy.deepcopy(self.server_instance),
            }
        }
        with (
            mock.patch.object(run_recipe, "cleanup_stale_pid_receipt"),
            mock.patch.object(run_recipe, "query_server_stats", return_value=stats),
            mock.patch.object(run_recipe, "get_recorded_pid", return_value=1234),
            mock.patch.object(run_recipe, "listener_pid", return_value=1234),
            mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
            mock.patch.object(run_recipe, "ensure_queue_idle"),
            mock.patch.object(
                run_recipe,
                "verified_server_instance",
                return_value=self.server_instance,
            ),
            mock.patch.object(
                run_recipe,
                "snapshot_server_idle_gate_sidecar",
                return_value=sidecar,
            ),
            mock.patch.object(run_recipe, "check_gpu_idle") as idle,
            mock.patch.object(run_recipe, "boot_lab_server") as boot,
        ):
            retained = run_recipe.check_server_up_and_ownership("recipe")
        marker = retained[run_recipe.GPU_IDLE_INTERNAL_STATS_KEY]
        self.assertEqual(marker["status"], "not-rerun-owned-server-reuse")
        self.assertEqual(
            retained[run_recipe.GPU_IDLE_SIDECAR_INTERNAL_STATS_KEY],
            sidecar["metadata"],
        )
        idle.assert_not_called()
        boot.assert_not_called()

    def test_cold_server_boot_binds_measured_gate_to_server_instance(self):
        measured = self.measured_evidence()
        measured.pop("server_instance")
        measured.pop("evidence_sha256")
        stats = {"system": {"argv": ["main.py", "--port", "8199"]}}
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(
                    run_recipe, "SERVER_PID_FILE", Path(tmp) / ".server.pid"
                ),
                mock.patch.object(
                    run_recipe,
                    "SERVER_IDLE_GATE_FILE",
                    Path(tmp) / ".server.idle-gate.json",
                ),
                mock.patch.object(run_recipe, "cleanup_stale_pid_receipt"),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "get_recorded_pid", return_value=None),
                mock.patch.object(run_recipe, "check_gpu_idle", return_value=measured),
                mock.patch.object(run_recipe, "boot_lab_server", return_value=stats),
                mock.patch.object(
                    run_recipe,
                    "verified_server_instance",
                    return_value=self.server_instance,
                ),
                mock.patch.object(run_recipe, "ensure_queue_idle"),
            ):
                retained = run_recipe.check_server_up_and_ownership("recipe")
        evidence = retained[run_recipe.GPU_IDLE_INTERNAL_STATS_KEY]
        self.assertEqual(evidence["status"], "measured")
        self.assertEqual(evidence["server_instance"], self.server_instance)
        self.assertEqual(
            run_recipe.gpu_idle_gate_validation_errors(
                evidence, self.server_instance
            ),
            [],
        )


class IdleGateSidecarLifecycleTests(unittest.TestCase):
    server_instance = WddmIdleGateTests.server_instance
    runner_exclusion = staticmethod(WddmIdleGateTests.runner_exclusion)
    listener_evidence = staticmethod(WddmIdleGateTests.listener_evidence)
    target_gpu = staticmethod(WddmIdleGateTests.target_gpu)
    activity = staticmethod(WddmIdleGateTests.activity)
    process_evidence = staticmethod(WddmIdleGateTests.process_evidence)
    lock_evidence = staticmethod(WddmIdleGateTests.lock_evidence)
    forbidden_scan = WddmIdleGateTests.forbidden_scan
    measured_evidence = WddmIdleGateTests.measured_evidence

    def test_sidecar_is_exclusive_canonical_and_revalidated(self):
        evidence = self.measured_evidence()
        with tempfile.TemporaryDirectory() as tmp:
            sidecar_path = Path(tmp) / ".server.idle-gate.json"
            with mock.patch.object(
                run_recipe, "SERVER_IDLE_GATE_FILE", sidecar_path
            ):
                created = run_recipe.create_server_idle_gate_sidecar(evidence)
                retained = run_recipe.snapshot_server_idle_gate_sidecar(
                    self.server_instance
                )
                self.assertEqual(created["evidence"], evidence)
                self.assertEqual(retained["raw"], run_recipe._server_idle_gate_bytes(evidence))
                self.assertEqual(
                    retained["metadata"]["sha256"],
                    run_recipe.sha256_bytes(retained["raw"]),
                )
                with self.assertRaises(run_recipe.ServerIdleGateSidecarError):
                    run_recipe.create_server_idle_gate_sidecar(evidence)
                sidecar_path.write_bytes(retained["raw"] + b"\n")
                with self.assertRaises(run_recipe.ServerIdleGateSidecarError):
                    run_recipe.snapshot_server_idle_gate_sidecar(
                        self.server_instance
                    )

    def test_existing_owned_server_without_sidecar_is_refused(self):
        stats = {"system": {"argv": ["main.py", "--port", "8199"]}}
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(
                    run_recipe,
                    "SERVER_IDLE_GATE_FILE",
                    Path(tmp) / ".server.idle-gate.json",
                ),
                mock.patch.object(run_recipe, "cleanup_stale_pid_receipt"),
                mock.patch.object(run_recipe, "query_server_stats", return_value=stats),
                mock.patch.object(run_recipe, "get_recorded_pid", return_value=1234),
                mock.patch.object(run_recipe, "listener_pid", return_value=1234),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
                mock.patch.object(run_recipe, "ensure_queue_idle"),
                mock.patch.object(
                    run_recipe,
                    "verified_server_instance",
                    return_value=self.server_instance,
                ),
                mock.patch.object(run_recipe, "check_gpu_idle") as idle,
                mock.patch.object(run_recipe, "boot_lab_server") as boot,
            ):
                with self.assertRaisesRegex(
                    run_recipe.PreflightError, "no valid persisted cold idle gate"
                ):
                    run_recipe.check_server_up_and_ownership("recipe")
            idle.assert_not_called()
            boot.assert_not_called()

    def test_successful_shutdown_removes_exact_sidecar_and_pid_receipt(self):
        evidence = run_recipe._idle_finalize_evidence(
            self.measured_evidence(),
            {"serving_pid": 123, "process_create_time": 50.0},
        )
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            sidecar = Path(tmp) / ".server.idle-gate.json"
            receipt.write_text("123", encoding="utf-8")
            alive = {"value": True}
            process = mock.Mock()
            process.create_time.return_value = 50.0

            def terminate(_pid):
                alive["value"] = False
                return True

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", sidecar),
            ):
                run_recipe.create_server_idle_gate_sidecar(evidence)
                with (
                    mock.patch.object(
                        run_recipe.psutil,
                        "pid_exists",
                        side_effect=lambda _pid: alive["value"],
                    ),
                    mock.patch.object(run_recipe.psutil, "Process", return_value=process),
                    mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
                    mock.patch.object(
                        run_recipe,
                        "listener_pid",
                        side_effect=lambda _port, **_kwargs: 123 if alive["value"] else None,
                    ),
                    mock.patch.object(
                        run_recipe,
                        "query_server_stats",
                        side_effect=lambda: {} if alive["value"] else None,
                    ),
                    mock.patch.object(
                        run_recipe, "terminate_owned_process_tree", side_effect=terminate
                    ),
                ):
                    result = run_recipe.shutdown_lab_server()
            self.assertTrue(result["success"])
            self.assertTrue(result["idle_gate_sidecar_validated"])
            self.assertTrue(result["idle_gate_sidecar_removed"])
            self.assertTrue(result["receipt_removed"])
            self.assertFalse(receipt.exists())
            self.assertFalse(sidecar.exists())

    def test_stale_cleanup_removes_bound_sidecar_and_pid_receipt(self):
        evidence = run_recipe._idle_finalize_evidence(
            self.measured_evidence(),
            {"serving_pid": 123, "process_create_time": 50.0},
        )
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            sidecar = Path(tmp) / ".server.idle-gate.json"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", sidecar),
            ):
                run_recipe.create_server_idle_gate_sidecar(evidence)
                with (
                    mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                    mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                    mock.patch.object(run_recipe, "listener_pid", return_value=None),
                ):
                    removed = run_recipe.cleanup_stale_pid_receipt()
            self.assertTrue(removed)
            self.assertFalse(receipt.exists())
            self.assertFalse(sidecar.exists())

    def test_stale_cleanup_refuses_missing_mandatory_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            sidecar = Path(tmp) / ".server.idle-gate.json"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", sidecar),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
            ):
                result = run_recipe.shutdown_lab_server()
            self.assertFalse(result["success"])
            self.assertIn("no mandatory server idle-gate sidecar", result["reason"])
            self.assertTrue(receipt.exists())
            self.assertFalse(sidecar.exists())

    def test_live_cleanup_refuses_missing_mandatory_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            sidecar = Path(tmp) / ".server.idle-gate.json"
            receipt.write_text("123", encoding="utf-8")
            process = mock.Mock()
            process.create_time.return_value = 50.0
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", sidecar),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=True),
                mock.patch.object(run_recipe.psutil, "Process", return_value=process),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()
            self.assertFalse(result["success"])
            self.assertIn("no mandatory server idle-gate sidecar", result["reason"])
            self.assertTrue(receipt.exists())
            self.assertFalse(sidecar.exists())
            terminate.assert_not_called()

    def test_orphan_sidecar_without_pid_receipt_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            sidecar = Path(tmp) / ".server.idle-gate.json"
            sidecar.write_bytes(b"{}\n")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", sidecar),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
            ):
                result = run_recipe.shutdown_lab_server()
            self.assertFalse(result["success"])
            self.assertIn("orphan .server.idle-gate.json", result["reason"])
            self.assertTrue(sidecar.exists())

    def test_boot_failure_removes_receipt_only_when_no_sidecar_appears(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot_cmd = root / "boot.cmd"
            boot_cmd.write_bytes(b"@echo off\r\n")
            receipt = root / ".server.pid"
            sidecar = root / ".server.idle-gate.json"
            proc = SimpleNamespace(pid=123)
            with (
                mock.patch.object(run_recipe, "BOOT_CMD", boot_cmd),
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", sidecar),
                mock.patch.object(run_recipe, "cleanup_stale_pid_receipt"),
                mock.patch.object(run_recipe, "manager_probe_requested", return_value=False),
                mock.patch.object(run_recipe.subprocess, "Popen", return_value=proc),
                mock.patch.object(
                    run_recipe, "query_server_stats", side_effect=RuntimeError("boot failed")
                ),
                mock.patch.object(
                    run_recipe, "terminate_owned_process_tree", return_value=True
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "boot failed"):
                    run_recipe.boot_lab_server("recipe")
            self.assertFalse(receipt.exists())
            self.assertFalse(sidecar.exists())

    def test_boot_failure_preserves_unexpected_sidecar_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot_cmd = root / "boot.cmd"
            boot_cmd.write_bytes(b"@echo off\r\n")
            receipt = root / ".server.pid"
            sidecar = root / ".server.idle-gate.json"
            proc = SimpleNamespace(pid=123)

            def fail_after_sidecar_appears():
                sidecar.write_bytes(b"unexpected\n")
                raise RuntimeError("boot failed")

            with (
                mock.patch.object(run_recipe, "BOOT_CMD", boot_cmd),
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", sidecar),
                mock.patch.object(run_recipe, "cleanup_stale_pid_receipt"),
                mock.patch.object(run_recipe, "manager_probe_requested", return_value=False),
                mock.patch.object(run_recipe.subprocess, "Popen", return_value=proc),
                mock.patch.object(
                    run_recipe,
                    "query_server_stats",
                    side_effect=fail_after_sidecar_appears,
                ),
                mock.patch.object(
                    run_recipe, "terminate_owned_process_tree", return_value=True
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "boot failed"):
                    run_recipe.boot_lab_server("recipe")
            self.assertTrue(receipt.exists())
            self.assertTrue(sidecar.exists())


if __name__ == "__main__":
    unittest.main()
