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

    def test_selected_h3_t8_is_blocked_until_weight_and_profile_admission(self):
        campaign = front_office.load_campaign("h3-t8")
        self.assertEqual(campaign["status"], "BLOCKED_WEIGHT_ADMISSION")
        self.assertIn("eight-step", campaign["independent_variable"])
        self.assertIn("h3-turbo-larry-v4", campaign["profiles"])
        self.assertNotIn("h3-turbo-larry-v4", front_office.list_enrolled_profiles())
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
        self.assertEqual(report["recipe_count"], 82)
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
