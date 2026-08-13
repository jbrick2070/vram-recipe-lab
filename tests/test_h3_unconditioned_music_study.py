from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_h3_unconditioned_music_study as builder
import h3_manager_offline_guard as guard
import record_h3_music_operator_launch as operator_launch
import record_h3_music_recovery as recovery
import run_h3_unconditioned_music_campaign as campaign
import run_recipe


class H3UnconditionedMusicRecipeTests(unittest.TestCase):
    def test_matrix_is_eleven_immutable_one_variable_cells(self):
        recipes = builder.build_matrix()
        plan = builder.plan(recipes)
        self.assertEqual(len(recipes), 11)
        self.assertEqual(plan["logical_cells"], 14)
        self.assertEqual(plan["warm_gate_executions"], 22)
        self.assertEqual(
            recipes[builder.SHARED_CONTROL]["study"]["logical_roles"],
            ["job0_A", "job1_seed42", "job2_A", "job3_f124"],
        )
        self.assertEqual(plan["saved_by_exact_control_reuse"]["unique_cells"], 3)
        for row in plan["cells"]:
            path = Path(row["path"])
            self.assertTrue(path.is_file())
            self.assertEqual(builder.sha256_file(path), row["sha256"])

    def test_every_cell_keeps_flat_v3_picture_only_native_audio(self):
        for recipe in builder.build_matrix().values():
            prompt = recipe["prompt"]
            ref = prompt["7"]["inputs"]
            self.assertEqual(ref["ref_images.ref_image_0"], ["11", 0])
            self.assertNotIn("ref_images", ref)
            self.assertFalse(any(key.startswith("ref_audio") for key in ref))
            self.assertNotIn(
                "LoadAudio", [node["class_type"] for node in prompt.values()]
            )
            self.assertEqual(prompt["15"]["inputs"], {"samples": ["8", 0], "vae": ["4", 0]})
            self.assertEqual(prompt["10"]["inputs"]["audio"], ["15", 0])
            frames = ref["length"]
            self.assertEqual((frames - 5) % 17, 0)

    def test_job0_motion_prompts_follow_wordless_contract(self):
        recipes = builder.build_matrix()
        for name in (
            "h3_unconditioned_music_motion_small_seed42_f124",
            "h3_unconditioned_music_motion_large_seed42_f124",
        ):
            prompt = recipes[name]["prompt"]["7"]["inputs"]["prompt"].lower()
            self.assertIn("wordless", prompt)
            for word in (*builder.FORBIDDEN_JOB0_WORDS, "audio", "sound", "music", "voice"):
                self.assertNotIn(word, prompt)

    def test_historical_positive_anchor_is_explicitly_confounded(self):
        evidence = builder.evidence_receipts()
        anchor = evidence["confounded_positive_music_anchor"]
        self.assertIn("lineage/human anchor only", anchor["disposition"])
        self.assertNotEqual(
            anchor["recipe_sha256"], builder.SOURCE_EVIDENCE["current_flat_v3_recipe"]["sha256"]
        )
        for recipe in builder.build_matrix().values():
            self.assertIs(
                recipe["study"]["historical_positive_anchor_is_execution_reusable"],
                False,
            )

    def test_builder_default_is_read_only(self):
        before = {
            path: path.read_bytes()
            for path in builder.RECIPES.glob("h3_unconditioned_music_*.json")
        }
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main([]), 0)
        after = {
            path: path.read_bytes()
            for path in builder.RECIPES.glob("h3_unconditioned_music_*.json")
        }
        self.assertEqual(before, after)


