import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import front_office


class FrontOfficeProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy_profile_path = front_office.PROFILE_DIR / "comfy0311-h3.json"
        cls.profile_path = front_office.PROFILE_DIR / "comfy0320-h3.json"
        cls.profile = json.loads(cls.profile_path.read_text(encoding="utf-8"))

    def test_current_profile_is_exactly_enrolled_and_legacy_profile_stays_historical(self):
        profile = front_office.load_enrolled_profile("comfy0320-h3")
        self.assertEqual(profile["comfyui"]["version"], "0.32.0")
        self.assertEqual(profile["comfyui"]["git_commit"], "c2bcbecd82ec5ae66594340b395c24ef0217b238")
        self.assertEqual(profile["custom_nodes"][0]["version"], "1.3.9")
        legacy = json.loads(self.legacy_profile_path.read_text(encoding="utf-8"))
        self.assertEqual(legacy["comfyui"]["version"], "0.31.1")
        with self.assertRaisesRegex(front_office.ProfileValidationError, "drifted"):
            front_office.load_enrolled_profile("comfy0311-h3")

    def test_unknown_key_fails_before_any_identity_probe(self):
        malformed = copy.deepcopy(self.profile)
        malformed["not_enrolled"] = True
        with self.assertRaisesRegex(front_office.FrontOfficeError, "unknown"):
            front_office.validate_profile(malformed)

    def test_wrong_full_git_commit_fails_closed(self):
        malformed = copy.deepcopy(self.profile)
        malformed["comfyui"]["git_commit"] = "0" * 40
        with self.assertRaisesRegex(front_office.ProfileValidationError, "commit"):
            front_office.validate_profile(malformed)

    def test_boot_argv_is_direct_sage_free_and_exactly_whitelisted(self):
        profile = front_office.load_enrolled_profile("comfy0320-h3")
        namespaces = front_office.derive_cell_namespaces(
            "front-office-r1", "t2i-low-smoke", "comfy0320-h3"
        )
        argv = front_office.canonical_server_argv(profile, namespaces)
        self.assertIsInstance(argv, list)
        self.assertEqual(argv[0], profile["python"]["path"])
        self.assertEqual(argv[1], str(Path(profile["comfyui"]["root"]) / "main.py"))
        self.assertNotIn("--use-sage-attention", argv)
        self.assertNotIn("cmd.exe", [item.lower() for item in argv])
        self.assertEqual(argv[-2:], ["--whitelist-custom-nodes", "ComfyUI-KJNodes"])
        self.assertEqual(argv[argv.index("--port") + 1], "8199")
        self.assertEqual(
            argv[argv.index("--temp-directory") + 1], namespaces["temp_directory"]
        )

    def test_bad_reparse_component_is_rejected(self):
        with mock.patch.object(front_office, "_has_reparse_point", return_value=True):
            with self.assertRaisesRegex(front_office.FrontOfficeError, "reparse"):
                front_office.validate_absolute_nonreparse_path(
                    str(self.profile_path), "profile test path", "file"
                )

    def test_parent_environment_is_not_inherited_into_a_child_plan(self):
        profile = front_office.load_enrolled_profile("comfy0320-h3")
        child = front_office.sanitized_child_environment(
            profile,
            {
                "LAB_RESERVE_VRAM_GB": "12",
                "PYTHONPATH": "unsafe",
                "HF_TOKEN": "not-copied",
                "HF_HOME": "wrong-parent-value",
            },
        )
        self.assertEqual(
            child,
            {
                "HF_HOME": profile["environment"]["HF_HOME"],
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        )
        stripped = front_office.inherited_environment_keys_to_strip(
            {"LAB_RESERVE_VRAM_GB": "12", "PYTHONPATH": "unsafe", "SAFE": "1"}
        )
        self.assertEqual(stripped, ["LAB_RESERVE_VRAM_GB", "PYTHONPATH"])


class FrontOfficeLaunchSpecTests(unittest.TestCase):
    def static_launch_inputs(self):
        profile = front_office.load_enrolled_profile("comfy0320-h3")
        campaign = json.loads(
            (front_office.CAMPAIGN_DIR / "front-office-static-h3.json").read_text(
                encoding="utf-8"
            )
        )
        campaign["profiles"] = [profile["id"]]
        campaign["cells"][0]["profiles"] = [profile["id"]]
        return campaign, profile

    def build_static_spec(self, nonce):
        campaign, profile = self.static_launch_inputs()
        with mock.patch.object(front_office, "load_campaign", return_value=campaign), mock.patch.object(
            front_office, "load_enrolled_profile", return_value=profile
        ):
            return front_office.build_launch_spec(
                campaign["id"], campaign["cells"][0]["id"], profile["id"], nonce
            )

    def test_namespaces_are_distinct_and_under_their_fixed_roots(self):
        first = front_office.derive_cell_namespaces(
            "front-office-static-h3", "h3-ref2va-seed42", "comfy0311-h3"
        )
        second = front_office.derive_cell_namespaces(
            "front-office-static-h3", "h3-ref2va-seed42", "different-profile"
        )
        self.assertEqual(len(set(first.values())), len(first))
        self.assertNotEqual(first["output_directory"], second["output_directory"])
        self.assertTrue(first["output_directory"].startswith(str(front_office.REPO_ROOT / "outputs")))
        self.assertTrue(first["result_directory"].startswith(str(front_office.REPO_ROOT / "results" / "runs")))
        self.assertTrue(first["log_directory"].startswith(str(front_office.REPO_ROOT / "logs")))

    def test_nonce_does_not_change_semantic_launch_identity(self):
        first = self.build_static_spec("a" * 32)
        second = self.build_static_spec("b" * 32)
        self.assertEqual(first["launch_spec_sha256"], second["launch_spec_sha256"])
        self.assertEqual(first["semantic"], second["semantic"])
        self.assertNotEqual(first["lease_nonce"], second["lease_nonce"])
        campaign, profile = self.static_launch_inputs()
        with mock.patch.object(front_office, "load_campaign", return_value=campaign), mock.patch.object(
            front_office, "load_enrolled_profile", return_value=profile
        ):
            front_office.validate_launch_spec(first)

    def test_hand_edited_semantic_plan_is_rejected(self):
        spec = self.build_static_spec("a" * 32)
        forged = copy.deepcopy(spec)
        forged["semantic"]["server"]["port"] = "8188"
        campaign, profile = self.static_launch_inputs()
        with mock.patch.object(front_office, "load_campaign", return_value=campaign), mock.patch.object(
            front_office, "load_enrolled_profile", return_value=profile
        ):
            with self.assertRaisesRegex(front_office.LaunchSpecValidationError, "semantic"):
                front_office.validate_launch_spec(forged)

    def test_static_spec_write_is_atomic_and_still_not_a_launch(self):
        spec = self.build_static_spec("c" * 32)
        campaign, profile = self.static_launch_inputs()
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(front_office, "load_campaign", return_value=campaign), mock.patch.object(
                front_office, "load_enrolled_profile", return_value=profile
            ):
                destination = front_office.write_launch_spec(spec, Path(directory))
            self.assertTrue(destination.is_file())
            loaded = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(loaded, spec)
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_c032_is_explicitly_blocked_without_a_fake_profile(self):
        campaign = front_office.load_campaign("h3-c032")
        self.assertEqual(campaign["status"], "BLOCKED_PROFILE_ENROLLMENT")
        self.assertIn("comfy0320-h3", campaign["profiles"])
        self.assertIn("comfy0320-h3", front_office.list_enrolled_profiles())
        with self.assertRaisesRegex(front_office.CampaignValidationError, "BLOCKED_PROFILE_ENROLLMENT"):
            front_office.build_launch_spec("h3-c032", "h3-i2v-sentinel", "comfy0311-h3", "d" * 32)

    def test_legacy_h3_t8_stays_blocked_even_after_the_new_turbo_profile_is_admitted(self):
        campaign = front_office.load_campaign("h3-t8")
        self.assertEqual(campaign["status"], "BLOCKED_WEIGHT_ADMISSION")
        self.assertIn("eight-step", campaign["independent_variable"])
        self.assertIn("h3-turbo-larry-v4", campaign["profiles"])
        self.assertIn("h3-turbo-larry-v4", front_office.list_enrolled_profiles())
        with self.assertRaisesRegex(front_office.CampaignValidationError, "BLOCKED_WEIGHT_ADMISSION"):
            front_office.build_launch_spec("h3-t8", "h3-i2v-sentinel", "comfy0311-h3", "e" * 32)

    def test_static_front_office_contains_no_comfy_launcher(self):
        source = Path(front_office.__file__).read_text(encoding="utf-8")
        self.assertNotIn("Popen(", source)
        self.assertNotIn("http://127.0.0.1", source)


class FrontOfficeExecutionSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile_path = front_office.PROFILE_DIR / "comfy0311-h3.json"
        cls.campaign_path = front_office.CAMPAIGN_DIR / "front-office-static-h3.json"

    def dispatchable_profile(self):
        profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
        profile["status"] = front_office.PROFILE_STATUS_DISPATCHABLE
        profile["floor_runner"]["sha256"] = front_office.sha256_file(
            Path(profile["floor_runner"]["path"])
        )
        return profile

    def dispatchable_campaign(self):
        campaign = json.loads(self.campaign_path.read_text(encoding="utf-8"))
        campaign["status"] = front_office.CAMPAIGN_STATUS_READY_FOR_DISPATCH
        campaign["cells"][0]["role"] = "control"
        campaign["cells"][0]["phase"] = "fresh-control"
        return campaign

    def test_execution_spec_is_a_distinct_dispatchable_kind(self):
        campaign = self.dispatchable_campaign()
        profile = self.dispatchable_profile()
        with mock.patch.object(front_office, "load_campaign", return_value=campaign), mock.patch.object(
            front_office, "load_enrolled_profile", return_value=profile
        ):
            spec = front_office.build_execution_spec(
                campaign["id"], campaign["cells"][0]["id"], profile["id"], "f" * 32
            )
            self.assertEqual(spec["kind"], front_office.EXECUTION_SPEC_KIND)
            self.assertEqual(spec["semantic"]["kind"], front_office.EXECUTION_SPEC_KIND)
            self.assertEqual(
                spec["semantic"]["execution_state"], front_office.CAMPAIGN_STATUS_READY_FOR_DISPATCH
            )
            self.assertEqual(spec["semantic"]["floor_runner"]["path"], profile["floor_runner"]["path"])
            front_office.validate_execution_spec(spec)

    def test_execution_spec_write_is_exclusive_and_read_is_runtime_bound(self):
        campaign = self.dispatchable_campaign()
        profile = self.dispatchable_profile()
        with mock.patch.object(front_office, "load_campaign", return_value=campaign), mock.patch.object(
            front_office, "load_enrolled_profile", return_value=profile
        ):
            spec = front_office.build_execution_spec(
                campaign["id"], campaign["cells"][0]["id"], profile["id"], "1" * 32
            )
            with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
                runtime = Path(directory)
                destination = front_office.write_execution_spec(spec, runtime)
                self.assertTrue(destination.name.startswith("front-office-execution-"))
                self.assertEqual(front_office.load_execution_spec(destination, runtime), spec)
                with self.assertRaisesRegex(front_office.LaunchSpecValidationError, "nonce replay"):
                    front_office.write_execution_spec(spec, runtime)
                outside_path = Path(outside) / destination.name
                outside_path.write_bytes(destination.read_bytes())
                with self.assertRaisesRegex(front_office.FrontOfficeError, "escapes"):
                    front_office.load_execution_spec(outside_path, runtime)

    def test_static_only_campaign_and_profile_are_never_dispatchable(self):
        with self.assertRaisesRegex(front_office.CampaignValidationError, "not READY_FOR_DISPATCH"):
            front_office.build_execution_spec(
                "front-office-static-h3", "h3-ref2va-seed42", "comfy0311-h3", "2" * 32
            )

        campaign = self.dispatchable_campaign()
        static_profile = self.dispatchable_profile()
        static_profile["status"] = front_office.PROFILE_STATUS_STATIC_ONLY
        with mock.patch.object(front_office, "load_campaign", return_value=campaign), mock.patch.object(
            front_office, "load_enrolled_profile", return_value=static_profile
        ):
            with self.assertRaisesRegex(front_office.CampaignValidationError, "ENROLLED_DISPATCHABLE"):
                front_office.build_execution_spec(
                    campaign["id"], campaign["cells"][0]["id"], static_profile["id"], "3" * 32
                )

    def test_tampered_execution_spec_and_static_kind_fail_before_dispatch(self):
        campaign = self.dispatchable_campaign()
        profile = self.dispatchable_profile()
        with mock.patch.object(front_office, "load_campaign", return_value=campaign), mock.patch.object(
            front_office, "load_enrolled_profile", return_value=profile
        ):
            spec = front_office.build_execution_spec(
                campaign["id"], campaign["cells"][0]["id"], profile["id"], "4" * 32
            )
            forged = copy.deepcopy(spec)
            forged["semantic"]["server"]["port"] = "8188"
            with self.assertRaisesRegex(front_office.LaunchSpecValidationError, "semantic"):
                front_office.validate_execution_spec(forged)

        static_envelope = {
            "schema_version": front_office.LAUNCH_SPEC_SCHEMA_VERSION,
            "kind": front_office.STATIC_LAUNCH_SPEC_KIND,
            "lease_nonce": "5" * 32,
            "launch_spec_sha256": "a" * 64,
            "semantic": {},
        }
        with self.assertRaisesRegex(front_office.LaunchSpecValidationError, "schema/kind"):
            front_office.validate_execution_spec(static_envelope)


class FrontOfficeReceiptTests(unittest.TestCase):
    def setUp(self):
        self.active = {"runner_sha256": "a" * 64, "runner_bundle_sha256": "b" * 64}

    def test_display_classification_keeps_old_receipts_immutable(self):
        self.assertEqual(
            front_office.classify_receipt_for_active_runner({"runner_sha256": "a" * 64}, self.active),
            "CURRENT_ACTIVE_RUNNER",
        )
        self.assertEqual(
            front_office.classify_receipt_for_active_runner({"runner_sha256": "c" * 64}, self.active),
            "STALE_FOR_ACTIVE_RUNNER",
        )
        self.assertEqual(
            front_office.classify_receipt_for_active_runner({"status": "legacy"}, self.active),
            "PRE_RUNNER_DIVISION_HISTORY",
        )
        self.assertEqual(
            front_office.classify_receipt_for_active_runner(
                {"front_office": {"runner_bundle_sha256": "b" * 64}}, self.active
            ),
            "CURRENT_ACTIVE_RUNNER",
        )

    def test_receipt_index_only_reads_existing_bytes(self):
        receipt_path = front_office.RESULTS_DIR / "h3_jobd_lipsync_refaudio_seed43_f192_run1.json"
        original = receipt_path.read_bytes()
        report = front_office.receipt_status_report()
        self.assertGreater(report["receipt_count"], 0)
        self.assertTrue(report["immutable"])
        self.assertEqual(receipt_path.read_bytes(), original)

    def test_r0_census_reaches_every_current_recipe_without_gpu_or_server(self):
        report = front_office.r0_static_census()
        self.assertEqual(report["recipe_count"], 86)
        self.assertEqual(report["recipe_json_bom_errors"], [])
        self.assertFalse(report["gpu_or_server_touched"])
        self.assertEqual(report["direct_launch"], "SEALED_DIRECT_DISPATCH_AVAILABLE")
        self.assertIn({"id": "comfy0320-h3", "status": "VALID"}, report["profile_results"])
        self.assertTrue(
            any(
                item["id"] == "comfy0311-h3" and item["status"] == "INVALID"
                for item in report["profile_results"]
            )
        )

    def test_current_h3_native_av_smoke_is_a_sealed_current_profile_cell(self):
        campaign = front_office.load_campaign("front-office-h3-current-r1")
        self.assertEqual(campaign["status"], front_office.CAMPAIGN_STATUS_READY_FOR_DISPATCH)
        self.assertEqual(campaign["profiles"], ["comfy0320-h3"])
        self.assertEqual(campaign["cells"], [{
            "id": "i2v-native-av-smoke",
            "recipe": "h3_i2v_current_profile_av_smoke.json",
            "role": "control",
            "phase": "sealed-one-shot-current-profile-native-av",
            "profiles": ["comfy0320-h3"],
        }])
        recipe = json.loads(
            (front_office.RECIPE_DIR / campaign["cells"][0]["recipe"]).read_text(encoding="utf-8")
        )
        topology = recipe["topology_contract"]
        self.assertEqual(recipe["name"], "h3_i2v_current_profile_av_smoke")
        self.assertEqual(topology["installed_schema"]["comfyui_version"], "0.32.0")
        self.assertEqual(topology["installed_schema"]["git_commit"], "c2bcbecd82ec5ae66594340b395c24ef0217b238")
        self.assertEqual(topology["installed_schema"]["node_source"], "comfy_extras/nodes_minimax_h3.py")
        self.assertEqual(topology["installed_schema"]["node_source_sha256"], "f767df4074b908efb345f5a87c2fd263ba82c12e65bcca932846207cc213e064")
        self.assertEqual(recipe["prompt"]["10"]["inputs"]["audio"], ["15", 0])
        self.assertEqual(recipe["prompt"]["12"]["inputs"]["filename_prefix"], "h3_i2v_current_profile_av_smoke_out")

    def test_current_h3_native_av_smoke_preserves_the_mime_graph_except_its_output_prefix(self):
        base = json.loads(
            (front_office.RECIPE_DIR / "h3_mime_i2v.json").read_text(encoding="utf-8")
        )
        clone = json.loads(
            (front_office.RECIPE_DIR / "h3_i2v_current_profile_av_smoke.json").read_text(
                encoding="utf-8"
            )
        )
        expected_prompt = copy.deepcopy(base["prompt"])
        expected_prompt["12"]["inputs"]["filename_prefix"] = "h3_i2v_current_profile_av_smoke_out"
        self.assertEqual(clone["prompt"], expected_prompt)
        self.assertEqual(clone["contract"], base["contract"])
        self.assertEqual(clone["receipt_requirements"], base["receipt_requirements"])
        spec = front_office.build_execution_spec(
            "front-office-h3-current-r1", "i2v-native-av-smoke", "comfy0320-h3", "a" * 32
        )
        self.assertEqual(
            spec["semantic"]["recipe"]["path"], "recipes/h3_i2v_current_profile_av_smoke.json"
        )
        self.assertEqual(spec["semantic"]["campaign"]["id"], "front-office-h3-current-r1")

    def test_current_ltx_video_smoke_is_a_sealed_current_profile_cell(self):
        campaign = front_office.load_campaign("front-office-ltx-current-r1")
        self.assertEqual(campaign["status"], front_office.CAMPAIGN_STATUS_READY_FOR_DISPATCH)
        self.assertEqual(campaign["profiles"], ["comfy0320-h3"])
        self.assertEqual(campaign["cells"], [{
            "id": "i2v-current-video-smoke",
            "recipe": "ltx_video_2b_current_profile_cold_smoke.json",
            "role": "control",
            "phase": "sealed-one-shot-current-profile-cold-video",
            "profiles": ["comfy0320-h3"],
        }])
        recipe = json.loads(
            (front_office.RECIPE_DIR / campaign["cells"][0]["recipe"]).read_text(encoding="utf-8")
        )
        topology = recipe["topology_contract"]
        self.assertEqual(recipe["name"], "ltx_video_2b_current_profile_cold_smoke")
        self.assertIn("cold", recipe["experiment"]["scope"])
        self.assertIn("not promotable", recipe["experiment"]["scope"])
        self.assertIn("not comparable", recipe["experiment"]["scope"])
        self.assertEqual(topology["installed_schema"]["comfyui_version"], "0.32.0")
        self.assertEqual(topology["installed_schema"]["git_commit"], "c2bcbecd82ec5ae66594340b395c24ef0217b238")
        self.assertEqual(topology["installed_schema"]["node_source"], "comfy_extras/nodes_lt.py")
        self.assertEqual(topology["installed_schema"]["node_source_sha256"], "542cadcc408ec54194c9bdad2f3afc3e1c3eead6b0c6400f6aef78b779d74e7d")
        self.assertEqual(recipe["prompt"]["12"]["inputs"]["filename_prefix"], "ltx_video_2b_current_profile_cold_smoke_out")

    def test_current_ltx_video_smoke_preserves_the_historical_graph_except_its_output_prefix(self):
        base = json.loads(
            (front_office.RECIPE_DIR / "ltx_video_2b_distilled_cmp_832x480_f193.json").read_text(
                encoding="utf-8"
            )
        )
        clone = json.loads(
            (front_office.RECIPE_DIR / "ltx_video_2b_current_profile_cold_smoke.json").read_text(
                encoding="utf-8"
            )
        )
        expected_prompt = copy.deepcopy(base["prompt"])
        expected_prompt["12"]["inputs"]["filename_prefix"] = "ltx_video_2b_current_profile_cold_smoke_out"
        self.assertEqual(clone["prompt"], expected_prompt)
        self.assertEqual(clone["contract"], base["contract"])
        self.assertEqual(clone["receipt_requirements"], base["receipt_requirements"])
        expected_topology = copy.deepcopy(base["topology_contract"])
        expected_topology["intent"] = (
            "Current-profile LTX-Video 0.9.8 distilled 2B cold video smoke; the immutable graph "
            "remains the historical same-canvas 193-frame graph"
        )
        expected_topology["installed_schema"] = {
            "comfyui_version": "0.32.0",
            "git_commit": "c2bcbecd82ec5ae66594340b395c24ef0217b238",
            "node_source": "comfy_extras/nodes_lt.py",
            "node_source_sha256": "542cadcc408ec54194c9bdad2f3afc3e1c3eead6b0c6400f6aef78b779d74e7d",
        }
        expected_topology["required_input_values"][-3]["equals"] = (
            "ltx_video_2b_current_profile_cold_smoke_out"
        )
        expected_topology["intentional_divergences"].append(
            "This immutable clone changes only identity metadata, the current installed-schema pin, "
            "and the SaveVideo prefix from ltx_video_2b_distilled_cmp_832x480_f193; it is a cold "
            "current-profile smoke, not a historical-lane comparison or promotion claim"
        )
        self.assertEqual(clone["topology_contract"], expected_topology)
        spec = front_office.build_execution_spec(
            "front-office-ltx-current-r1", "i2v-current-video-smoke", "comfy0320-h3", "b" * 32
        )
        self.assertEqual(
            spec["semantic"]["recipe"]["path"], "recipes/ltx_video_2b_current_profile_cold_smoke.json"
        )
        self.assertEqual(spec["semantic"]["campaign"]["id"], "front-office-ltx-current-r1")

    def test_larry_turbo_pair_is_profile_isolated_and_has_only_the_declared_graph_delta(self):
        campaign = front_office.load_campaign("front-office-h3-t8-current-r1")
        self.assertEqual(campaign["status"], front_office.CAMPAIGN_STATUS_READY_FOR_DISPATCH)
        self.assertEqual(campaign["profiles"], ["comfy0320-h3", "h3-turbo-larry-v4"])
        self.assertEqual([cell["id"] for cell in campaign["cells"]], [
            "i2v-action-control-20step",
            "i2v-action-turbo-v4-8step",
        ])
        control = json.loads(
            (front_office.RECIPE_DIR / "h3_turbo_larry_v4_i2v_action_control.json").read_text(
                encoding="utf-8"
            )
        )
        candidate = json.loads(
            (front_office.RECIPE_DIR / "h3_turbo_larry_v4_i2v_action_8step.json").read_text(
                encoding="utf-8"
            )
        )
        base_profile = front_office.load_enrolled_profile("comfy0320-h3")
        turbo = front_office.load_enrolled_profile("h3-turbo-larry-v4")
        admission = json.loads(
            (front_office.REPO_ROOT / "model_admissions" / "h3-turbo-larry-v4" / "admission.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(admission["status"], "ADMITTED_FOR_ONE_SEALED_COLD_I2V_CANDIDATE")
        self.assertEqual(
            admission["weight"]["sha256"],
            "5f3a626cd72c93a8b9318d6760c510bc5092d2ab13aaba1f932c5bab07a416d3",
        )
        self.assertEqual(admission["weight"]["bytes"], 779849816)
        self.assertEqual(
            admission["execution_contract"]["required_live_node_classes"],
            ["MiniMaxH3TurboLoRA", "MiniMaxH3TurboSampler"],
        )
        self.assertTrue(turbo["model_manifest"]["path"].endswith("model_admissions\\h3-turbo-larry-v4\\models_manifest.md"))
        self.assertEqual(turbo["python"], base_profile["python"])
        self.assertEqual(turbo["comfyui"], base_profile["comfyui"])
        self.assertEqual(turbo["model_paths_config"], base_profile["model_paths_config"])
        self.assertEqual(turbo["environment"], base_profile["environment"])
        self.assertEqual(turbo["boot"]["fixed_argv"][:-1], base_profile["boot"]["fixed_argv"])
        self.assertEqual(
            [node["id"] for node in turbo["custom_nodes"]],
            ["ComfyUI-KJNodes", "ComfyUI-MiniMax-H3-Turbo"],
        )
        turbo_argv = front_office.canonical_server_argv(
            turbo,
            front_office.derive_cell_namespaces(
                campaign["id"], campaign["cells"][1]["id"], turbo["id"]
            ),
        )
        self.assertNotIn("--use-sage-attention", turbo_argv)
        self.assertEqual(turbo_argv[-3:], [
            "--whitelist-custom-nodes",
            "ComfyUI-KJNodes",
            "ComfyUI-MiniMax-H3-Turbo",
        ])
        self.assertEqual(candidate["contract"], control["contract"])
        self.assertEqual(
            candidate["prompt"]["7"]["inputs"]["prompt"],
            control["prompt"]["7"]["inputs"]["prompt"],
        )
        self.assertEqual(candidate["prompt"]["5"], control["prompt"]["5"])
        self.assertEqual(candidate["prompt"]["10"], control["prompt"]["10"])
        self.assertEqual(candidate["prompt"]["15"], control["prompt"]["15"])
        self.assertNotIn("13", candidate["prompt"])
        self.assertEqual(candidate["prompt"]["16"]["class_type"], "MiniMaxH3TurboLoRA")
        self.assertEqual(candidate["prompt"]["16"]["inputs"], {
            "model": ["1", 0],
            "lora_name": "h3-turbo-larry-v4/minimax_h3_turbo_v4_step600_ema.safetensors",
            "strength": 1.0,
            "low_vram": False,
        })
        self.assertEqual(candidate["prompt"]["17"], {"class_type": "MiniMaxH3TurboSampler", "inputs": {}})
        self.assertEqual(candidate["prompt"]["6"]["inputs"]["model"], ["16", 0])
        self.assertEqual(candidate["prompt"]["14"]["inputs"], {
            "model": ["16", 0], "scheduler": "simple", "steps": 8, "denoise": 1.0,
        })
        self.assertEqual(candidate["prompt"]["8"]["inputs"]["sampler"], ["17", 0])
        self.assertEqual(candidate["prompt"]["10"]["inputs"]["audio"], ["15", 0])
        node_contract = candidate["topology_contract"]["external_node_contract"]
        self.assertEqual(set(node_contract), {
            "node_id", "git_commit", "version", "init_py_sha256", "lora",
            "support_asset", "live_object_info_required",
        })
        self.assertEqual(node_contract["git_commit"], "546b5028f4934f5129eb6c7142c2f3e461dfddbf")
        self.assertEqual(node_contract["init_py_sha256"], "036089da474d9d06fd277fd9686ff05aad913824220dd8a2f5882b271c21022f")
        self.assertEqual(node_contract["lora"], {
            "runtime_name": "h3-turbo-larry-v4/minimax_h3_turbo_v4_step600_ema.safetensors",
            "managed_path": "C:\\ComfyUI-Models\\loras\\h3-turbo-larry-v4\\minimax_h3_turbo_v4_step600_ema.safetensors",
            "bytes": 779849816,
            "sha256": "5f3a626cd72c93a8b9318d6760c510bc5092d2ab13aaba1f932c5bab07a416d3",
        })
        self.assertEqual(node_contract["support_asset"], {
            "filename": "h3_silu_temb_grid.safetensors",
            "managed_path": "C:\\ComfyUI-Models\\custom_node_assets\\ComfyUI-MiniMax-H3-Turbo\\h3_silu_temb_grid.safetensors",
            "source_checkout_path": "C:\\Users\\jeffr\\Documents\\ComfyUI\\custom_nodes\\ComfyUI-MiniMax-H3-Turbo\\h3_silu_temb_grid.safetensors",
            "bytes": 5510600,
            "sha256": "30eb3c2cc7fb6b470d9717ff840d359313ac27cd64b705e32da1baa10f72d6a8",
        })
        referenced_model_paths = set()

        def collect_model_paths(value):
            if isinstance(value, str) and value.endswith(
                (".safetensors", ".ckpt", ".pth", ".bin", ".gguf", ".onnx")
            ):
                referenced_model_paths.add(value)
            elif isinstance(value, dict):
                for child in value.values():
                    collect_model_paths(child)
            elif isinstance(value, list):
                for child in value:
                    collect_model_paths(child)

        collect_model_paths(candidate)
        turbo_manifest = Path(turbo["model_manifest"]["path"]).read_text(
            encoding="utf-8"
        )
        self.assertFalse(
            sorted(path for path in referenced_model_paths if path not in turbo_manifest),
            "Every candidate-declared model or support path must be in its immutable profile manifest",
        )
        self.assertEqual(
            node_contract["live_object_info_required"],
            ["MiniMaxH3TurboLoRA", "MiniMaxH3TurboSampler"],
        )
        spec = front_office.build_execution_spec(
            campaign["id"], campaign["cells"][1]["id"], turbo["id"], "c" * 32
        )
        self.assertEqual(spec["semantic"]["recipe"]["path"], "recipes/h3_turbo_larry_v4_i2v_action_8step.json")
        self.assertEqual(spec["semantic"]["profile"]["id"], "h3-turbo-larry-v4")
