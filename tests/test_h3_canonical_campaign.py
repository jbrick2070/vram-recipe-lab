import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from scratch import run_h3_canonical_campaign as campaign


ROOT = Path(__file__).resolve().parents[1]


def clean_state():
    return {
        "gpu_lock_exists": False,
        "suite_lock_exists": False,
        "server_pid_receipt_exists": False,
        "server_pid_receipt": None,
        "server_pid_create_time": None,
        "queue_quarantine_exists": False,
        "idle_gate_sidecar_exists": False,
        "idle_gate_sidecar": None,
        "listener_pids_8199": [],
        "expected_server_identity_live": False,
    }


class H3CanonicalCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.temp = Path(self.temporary.name)
        self.results = self.temp / "results"
        self.outputs = self.temp / "outputs"
        self.results.mkdir()
        self.outputs.mkdir()
        self.actual_manager = self.temp / "actual_manager.ini"
        self.lab_manager = self.temp / "lab_manager.ini"
        offline = b"[default]\nnetwork_mode = offline\n"
        self.actual_manager.write_bytes(offline)
        self.lab_manager.write_bytes(offline)
        self.layout = campaign.Layout(
            root=ROOT,
            results=self.results,
            outputs=self.outputs,
            lifecycle=self.results / "h3_canonical_canvas_campaign" / "lifecycle.jsonl",
            runner=ROOT / "run_recipe.py",
            lab_locks=ROOT / "lab_locks.py",
            boot_cmd=ROOT / "boot_lab_server.cmd",
            actual_manager_config=self.actual_manager,
            lab_manager_config=self.lab_manager,
            actual_user_directory=campaign.ACTUAL_USER_DIRECTORY,
            python=campaign.PYTHON,
            gpu_lock=self.temp / ".gpu.lock",
            suite_lock=self.temp / ".suite.lock",
            server_pid=self.temp / ".server.pid",
            queue_quarantine=self.temp / ".queue.quarantine.json",
            idle_gate_sidecar=self.temp / ".server.idle-gate.json",
        )
        production_loader = campaign.load_runner_verifier

        def test_context_runner_loader(path):
            runner = production_loader(path)
            runner.REPO_ROOT = self.temp
            # These fixtures reconstruct the frozen canonical campaign's
            # runner contract.  The live runner has intentionally advanced
            # since that campaign and must reject its archived contract in
            # production; this unit fixture still needs to exercise the
            # archived campaign verifier's own invariant checks.
            current_validator = runner.gpu_idle_gate_validation_errors

            archived_only_errors = {
                "idle gate contract drifted",
                "sample 4 exceeds the 3072 MiB absolute baseline gate",
            }

            def archived_contract_validator(*args, **kwargs):
                return [
                    error
                    for error in current_validator(*args, **kwargs)
                    if error not in archived_only_errors
                ]

            runner.gpu_idle_gate_validation_errors = archived_contract_validator
            return runner

        self.runner_loader_patch = mock.patch.object(
            campaign,
            "load_runner_verifier",
            side_effect=test_context_runner_loader,
        )
        self.runner_loader_patch.start()
        self.addCleanup(self.runner_loader_patch.stop)
        self.specs = campaign.load_recipe_specs(self.layout)
        self.sources = campaign.source_evidence(self.layout)
        self.models = self._make_model_fingerprints()

    def tearDown(self):
        self.temporary.cleanup()

    def _make_model_fingerprints(self):
        directory = self.temp / "models"
        directory.mkdir()
        names = sorted(
            {name for spec in self.specs for name in campaign.recipe_model_names(spec)}
        )
        rows = {}
        for name in names:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("model:" + name).encode("utf-8"))
            model_stat = path.stat()
            rows[name] = {
                "resolved": True,
                "path": str(path),
                "bytes": model_stat.st_size,
                "mtime_ns": model_stat.st_mtime_ns,
            }
        return rows

    def _server_argv(self):
        return campaign.expected_server_argv(self.layout)

    def _nonce_identity(self, nonce):
        prefix, campaign_id, pair_text, role = nonce.split(":")
        self.assertEqual(prefix, "h3canon")
        self.assertIn(role, {"cold", "warm"})
        return campaign_id, int(pair_text.removeprefix("p")), role

    @staticmethod
    def _advisory_process(pid=777):
        return {
            "pid": pid,
            "process_create_time": 4567.25,
            "process_basename": "python.exe",
            "executable_basename": "python.exe",
            "target_basename": None,
            "matched_markers": [],
            "match_basis": ["advisory_python_without_positive_marker"],
            "argv_sha256": "5" * 64,
        }

    def _idle_contract(self):
        return {
            "schema_version": 1,
            "kind": "run-recipe-preboot-wddm-idle-gate-contract",
            "gpu_index": 0,
            "port": 8199,
            "sample_count": 5,
            "sampling_interval_s": 0.2,
            "aggregation": "maximum of five conjunctively quiescent WDDM samples",
            "policy": {
                "advisory_vram_used_mib": 3072.0,
                "vram_used_mib_threshold_gating": False,
                "operator_idle_policy": campaign.expected_operator_idle_policy(),
                "gpu_utilization_recorded_non_gating": True,
                "memory_utilization_recorded_non_gating": True,
                "recognized_unmetered_wddm_memory_token": "[N/A]",
                "numeric_or_unknown_process_memory_tokens_block": True,
                "live_process_identity_required": True,
                "desktop_graphics_signals_retained_but_not_required": True,
                "model_workload_markers": list(
                    campaign.EXPECTED_GPU_IDLE_MODEL_WORKLOAD_MARKERS
                ),
                "known_workload_classifier": (
                    campaign.expected_known_workload_classifier_contract()
                ),
                "port_8199_listener_required_absent": True,
                "same_gpu_lease_required_each_sample": True,
                "required_driver_model": "WDDM",
                "display_active_allowed_measured_states": [
                    "Disabled",
                    "Enabled",
                ],
                "display_active_recorded_non_gating": True,
                "current_runner_exclusion": (
                    "exact real runner PID/create-time/target plus at most one "
                    "verified direct Windows venv launcher stub"
                ),
            },
            "collector": {
                "path": self.sources["runner"]["path"],
                "sha256": self.sources["runner"]["sha256"],
            },
        }

    def _idle_gate(self, role, server_instance):
        contract = self._idle_contract()
        common = {
            "schema_version": 1,
            "kind": "run-recipe-preboot-wddm-idle-gate",
            "contract": contract,
            "server_instance": server_instance,
        }
        if role == "warm":
            body = {
                **common,
                "status": "not-rerun-owned-server-reuse",
                "gate_ran": False,
                "reason": (
                    "verified owned lab server already active; "
                    "no fresh idle sampling claimed"
                ),
            }
            return {
                **body,
                "evidence_sha256": campaign.sha256_bytes(
                    campaign.canonical_bytes(body)
                ),
            }
        runner_path = str(Path(self.sources["runner"]["path"]).resolve())
        runner_identity = {
            "pid": 999,
            "exists": True,
            "name": "python.exe",
            "executable": str(campaign.PYTHON),
            "command_line": [str(campaign.PYTHON), runner_path],
            "process_create_time": 1234.25,
            "identity_errors": [],
        }
        runner_exclusion = {
            "pid": 999,
            "process_create_time": 1234.25,
            "resolved_runner_path": runner_path,
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": runner_identity,
            "verified_windows_venv_launcher": None,
            "expected_excluded_process_count": 1,
        }
        lock_owner = {
            "lock_schema_version": 1,
            "pid": 999,
            "process_create_time": 1234.25,
            "nonce": "1" * 64,
            "role": "standalone",
            "created_at_unix": 1234.5,
        }
        lock_bytes = (
            json.dumps(lock_owner, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        target = {
            "gpu_index": 0,
            "gpu_uuid": "GPU-test-uuid",
            "gpu_name": "NVIDIA GeForce RTX 5080 Laptop GPU",
            "vram_total_mib": 16384.0,
            "driver_model_current": "WDDM",
            "display_active": "Enabled",
            "query_argv": ["nvidia-smi", "--query-gpu=test"],
            "raw_stdout_sha256": "2" * 64,
        }
        samples = []
        for index in range(5):
            samples.append(
                {
                    "sample_index": index,
                    "sampled_at_ns": 10_000 + index,
                    "sampled_at_utc": f"2026-08-10T00:00:0{index}Z",
                    "sampled_monotonic_ns": 20_000 + index,
                    "gpu_index": 0,
                    "gpu_uuid": target["gpu_uuid"],
                    "gpu_name": target["gpu_name"],
                    "vram_used_mib": 512.0 + index,
                    "vram_total_mib": target["vram_total_mib"],
                    "gpu_utilization_percent": 1.0 + index,
                    "memory_utilization_percent": 2.0 + index,
                    "performance_state": "P8",
                    "driver_model_current": "WDDM",
                    "display_active": "Enabled",
                    "query_argv": ["nvidia-smi", "--query-gpu=activity"],
                    "raw_stdout_sha256": "3" * 64,
                    "host_ram_used_bytes": 1_000,
                    "host_ram_total_bytes": 2_000,
                    "port_8199_listener_evidence": {
                        "port": 8199,
                        "listeners": [],
                        "listener_pids": [],
                        "unknown_owner_count": 0,
                    },
                    "gpu_lock": {
                        "path": str(self.layout.gpu_lock.resolve()),
                        "receipt": copy.deepcopy(lock_owner),
                        "receipt_sha256": hashlib.sha256(lock_bytes).hexdigest(),
                        "authorization": "current standalone owner",
                        "matches_expected_owner": True,
                        "matches_acquired_owner": True,
                    },
                    "nvidia_process_evidence": {
                        "target_gpu_index": 0,
                        "target_gpu_uuid": target["gpu_uuid"],
                        "query_argv": ["nvidia-smi", "--query-compute-apps=test"],
                        "raw_stdout_sha256": "4" * 64,
                        "row_count": 0,
                        "rows": [],
                        "blocking_rows": [],
                    },
                    "forbidden_process_scan": {
                        "scanned_process_count": 10,
                        "model_workload_markers": contract["policy"][
                            "model_workload_markers"
                        ],
                        "classifier_contract": (
                            campaign.expected_known_workload_classifier_contract()
                        ),
                        "current_runner_exclusion": copy.deepcopy(
                            runner_exclusion
                        ),
                        "excluded_current_runner": [
                            {
                                "pid": 999,
                                "process_create_time": 1234.25,
                                "reason": "exact current run_recipe process",
                            }
                        ],
                        "blocking_processes": [],
                        "advisory_unreadable_processes": [
                            self._advisory_process()
                        ],
                    },
                    "quiescence_errors": [],
                    "quiescent": True,
                }
            )
        body = {
            **common,
            "status": "measured",
            "gate_ran": True,
            "gpu_index": 0,
            "target_gpu": target,
            "sample_count": 5,
            "sampling_interval_s": 0.2,
            "aggregation": "maximum of five conjunctively quiescent WDDM samples",
            "policy": contract["policy"],
            "port_8199_listener_pids_before": [],
            "port_8199_listener_pids_after": [],
            "current_runner_exclusion": runner_exclusion,
            "gpu_lock_owner": lock_owner,
            "samples": samples,
            "summary": {
                "max_vram_used_mib": 516.0,
                "max_gpu_utilization_percent": 5.0,
                "max_memory_utilization_percent": 6.0,
            },
            "collector": contract["collector"],
        }
        return {
            **body,
            "evidence_sha256": campaign.sha256_bytes(campaign.canonical_bytes(body)),
        }

    @staticmethod
    def _rehash_idle_gate(gate):
        gate.pop("evidence_sha256", None)
        gate["evidence_sha256"] = campaign.sha256_bytes(
            campaign.canonical_bytes(gate)
        )
        return gate

    def _attach_verified_launcher(self, gate):
        current = gate["current_runner_exclusion"]
        launcher_path = str(
            (Path(sys.prefix).resolve() / "Scripts" / "python.exe").resolve()
        )
        runner_path = str(Path(self.sources["runner"]["path"]).resolve())
        current["process_identity"]["executable"] = str(
            Path(getattr(sys, "_base_executable", sys.executable)).resolve()
        )
        launcher_identity = {
            "pid": 998,
            "exists": True,
            "name": "python.exe",
            "executable": launcher_path,
            "command_line": [launcher_path, runner_path],
            "process_create_time": 1234.0,
            "identity_errors": [],
        }
        current["verified_windows_venv_launcher"] = {
            "pid": 998,
            "process_create_time": 1234.0,
            "expected_launcher_path": launcher_path,
            "direct_child_pid": current["pid"],
            "direct_parent_verified": True,
            "launcher_identity_live": True,
            "child_identity_live": True,
            "argv_tail_matches_child": True,
            "both_exact_runner_target": True,
            "child_executable_differs": True,
            "creation_delta_s": 0.25,
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": launcher_identity,
        }
        current["expected_excluded_process_count"] = 2
        for sample in gate["samples"]:
            scan = sample["forbidden_process_scan"]
            scan["current_runner_exclusion"] = copy.deepcopy(current)
            scan["excluded_current_runner"].append(
                {
                    "pid": 998,
                    "process_create_time": 1234.0,
                    "reason": "exact verified direct Windows venv launcher stub",
                }
            )
        return gate

    def _prequeue_scan(self, server_instance, server_argv):
        runner_path = str(Path(self.sources["runner"]["path"]).resolve())
        current_identity = {
            "pid": 999,
            "exists": True,
            "name": "python.exe",
            "executable": str(campaign.PYTHON),
            "command_line": [str(campaign.PYTHON), runner_path],
            "process_create_time": 1234.25,
            "identity_errors": [],
        }
        current = {
            "pid": 999,
            "process_create_time": 1234.25,
            "resolved_runner_path": runner_path,
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": current_identity,
            "verified_windows_venv_launcher": None,
            "expected_excluded_process_count": 1,
        }
        server_identity = {
            "pid": server_instance["serving_pid"],
            "exists": True,
            "name": "python.exe",
            "executable": str(campaign.PYTHON),
            "command_line": list(server_argv),
            "process_create_time": server_instance["process_create_time"],
            "identity_errors": [],
        }
        owned = {
            "pid": server_instance["serving_pid"],
            "process_create_time": server_instance["process_create_time"],
            "server_instance": copy.deepcopy(server_instance),
            "process_identity": server_identity,
            "argv_match": {
                "matches": True,
                "match_mode": "exact-self-reported-argv",
                "actual_argv": list(server_argv),
                "reported_server_argv": list(server_argv),
            },
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "verified_windows_venv_launcher": None,
            "expected_excluded_process_count": 1,
        }
        body = {
            "schema_version": 1,
            "kind": "per-leg-immediate-prequeue-known-workload-scan",
            "status": "clean",
            "scan_ran": True,
            "sampled_at_ns": 30_000,
            "sampled_at_utc": "2026-08-10T00:00:00Z",
            "completed_at_ns": 30_001,
            "contract": campaign.expected_operator_idle_policy()[
                "prequeue_known_workload_scan_contract"
            ],
            "server_instance": copy.deepcopy(server_instance),
            "server_argv": list(server_argv),
            "listener_pid_before": server_instance["serving_pid"],
            "listener_pid_after": server_instance["serving_pid"],
            "current_runner_exclusion": current,
            "owned_lab_server_exclusion": owned,
            "scanned_process_count": 10,
            "excluded_current_runner": [
                {
                    "pid": 999,
                    "process_create_time": 1234.25,
                    "reason": "exact current run_recipe process",
                }
            ],
            "excluded_owned_lab_server": [
                {
                    "pid": server_instance["serving_pid"],
                    "process_create_time": server_instance["process_create_time"],
                    "reason": "exact owned port-8199 server PID/create-time/argv",
                }
            ],
            "blocking_processes": [],
            "advisory_unreadable_processes": [self._advisory_process()],
            "scan_errors": [],
        }
        return {**body, "evidence_sha256": campaign.stable_identity(body)}

    def _attach_owned_server_launcher(
        self, scan, server_instance, server_argv
    ):
        owned = scan["owned_lab_server_exclusion"]
        launcher_path = str(
            (Path(sys.prefix).resolve() / "Scripts" / "python.exe").resolve()
        )
        owned["process_identity"]["executable"] = str(
            Path(getattr(sys, "_base_executable", sys.executable)).resolve()
        )
        launcher_created = round(
            float(server_instance["process_create_time"]) - 0.25, 6
        )
        launcher_pid = int(server_instance["serving_pid"]) - 1
        launcher_identity = {
            "pid": launcher_pid,
            "exists": True,
            "name": "python.exe",
            "executable": launcher_path,
            "command_line": list(server_argv),
            "process_create_time": launcher_created,
            "identity_errors": [],
        }
        launcher_argv_match = {
            "matches": True,
            "match_mode": "exact-self-reported-argv",
            "actual_argv": list(server_argv),
            "reported_server_argv": list(server_argv),
        }
        owned["verified_windows_venv_launcher"] = {
            "pid": launcher_pid,
            "process_create_time": launcher_created,
            "expected_launcher_path": launcher_path,
            "direct_child_pid": server_instance["serving_pid"],
            "direct_parent_verified": True,
            "launcher_identity_live": True,
            "child_identity_live": True,
            "argv_tail_matches_child": True,
            "both_exact_validated_server_argv": True,
            "child_executable_differs": True,
            "creation_delta_s": 0.25,
            "narrowly_verified": True,
            "excluded_pid_only": True,
            "process_identity": launcher_identity,
            "argv_match": launcher_argv_match,
        }
        owned["expected_excluded_process_count"] = 2
        scan["scanned_process_count"] += 1
        scan["excluded_owned_lab_server"].append(
            {
                "pid": launcher_pid,
                "process_create_time": launcher_created,
                "reason": (
                    "exact verified direct Windows venv owned-server launcher stub"
                ),
            }
        )
        scan.pop("evidence_sha256", None)
        scan["evidence_sha256"] = campaign.stable_identity(scan)
        return scan

    def _manager_bundle(self, spec, nonce, server_instance):
        campaign_id, pair_index, role = self._nonce_identity(nonce)
        log_path = campaign.pair_log_path(
            spec, pair_index, campaign_id, self.layout
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        argv = self._server_argv()
        guard = campaign.manager_guard
        config = self.layout.actual_user_directory / "__manager" / "config.ini"
        if role == "cold":
            base = (
                guard.preboot_log_line(
                    self.layout.actual_user_directory,
                    dict(guard.OFFLINE_ENVIRONMENT),
                ).decode("utf-8")
                + "\n".join(
                    (
                        f"** ComfyUI-Manager config path: {config}",
                        "[ComfyUI-Manager] network_mode: offline",
                        guard.STARTUP_MARKER,
                        "To see the GUI go to: http://127.0.0.1:8199",
                    )
                )
                + "\n"
            )
            log_path.write_bytes(base.encode("utf-8"))
            pre_scan = guard.scan_log(log_path, argv, require_pre_prompt=True)
        else:
            self.assertTrue(log_path.is_file())
            pre_scan = guard.scan_log(log_path, argv, require_pre_prompt=False)

        def evidence(scan, require_no_prior_prompt):
            return {
                "enabled": True,
                "valid": True,
                "recipe_scope": {
                    "scope": "h3-canonical-canvas-job-c",
                    "match_type": "exact",
                    "match_value": spec.name,
                    "log_root": str(log_path.parent.resolve()),
                },
                "verified_before_this_prompt": True,
                "require_no_prior_prompt": require_no_prior_prompt,
                "log_path": str(log_path.resolve()),
                "serving_pid": server_instance["serving_pid"],
                "serving_process_create_time_ns": int(
                    round(server_instance["process_create_time"] * 1_000_000_000)
                ),
                "offline_environment": guard.offline_environment_evidence(
                    dict(guard.OFFLINE_ENVIRONMENT)
                ),
                "advisory_config": guard.config_evidence(argv),
                "log_scan": scan,
                "guard_source": {
                    "path": self.sources["manager_guard"]["path"],
                    "sha256": self.sources["manager_guard"]["sha256"],
                },
                "test_boot_source": {
                    "path": self.sources["test_boot_cmd"]["path"],
                    "sha256": self.sources["test_boot_cmd"]["sha256"],
                },
            }

        pre = evidence(pre_scan, role == "cold")
        with log_path.open("ab") as handle:
            handle.write(b"got prompt\nPrompt executed in 1.00 seconds\n")
        post_scan = guard.scan_log(log_path, argv, require_pre_prompt=False)
        post = evidence(post_scan, False)
        return (
            log_path,
            {
                "pre_queue": pre,
                "post_render": post,
                "provenance_unchanged": True,
            },
            campaign.expected_manager_identity(pre),
        )

    def _write_receipt(self, spec, run_number, nonce, server_instance):
        artifact_name = f"{spec.prefix}_{run_number:05d}_.mp4"
        artifact_path = self.outputs / artifact_name
        artifact_path.write_bytes(
            f"artifact:{spec.name}:{run_number}".encode("utf-8")
        )
        argv = self._server_argv()
        cache_contract = campaign.expected_cache_contract(spec, nonce)
        prompt_sha = cache_contract.pop("queued_prompt_sha256")
        cache_evidence = {
            **cache_contract,
            "cache_event_found": True,
            "cached_node_ids": cache_contract["stable_node_ids"] if run_number == 2 else [],
            "cached_fresh_node_ids": [],
            "fresh_execution_proved": True,
        }
        cache_runtime = {
            name: "a" * 64 for name in campaign.EXPECTED_STANDALONE_CACHE_SOURCES
        }
        audio_receipts = campaign.expected_audio_receipt_hashes(spec, self.layout)
        models = {
            name: self.models[name] for name in campaign.recipe_model_names(spec)
        }
        _, _, role = self._nonce_identity(nonce)
        log_path, manager_bundle, manager_identity = self._manager_bundle(
            spec, nonce, server_instance
        )
        idle_gate = self._idle_gate(role, server_instance)
        if role == "cold":
            self.layout.idle_gate_sidecar.write_bytes(
                (
                    json.dumps(
                        idle_gate,
                        indent=2,
                        sort_keys=True,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n"
                ).encode("utf-8")
            )
        sidecar_evidence, sidecar_snapshot = campaign.stable_idle_gate_sidecar(
            self.layout
        )
        if role == "cold":
            self.assertEqual(sidecar_evidence, idle_gate)
        prequeue_scan = self._prequeue_scan(server_instance, argv)
        identity = {
            "recipe_sha256": spec.sha256,
            "runner_sha256": self.sources["runner"]["sha256"],
            "lab_locks_sha256": self.sources["lab_locks"]["sha256"],
            "fixture_sha256s": dict(spec.fixture_hashes),
            "audio_receipt_sha256s": audio_receipts,
            "model_fingerprints": models,
            "boot_lane": campaign.EXPECTED_BOOT_LANE,
            "server_argv": argv,
            "server_instance": server_instance,
            "comfyui_git_commit": "f" * 40,
            "standalone_cache_runtime_sha256s": cache_runtime,
            "completion_timeout_s": campaign.completion_timeout_s(spec),
            "manager_offline_probe_identity": manager_identity,
            "preboot_gpu_idle_gate_contract": idle_gate["contract"],
            "operator_idle_policy": campaign.expected_operator_idle_policy(),
            "prequeue_known_workload_scan_contract": (
                campaign.expected_operator_idle_policy()[
                    "prequeue_known_workload_scan_contract"
                ]
            ),
        }
        warm = run_number == 2
        baseline_advisory = {
            "schema_version": 1,
            "kind": "per-leg-prequeue-baseline-advisory",
            "baseline_vram_gb": 2.0,
            "advisory_threshold_gb": 3.0,
            "threshold_exceeded": False,
            "gating": False,
            "disposition": "record-only; proceed regardless of baseline",
        }
        drift_advisory = {
            "schema_version": 1,
            "kind": "same-identity-cold-warm-baseline-drift-advisory",
            "applicable": warm,
            "measurement_available": warm,
            "previous_baseline_vram_gb": 2.0 if warm else None,
            "current_baseline_vram_gb": 2.0,
            "absolute_drift_gb": 0.0 if warm else None,
            "advisory_threshold_gb": 0.5,
            "threshold_exceeded": False,
            "gating": False,
            "disposition": (
                "record-only; proceed regardless of drift"
                if warm
                else "record-only; no same-identity prior leg"
            ),
        }
        payload = {
            "receipt_schema_version": 3,
            "recipe": spec.name,
            "run_number": run_number,
            "run_count": run_number,
            "config_run_count": run_number,
            "status": "PASS" if warm else "PASS (cold)",
            "gate_pass": True,
            "pass": warm,
            "warm_pass": warm,
            "marginal": False,
            "recipe_sha256": spec.sha256,
            "runner_sha256": self.sources["runner"]["sha256"],
            "lab_locks_sha256": self.sources["lab_locks"]["sha256"],
            "fixture_sha256s": dict(spec.fixture_hashes),
            "audio_receipt_sha256s": audio_receipts,
            "model_fingerprints": models,
            "provenance_unchanged": True,
            "server_instance_unchanged": True,
            "valid_measurement": True,
            "accepted_prompt": True,
            "requires_human_eyeball": True,
            "eyeball": "pending",
            "promotion_ready": False,
            "certification_scope": "machine-only",
            "clamp_target_gib": None,
            "reserve_vram_gib": None,
            "boot_lane": campaign.EXPECTED_BOOT_LANE,
            "encoded_width": 832,
            "encoded_height": 480,
            "encoded_frame_count": spec.frames,
            "completion_timeout_s": campaign.completion_timeout_s(spec),
            "encoded_fps": 24.0,
            "video_duration_s": spec.frames / 24.0,
            "audio_present": True,
            "audio_duration_s": spec.frames / 24.0,
            "server_argv": argv,
            "server_instance": server_instance,
            "final_server_instance": server_instance,
            "identity": identity,
            "run_identity_sha256": campaign.stable_identity(identity),
            "execution_cache_control": cache_evidence,
            "standalone_cache_runtime_sha256s": cache_runtime,
            "final_standalone_cache_runtime_sha256s": cache_runtime,
            "queued_prompt_sha256": prompt_sha,
            "output_path": artifact_name,
            "artifact_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "artifact_bytes": artifact_path.stat().st_size,
            "comfyui_git_commit": "f" * 40,
            "peak_vram_gb": 12.34,
            "baseline_vram_gb": 2.0,
            "absolute_peak_vram_gb": 12.34,
            "net_peak_vram_gb": 10.34,
            "elevated_baseline_lane": False,
            "baseline_lane_stamp": None,
            "baseline_advisory": baseline_advisory,
            "cold_warm_baseline_drift_advisory": drift_advisory,
            "vram_measurement": {
                "units": "GiB (nvidia-smi MiB / 1024)",
                "baseline_measurement_point": (
                    "immediately before prompt queue; includes owned lab server "
                    "and desktop load"
                ),
                "baseline_absolute_gib": 2.0,
                "peak_absolute_gib": 12.34,
                "net_peak_gib": 10.34,
                "net_peak_formula": "peak_vram_gb - baseline_vram_gb",
            },
            "duration_s": 10.0,
            "manager_offline_probe": manager_bundle,
            "preboot_gpu_idle_gate": idle_gate,
            "preboot_gpu_idle_gate_contract": idle_gate["contract"],
            "preboot_gpu_idle_gate_sidecar": sidecar_snapshot,
            "operator_idle_policy": campaign.expected_operator_idle_policy(),
            "prequeue_known_workload_scan_contract": (
                campaign.expected_operator_idle_policy()[
                    "prequeue_known_workload_scan_contract"
                ]
            ),
            "prequeue_known_workload_scan": prequeue_scan,
        }
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        (self.results / f"{spec.name}_run{run_number}.json").write_bytes(encoded)
        (self.results / f"{spec.name}.json").write_bytes(encoded)
        return payload

    def test_read_only_runbook_has_six_ordered_pairs_and_unique_nonces(self):
        before = self.layout.lifecycle.exists()
        plan = campaign.runbook("test-campaign", self.layout)
        self.assertEqual(
            plan["operator_idle_policy"], campaign.expected_operator_idle_policy()
        )
        self.assertEqual(before, self.layout.lifecycle.exists())
        self.assertEqual(
            [(row["mode"], row["frames"]) for row in plan["pairs"]],
            [
                ("i2v", 107),
                ("i2v", 192),
                ("i2v", 277),
                ("r2v_refaudio", 107),
                ("r2v_refaudio", 192),
                ("r2v_refaudio", 277),
            ],
        )
        nonces = []
        for pair in plan["pairs"]:
            cold = pair["cold_argv"]
            warm = pair["warm_shutdown_argv"]
            self.assertEqual(Path(cold[1]), self.layout.runner)
            self.assertNotIn("--shutdown", cold)
            self.assertIn("--shutdown", warm)
            self.assertIn("--disable-pinned-memory", cold)
            self.assertIn("--manager-offline-test", cold)
            self.assertEqual(
                cold[cold.index("--manager-probe-phase") + 1], "cold"
            )
            self.assertEqual(
                warm[warm.index("--manager-probe-phase") + 1], "warm"
            )
            self.assertEqual(
                int(cold[cold.index("--completion-timeout-s") + 1]),
                pair["completion_timeout_s"],
            )
            self.assertEqual(
                pair["manager_log"],
                str(
                    campaign.pair_log_path(
                        self.specs[pair["pair_index"] - 1],
                        pair["pair_index"],
                        "test-campaign",
                        self.layout,
                    )
                ),
            )
            self.assertNotIn("--force", cold + warm)
            nonces.extend(
                [
                    cold[cold.index("--executor-cache-nonce") + 1],
                    warm[warm.index("--executor-cache-nonce") + 1],
                ]
            )
        self.assertEqual(len(nonces), len(set(nonces)))
        self.assertEqual(len(nonces), 12)

    def test_default_main_is_read_only(self):
        output = types.SimpleNamespace(buffer=io.BytesIO())
        with mock.patch.object(campaign.sys, "stdout", output):
            self.assertEqual(campaign.main([], layout=self.layout), 0)
        parsed = json.loads(output.buffer.getvalue().decode("utf-8"))
        self.assertEqual(len(parsed["pairs"]), 6)
        self.assertFalse(self.layout.lifecycle.exists())
        self.assertEqual(list(self.results.iterdir()), [])
        self.assertEqual(list(self.outputs.iterdir()), [])

    def test_manager_both_offline_and_source_drift_are_fail_closed(self):
        baseline = campaign.manager_evidence(self.layout)
        self.assertTrue(baseline["both_offline"])
        self.lab_manager.write_bytes(b"[default]\nnetwork_mode = public\n")
        with self.assertRaisesRegex(campaign.CampaignError, "must be offline"):
            campaign.manager_evidence(self.layout)

        sources = dict(self.sources)
        drift = json.loads(json.dumps(self.sources))
        drift["runner"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(campaign.CampaignError, "runner source changed"):
            campaign.require_same_source_evidence(sources, drift, "test")

    def test_state_and_pristine_history_guards(self):
        campaign.require_clean_state(clean_state(), "clean")
        dirty = clean_state()
        dirty["listener_pids_8199"] = [123]
        with self.assertRaisesRegex(campaign.CampaignError, "not clean"):
            campaign.require_clean_state(dirty, "dirty")

        spec = self.specs[0]
        (self.results / f"{spec.name}.json").write_bytes(b"{}\n")
        with self.assertRaisesRegex(campaign.CampaignError, "refusing overwrite"):
            campaign.ensure_pristine_history(spec, self.layout)

    def test_pending_child_ownership_requires_exact_descendant_proof(self):
        identity = {"serving_pid": 61000, "process_create_time": 4100.0}
        runner_pid = 60000
        runner_create_time = 4000.0
        observation = {
            **identity,
            "server_argv": self._server_argv(),
            "observed_descendant_of_runner_pid": runner_pid,
            "runner_process_create_time": runner_create_time,
            "observed_at_ns": 1,
        }
        outcome = campaign.ChildOutcome(
            returncode=7,
            runner_pid=runner_pid,
            runner_create_time=runner_create_time,
            descendant_server_instances=(observation,),
        )
        state = {
            **clean_state(),
            "server_pid_receipt_exists": True,
            "server_pid_receipt": identity["serving_pid"],
            "server_pid_create_time": identity["process_create_time"],
            "listener_pids_8199": [identity["serving_pid"]],
        }
        process = mock.Mock()
        process.create_time.return_value = identity["process_create_time"]
        with mock.patch.object(campaign.psutil, "Process", return_value=process), mock.patch.object(
            campaign,
            "_live_server_argv",
            return_value=self._server_argv(),
        ):
            self.assertEqual(
                campaign.pending_child_owned_server(outcome, state, self.layout),
                identity,
            )
            wrong_listener = dict(state)
            wrong_listener["listener_pids_8199"] = [62000]
            self.assertIsNone(
                campaign.pending_child_owned_server(
                    outcome, wrong_listener, self.layout
                )
            )
            wrong_outcome = campaign.ChildOutcome(
                returncode=7,
                runner_pid=runner_pid,
                runner_create_time=runner_create_time,
                descendant_server_instances=(
                    {**observation, "observed_descendant_of_runner_pid": 99999},
                ),
            )
            self.assertIsNone(
                campaign.pending_child_owned_server(
                    wrong_outcome, state, self.layout
                )
            )

    def test_receipt_verifier_binds_archive_artifact_lane_nonce_and_identity(self):
        spec = self.specs[0]
        server = {"serving_pid": 43210, "process_create_time": 1234.5}
        cold_nonce = campaign.executor_nonce("receipt-test", 1, "cold")
        self._write_receipt(spec, 1, cold_nonce, server)
        verified = campaign.verify_run_receipt(
            spec, 1, cold_nonce, self.sources, self.layout
        )
        self.assertEqual(verified["server_instance"], server)
        self.assertEqual(
            verified["artifact"]["bytes"],
            len(f"artifact:{spec.name}:1".encode("utf-8")),
        )
        self.assertEqual(
            verified["prequeue_known_workload_scan"]["status"], "clean"
        )
        self.assertEqual(
            len(
                verified["prequeue_known_workload_scan"][
                    "advisory_unreadable_processes"
                ]
            ),
            1,
        )

        alias = self.results / f"{spec.name}.json"
        drifted = json.loads(alias.read_text(encoding="utf-8"))
        drifted["execution_cache_control"]["nonce"] = "wrong"
        alias.write_bytes(
            (json.dumps(drifted, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
        with self.assertRaisesRegex(campaign.CampaignError, "alias != immutable"):
            campaign.verify_run_receipt(spec, 1, cold_nonce, self.sources, self.layout)

    def test_receipt_verifier_rejects_global_sage_and_missing_warm_cache_hits(self):
        spec = self.specs[0]
        server = {"serving_pid": 43211, "process_create_time": 1235.5}
        cold_nonce = campaign.executor_nonce("negative-test", 1, "cold")
        payload = self._write_receipt(spec, 1, cold_nonce, server)
        payload["server_argv"].append("--use-sage-attention")
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        (self.results / f"{spec.name}_run1.json").write_bytes(encoded)
        (self.results / f"{spec.name}.json").write_bytes(encoded)
        with self.assertRaisesRegex(campaign.CampaignError, "server argv"):
            campaign.verify_run_receipt(
                spec, 1, cold_nonce, self.sources, self.layout
            )

        for path in self.results.glob(f"{spec.name}*.json"):
            path.unlink()
        (self.outputs / f"{spec.prefix}_00001_.mp4").unlink()
        warm_nonce = campaign.executor_nonce("negative-test", 1, "warm")
        warm = self._write_receipt(spec, 2, warm_nonce, server)
        warm["execution_cache_control"]["cached_node_ids"] = []
        encoded = (json.dumps(warm, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        (self.results / f"{spec.name}_run2.json").write_bytes(encoded)
        (self.results / f"{spec.name}.json").write_bytes(encoded)
        with self.assertRaisesRegex(campaign.CampaignError, "stable-node cache hit"):
            campaign.verify_run_receipt(
                spec, 2, warm_nonce, self.sources, self.layout
            )

    def test_operator_idle_metrics_enforce_three_gib_stamp_and_net_arithmetic(self):
        policy = campaign.expected_operator_idle_policy()
        base = {
            "baseline_vram_gb": 2.57,
            "peak_vram_gb": 12.34,
            "absolute_peak_vram_gb": 12.34,
            "net_peak_vram_gb": 9.77,
            "elevated_baseline_lane": True,
            "baseline_lane_stamp": (
                "elevated-baseline lane, operator-authorized 2026-08-10"
            ),
            "operator_idle_policy": policy,
            "identity": {"operator_idle_policy": policy},
            "vram_measurement": {
                "units": "GiB (nvidia-smi MiB / 1024)",
                "baseline_measurement_point": (
                    "immediately before prompt queue; includes owned lab server "
                    "and desktop load"
                ),
                "baseline_absolute_gib": 2.57,
                "peak_absolute_gib": 12.34,
                "net_peak_gib": 9.77,
                "net_peak_formula": "peak_vram_gb - baseline_vram_gb",
            },
        }
        verified = campaign.verify_operator_idle_measurement(base, "unit")
        self.assertEqual(verified["net_peak_vram_gb"], 9.77)
        for field, value in (
            ("net_peak_vram_gb", 9.76),
            ("baseline_lane_stamp", None),
            ("elevated_baseline_lane", False),
        ):
            with self.subTest(field=field):
                tampered = copy.deepcopy(base)
                tampered[field] = value
                with self.assertRaises(campaign.CampaignError):
                    campaign.verify_operator_idle_measurement(tampered, "unit")

        high_baseline = copy.deepcopy(base)
        high_baseline.update(
            {"baseline_vram_gb": 3.01, "net_peak_vram_gb": 9.33}
        )
        high_baseline["vram_measurement"].update(
            {"baseline_absolute_gib": 3.01, "net_peak_gib": 9.33}
        )
        campaign.verify_operator_idle_measurement(high_baseline, "unit")

        ordinary = copy.deepcopy(base)
        ordinary.update(
            {
                "baseline_vram_gb": 2.0,
                "net_peak_vram_gb": 10.34,
                "elevated_baseline_lane": False,
                "baseline_lane_stamp": None,
            }
        )
        ordinary["vram_measurement"].update(
            {"baseline_absolute_gib": 2.0, "net_peak_gib": 10.34}
        )
        campaign.verify_operator_idle_measurement(ordinary, "unit")

    def test_receipt_rejects_tampered_prequeue_known_workload_scan(self):
        spec = self.specs[0]
        server = {"serving_pid": 43215, "process_create_time": 1239.5}
        nonce = campaign.executor_nonce("prequeue-tamper", 1, "cold")
        payload = self._write_receipt(spec, 1, nonce, server)

        scan = payload["prequeue_known_workload_scan"]
        scan["listener_pid_after"] = 99999
        scan.pop("evidence_sha256")
        scan["evidence_sha256"] = campaign.stable_identity(scan)
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        (self.results / f"{spec.name}_run1.json").write_bytes(encoded)
        (self.results / f"{spec.name}.json").write_bytes(encoded)
        with self.assertRaisesRegex(campaign.CampaignError, "prequeue"):
            campaign.verify_run_receipt(
                spec, 1, nonce, self.sources, self.layout
            )

        payload = self._write_receipt(
            self.specs[1],
            1,
            campaign.executor_nonce("prequeue-advisory-tamper", 2, "cold"),
            server,
        )
        scan = payload["prequeue_known_workload_scan"]
        advisory = scan["advisory_unreadable_processes"][0]
        advisory["matched_markers"] = ["main.py"]
        advisory["match_basis"] = ["python_script_target"]
        scan.pop("evidence_sha256")
        scan["evidence_sha256"] = campaign.stable_identity(scan)
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        second = self.specs[1]
        (self.results / f"{second.name}_run1.json").write_bytes(encoded)
        (self.results / f"{second.name}.json").write_bytes(encoded)
        with self.assertRaisesRegex(campaign.CampaignError, "prequeue"):
            campaign.verify_run_receipt(
                second,
                1,
                campaign.executor_nonce("prequeue-advisory-tamper", 2, "cold"),
                self.sources,
                self.layout,
            )

    def test_prequeue_accepts_only_exact_owned_server_launcher_proof(self):
        server = {"serving_pid": 43218, "process_create_time": 1242.5}
        server_argv = self._server_argv()
        scan = self._attach_owned_server_launcher(
            self._prequeue_scan(server, server_argv), server, server_argv
        )
        contract = campaign.expected_operator_idle_policy()[
            "prequeue_known_workload_scan_contract"
        ]
        receipt = {
            "prequeue_known_workload_scan_contract": contract,
            "prequeue_known_workload_scan": scan,
            "identity": {"prequeue_known_workload_scan_contract": contract},
        }
        verified = campaign.verify_prequeue_known_workload_scan(
            receipt,
            sources=self.sources,
            server_instance=server,
            server_argv=server_argv,
            label="owned-launcher unit",
        )
        self.assertEqual(len(verified["excluded_owned_lab_server"]), 2)

        forged = copy.deepcopy(receipt)
        forged_scan = forged["prequeue_known_workload_scan"]
        forged_scan["owned_lab_server_exclusion"][
            "verified_windows_venv_launcher"
        ]["direct_parent_verified"] = False
        forged_scan.pop("evidence_sha256")
        forged_scan["evidence_sha256"] = campaign.stable_identity(forged_scan)
        with self.assertRaisesRegex(campaign.CampaignError, "owned.server|prequeue"):
            campaign.verify_prequeue_known_workload_scan(
                forged,
                sources=self.sources,
                server_instance=server,
                server_argv=server_argv,
                label="forged owned-launcher unit",
            )

    def test_full_cold_receipt_accepts_baseline_over_three_as_advisory(self):
        spec = self.specs[0]
        server = {"serving_pid": 43216, "process_create_time": 1240.5}
        nonce = campaign.executor_nonce("high-baseline", 1, "cold")
        payload = self._write_receipt(spec, 1, nonce, server)
        payload.update(
            {
                "baseline_vram_gb": 3.2,
                "net_peak_vram_gb": 9.14,
                "elevated_baseline_lane": True,
                "baseline_lane_stamp": (
                    "elevated-baseline lane, operator-authorized 2026-08-10"
                ),
            }
        )
        payload["vram_measurement"].update(
            {"baseline_absolute_gib": 3.2, "net_peak_gib": 9.14}
        )
        payload["baseline_advisory"].update(
            {"baseline_vram_gb": 3.2, "threshold_exceeded": True}
        )
        payload["cold_warm_baseline_drift_advisory"].update(
            {"current_baseline_vram_gb": 3.2}
        )
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        (self.results / f"{spec.name}_run1.json").write_bytes(encoded)
        (self.results / f"{spec.name}.json").write_bytes(encoded)
        verified = campaign.verify_run_receipt(
            spec, 1, nonce, self.sources, self.layout
        )
        self.assertTrue(verified["baseline_advisory"]["threshold_exceeded"])
        self.assertFalse(verified["baseline_advisory"]["gating"])

    def test_pair_records_cold_warm_baseline_drift_over_half_gib_as_advisory(self):
        spec = self.specs[0]
        server = {"serving_pid": 43214, "process_create_time": 1238.5}
        campaign_id = "baseline-drift-test"
        self._write_receipt(
            spec,
            1,
            campaign.executor_nonce(campaign_id, 1, "cold"),
            server,
        )
        warm = self._write_receipt(
            spec,
            2,
            campaign.executor_nonce(campaign_id, 1, "warm"),
            server,
        )
        warm.update(
            {
                "baseline_vram_gb": 2.51,
                "net_peak_vram_gb": 9.83,
                "elevated_baseline_lane": True,
                "baseline_lane_stamp": (
                    "elevated-baseline lane, operator-authorized 2026-08-10"
                ),
            }
        )
        warm["vram_measurement"].update(
            {"baseline_absolute_gib": 2.51, "net_peak_gib": 9.83}
        )
        warm["baseline_advisory"].update({"baseline_vram_gb": 2.51})
        warm["cold_warm_baseline_drift_advisory"].update(
            {
                "previous_baseline_vram_gb": 2.0,
                "current_baseline_vram_gb": 2.51,
                "absolute_drift_gb": 0.51,
                "threshold_exceeded": True,
            }
        )
        encoded = (json.dumps(warm, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        (self.results / f"{spec.name}_run2.json").write_bytes(encoded)
        (self.results / f"{spec.name}.json").write_bytes(encoded)
        pair = campaign.verify_pair(
            spec,
            1,
            campaign_id,
            self.sources,
            layout=self.layout,
        )
        self.assertEqual(pair["cold_warm_baseline_drift_gb"], 0.51)
        self.assertFalse(pair["cold_warm_baseline_drift_gating"])

    def test_idle_gate_recomputes_each_sample_and_accepts_over_advisory_baseline(self):
        spec = self.specs[0]
        server = {"serving_pid": 43212, "process_create_time": 1236.5}
        nonce = campaign.executor_nonce("idle-tamper", 1, "cold")
        payload = self._write_receipt(spec, 1, nonce, server)

        disabled = copy.deepcopy(payload)
        disabled_gate = disabled["preboot_gpu_idle_gate"]
        disabled_gate["target_gpu"]["display_active"] = "Disabled"
        for sample in disabled_gate["samples"]:
            sample["display_active"] = "Disabled"
        self._rehash_idle_gate(disabled_gate)
        campaign.verify_preboot_idle_gate(
            disabled,
            role="cold",
            sources=self.sources,
            server_instance=server,
            layout=self.layout,
        )

        launcher_bound = copy.deepcopy(payload)
        launcher_gate = self._attach_verified_launcher(
            launcher_bound["preboot_gpu_idle_gate"]
        )
        self._rehash_idle_gate(launcher_gate)
        campaign.verify_preboot_idle_gate(
            launcher_bound,
            role="cold",
            sources=self.sources,
            server_instance=server,
            layout=self.layout,
        )
        forged_launcher = copy.deepcopy(launcher_bound)
        forged_launcher["preboot_gpu_idle_gate"]["current_runner_exclusion"][
            "verified_windows_venv_launcher"
        ]["direct_parent_verified"] = False
        self._rehash_idle_gate(forged_launcher["preboot_gpu_idle_gate"])
        with self.assertRaises(campaign.CampaignError):
            campaign.verify_preboot_idle_gate(
                forged_launcher,
                role="cold",
                sources=self.sources,
                server_instance=server,
                layout=self.layout,
            )

        boundary = copy.deepcopy(payload)
        boundary_gate = boundary["preboot_gpu_idle_gate"]
        boundary_gate["samples"][-1]["vram_used_mib"] = 4096.0
        boundary_gate["summary"]["max_vram_used_mib"] = 4096.0
        self._rehash_idle_gate(boundary_gate)
        campaign.verify_preboot_idle_gate(
            boundary,
            role="cold",
            sources=self.sources,
            server_instance=server,
            layout=self.layout,
        )

        def listener(gate):
            evidence = gate["samples"][0]["port_8199_listener_evidence"]
            evidence["listeners"] = [
                {"pid": 777, "local_address": "127.0.0.1:8199", "owner_known": True}
            ]
            evidence["listener_pids"] = [777]

        def nvidia_blocker(gate):
            gate["samples"][0]["nvidia_process_evidence"]["blocking_rows"] = [
                {"pid": 888}
            ]

        def forbidden_process(gate):
            gate["samples"][0]["forbidden_process_scan"][
                "blocking_processes"
            ] = [{"pid": 9999}]

        def misclassified_advisory(gate):
            advisory = gate["samples"][0]["forbidden_process_scan"][
                "advisory_unreadable_processes"
            ][0]
            advisory["matched_markers"] = ["main.py"]
            advisory["match_basis"] = ["python_script_target"]

        def unstable_lock(gate):
            receipt = gate["samples"][0]["gpu_lock"]["receipt"]
            receipt["nonce"] = "2" * 64
            receipt_bytes = (
                json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            gate["samples"][0]["gpu_lock"]["receipt_sha256"] = hashlib.sha256(
                receipt_bytes
            ).hexdigest()

        tamper_cases = {
            "over-physical": lambda gate: (
                gate["samples"][-1].__setitem__("vram_used_mib", 16384.0001),
                gate["summary"].__setitem__("max_vram_used_mib", 16384.0001),
            ),
            "listener": listener,
            "nvidia-blocker": nvidia_blocker,
            "forbidden-process": forbidden_process,
            "misclassified-advisory": misclassified_advisory,
            "quiescence-error": lambda gate: gate["samples"][0].__setitem__(
                "quiescence_errors", ["busy"]
            ),
            "driver-model": lambda gate: gate["samples"][0].__setitem__(
                "driver_model_current", "TCC"
            ),
            "invalid-display-state": lambda gate: gate["samples"][0].__setitem__(
                "display_active", "Unknown"
            ),
            "gpu-identity": lambda gate: gate["samples"][0].__setitem__(
                "gpu_uuid", "GPU-other"
            ),
            "lease-owner": unstable_lock,
            "summary": lambda gate: gate["summary"].__setitem__(
                "max_vram_used_mib", 1.0
            ),
        }
        for label, mutate in tamper_cases.items():
            with self.subTest(label=label):
                tampered = copy.deepcopy(payload)
                mutate(tampered["preboot_gpu_idle_gate"])
                self._rehash_idle_gate(tampered["preboot_gpu_idle_gate"])
                with self.assertRaises(campaign.CampaignError):
                    campaign.verify_preboot_idle_gate(
                        tampered,
                        role="cold",
                        sources=self.sources,
                        server_instance=server,
                        layout=self.layout,
                    )

    def test_pair_rejects_extra_prompt_marker_and_changed_sidecar_snapshot(self):
        spec = self.specs[0]
        server = {"serving_pid": 43213, "process_create_time": 1237.5}
        campaign_id = "manager-marker-test"
        cold = self._write_receipt(
            spec,
            1,
            campaign.executor_nonce(campaign_id, 1, "cold"),
            server,
        )
        warm = self._write_receipt(
            spec,
            2,
            campaign.executor_nonce(campaign_id, 1, "warm"),
            server,
        )
        log_path = campaign.pair_log_path(spec, 1, campaign_id, self.layout)
        with log_path.open("ab") as handle:
            handle.write(b"got prompt\n")
        with self.assertRaisesRegex(campaign.CampaignError, "final Manager log"):
            campaign.verify_pair(
                spec,
                1,
                campaign_id,
                self.sources,
                layout=self.layout,
                log_path=log_path,
            )

        raw = log_path.read_bytes().rsplit(b"got prompt\n", 1)[0]
        log_path.write_bytes(raw)
        cold["preboot_gpu_idle_gate_sidecar"]["sha256"] = "0" * 64
        warm["preboot_gpu_idle_gate_sidecar"]["sha256"] = "0" * 64
        cold_encoded = (json.dumps(cold, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        warm_encoded = (json.dumps(warm, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        (self.results / f"{spec.name}_run1.json").write_bytes(cold_encoded)
        (self.results / f"{spec.name}_run2.json").write_bytes(warm_encoded)
        (self.results / f"{spec.name}.json").write_bytes(warm_encoded)
        with self.assertRaisesRegex(campaign.CampaignError, "sidecar bytes"):
            campaign.verify_pair(
                spec,
                1,
                campaign_id,
                self.sources,
                layout=self.layout,
                log_path=log_path,
            )

    def test_lifecycle_is_hash_chained_append_only_and_rejects_tamper(self):
        ledger = campaign.AppendOnlyLifecycle(self.layout.lifecycle, "ledger-a")
        first = ledger.append("started", {"value": 1})
        second = ledger.append("finished", {"value": 2})
        self.assertEqual(second["previous_event_sha256"], first["event_sha256"])
        initial = self.layout.lifecycle.read_bytes()

        next_ledger = campaign.AppendOnlyLifecycle(self.layout.lifecycle, "ledger-b")
        next_ledger.append("started", {"value": 3})
        self.assertTrue(self.layout.lifecycle.read_bytes().startswith(initial))
        with self.assertRaisesRegex(campaign.CampaignError, "already exists"):
            campaign.AppendOnlyLifecycle(self.layout.lifecycle, "ledger-a")

        raw = self.layout.lifecycle.read_bytes()
        self.layout.lifecycle.write_bytes(raw.replace(b'"value":1', b'"value":9', 1))
        with self.assertRaisesRegex(campaign.CampaignError, "SHA mismatch"):
            campaign.AppendOnlyLifecycle(self.layout.lifecycle, "ledger-c")

    def test_lifecycle_stale_writer_refuses_before_appending(self):
        first = campaign.AppendOnlyLifecycle(self.layout.lifecycle, "writer-a")
        stale = campaign.AppendOnlyLifecycle(self.layout.lifecycle, "writer-b")
        first.append("started", {"writer": "a"})
        frozen = self.layout.lifecycle.read_bytes()
        with self.assertRaisesRegex(campaign.CampaignError, "changed since"):
            stale.append("started", {"writer": "b"})
        self.assertEqual(self.layout.lifecycle.read_bytes(), frozen)

    def test_resume_allows_only_a_clean_unrendered_tail_start(self):
        campaign_id = "resume-clean-tail"
        spec = self.specs[0]
        server = {"serving_pid": 43214, "process_create_time": 1238.5}
        self._write_receipt(
            spec,
            1,
            campaign.executor_nonce(campaign_id, 1, "cold"),
            server,
        )
        self._write_receipt(
            spec,
            2,
            campaign.executor_nonce(campaign_id, 1, "warm"),
            server,
        )
        pair = campaign.verify_pair(
            spec,
            1,
            campaign_id,
            self.sources,
            layout=self.layout,
            log_path=campaign.pair_log_path(spec, 1, campaign_id, self.layout),
        )
        self.layout.idle_gate_sidecar.unlink()
        manager = campaign.manager_evidence(self.layout)
        completed = {
            "pair_index": 1,
            "recipe": spec.name,
            "pair": pair,
            "post_shutdown_state": clean_state(),
            "manager_after_shutdown": manager,
            "evidence_campaign_id": campaign_id,
        }
        ledger = campaign.AppendOnlyLifecycle(self.layout.lifecycle, campaign_id)
        ledger.append(
            "campaign_started",
            {
                "plan": campaign.runbook(campaign_id, self.layout),
                "sources": self.sources,
            },
        )
        ledger.append("pair_started", {"pair_index": 1})
        ledger.append("pair_verified", completed)
        ledger.append("pair_started", {"pair_index": 2})
        ledger.append(
            "campaign_failed",
            {"completed_pair_count": 1, "status": "FAILED"},
        )

        carried = campaign.verified_resume_prefix(
            campaign_id,
            self.specs,
            self.sources,
            manager,
            self.layout,
        )
        self.assertEqual([row["pair_index"] for row in carried], [1])

        tail_spec = self.specs[1]
        tail_log = campaign.pair_log_path(
            tail_spec, 2, campaign_id, self.layout
        )
        tail_log.write_bytes(b"partial pre-render log\n")
        with self.assertRaisesRegex(campaign.CampaignError, "Manager log set drifted"):
            campaign.verified_resume_prefix(
                campaign_id,
                self.specs,
                self.sources,
                manager,
                self.layout,
            )
        tail_log.unlink()

        partial_artifact = self.outputs / f"{tail_spec.prefix}_00001_.mp4"
        partial_artifact.write_bytes(b"partial")
        with self.assertRaisesRegex(campaign.CampaignError, "refusing overwrite"):
            campaign.verified_resume_prefix(
                campaign_id,
                self.specs,
                self.sources,
                manager,
                self.layout,
            )

    def test_mock_campaign_runs_all_pairs_only_through_runner_and_cleans_each_pair(self):
        spec_by_path = {str(spec.path): spec for spec in self.specs}
        calls = []
        live = {"identity": None, "sidecar": None}
        counts = {spec.name: 0 for spec in self.specs}

        def state_probe(expected=None):
            identity = live["identity"]
            if identity is None:
                return clean_state()
            return {
                **clean_state(),
                "server_pid_receipt_exists": True,
                "server_pid_receipt": identity["serving_pid"],
                "server_pid_create_time": identity["process_create_time"],
                "listener_pids_8199": [identity["serving_pid"]],
                "expected_server_identity_live": expected == identity,
                "idle_gate_sidecar_exists": True,
                "idle_gate_sidecar": live["sidecar"],
            }

        def child_runner(command, environment, cwd):
            command = list(command)
            calls.append(command)
            self.assertEqual(Path(command[1]), self.layout.runner)
            self.assertEqual(Path(cwd), ROOT)
            self.assertEqual(environment["LAB_PORT"], "8199")
            self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
            self.assertNotIn("LAB_RESERVE_VRAM_GB", environment)
            self.assertNotIn("--force", command)
            spec = spec_by_path[command[2]]
            counts[spec.name] += 1
            run_number = counts[spec.name]
            nonce = command[command.index("--executor-cache-nonce") + 1]
            campaign_id, pair_index, role = self._nonce_identity(nonce)
            self.assertEqual(
                environment["LAB_MANAGER_PROBE_LOG"],
                str(
                    campaign.pair_log_path(
                        spec, pair_index, campaign_id, self.layout
                    ).resolve()
                ),
            )
            self.assertEqual(
                command[command.index("--manager-probe-phase") + 1], role
            )
            self.assertEqual(
                int(command[command.index("--completion-timeout-s") + 1]),
                campaign.completion_timeout_s(spec),
            )
            if run_number == 1:
                self.assertIsNone(live["identity"])
                pair_index = self.specs.index(spec) + 1
                live["identity"] = {
                    "serving_pid": 45000 + pair_index,
                    "process_create_time": 2000.0 + pair_index,
                }
                self.assertNotIn("--shutdown", command)
                runner_pid = 55000 + pair_index
                runner_create_time = 3000.0 + pair_index
                observation = {
                    **live["identity"],
                    "server_argv": self._server_argv(),
                    "observed_descendant_of_runner_pid": runner_pid,
                    "runner_process_create_time": runner_create_time,
                    "observed_at_ns": 1,
                }
            else:
                self.assertEqual(run_number, 2)
                self.assertIn("--shutdown", command)
            payload = self._write_receipt(
                spec, run_number, nonce, live["identity"]
            )
            live["sidecar"] = payload["preboot_gpu_idle_gate_sidecar"]
            if run_number == 2:
                self.layout.idle_gate_sidecar.unlink()
                live["identity"] = None
                live["sidecar"] = None
                return campaign.ChildOutcome(returncode=0)
            return campaign.ChildOutcome(
                returncode=0,
                runner_pid=runner_pid,
                runner_create_time=runner_create_time,
                descendant_server_instances=(observation,),
            )

        cleanup = mock.Mock(side_effect=AssertionError("cleanup must not run"))
        result = campaign.execute_campaign(
            campaign_id="mock-complete",
            layout=self.layout,
            child_runner=child_runner,
            state_probe=state_probe,
            manager_probe=lambda: campaign.manager_evidence(self.layout),
            cleanup_owned_server=cleanup,
        )
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(len(result["pairs"]), 6)
        self.assertEqual(len(calls), 12)
        self.assertEqual(counts, {spec.name: 2 for spec in self.specs})
        cleanup.assert_not_called()
        events = [
            json.loads(line)["event"]
            for line in self.layout.lifecycle.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(events.count("pair_verified"), 6)
        self.assertEqual(events[-1], "campaign_completed")
        logs = sorted(
            (
                self.results
                / "h3_canonical_canvas_campaign"
                / "server_logs"
            ).glob("mock-complete-*.log")
        )
        self.assertEqual(len(logs), 6)
        final_record = json.loads(
            self.layout.lifecycle.read_text(encoding="utf-8").splitlines()[-1]
        )
        final_audit = final_record["details"]["final_evidence_audit"]
        self.assertEqual(len(final_audit), 6)
        self.assertEqual(
            {row["manager_log"]["path"] for row in final_audit},
            {str(path.resolve()) for path in logs},
        )
        for row in final_audit:
            self.assertEqual(
                set(row["cold_vram"]),
                {
                    "baseline_vram_gb",
                    "absolute_peak_vram_gb",
                    "net_peak_vram_gb",
                    "elevated_baseline_lane",
                    "baseline_lane_stamp",
                },
            )
            self.assertEqual(row["cold_vram"]["net_peak_vram_gb"], 10.34)
            self.assertEqual(row["warm_vram"]["net_peak_vram_gb"], 10.34)
            self.assertEqual(row["cold_warm_baseline_drift_gb"], 0.0)
            self.assertFalse(row["cold_warm_baseline_drift_gating"])
            self.assertFalse(row["cold_baseline_advisory"]["gating"])
            self.assertFalse(row["warm_baseline_advisory"]["gating"])
            self.assertFalse(
                row["cold_warm_baseline_drift_advisory"]["gating"]
            )
            self.assertRegex(
                row["cold_prequeue_workload_scan_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertRegex(
                row["warm_prequeue_workload_scan_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertEqual(
                row["cold_prequeue_advisory_unreadable_process_count"], 1
            )
            self.assertEqual(
                row["warm_prequeue_advisory_unreadable_process_count"], 1
            )
            self.assertEqual(
                row["cold_preboot_advisory_unreadable_process_counts"],
                [1, 1, 1, 1, 1],
            )
            self.assertEqual(
                row["cold_preboot_display_active"],
                {
                    "target": "Enabled",
                    "samples": ["Enabled"] * 5,
                    "gating": False,
                },
            )
            self.assertEqual(
                row["cold_preboot_current_runner_exclusion_count"], 1
            )
            self.assertEqual(
                row["cold_prequeue_current_runner_exclusion_count"], 1
            )
            self.assertEqual(
                row["warm_prequeue_current_runner_exclusion_count"], 1
            )
            self.assertEqual(
                row["cold_prequeue_owned_server_exclusion_count"], 1
            )
            self.assertEqual(
                row["warm_prequeue_owned_server_exclusion_count"], 1
            )
            log_path = Path(row["manager_log"]["path"])
            self.assertEqual(row["manager_log"]["bytes"], log_path.stat().st_size)
            self.assertEqual(
                row["manager_log"]["sha256"],
                hashlib.sha256(log_path.read_bytes()).hexdigest(),
            )

    def test_default_cleanup_loads_absolute_runner_with_isolated_sys_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "shutdown-called.txt"
            fake_runner = root / "run_recipe_probe.py"
            fake_runner.write_bytes(
                (
                    "from pathlib import Path\n"
                    f"MARKER = Path({str(marker)!r})\n"
                    "def current_runner_exclusion_validation_errors(*args, **kwargs): return []\n"
                    "def owned_lab_server_exclusion_validation_errors(*args, **kwargs): return []\n"
                    "def gpu_idle_gate_validation_errors(*args, **kwargs): return []\n"
                    "def prequeue_known_workload_scan_validation_errors(*args, **kwargs): return []\n"
                    "def shutdown_lab_server():\n"
                    "    MARKER.write_bytes(b'called')\n"
                    "    return {'called': True}\n"
                ).encode("utf-8")
            )
            probe = root / "isolated_cleanup_probe.py"
            probe.write_bytes(
                (
                    "from dataclasses import replace\n"
                    "import importlib.util\n"
                    "import json\n"
                    "from pathlib import Path\n"
                    "import sys\n"
                    "campaign_path, fake_runner, scratch, repo_root = map(Path, sys.argv[1:])\n"
                    "sys.path.insert(0, str(scratch))\n"
                    "spec = importlib.util.spec_from_file_location('_isolated_h3_campaign', campaign_path)\n"
                    "module = importlib.util.module_from_spec(spec)\n"
                    "sys.modules[spec.name] = module\n"
                    "spec.loader.exec_module(module)\n"
                    "sys.path.remove(str(scratch))\n"
                    "module.DEFAULT_LAYOUT = replace(module.DEFAULT_LAYOUT, runner=fake_runner)\n"
                    "result = module._default_cleanup()\n"
                    "root_present = any(Path(value).resolve() == repo_root.resolve() for value in sys.path if value)\n"
                    "print(json.dumps({'result': result, 'root_present': root_present}))\n"
                ).encode("utf-8")
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(probe),
                    str(campaign.CAMPAIGN_SOURCE),
                    str(fake_runner),
                    str(ROOT / "scratch"),
                    str(ROOT),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(marker.read_bytes(), b"called")
            result = json.loads(completed.stdout)
            self.assertEqual(result["result"], {"called": True})
            self.assertFalse(result["root_present"])

    def test_first_child_failure_stops_without_force_or_follow_on_work(self):
        calls = []

        def child_runner(command, environment, cwd):
            calls.append(list(command))
            return 7

        with self.assertRaisesRegex(campaign.CampaignError, "returned 7"):
            campaign.execute_campaign(
                campaign_id="mock-fail",
                layout=self.layout,
                child_runner=child_runner,
                state_probe=lambda expected=None: clean_state(),
                manager_probe=lambda: campaign.manager_evidence(self.layout),
                cleanup_owned_server=mock.Mock(),
            )
        self.assertEqual(len(calls), 1)
        self.assertNotIn("--force", calls[0])
        events = [
            json.loads(line)["event"]
            for line in self.layout.lifecycle.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(events[-1], "campaign_failed")
        self.assertNotIn("pair_verified", events)

    def test_nonzero_cold_child_with_proved_live_server_is_cleaned(self):
        identity = {"serving_pid": 63000, "process_create_time": 4300.0}
        live = {"value": False}

        def state_probe(expected=None):
            if not live["value"]:
                return clean_state()
            return {
                **clean_state(),
                "server_pid_receipt_exists": True,
                "server_pid_receipt": identity["serving_pid"],
                "server_pid_create_time": identity["process_create_time"],
                "listener_pids_8199": [identity["serving_pid"]],
                "expected_server_identity_live": expected == identity,
            }

        def child_runner(command, environment, cwd):
            live["value"] = True
            return campaign.ChildOutcome(returncode=7)

        def cleanup():
            live["value"] = False
            return {"success": True, "proof": "test-owned"}

        with mock.patch.object(
            campaign, "pending_child_owned_server", return_value=identity
        ), self.assertRaisesRegex(campaign.CampaignError, "returned 7"):
            campaign.execute_campaign(
                campaign_id="proved-live-fail",
                layout=self.layout,
                child_runner=child_runner,
                state_probe=state_probe,
                manager_probe=lambda: campaign.manager_evidence(self.layout),
                cleanup_owned_server=cleanup,
            )
        self.assertFalse(live["value"])
        failure = json.loads(
            self.layout.lifecycle.read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertTrue(failure["details"]["owned_server_cleanup"]["attempted"])
        self.assertTrue(failure["details"]["owned_server_cleanup"]["success"])

    def test_rejected_cold_receipt_with_proved_live_server_is_cleaned(self):
        spec = self.specs[0]
        identity = {"serving_pid": 64000, "process_create_time": 4400.0}
        live = {"value": False}

        def state_probe(expected=None):
            if not live["value"]:
                return clean_state()
            return {
                **clean_state(),
                "server_pid_receipt_exists": True,
                "server_pid_receipt": identity["serving_pid"],
                "server_pid_create_time": identity["process_create_time"],
                "listener_pids_8199": [identity["serving_pid"]],
                "expected_server_identity_live": expected == identity,
            }

        def child_runner(command, environment, cwd):
            live["value"] = True
            nonce = command[command.index("--executor-cache-nonce") + 1]
            payload = self._write_receipt(spec, 1, nonce, identity)
            payload["gate_pass"] = False
            encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
            (self.results / f"{spec.name}_run1.json").write_bytes(encoded)
            (self.results / f"{spec.name}.json").write_bytes(encoded)
            return campaign.ChildOutcome(returncode=0)

        def cleanup():
            live["value"] = False
            return {"success": True, "proof": "test-owned"}

        with mock.patch.object(
            campaign, "pending_child_owned_server", return_value=identity
        ), self.assertRaisesRegex(campaign.CampaignError, "gate_pass"):
            campaign.execute_campaign(
                campaign_id="proved-live-receipt-fail",
                layout=self.layout,
                child_runner=child_runner,
                state_probe=state_probe,
                manager_probe=lambda: campaign.manager_evidence(self.layout),
                cleanup_owned_server=cleanup,
            )
        self.assertFalse(live["value"])
        failure = json.loads(
            self.layout.lifecycle.read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertTrue(failure["details"]["owned_server_cleanup"]["success"])


if __name__ == "__main__":
    unittest.main()