class H3ManagerOfflineGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.log = Path(self.temp.name) / "attempt.log"
        self.argv = campaign.expected_server_argv()
        self.config = (
            campaign.DEFAULT_LAYOUT.actual_user_directory
            / "__manager"
            / "config.ini"
        )

    def tearDown(self):
        self.temp.cleanup()

    def _text(
        self,
        *,
        mode="offline",
        omit_mode=False,
        duplicate=False,
        execution=False,
        network=False,
        late=False,
        omit_preboot=False,
        duplicate_preboot=False,
        extra_rows=(),
    ):
        preboot = guard.preboot_log_line(
            campaign.DEFAULT_LAYOUT.actual_user_directory,
            dict(guard.OFFLINE_ENVIRONMENT),
        ).decode("utf-8").rstrip("\n")
        rows = [] if omit_preboot else [preboot]
        if duplicate_preboot:
            rows.append(preboot)
        rows.append(f"** ComfyUI-Manager config path: {self.config}")
        if late:
            rows.append(guard.STARTUP_MARKER)
        if not omit_mode:
            rows.append(f"[INFO] [ComfyUI-Manager] network_mode: {mode}")
        if duplicate:
            rows.append("[ComfyUI-Manager] network_mode: offline")
        if not late:
            rows.append(guard.STARTUP_MARKER)
        if execution:
            rows.append("got prompt")
        if network:
            rows.append("FETCH ComfyRegistry Data: 5/100")
        rows.extend(extra_rows)
        rows.append("To see the GUI go to: http://127.0.0.1:8199")
        return "\n".join(rows) + "\n"

    def _scan(self, **kwargs):
        self.log.write_text(self._text(**kwargs), encoding="utf-8")
        return guard.scan_log(
            self.log,
            self.argv,
            expected_url="http://127.0.0.1:8199",
            require_pre_prompt=not kwargs.get("execution", False),
        )

    def test_exact_one_offline_line_is_authoritative(self):
        scan = self._scan()
        self.assertEqual(scan["status"], "pass")
        authority = scan["authoritative_server_reported_mode"]
        self.assertEqual(authority["observed_values"], ["offline"])
        self.assertTrue(authority["mode_precedes_startup_completion"])
        self.assertEqual(guard.validate_scan_binding(scan, self.log, self.argv), [])
        forged = copy.deepcopy(scan)
        forged["config_announcements"] = []
        self.assertTrue(guard.validate_scan_binding(forged, self.log, self.argv))

    def test_missing_public_duplicate_late_or_network_fails(self):
        variants = (
            {"omit_mode": True},
            {"mode": "public"},
            {"duplicate": True},
            {"late": True},
            {"network": True},
            {"omit_preboot": True},
            {"duplicate_preboot": True},
        )
        for variant in variants:
            with self.subTest(variant=variant):
                scan = self._scan(**variant)
                self.assertEqual(scan["status"], "fail")
                self.assertTrue(scan["errors"])

    def test_real_manager_update_and_check_markers_all_fail(self):
        markers = (
            "Start updating...",
            "Start update check...",
            "Update done.",
            "Update check done.",
            "All extensions are already up-to-date.",
        )
        for marker in markers:
            with self.subTest(marker=marker):
                scan = self._scan(extra_rows=(marker,))
                self.assertEqual(scan["status"], "fail")
                self.assertTrue(scan["network_markers"])

    def test_real_manager_install_restore_and_fixer_markers_all_fail(self):
        markers = (
            "## ComfyUI-Manager: installing dependencies. (GitPython)",
            "[ComfyUI-Manager] Restore snapshot.",
            "[ComfyUI-Manager] Starting dependency installation/(de)activation for the extension",
            "## ComfyUI-Manager: EXECUTE => ['pip', 'install', 'x']",
            "Install: pip packages for 'node'",
            "[ComfyUI-Manager] 'comfy' python package is uninstalled.",
            "[ComfyUI-Manager] restore PyTorch to 2.10.0+cu130",
            "[ComfyUI-Manager] 'opencv' dependencies were fixed: ['opencv-python']",
            "[ComfyUI-Manager] 'comfyui-frontend-package' dependency were fixed",
            "[ComfyUI-Manager] Restarting to reapply dependency installation.",
        )
        for marker in markers:
            with self.subTest(marker=marker):
                scan = self._scan(extra_rows=(marker,))
                self.assertEqual(scan["status"], "fail")
                self.assertTrue(scan["mutation_markers"])

    def test_prestartup_state_rejects_pending_and_implicit_mutations(self):
        user = Path(self.temp.name) / "user"
        startup = user / "__manager" / "startup-scripts"
        startup.mkdir(parents=True)
        (user / "__manager" / "config.ini").write_text(
            "[default]\nnetwork_mode = offline\nuse_uv = False\n",
            encoding="utf-8",
        )
        state = guard.prestartup_state_evidence(user)
        self.assertEqual(state["startup_scripts"]["entry_count"], 0)
        self.assertTrue(state["pip_fixer_noop"]["conditions"]["pip_auto_fix_absent"])

        install = startup / "install-scripts.txt"
        install.write_text("queued mutation\n", encoding="utf-8")
        with self.assertRaises(guard.ManagerProbeError):
            guard.prestartup_state_evidence(user)
        install.unlink()
        pip_auto_fix = user / "__manager" / "pip_auto_fix.list"
        pip_auto_fix.write_text("torch==0\n", encoding="utf-8")
        with self.assertRaises(guard.ManagerProbeError):
            guard.prestartup_state_evidence(user)
        pip_auto_fix.unlink()

        distributions = guard._installed_distribution_map()
        bad = copy.deepcopy(distributions)
        bad["comfy"] = [
            {"distribution_name": "comfy", "version": "1.0"}
        ]
        with self.assertRaises(guard.ManagerProbeError):
            guard._pip_fixer_noop_evidence(bad)
        bad = copy.deepcopy(distributions)
        bad["opencv_python_headless"][0]["version"] = "0.0.1"
        with self.assertRaises(guard.ManagerProbeError):
            guard._pip_fixer_noop_evidence(bad)

        real_import = guard.importlib.import_module

        def missing_dependency(name):
            if name == "git":
                raise ModuleNotFoundError("git")
            return real_import(name)

        with mock.patch.object(
            guard.importlib, "import_module", side_effect=missing_dependency
        ):
            with self.assertRaises(guard.ManagerProbeError):
                guard.prestartup_state_evidence(user)

        config = user / "__manager" / "config.ini"
        config.write_text(
            "[default]\nnetwork_mode = offline\nuse_uv = True\n",
            encoding="utf-8",
        )
        with self.assertRaises(guard.ManagerProbeError):
            guard.prestartup_state_evidence(user)

    def test_preboot_record_detects_state_change_after_byte_zero(self):
        user = Path(self.temp.name) / "preboot-user"
        startup = user / "__manager" / "startup-scripts"
        startup.mkdir(parents=True)
        (user / "__manager" / "config.ini").write_text(
            "[default]\nnetwork_mode = offline\nuse_uv = False\n",
            encoding="utf-8",
        )
        argv = list(self.argv)
        argv[argv.index("--user-directory") + 1] = str(user.resolve())
        marker = guard.preboot_log_line(
            user, dict(guard.OFFLINE_ENVIRONMENT)
        ).decode("utf-8")
        (startup / "restore-snapshot.json").write_text("{}\n", encoding="utf-8")
        config = user / "__manager" / "config.ini"
        self.log.write_text(
            marker
            + f"** ComfyUI-Manager config path: {config}\n"
            + "[ComfyUI-Manager] network_mode: offline\n"
            + guard.STARTUP_MARKER
            + "\nTo see the GUI go to: http://127.0.0.1:8199\n",
            encoding="utf-8",
        )
        scan = guard.scan_log(self.log, argv, require_pre_prompt=True)
        self.assertEqual(scan["status"], "fail")
        self.assertTrue(any("prestartup" in row for row in scan["errors"]))

    def test_preboot_record_hash_and_environment_tampering_fail(self):
        text = self._text()
        first, remainder = text.split("\n", 1)
        record = json.loads(first[len(guard.PREBOOT_MARKER) :])
        record["offline_environment"]["set_nonsecret"]["PIP_NO_INDEX"] = "0"
        forged = guard.PREBOOT_MARKER + json.dumps(
            record, sort_keys=True, separators=(",", ":")
        )
        self.log.write_text(forged + "\n" + remainder, encoding="utf-8")
        scan = guard.scan_log(self.log, self.argv, require_pre_prompt=True)
        self.assertEqual(scan["status"], "fail")
        self.assertTrue(any("preboot" in row.lower() for row in scan["errors"]))

    def test_ansi_before_or_inside_preboot_record_cannot_spoof_byte_zero(self):
        valid = self._text()
        for forged in (
            "\x1b[31m" + valid,
            valid.replace(guard.PREBOOT_MARKER, guard.PREBOOT_MARKER + "\x1b[31m", 1),
        ):
            with self.subTest(prefix=repr(forged[:40])):
                self.log.write_text(forged, encoding="utf-8")
                scan = guard.scan_log(
                    self.log, self.argv, require_pre_prompt=True
                )
                self.assertEqual(scan["status"], "fail")
                self.assertTrue(scan["errors"])
                if forged.startswith("\x1b"):
                    self.assertFalse(scan["preboot_record_starts_at_byte_zero"])

    def test_pre_prompt_gate_rejects_any_execution_marker(self):
        self.log.write_text(self._text(execution=True), encoding="utf-8")
        scan = guard.scan_log(
            self.log, self.argv, require_pre_prompt=True
        )
        self.assertEqual(scan["status"], "fail")
        self.assertTrue(any("before the pre-prompt" in row for row in scan["errors"]))

    def test_runner_phase_is_explicit_and_default_remains_disabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(run_recipe.manager_probe_phase(["run_recipe.py"]))
        with mock.patch.dict(
            os.environ, {run_recipe.MANAGER_PROBE_ENV: "1"}, clear=True
        ):
            self.assertEqual(
                run_recipe.manager_probe_phase(
                    [run_recipe.MANAGER_PROBE_PHASE_FLAG, "cold"]
                ),
                "cold",
            )
            with self.assertRaises(ValueError):
                run_recipe.manager_probe_phase([])

    def test_runner_exclusively_writes_real_preboot_record_at_byte_zero(self):
        path = Path(self.temp.name) / "exclusive.log"
        environment = dict(guard.OFFLINE_ENVIRONMENT)
        with mock.patch.dict(os.environ, environment, clear=True):
            evidence = run_recipe.initialize_manager_probe_log(path)
            retained = path.read_bytes()
            self.assertTrue(retained.startswith(guard.PREBOOT_MARKER.encode("utf-8")))
            self.assertEqual(evidence["bytes"], len(retained))
            self.assertEqual(evidence["sha256"], guard.sha256_bytes(retained))
            with self.assertRaises(run_recipe.PreflightError):
                run_recipe.initialize_manager_probe_log(path)
            self.assertEqual(path.read_bytes(), retained)

    def test_boot_script_has_narrow_opt_in_and_empty_default(self):
        default_path = ROOT / "boot_lab_server.cmd"
        default = default_path.read_text(encoding="utf-8")
        executable = "\n".join(
            line
            for line in default.splitlines()
            if not line.lstrip().lower().startswith(("rem ", "::"))
        )
        self.assertNotIn("ComfyUI-Manager", executable)
        self.assertEqual(
            builder.sha256_file(default_path),
            "5f9c313a050e2cec6356c9d31b54cb7e0f1825b0a5314ec7eec436466036ccb4",
        )
        test_boot = (ROOT / "boot_h3_manager_offline_test.cmd").read_text(
            encoding="utf-8"
        )
        self.assertIn("ComfyUI-Manager", test_boot)
        self.assertIn('if not "%LAB_MANAGER_OFFLINE_PROBE%"=="1"', test_boot)
        self.assertIn("%LAB_MANAGER_PROBE_LOG%", test_boot)
        self.assertIn('if not "%HF_HUB_OFFLINE%"=="1"', test_boot)
        self.assertIn('if not "%TRANSFORMERS_OFFLINE%"=="1"', test_boot)
        self.assertIn('if not "%PIP_NO_INDEX%"=="1"', test_boot)
        self.assertIn(
            'if not "%PIP_DISABLE_PIP_VERSION_CHECK%"=="1"', test_boot
        )
        self.assertIn('if not "%UV_OFFLINE%"=="1"', test_boot)
        self.assertIn('if not "%GIT_TERMINAL_PROMPT%"=="0"', test_boot)
        self.assertIn("if defined HF_API_TOKEN", test_boot)
        runner = (ROOT / "run_recipe.py").read_text(encoding="utf-8")
        self.assertIn("os.O_CREAT | os.O_EXCL | os.O_WRONLY", runner)


class H3UnconditionedMusicCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp_owner = tempfile.TemporaryDirectory()
        self.temp = Path(self.temp_owner.name)
        self.results = self.temp / "results"
        self.outputs = self.temp / "outputs"
        self.results.mkdir()
        self.outputs.mkdir()
        base = campaign.DEFAULT_LAYOUT
        self.layout = campaign.canon.Layout(
            root=ROOT,
            results=self.results,
            outputs=self.outputs,
            lifecycle=self.results / "h3_unconditioned_music_campaign" / "lifecycle.jsonl",
            runner=ROOT / "run_recipe.py",
            lab_locks=ROOT / "lab_locks.py",
            boot_cmd=ROOT / "boot_lab_server.cmd",
            actual_manager_config=base.actual_manager_config,
            lab_manager_config=base.lab_manager_config,
            actual_user_directory=base.actual_user_directory,
            comfyui_main=base.comfyui_main,
            python=base.python,
            gpu_lock=self.temp / ".gpu.lock",
            suite_lock=self.temp / ".suite.lock",
            server_pid=self.temp / ".server.pid",
            queue_quarantine=self.temp / ".queue.quarantine.json",
        )

    def tearDown(self):
        self.temp_owner.cleanup()

    def test_read_only_runbook_has_eleven_pairs_and_unique_nonces(self):
        plan = campaign.runbook("unit-test", self.layout)
        self.assertEqual(plan["pair_count"], 11)
        self.assertEqual(plan["logical_cell_count"], 14)
        self.assertEqual(plan["actual_execution_count"], 22)
        self.assertEqual(plan["control_reuse"]["saved_executions"], 6)
        self.assertEqual(plan["boot_invariants"]["reserve_vram_gib"], 12.0)
        self.assertTrue(plan["boot_invariants"]["cache_classic"])
        nonces = []
        logs = []
        for pair in plan["pairs"]:
            cold = pair["cold"]
            warm = pair["warm_shutdown"]
            self.assertIn("--manager-offline-test", cold)
            self.assertEqual(cold[cold.index("--manager-probe-phase") + 1], "cold")
            self.assertEqual(warm[warm.index("--manager-probe-phase") + 1], "warm")
            self.assertIn("--disable-pinned-memory", cold)
            self.assertNotIn("--force", cold + warm)
            self.assertEqual(warm[-1], "--shutdown")
            nonces.extend(
                (
                    cold[cold.index("--executor-cache-nonce") + 1],
                    warm[warm.index("--executor-cache-nonce") + 1],
                )
            )
            logs.append(pair["manager_log"])
        self.assertEqual(len(set(nonces)), 22)
        self.assertEqual(len(set(logs)), 11)

    def test_attempt_002_runbook_uses_run2_cold_then_run3_warm(self):
        plan = campaign.runbook(
            campaign.RESUME_CAMPAIGN_ID,
            self.layout,
            resume_attempt_001=True,
        )
        first = plan["pairs"][0]["receipt_schedule"]
        self.assertEqual(
            (
                first["cold_run_number"],
                first["cold_config_run_count"],
                first["warm_run_number"],
                first["warm_config_run_count"],
            ),
            (2, 1, 3, 2),
        )
        self.assertEqual(first["allowed_run_numbers"], [1, 2, 3])
        for pair in plan["pairs"][1:]:
            schedule = pair["receipt_schedule"]
            self.assertEqual(
                (
                    schedule["cold_run_number"],
                    schedule["cold_config_run_count"],
                    schedule["warm_run_number"],
                    schedule["warm_config_run_count"],
                ),
                (1, 1, 2, 2),
            )

    def test_attempt_003_runbook_carries_pair1_and_executes_only_pairs2_to11(self):
        plan = campaign.runbook(
            campaign.RESUME_ATTEMPT2_CAMPAIGN_ID,
            self.layout,
            resume_attempt_002=True,
        )
        self.assertEqual(plan["pair_count"], 11)
        self.assertEqual(plan["carried_pair_count"], 1)
        self.assertEqual(plan["executed_pair_count"], 10)
        self.assertEqual(plan["actual_execution_count"], 20)
        self.assertEqual(plan["new_execution_count"], 20)
        self.assertEqual(plan["study_leg_count"], 22)
        self.assertEqual(plan["orphan_historical_cold_count"], 1)
        self.assertEqual(plan["evidence_execution_count"], 23)

        carried = plan["pairs"][0]
        self.assertEqual(carried["action"], "carry_forward")
        self.assertEqual(carried["source_campaign_id"], campaign.RESUME_CAMPAIGN_ID)
        self.assertEqual(carried["new_executions"], 0)
        self.assertNotIn("cold", carried)
        self.assertNotIn("warm_shutdown", carried)
        self.assertEqual(
            (
                carried["receipt_schedule"]["cold_run_number"],
                carried["receipt_schedule"]["warm_run_number"],
                carried["receipt_schedule"]["allowed_run_numbers"],
            ),
            (2, 3, [1, 2, 3]),
        )

        nonces = []
        for expected_index, pair in enumerate(plan["pairs"][1:], start=2):
            self.assertEqual(pair["pair_index"], expected_index)
            self.assertEqual(pair["action"], "execute")
            self.assertEqual(pair["new_executions"], 2)
            self.assertEqual(pair["receipt_schedule"]["cold_run_number"], 1)
            self.assertEqual(pair["receipt_schedule"]["warm_run_number"], 2)
            for command in (pair["cold"], pair["warm_shutdown"]):
                self.assertNotIn("--force", command)
                nonce = command[command.index("--executor-cache-nonce") + 1]
                self.assertIn(f":p{expected_index:02d}:", nonce)
                nonces.append(nonce)
        self.assertEqual(len(nonces), 20)
        self.assertEqual(len(set(nonces)), 20)
        self.assertFalse(any(":p01:" in nonce for nonce in nonces))

        with self.assertRaisesRegex(campaign.CampaignError, "exact campaign id"):
            campaign.runbook(
                "wrong-attempt-003",
                self.layout,
                resume_attempt_002=True,
            )

    def test_attempt_003_operator_transport_binds_exact_paths_and_descriptors(self):
        paths = campaign.operator_transport_paths(self.layout)
        paths["attempt_directory"].mkdir(parents=True)
        sources = campaign.source_evidence(self.layout)
        with paths["stdout"].open("wb", buffering=0) as stdout, paths[
            "stderr"
        ].open("wb", buffering=0) as stderr:
            evidence = campaign.validate_operator_transport(
                paths["stdout"],
                paths["stderr"],
                sources,
                self.layout,
                stdout_fd=stdout.fileno(),
                stderr_fd=stderr.fileno(),
            )
        self.assertEqual(
            evidence["contract"], campaign.operator_log_contract(sources, self.layout)
        )
        self.assertEqual(
            evidence["attempt_directory_entries"], ["stderr.log", "stdout.log"]
        )
        self.assertFalse(evidence["growing_log_bytes_hashed_as_sources"])
        self.assertNotEqual(
            (
                evidence["fd_identities"]["stdout"]["device"],
                evidence["fd_identities"]["stdout"]["inode"],
            ),
            (
                evidence["fd_identities"]["stderr"]["device"],
                evidence["fd_identities"]["stderr"]["inode"],
            ),
        )
        self.assertEqual(evidence["fd_identities"]["stdout"]["link_count"], 1)
        self.assertEqual(evidence["fd_identities"]["stderr"]["link_count"], 1)
        self.assertEqual(
            evidence["contract"]["launcher_source"]["sha256"],
            campaign.OPERATOR_LAUNCHER_SHA256,
        )
        self.assertEqual(
            evidence["contract"]["recorder_source"]["sha256"],
            campaign.OPERATOR_RECORDER_SHA256,
        )

    def test_attempt_003_operator_contract_exactly_matches_frozen_recorder(self):
        sources = campaign.source_evidence()
        self.assertEqual(
            campaign.operator_log_contract(sources),
            operator_launch.expected_operator_log_contract(ROOT),
        )

    def test_attempt_003_operator_transport_rejects_extra_or_hardlinked_logs(self):
        paths = campaign.operator_transport_paths(self.layout)
        paths["attempt_directory"].mkdir(parents=True)
        paths["stdout"].write_bytes(b"")
        paths["stderr"].write_bytes(b"")
        extra = paths["attempt_directory"] / "extra.txt"
        extra.write_bytes(b"")
        with self.assertRaisesRegex(campaign.CampaignError, "entries drifted"):
            campaign.validate_operator_transport(
                paths["stdout"], paths["stderr"], {}, self.layout
            )

        extra.unlink()
        for label in ("stdout", "stderr"):
            external_link = self.temp / f"external-{label}-hardlink.log"
            os.link(paths[label], external_link)
            with self.subTest(label=label), self.assertRaisesRegex(
                campaign.CampaignError, "external hardlinks"
            ):
                campaign.validate_operator_transport(
                    paths["stdout"], paths["stderr"], {}, self.layout
                )
            external_link.unlink()

        paths["stderr"].unlink()
        os.link(paths["stdout"], paths["stderr"])
        with self.assertRaisesRegex(campaign.CampaignError, "external hardlinks"):
            campaign.validate_operator_transport(
                paths["stdout"], paths["stderr"], {}, self.layout
            )

    def test_attempt_003_requires_the_exact_unextended_attempt2_boundary(self):
        self.layout.lifecycle.parent.mkdir(parents=True)
        prefix = campaign.LIFECYCLE.read_bytes()[
            : campaign.ATTEMPT2_LIFECYCLE_PREFIX_BYTES
        ]
        self.layout.lifecycle.write_bytes(prefix + b"{}\n")
        clean = json.loads(
            campaign.attempt2_recovery_receipt_path().read_text(encoding="utf-8")
        )["current_clean_state"]
        with self.assertRaisesRegex(campaign.CampaignError, "immediately after"):
            campaign.verify_attempt2_recovery_receipt({}, clean, self.layout)

    def test_canonical_monitor_accepts_only_parameterized_music_lane(self):
        identity = {"serving_pid": 51136, "process_create_time": 1234.5}
        observation = {
            **identity,
            "server_argv": campaign.expected_server_argv(self.layout),
            "observed_descendant_of_runner_pid": 50000,
            "runner_process_create_time": 1200.0,
            "observed_at_ns": 1,
        }
        outcome = campaign.canon.ChildOutcome(
            returncode=0,
            runner_pid=50000,
            runner_create_time=1200.0,
            descendant_server_instances=(observation,),
        )
        campaign.canon.require_observed_child_server(
            outcome,
            identity,
            self.layout,
            campaign.expected_server_argv,
        )
        with self.assertRaises(campaign.CampaignError):
            campaign.canon.require_observed_child_server(
                outcome, identity, self.layout
            )
        errored = campaign.canon.ChildOutcome(
            **{
                **outcome.__dict__,
                "ownership_monitor_errors": ("transient-but-unproved",),
            }
        )
        with self.assertRaisesRegex(campaign.CampaignError, "monitor reported"):
            campaign.canon.require_observed_child_server(
                errored,
                identity,
                self.layout,
                campaign.expected_server_argv,
            )

    def test_transitional_receipted_wrapper_is_not_observed_before_listener(self):
        runner = mock.Mock()
        runner.create_time.return_value = 1200.0
        child = mock.Mock()
        child.pid = 51136
        runner.children.return_value = [child]
        server = mock.Mock()
        server.create_time.return_value = 1234.5

        def process(pid):
            return runner if pid == 50000 else server

        with mock.patch.object(
            campaign.canon, "_read_pid_receipt", return_value=51136
        ), mock.patch.object(
            campaign.canon.psutil, "Process", side_effect=process
        ), mock.patch.object(
            campaign.canon, "_listener_pids", return_value=[]
        ), mock.patch.object(
            campaign.canon, "_live_server_argv"
        ) as live_argv:
            self.assertIsNone(
                campaign.canon._observe_descendant_server(
                    50000,
                    1200.0,
                    self.layout,
                    campaign.validate_server_argv,
                )
            )
            live_argv.assert_not_called()

    def test_child_environment_scrubs_secrets_and_lane_injection(self):
        log = self.results / "h3_unconditioned_music_campaign" / "server_logs" / "x.log"
        environment = campaign.child_environment(
            log,
            {
                "LAB_RESERVE_VRAM_GB": "99",
                "LAB_MANAGER_OFFLINE_PROBE": "1",
                "HF_API_TOKEN": "secret",
            },
        )
        self.assertEqual(environment["LAB_RESERVE_VRAM_GB"], "12")
        self.assertEqual(environment["LAB_CACHE_CLASSIC"], "1")
        self.assertNotIn("LAB_MANAGER_OFFLINE_PROBE", environment)
        self.assertNotIn("HF_API_TOKEN", environment)
        self.assertEqual(environment["LAB_MANAGER_PROBE_LOG"], str(log.resolve()))
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")

    def test_server_argv_pins_proven_reserve_cache_lane(self):
        argv = campaign.expected_server_argv(self.layout)
        self.assertEqual(argv[argv.index("--reserve-vram") + 1], "12")
        self.assertIn("--cache-classic", argv)
        self.assertIn("--disable-pinned-memory", argv)
        self.assertEqual(campaign.validate_server_argv(argv, self.layout), argv)
        bad = list(argv)
        bad[bad.index("--reserve-vram") + 1] = "11"
        with self.assertRaises(campaign.CampaignError):
            campaign.validate_server_argv(bad, self.layout)

    def test_source_evidence_hash_binds_imported_canonical_campaign(self):
        sources = campaign.source_evidence(self.layout)
        pinned = sources["campaign_canonical"]
        self.assertEqual(
            pinned["sha256"],
            campaign.canon.sha256_file(campaign.CANONICAL_CAMPAIGN),
        )
        drifted = copy.deepcopy(sources)
        drifted["campaign_canonical"]["sha256"] = "0" * 64
        with self.assertRaises(campaign.CampaignError):
            campaign.require_same_sources(sources, drifted, "unit drift")

    def test_attempt_002_control_preflight_allows_only_preserved_run1(self):
        spec = campaign.load_specs(self.layout)[0]
        (self.results / f"{spec.name}.json").write_bytes(b"same\n")
        (self.results / f"{spec.name}_run1.json").write_bytes(b"same\n")
        (self.outputs / f"{spec.prefix}_00001_.mp4").write_bytes(b"video")
        log = campaign.pair_log_path(
            spec, 1, campaign.RESUME_CAMPAIGN_ID, self.layout
        )
        campaign.ensure_pristine_pair(
            spec,
            log,
            self.layout,
            resume_attempt_001=True,
            pair_index=1,
        )
        (self.results / f"{spec.name}_run2.json").write_bytes(b"unexpected\n")
        with self.assertRaisesRegex(campaign.CampaignError, "exactly preserved"):
            campaign.ensure_pristine_pair(
                spec,
                log,
                self.layout,
                resume_attempt_001=True,
                pair_index=1,
            )

    def test_verify_pair_accepts_dynamic_run2_cold_run3_warm_schedule(self):
        spec = campaign.load_specs(self.layout)[0]
        shared = {
            "run_identity_sha256": "a" * 64,
            "identity": {"same": True},
            "server_instance": {"serving_pid": 1, "process_create_time": 2.0},
            "server_argv": campaign.expected_server_argv(self.layout),
        }
        cold = {
            **shared,
            "receipt_sha256": "b" * 64,
            "artifact": {"sha256": "c" * 64},
            "artifact_path": str(self.outputs / f"{spec.prefix}_00002_.mp4"),
            "queued_prompt_sha256": "d" * 64,
        }
        warm = {
            **shared,
            "receipt_sha256": "e" * 64,
            "artifact": {"sha256": "f" * 64},
            "artifact_path": str(self.outputs / f"{spec.prefix}_00003_.mp4"),
            "queued_prompt_sha256": "1" * 64,
        }
        with mock.patch.object(
            campaign, "verify_run_receipt", side_effect=(cold, warm)
        ) as verify, mock.patch.object(
            campaign, "verify_final_log", return_value={"log": {"sha256": "2" * 64}}
        ):
            pair = campaign.verify_pair(
                spec,
                1,
                campaign.RESUME_CAMPAIGN_ID,
                {},
                self.temp / "attempt-002.log",
                self.layout,
                cold_run_number=2,
                cold_config_run_count=1,
                warm_run_number=3,
                warm_config_run_count=2,
                allowed_run_numbers=(1, 2, 3),
            )
        self.assertEqual(pair["cold"], cold)
        self.assertEqual(pair["warm"], warm)
        self.assertEqual(verify.call_args_list[0].args[1], 2)
        self.assertEqual(verify.call_args_list[0].kwargs["role"], "cold")
        self.assertEqual(
            verify.call_args_list[0].kwargs["expected_config_run_count"], 1
        )
        self.assertEqual(verify.call_args_list[1].args[1], 3)
        self.assertEqual(verify.call_args_list[1].kwargs["role"], "warm")
        self.assertEqual(
            verify.call_args_list[1].kwargs["expected_config_run_count"], 2
        )

    def test_resume_rehashes_preserved_run1_after_each_child_leg(self):
        prior = campaign.canon.AppendOnlyLifecycle(
            self.layout.lifecycle, campaign.FAILED_CAMPAIGN_ID
        )
        for index in range(5):
            prior.append(f"prior-{index}", {"index": index})
        spec = campaign.load_specs(self.layout)[0]
        identity = {"serving_pid": 51136, "process_create_time": 1234.5}
        clean = {
            "gpu_lock_exists": False,
            "suite_lock_exists": False,
            "server_pid_receipt_exists": False,
            "server_pid_receipt": None,
            "server_pid_create_time": None,
            "queue_quarantine_exists": False,
            "expected_server_identity_live": False,
            "listener_pids_8199": [],
        }
        warm = {
            **clean,
            "server_pid_receipt_exists": True,
            "server_pid_receipt": identity["serving_pid"],
            "server_pid_create_time": identity["process_create_time"],
            "expected_server_identity_live": True,
            "listener_pids_8199": [identity["serving_pid"]],
        }
        states = iter((clean, clean, warm, warm, clean))
        preserved = {
            "campaign_id": campaign.FAILED_CAMPAIGN_ID,
            "lifecycle_prefix": {},
            "run1_receipt": {},
            "manager_log": {},
            "artifact": {},
            "run1_semantics": {},
            "alias_equal_run1_required": False,
        }
        child_calls = []

        def child(command, environment, cwd):
            child_calls.append(list(command))
            return campaign.canon.ChildOutcome(returncode=0)

        with mock.patch.object(
            campaign, "load_specs", return_value=[spec]
        ), mock.patch.object(
            campaign, "runbook", return_value={"pairs": []}
        ), mock.patch.object(
            campaign, "source_evidence", return_value={"frozen": True}
        ), mock.patch.object(
            campaign, "ensure_pristine_pair"
        ), mock.patch.object(
            campaign, "verify_recovery_receipt", return_value={"valid": True}
        ), mock.patch.object(
            campaign,
            "verify_failed_attempt_evidence",
            return_value=preserved,
        ) as preserve_check, mock.patch.object(
            campaign,
            "verify_run_receipt",
            return_value={"server_instance": identity},
        ) as receipt_check, mock.patch.object(
            campaign.canon, "require_observed_child_server"
        ), mock.patch.object(
            campaign,
            "verify_pair",
            side_effect=campaign.CampaignError("intentional stop after warm"),
        ) as pair_check:
            with self.assertRaisesRegex(campaign.CampaignError, "intentional stop"):
                campaign.execute_campaign(
                    campaign_id=campaign.RESUME_CAMPAIGN_ID,
                    campaign_layout=self.layout,
                    child_runner=child,
                    state_probe=lambda expected=None: copy.deepcopy(next(states)),
                    cleanup_owned_server=lambda: {"success": True},
                    resume_attempt_001=True,
                )
        self.assertEqual(len(child_calls), 2)
        self.assertEqual(
            [call.kwargs["require_alias_run1"] for call in preserve_check.call_args_list],
            [True, False, False],
        )
        self.assertEqual(receipt_check.call_args.args[1], 2)
        self.assertEqual(receipt_check.call_args.kwargs["role"], "cold")
        self.assertEqual(
            receipt_check.call_args.kwargs["expected_config_run_count"], 1
        )
        self.assertEqual(pair_check.call_args.kwargs["cold_run_number"], 2)
        self.assertEqual(pair_check.call_args.kwargs["warm_run_number"], 3)

    def test_campaign_accepts_only_literal_sha_pinned_recovery_receipt(self):
        payload = json.loads(
            campaign.recovery_receipt_path().read_text(encoding="utf-8")
        )
        clean = payload["current_clean_state"]
        destination = campaign.recovery_receipt_path(self.layout)
        destination.parent.mkdir(parents=True)
        raw = recovery.receipt_bytes(payload)
        destination.write_bytes(raw)
        digest = campaign.sha256_bytes(raw)
        sources = campaign.source_evidence(self.layout)
        with mock.patch.object(
            campaign, "RECOVERY_RECEIPT_SHA256", digest
        ):
            verified = campaign.verify_recovery_receipt(
                sources, clean, self.layout
            )
            self.assertEqual(verified["sha256"], digest)

            forged = copy.deepcopy(payload)
            forged["certification_effect"]["run1_is_warm_evidence"] = True
            forged_raw = recovery.receipt_bytes(forged)
            destination.write_bytes(forged_raw)
            with mock.patch.object(
                campaign,
                "RECOVERY_RECEIPT_SHA256",
                campaign.sha256_bytes(forged_raw),
            ):
                with self.assertRaisesRegex(
                    campaign.CampaignError, "certification effect"
                ):
                    campaign.verify_recovery_receipt(
                        sources, clean, self.layout
                    )

    def test_attempt_003_nonzero_child_stays_fail_closed_after_preservation_rehash(self):
        specs = campaign.load_specs(self.layout)[:2]
        clean = {
            "gpu_lock_exists": False,
            "suite_lock_exists": False,
            "server_pid_receipt_exists": False,
            "server_pid_receipt": None,
            "server_pid_create_time": None,
            "queue_quarantine_exists": False,
            "expected_server_identity_live": False,
            "listener_pids_8199": [],
        }
        carried_pair = {
            "cold": {
                "receipt_sha256": "1" * 64,
                "artifact": {"sha256": "2" * 64},
                "run_identity_sha256": "3" * 64,
                "server_instance": {"serving_pid": 1, "process_create_time": 2.0},
            },
            "warm": {
                "receipt_sha256": "4" * 64,
                "artifact": {"sha256": "5" * 64},
            },
            "final_manager_log": {"log": {"sha256": "6" * 64}},
        }
        preserved = {
            "pair": carried_pair,
            "receipt_schedule": campaign.pair_run_schedule(1, False, True),
            "recovery2": {"sha256": campaign.ATTEMPT2_RECOVERY_RECEIPT_SHA256},
            "recovery1": {"sha256": campaign.RECOVERY_RECEIPT_SHA256},
            "lifecycle": {"prefix": {"sha256": campaign.ATTEMPT2_LIFECYCLE_PREFIX_SHA256}},
            "attempt2_status": "FAILED",
            "attempt2_ledger_completed_pair_count": 0,
            "pair1_human_judgment": "PENDING",
            "orphan_historical_cold_count": 1,
        }
        sources = {"frozen": True}
        calls = []

        def child(command, environment, cwd):
            calls.append(list(command))
            return campaign.canon.ChildOutcome(returncode=120)

        def operator_probe(stdout_log, stderr_log, current_sources):
            return {
                "contract": campaign.operator_log_contract(
                    current_sources, self.layout
                )
            }

        with mock.patch.object(
            campaign, "load_specs", return_value=specs
        ), mock.patch.object(
            campaign, "runbook", return_value={"pairs": []}
        ), mock.patch.object(
            campaign, "source_evidence", return_value=sources
        ), mock.patch.object(
            campaign, "ensure_pristine_pair"
        ), mock.patch.object(
            campaign,
            "verify_attempt2_recovery_receipt",
            return_value=preserved,
        ), mock.patch.object(
            campaign,
            "verify_attempt2_preserved_evidence",
            return_value=preserved,
        ) as preserve_check:
            with self.assertRaisesRegex(campaign.CampaignError, "returned 120"):
                campaign.execute_campaign(
                    campaign_id=campaign.RESUME_ATTEMPT2_CAMPAIGN_ID,
                    campaign_layout=self.layout,
                    child_runner=child,
                    state_probe=lambda expected=None: copy.deepcopy(clean),
                    cleanup_owned_server=lambda: {"success": True},
                    resume_attempt_002=True,
                    operator_stdout_log="stdout",
                    operator_stderr_log="stderr",
                    operator_transport_probe=operator_probe,
                )

        self.assertEqual(len(calls), 1)
        self.assertEqual(Path(calls[0][2]), specs[1].path)
        self.assertNotIn("--force", calls[0])
        self.assertEqual(preserve_check.call_count, 1)
        rows = [
            json.loads(line)
            for line in self.layout.lifecycle.read_text(encoding="utf-8").splitlines()
        ]
        events = [row["event"] for row in rows]
        self.assertLess(events.index("pair_carried_forward"), events.index("pair_started"))
        self.assertEqual(rows[-1]["event"], "campaign_failed")
        terminal = rows[-1]["details"]
        self.assertEqual(terminal["completed_pair_count"], 1)
        self.assertEqual(terminal["carried_pair_count"], 1)
        self.assertEqual(terminal["new_verified_pair_count"], 0)
        self.assertEqual(terminal["pending_cold_child_outcome"]["returncode"], 120)

    def test_attempt_003_success_path_rehashes_each_child_and_mixes_final_audit(self):
        specs = campaign.load_specs(self.layout)[:2]
        identity = {"serving_pid": 321, "process_create_time": 654.25}
        clean = {
            "gpu_lock_exists": False,
            "suite_lock_exists": False,
            "server_pid_receipt_exists": False,
            "server_pid_receipt": None,
            "server_pid_create_time": None,
            "queue_quarantine_exists": False,
            "expected_server_identity_live": False,
            "listener_pids_8199": [],
        }
        warm_state = {
            **clean,
            "server_pid_receipt_exists": True,
            "server_pid_receipt": identity["serving_pid"],
            "server_pid_create_time": identity["process_create_time"],
            "expected_server_identity_live": True,
            "listener_pids_8199": [identity["serving_pid"]],
        }

        def pair(prefix):
            return {
                "cold": {
                    "receipt_sha256": prefix + "1" * 63,
                    "artifact": {"sha256": prefix + "2" * 63},
                    "run_identity_sha256": prefix + "3" * 63,
                    "server_instance": identity,
                },
                "warm": {
                    "receipt_sha256": prefix + "4" * 63,
                    "artifact": {"sha256": prefix + "5" * 63},
                    "run_identity_sha256": prefix + "3" * 63,
                    "server_instance": identity,
                },
                "final_manager_log": {
                    "log": {"sha256": prefix + "6" * 63}
                },
            }

        carried_pair = pair("a")
        executed_pair = pair("b")
        preserved = {
            "pair": carried_pair,
            "receipt_schedule": campaign.pair_run_schedule(1, False, True),
            "recovery2": {"sha256": campaign.ATTEMPT2_RECOVERY_RECEIPT_SHA256},
            "recovery1": {"sha256": campaign.RECOVERY_RECEIPT_SHA256},
            "lifecycle": {"prefix": {"sha256": campaign.ATTEMPT2_LIFECYCLE_PREFIX_SHA256}},
            "attempt2_status": "FAILED",
            "attempt2_ledger_completed_pair_count": 0,
            "pair1_human_judgment": "PENDING",
            "orphan_historical_cold_count": 1,
        }
        sources = {"frozen": True}
        states = iter((clean, clean, warm_state, clean, clean))
        child_calls = []

        def child(command, environment, cwd):
            child_calls.append(list(command))
            return campaign.canon.ChildOutcome(returncode=0)

        def operator_probe(stdout_log, stderr_log, current_sources):
            return {
                "contract": campaign.operator_log_contract(
                    current_sources, self.layout
                )
            }

        with mock.patch.object(
            campaign, "load_specs", return_value=specs
        ), mock.patch.object(
            campaign, "runbook", return_value={"pairs": []}
        ), mock.patch.object(
            campaign, "source_evidence", return_value=sources
        ), mock.patch.object(
            campaign, "ensure_pristine_pair"
        ), mock.patch.object(
            campaign,
            "verify_attempt2_recovery_receipt",
            return_value=preserved,
        ), mock.patch.object(
            campaign,
            "verify_attempt2_preserved_evidence",
            return_value=preserved,
        ) as preserve_check, mock.patch.object(
            campaign,
            "verify_run_receipt",
            return_value={"server_instance": identity},
        ), mock.patch.object(
            campaign.canon, "require_observed_child_server"
        ), mock.patch.object(
            campaign, "verify_pair", side_effect=(executed_pair, executed_pair)
        ) as pair_check:
            result = campaign.execute_campaign(
                campaign_id=campaign.RESUME_ATTEMPT2_CAMPAIGN_ID,
                campaign_layout=self.layout,
                child_runner=child,
                state_probe=lambda expected=None: copy.deepcopy(next(states)),
                cleanup_owned_server=lambda: {"success": True},
                resume_attempt_002=True,
                operator_stdout_log="stdout",
                operator_stderr_log="stderr",
                operator_transport_probe=operator_probe,
            )

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["carried_pair_count"], 1)
        self.assertEqual(len(result["pairs"]), 2)
        self.assertEqual(result["pairs"][0]["status"], "CARRIED_FORWARD")
        self.assertEqual(result["pairs"][0]["new_execution_count"], 0)
        self.assertEqual(result["pairs"][1]["new_execution_count"], 2)
        self.assertEqual(len(child_calls), 2)
        self.assertTrue(all(Path(command[2]) == specs[1].path for command in child_calls))
        self.assertEqual(preserve_check.call_count, 4)
        self.assertEqual(pair_check.call_args_list[0].kwargs["cold_run_number"], 1)
        self.assertEqual(pair_check.call_args_list[0].kwargs["warm_run_number"], 2)

        rows = [
            json.loads(line)
            for line in self.layout.lifecycle.read_text(encoding="utf-8").splitlines()
        ]
        terminal = rows[-1]
        self.assertEqual(terminal["event"], "campaign_completed")
        audit = terminal["details"]["final_evidence_audit"]
        self.assertEqual(
            [row["disposition"] for row in audit],
            ["CARRIED_FORWARD", "EXECUTED"],
        )
        self.assertEqual(audit[0]["source_campaign_id"], campaign.RESUME_CAMPAIGN_ID)
        self.assertEqual(
            audit[1]["source_campaign_id"], campaign.RESUME_ATTEMPT2_CAMPAIGN_ID
        )

    def test_default_main_writes_no_lifecycle_or_logs(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                campaign.main(["--campaign-id", "dry-test"], campaign_layout=self.layout),
                0,
            )
        self.assertFalse(self.layout.lifecycle.exists())
        self.assertFalse(
            (self.results / "h3_unconditioned_music_campaign" / "server_logs").exists()
        )

    def test_first_child_failure_stops_after_one_runner_call(self):
        calls = []

        def child(command, environment, cwd):
            calls.append(list(command))
            return campaign.canon.ChildOutcome(returncode=9)

        clean = {
            "gpu_lock_exists": False,
            "suite_lock_exists": False,
            "server_pid_receipt_exists": False,
            "server_pid_receipt": None,
            "server_pid_create_time": None,
            "queue_quarantine_exists": False,
            "expected_server_identity_live": False,
            "listener_pids_8199": [],
        }
        with self.assertRaises(campaign.CampaignError):
            campaign.execute_campaign(
                campaign_id="first-fail",
                campaign_layout=self.layout,
                child_runner=child,
                state_probe=lambda expected=None: copy.deepcopy(clean),
            )
        self.assertEqual(len(calls), 1)
        self.assertNotIn("--force", calls[0])
        rows = [
            json.loads(line)
            for line in self.layout.lifecycle.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(rows[-1]["event"], "campaign_failed")
        self.assertEqual(rows[-1]["details"]["completed_pair_count"], 0)

    def test_manager_receipt_verifier_binds_cold_phase_and_identity(self):
        log = self.temp / "receipt.log"
        config = (
            self.layout.actual_user_directory / "__manager" / "config.ini"
        )
        log.write_text(
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
            + "\n",
            encoding="utf-8",
        )
        argv = campaign.expected_server_argv(self.layout)
        scan = guard.scan_log(log, argv, require_pre_prompt=True)
        evidence = {
            "enabled": True,
            "valid": True,
            "verified_before_this_prompt": True,
            "require_no_prior_prompt": True,
            "log_path": str(log.resolve()),
            "serving_pid": 123,
            "serving_process_create_time_ns": 456,
            "offline_environment": guard.offline_environment_evidence(
                dict(guard.OFFLINE_ENVIRONMENT)
            ),
            "advisory_config": guard.config_evidence(argv),
            "log_scan": scan,
            "guard_source": {
                "path": str(campaign.GUARD.resolve()),
                "sha256": campaign.canon.sha256_file(campaign.GUARD),
            },
            "test_boot_source": {
                "path": str(campaign.TEST_BOOT_CMD.resolve()),
                "sha256": campaign.canon.sha256_file(campaign.TEST_BOOT_CMD),
            },
        }
        receipt = {
            "identity": {
                "manager_offline_probe_identity": campaign.expected_manager_identity(
                    evidence
                )
            },
            "manager_offline_probe": {
                "pre_queue": evidence,
                "post_render": copy.deepcopy(evidence),
                "provenance_unchanged": True,
            },
        }
        campaign.verify_manager_receipt(
            receipt, log_path=log, argv=argv, role="cold"
        )
        bad = copy.deepcopy(receipt)
        bad["manager_offline_probe"]["pre_queue"]["require_no_prior_prompt"] = False
        with self.assertRaises(campaign.CampaignError):
            campaign.verify_manager_receipt(
                bad, log_path=log, argv=argv, role="cold"
            )


class H3MusicIncidentRegressionTests(unittest.TestCase):
    def test_attempt_002_recovery_and_pair_are_literal_and_fully_reverified(self):
        receipt = json.loads(
            campaign.attempt2_recovery_receipt_path().read_text(encoding="utf-8")
        )
        verified = campaign.verify_attempt2_recovery_receipt(
            campaign.source_evidence(), receipt["current_clean_state"]
        )
        self.assertEqual(
            verified["recovery2"]["sha256"],
            campaign.ATTEMPT2_RECOVERY_RECEIPT_SHA256,
        )
        self.assertEqual(
            verified["lifecycle"]["prefix"]["sha256"],
            campaign.ATTEMPT2_LIFECYCLE_PREFIX_SHA256,
        )
        self.assertEqual(verified["lifecycle"]["prefix"]["row_count"], 13)
        self.assertEqual(verified["attempt2_status"], "FAILED")
        self.assertEqual(verified["attempt2_ledger_completed_pair_count"], 0)
        self.assertEqual(
            campaign.sha256_bytes(campaign.canon.canonical_bytes(verified["pair"])),
            campaign.ATTEMPT2_PAIR_RESULT_SHA256,
        )
        self.assertEqual(
            verified["pair"]["cold"]["receipt_sha256"],
            campaign.ATTEMPT2_RUN2_SHA256,
        )
        self.assertEqual(
            verified["pair"]["warm"]["receipt_sha256"],
            campaign.ATTEMPT2_RUN3_SHA256,
        )

    def test_published_recovery_receipt_matches_literal_resume_pin(self):
        path = campaign.recovery_receipt_path()
        raw = path.read_bytes()
        self.assertEqual(
            campaign.sha256_bytes(raw), campaign.RECOVERY_RECEIPT_SHA256
        )
        clean = campaign.canon.runtime_state(None, campaign.DEFAULT_LAYOUT)
        verified = campaign.verify_recovery_receipt(
            campaign.source_evidence(), clean
        )
        self.assertEqual(
            verified["sha256"], campaign.RECOVERY_RECEIPT_SHA256
        )

    def test_real_attempt_001_run1_is_valid_cold_evidence(self):
        sources = campaign.source_evidence()
        evidence = campaign.verify_failed_attempt_evidence(
            sources,
            require_alias_run1=False,
        )
        self.assertEqual(
            evidence["run1_receipt"]["sha256"],
            campaign.FAILED_RUN1_SHA256,
        )
        self.assertEqual(
            evidence["artifact"]["sha256"],
            campaign.FAILED_ARTIFACT_SHA256,
        )
        self.assertEqual(
            evidence["run1_semantics"]["queued_prompt_sha256"],
            "d2d41c7f137253778f2d8ce7fc06656d238364344a2263ea572db73bd069f3bd",
        )

    def test_cache_subdict_does_not_own_queued_prompt_hash(self):
        sources = campaign.source_evidence()
        spec = campaign.load_specs()[0]
        archive = campaign.RESULTS / f"{spec.name}_run1.json"
        receipt = json.loads(archive.read_text(encoding="utf-8"))
        original_strict_json = campaign.canon.strict_json

        def run_with(forged):
            raw = (json.dumps(forged, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )

            def strict_json(path, label):
                if Path(path) == archive:
                    return copy.deepcopy(forged), raw
                return original_strict_json(path, label)

            with mock.patch.object(
                campaign.canon, "strict_json", side_effect=strict_json
            ):
                return campaign.verify_run_receipt(
                    spec,
                    1,
                    campaign.executor_nonce(
                        campaign.FAILED_CAMPAIGN_ID, 1, "cold"
                    ),
                    sources,
                    campaign.failed_attempt_log_path(),
                    role="cold",
                    expected_config_run_count=1,
                    require_alias_current=False,
                )

        verifier_only_drift = copy.deepcopy(receipt)
        verifier_only_drift["execution_cache_control"][
            "queued_prompt_sha256"
        ] = "0" * 64
        accepted = run_with(verifier_only_drift)
        self.assertEqual(
            accepted["queued_prompt_sha256"], receipt["queued_prompt_sha256"]
        )

        authoritative_drift = copy.deepcopy(receipt)
        authoritative_drift["queued_prompt_sha256"] = "0" * 64
        with self.assertRaisesRegex(campaign.CampaignError, "queued prompt"):
            run_with(authoritative_drift)


if __name__ == "__main__":
    unittest.main()
