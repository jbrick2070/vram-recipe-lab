import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run_recipe
import run_h3_suite
import lab_locks
import live_schema_check
import validate_recipes
from scratch import build_clean_h3_recipes


class TestRunnerProvenance(unittest.TestCase):
    def test_audio_encoder_is_part_of_model_identity(self):
        recipe = {
            "prompt": {
                "1": {
                    "class_type": "AudioEncoderLoader",
                    "inputs": {"audio_encoder_name": "whisper_probe.safetensors"},
                }
            }
        }
        self.assertEqual(
            run_recipe.referenced_model_names(recipe),
            ["whisper_probe.safetensors"],
        )

    def test_suite_cache_nonce_is_executor_only_and_preserves_seed_and_topology(self):
        recipe = json.loads(
            (run_recipe.REPO_ROOT / "recipes" / "h3_i2v_suite_sentinel.json").read_text(
                encoding="utf-8"
            )
        )
        original = recipe["prompt"]
        queued, control = run_recipe.apply_suite_cache_nonce(
            original, "suite-run:S0"
        )

        self.assertNotIn(run_recipe.SUITE_CACHE_NONCE_INPUT, original["5"]["inputs"])
        self.assertEqual(original["5"]["inputs"]["noise_seed"], 42)
        self.assertEqual(queued["5"]["inputs"]["noise_seed"], 42)
        self.assertEqual(
            queued["5"]["inputs"][run_recipe.SUITE_CACHE_NONCE_INPUT],
            "suite-run:S0",
        )
        self.assertEqual(
            {node_id: node["class_type"] for node_id, node in queued.items()},
            {node_id: node["class_type"] for node_id, node in original.items()},
        )
        self.assertEqual(
            set(control["fresh_node_ids"]), {"5", "8", "9", "10", "12", "15"}
        )
        self.assertEqual(control["sampler_node_ids"], ["8"])
        self.assertIn("4", control["stable_node_ids"])
        self.assertIn("1", control["stable_node_ids"])

    def test_suite_cache_evidence_requires_fresh_branch_and_tracks_warm_stable_hits(self):
        prompt = json.loads(
            (run_recipe.REPO_ROOT / "recipes" / "h3_i2v_suite_sentinel.json").read_text(
                encoding="utf-8"
            )
        )["prompt"]
        _, control = run_recipe.apply_suite_cache_nonce(prompt, "suite-run:S0")
        valid = run_recipe.execution_cache_evidence(
            [["execution_cached", {"nodes": control["stable_node_ids"]}]],
            control,
        )
        self.assertTrue(valid["fresh_execution_proved"])
        self.assertEqual(valid["cached_fresh_node_ids"], [])
        self.assertTrue(
            set(valid["stable_node_ids"]).issubset(valid["cached_node_ids"])
        )

        invalid = run_recipe.execution_cache_evidence(
            [["execution_cached", {"nodes": [*control["stable_node_ids"], "8"]}]],
            control,
        )
        self.assertFalse(invalid["fresh_execution_proved"])
        self.assertEqual(invalid["cached_fresh_node_ids"], ["8"])

    def test_suite_cache_nonce_flag_is_strict_and_suite_only(self):
        self.assertEqual(
            run_recipe.parse_suite_cache_nonce(
                ["run_recipe.py", "recipe.json", "--suite", "--suite-cache-nonce", "run:W0"],
                True,
            ),
            "run:W0",
        )
        for argv, is_suite in (
            (["run_recipe.py", "recipe.json", "--suite"], True),
            (
                ["run_recipe.py", "recipe.json", "--suite-cache-nonce", "run:W0"],
                False,
            ),
            (
                ["run_recipe.py", "recipe.json", "--suite", "--suite-cache-nonce", "bad/value"],
                True,
            ),
        ):
            with self.assertRaises(ValueError):
                run_recipe.parse_suite_cache_nonce(argv, is_suite)

    def test_suite_cache_runtime_sources_are_exactly_pinned(self):
        self.assertEqual(
            run_recipe.suite_cache_runtime_sha256s(),
            run_recipe.SUITE_CACHE_RUNTIME_SOURCES,
        )

    def test_standalone_cache_nonce_preserves_legacy_ksampler_seed(self):
        prompt = {
            "1": {"class_type": "UNETLoader", "inputs": {}},
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "seed": 42,
                    "steps": 20,
                    "cfg": 6.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                },
            },
            "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0]}},
            "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0]}},
            "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0]}},
        }

        queued, control = run_recipe.apply_standalone_cache_nonce(prompt, "pair:wan:W1")

        self.assertEqual(prompt["8"]["inputs"]["seed"], 42)
        self.assertNotIn(run_recipe.SUITE_CACHE_NONCE_INPUT, prompt["8"]["inputs"])
        self.assertEqual(queued["8"]["inputs"]["seed"], 42)
        self.assertEqual(
            queued["8"]["inputs"][run_recipe.SUITE_CACHE_NONCE_INPUT],
            "pair:wan:W1",
        )
        self.assertEqual(control["source_class_type"], "KSampler")
        self.assertEqual(control["sampler_node_ids"], ["8"])
        self.assertEqual(set(control["fresh_node_ids"]), {"8", "9", "10", "11"})
        self.assertEqual(control["stable_node_ids"], ["1"])

    def test_standalone_cache_nonce_supports_ltx_sampler_custom(self):
        recipe = json.loads(
            (
                run_recipe.REPO_ROOT
                / "recipes"
                / "ltx_video_2b_distilled_cmp_832x480_f193.json"
            ).read_text(encoding="utf-8")
        )

        queued, control = run_recipe.apply_standalone_cache_nonce(
            recipe["prompt"], "pair:ltx:L1"
        )

        self.assertEqual(control["source_class_type"], "SamplerCustom")
        self.assertEqual(control["sampler_node_ids"], ["9"])
        self.assertEqual(queued["9"]["inputs"]["noise_seed"], 42)
        self.assertEqual(
            queued["9"]["inputs"][run_recipe.SUITE_CACHE_NONCE_INPUT],
            "pair:ltx:L1",
        )
        self.assertTrue({"9", "10", "11", "12"}.issubset(control["fresh_node_ids"]))
        self.assertIn("1", control["stable_node_ids"])

    def test_standalone_cache_nonce_rejects_orphan_sampler_branch(self):
        prompt = {
            "1": {"class_type": "UNETLoader", "inputs": {}},
            "8": {
                "class_type": "KSampler",
                "inputs": {"model": ["1", 0], "seed": 42},
            },
            "20": {"class_type": "CreateVideo", "inputs": {"images": ["1", 0]}},
            "21": {"class_type": "SaveVideo", "inputs": {"video": ["20", 0]}},
        }

        with self.assertRaisesRegex(ValueError, "must feed a file-output sink"):
            run_recipe.apply_standalone_cache_nonce(prompt, "pair:orphan:W1")

    def test_standalone_cache_nonce_flag_is_strict_and_not_for_suite(self):
        self.assertEqual(
            run_recipe.parse_standalone_cache_nonce(
                ["run_recipe.py", "recipe.json", "--executor-cache-nonce", "pair:L0"],
                False,
            ),
            "pair:L0",
        )
        for argv, is_suite in (
            (
                [
                    "run_recipe.py",
                    "recipe.json",
                    "--suite",
                    "--executor-cache-nonce",
                    "pair:L0",
                ],
                True,
            ),
            (["run_recipe.py", "recipe.json", "--executor-cache-nonce"], False),
            (
                ["run_recipe.py", "recipe.json", "--executor-cache-nonce", "bad/value"],
                False,
            ),
        ):
            with self.assertRaises(ValueError):
                run_recipe.parse_standalone_cache_nonce(argv, is_suite)

    def test_standalone_cache_runtime_sources_are_exactly_pinned(self):
        self.assertEqual(
            run_recipe.standalone_cache_runtime_sha256s(),
            run_recipe.STANDALONE_CACHE_RUNTIME_SOURCES,
        )

    def test_forbidden_lab_port_override_fails_before_network_or_gpu_query(self):
        with (
            mock.patch.dict(os.environ, {"LAB_PORT": "8188"}, clear=False),
            mock.patch.object(run_recipe, "query_gpu_total_gib") as gpu_query,
            mock.patch.object(run_recipe, "query_server_stats") as server_query,
            mock.patch.object(run_recipe.sys, "argv", ["run_recipe.py", "missing.json"]),
        ):
            self.assertEqual(run_recipe.main(), 1)
        gpu_query.assert_not_called()
        server_query.assert_not_called()

    def test_h3_generator_preserves_bytes_for_semantic_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recipe.json"
            original = b'{\r\n  "name": "sample",\r\n  "value": 1\r\n}'
            path.write_bytes(original)

            changed = build_clean_h3_recipes.write_recipe_if_changed(
                path, {"name": "sample", "value": 1}
            )

            self.assertFalse(changed)
            self.assertEqual(path.read_bytes(), original)

            changed = build_clean_h3_recipes.write_recipe_if_changed(
                path, {"name": "sample", "value": 2}
            )

            self.assertTrue(changed)
            self.assertEqual(path.read_bytes(), b'{\n  "name": "sample",\n  "value": 2\n}\n')

    def test_identity_change_resets_configuration_count_but_not_run_number(self):
        previous = {
            "run_count": 7,
            "config_run_count": 2,
            "run_identity_sha256": "old",
            "gate_pass": True,
        }

        state = run_recipe.next_run_state(previous, "new")

        self.assertEqual(state["run_count"], 8)
        self.assertEqual(state["config_run_count"], 1)
        self.assertFalse(state["same_identity"])
        self.assertFalse(state["previous_gate_pass"])

    def test_identical_passing_configuration_can_become_warm(self):
        previous = {
            "run_count": 7,
            "config_run_count": 1,
            "run_identity_sha256": "same",
            "gate_pass": True,
            "warm_pass": False,
            "pass": False,
            "status": "PASS (cold)",
        }

        state = run_recipe.next_run_state(previous, "same")

        self.assertEqual(state["run_count"], 8)
        self.assertEqual(state["config_run_count"], 2)
        self.assertTrue(state["same_identity"])
        self.assertTrue(state["previous_gate_pass"])

    def test_legacy_receipt_without_identity_restarts_cold(self):
        state = run_recipe.next_run_state({"run_count": 3, "pass": True}, "new")
        self.assertEqual(state["run_count"], 4)
        self.assertEqual(state["config_run_count"], 1)
        self.assertFalse(state["previous_gate_pass"])

    def test_audited_max_run_number_overrides_mutable_alias_counter(self):
        previous = {
            "run_number": 2,
            "config_run_count": 1,
            "run_identity_sha256": "same",
            "gate_pass": True,
        }
        state = run_recipe.next_run_state(previous, "same", previous_run_number=7)
        self.assertEqual(state["run_count"], 8)
        self.assertEqual(state["config_run_count"], 2)

    def test_receipt_history_rejects_rollback_and_malformed_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            (results / "sample_run2.json").write_text(
                json.dumps({"recipe": "sample", "run_number": 2}), encoding="utf-8"
            )
            (results / "sample.json").write_text(
                json.dumps({"recipe": "sample", "run_number": 1}), encoding="utf-8"
            )
            with self.assertRaisesRegex(run_recipe.ReceiptHistoryError, "rolled back"):
                run_recipe.audit_run_history(results, "sample")

            (results / "sample.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(run_recipe.ReceiptHistoryError, "Malformed receipt"):
                run_recipe.audit_run_history(results, "sample")

    def test_receipt_history_surfaces_legacy_alias_archive_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            archive = {"recipe": "sample", "run_number": 1, "status": "PASS"}
            alias = {**archive, "legacy_provenance": True}
            (results / "sample_run1.json").write_text(json.dumps(archive), encoding="utf-8")
            (results / "sample.json").write_text(json.dumps(alias), encoding="utf-8")
            history = run_recipe.audit_run_history(results, "sample")
            self.assertFalse(history["alias_archive_match"])
            self.assertEqual(history["next_run_number"], 2)
            self.assertEqual(history["machine_previous"], archive)
            self.assertEqual(history["machine_previous_source"], "archive_run1")

    def test_modern_current_receipt_without_immutable_archive_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            (results / "sample.json").write_text(
                json.dumps(
                    {
                        "receipt_schema_version": 2,
                        "recipe": "sample",
                        "run_number": 3,
                        "run_identity_sha256": "forged",
                        "config_run_count": 1,
                        "status": "FAIL",
                        "gate_pass": False,
                        "warm_pass": False,
                        "pass": False,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(run_recipe.ReceiptHistoryError, "no matching immutable"):
                run_recipe.audit_run_history(results, "sample")

    def test_history_rejects_results_archive_and_alias_links(self):
        payload = {"recipe": "sample", "run_number": 1, "status": "PASS"}
        encoded = json.dumps(payload)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual = root / "actual-results"
            actual.mkdir()
            (actual / "sample.json").write_text(encoded, encoding="utf-8")
            linked_results = root / "results"
            try:
                linked_results.symlink_to(actual, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")
            with self.assertRaisesRegex(
                run_recipe.ReceiptHistoryError, "symlink or reparse point"
            ):
                run_recipe.audit_run_history(linked_results, "sample")

        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            backing = results / "backing.json"
            backing.write_text(encoded, encoding="utf-8")
            alias = results / "sample.json"
            alias.symlink_to(backing.name)
            with self.assertRaisesRegex(
                run_recipe.ReceiptHistoryError, "symlink or reparse point"
            ):
                run_recipe.audit_run_history(results, "sample")

        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            alias = results / "sample.json"
            alias.write_text(encoded, encoding="utf-8")
            archive = results / "sample_run1.json"
            archive.symlink_to(alias.name)
            with self.assertRaisesRegex(
                run_recipe.ReceiptHistoryError, "symlink or reparse point"
            ):
                run_recipe.audit_run_history(results, "sample")

    def test_history_rejects_archive_hardlinked_to_mutable_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            payload = {"recipe": "sample", "run_number": 1, "status": "PASS"}
            alias = results / "sample.json"
            alias.write_text(json.dumps(payload), encoding="utf-8")
            archive = results / "sample_run1.json"
            try:
                os.link(alias, archive)
            except OSError as exc:
                self.skipTest(f"hardlinks are unavailable: {exc}")
            self.assertTrue(os.path.samefile(alias, archive))
            with self.assertRaisesRegex(
                run_recipe.ReceiptHistoryError, "same file as the mutable current alias"
            ):
                run_recipe.audit_run_history(results, "sample")

    def test_modern_history_and_next_state_reject_type_confusion_and_bad_status(self):
        valid = {
            "receipt_schema_version": 2,
            "recipe": "sample",
            "run_number": 1,
            "run_count": 1,
            "config_run_count": 1,
            "run_identity_sha256": "same",
            "status": "PASS (cold)",
            "gate_pass": True,
            "warm_pass": False,
            "pass": False,
        }
        mutations = (
            ("gate_pass", "false"),
            ("warm_pass", 1),
            ("pass", "false"),
            ("config_run_count", "1"),
            ("config_run_count", True),
            ("status", "FAIL"),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as tmp:
                results = Path(tmp)
                receipt = {**valid, field: value}
                (results / "sample_run1.json").write_text(
                    json.dumps(receipt), encoding="utf-8"
                )
                (results / "sample.json").write_text(
                    json.dumps(receipt), encoding="utf-8"
                )
                with self.assertRaises(run_recipe.ReceiptHistoryError):
                    run_recipe.audit_run_history(results, "sample")

        for previous in (
            {**valid, "gate_pass": "false"},
            {**valid, "config_run_count": "1"},
            {**valid, "config_run_count": True},
            {**valid, "status": "FAIL"},
        ):
            state = run_recipe.next_run_state(previous, "same", previous_run_number=1)
            self.assertFalse(
                state["config_run_count"] >= 2 and state["previous_gate_pass"],
                previous,
            )

    def test_matching_archive_rejects_symlink_and_hardlink_to_current_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            recipe_file = root / "sample.json"
            recipe_file.write_text("{}", encoding="utf-8")
            receipt = {"recipe": "sample", "run_number": 1}
            alias = results / "sample.json"
            alias.write_text(json.dumps(receipt), encoding="utf-8")
            archive = results / "sample_run1.json"
            archive.symlink_to(alias.name)

            *_, errors = validate_recipes.matching_run_archive(
                receipt, recipe_file, root, 2
            )
            self.assertTrue(any("symlink or reparse point" in error for error in errors), errors)

            archive.unlink()
            try:
                os.link(alias, archive)
            except OSError as exc:
                self.skipTest(f"hardlinks are unavailable: {exc}")
            *_, errors = validate_recipes.matching_run_archive(
                receipt, recipe_file, root, 2
            )
            self.assertTrue(any("same file as the mutable current alias" in error for error in errors), errors)

    def test_run_archive_is_exclusive_and_alias_bytes_match_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            archive = results / "sample_run1.json"
            alias = results / "sample.json"
            payload = {"recipe": "sample", "run_number": 1}
            encoded = run_recipe.write_run_receipts_atomic(payload, archive, alias)
            self.assertEqual(archive.read_bytes(), encoded)
            self.assertEqual(alias.read_bytes(), encoded)
            with self.assertRaises(FileExistsError):
                run_recipe.write_run_receipts_atomic(payload, archive, alias)

    def test_busy_queue_creates_durable_quarantine_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            quarantine = Path(tmp) / ".queue.quarantine.json"
            with (
                mock.patch.object(run_recipe, "QUEUE_QUARANTINE_PATH", quarantine),
                mock.patch.object(
                    run_recipe,
                    "query_queue_state",
                    return_value={"queue_running": [[1]], "queue_pending": []},
                ) as query,
                mock.patch.object(run_recipe, "listener_pid", return_value=123),
            ):
                with self.assertRaisesRegex(run_recipe.PreflightError, "quarantined"):
                    run_recipe.ensure_queue_idle()
                self.assertTrue(quarantine.is_file())
                query.reset_mock()
                with self.assertRaisesRegex(run_recipe.PreflightError, "quarantine is present"):
                    run_recipe.ensure_queue_idle()
                query.assert_not_called()

    def test_suite_parent_watchdog_exits_child_after_proved_cleanup(self):
        cleanup = mock.Mock(return_value={"success": True})
        exit_fn = mock.Mock()
        watchdog = run_recipe.SuiteParentWatchdog(
            123,
            1.0,
            interval_s=0.001,
            cleanup_fn=cleanup,
            exit_fn=exit_fn,
        )
        with mock.patch.object(watchdog, "parent_alive", return_value=False):
            watchdog.start()
            watchdog.join(timeout=1)
        cleanup.assert_called_once()
        exit_fn.assert_called_once_with(97)

    def test_suite_parent_watchdog_exits_even_when_cleanup_and_quarantine_raise(self):
        cleanup = mock.Mock(side_effect=RuntimeError("cleanup boom"))
        exit_fn = mock.Mock()
        watchdog = run_recipe.SuiteParentWatchdog(
            123,
            1.0,
            interval_s=0.001,
            cleanup_fn=cleanup,
            exit_fn=exit_fn,
        )
        with (
            mock.patch.object(watchdog, "parent_alive", return_value=False),
            mock.patch.object(
                run_recipe,
                "write_queue_quarantine",
                side_effect=RuntimeError("quarantine boom"),
            ) as quarantine,
        ):
            watchdog.start()
            watchdog.join(timeout=1)

        self.assertFalse(watchdog.is_alive())
        cleanup.assert_called_once()
        quarantine.assert_called_once()
        exit_fn.assert_called_once_with(97)

    def test_new_server_instance_changes_run_identity_and_resets_warm(self):
        base = {"recipe_sha256": "a", "server_instance": {"serving_pid": 10, "process_create_time": 1.0}}
        restarted = {**base, "server_instance": {"serving_pid": 11, "process_create_time": 2.0}}
        first_identity = run_recipe.stable_identity(base)
        second_identity = run_recipe.stable_identity(restarted)
        self.assertNotEqual(first_identity, second_identity)
        state = run_recipe.next_run_state(
            {
                "run_number": 1,
                "config_run_count": 1,
                "run_identity_sha256": first_identity,
                "gate_pass": True,
            },
            second_identity,
        )
        self.assertEqual(state["config_run_count"], 1)
        self.assertFalse(state["previous_gate_pass"])

    def test_lab_lock_helper_change_changes_identity_and_resets_warm(self):
        first_payload = {
            "recipe_sha256": "recipe",
            "runner_sha256": "runner",
            "lab_locks_sha256": "a" * 64,
        }
        second_payload = {**first_payload, "lab_locks_sha256": "b" * 64}
        first_identity = run_recipe.stable_identity(first_payload)
        second_identity = run_recipe.stable_identity(second_payload)

        self.assertNotEqual(first_identity, second_identity)
        state = run_recipe.next_run_state(
            {
                "run_number": 4,
                "config_run_count": 1,
                "run_identity_sha256": first_identity,
                "gate_pass": True,
            },
            second_identity,
        )
        self.assertEqual(state["config_run_count"], 1)
        self.assertFalse(state["previous_gate_pass"])

    def test_fixture_discovery_uses_literal_loader_inputs(self):
        recipe = {
            "prompt": {
                "1": {"class_type": "LoadImage", "inputs": {"image": "scene_still.png"}},
                "2": {"class_type": "LoadAudio", "inputs": {"audio": "music_opening.wav"}},
                "3": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "tts_dialogue.wav"}},
            }
        }
        self.assertEqual(
            run_recipe.referenced_fixtures(recipe),
            ["music_opening.wav", "scene_still.png"],
        )

    def test_fixture_discovery_rejects_paths_outside_fixture_root(self):
        recipe = {
            "prompt": {
                "1": {"class_type": "LoadImage", "inputs": {"image": "../secret.png"}},
            }
        }
        with self.assertRaises(ValueError):
            run_recipe.referenced_fixtures(recipe)

    def test_audio_ear_gate_reprobes_hash_bound_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_root = Path(tmp)
            receipt_root = fixture_root / "audio_receipts"
            receipt_root.mkdir()
            fixture = fixture_root / "sample.wav"
            fixture.write_bytes(b"frozen-audio")
            receipt = {
                "schema_version": 1,
                "fixture": "sample.wav",
                "sha256": run_recipe.sha256_file(fixture),
                "ear_gate_pass": True,
                "human_review": {
                    "reviewer": "human",
                    "reviewed_at": "2026-08-08",
                    "content_class": "speech",
                    "description": "Clearly intelligible character dialogue.",
                },
                "ffprobe": {
                    "codec_name": "pcm_f32le",
                    "sample_rate_hz": 32000,
                    "channels": 1,
                    "duration_s": 3.88,
                },
                "volumedetect": {"mean_volume_db": -25.0, "max_volume_db": -6.0},
                "matrix_window": {
                    "method": "ebur128=peak=true",
                    "duration_s": 3.88,
                    "target_lufs": -25.8,
                    "tolerance_lu": 0.3,
                    "gain_db": 0.0,
                    "matched_lufs": -25.8,
                },
                "commands": {
                    "ffprobe": "ffprobe ...",
                    "volumedetect": "ffmpeg ... volumedetect",
                    "matrix_loudness": "ffmpeg ... ebur128=peak=true",
                },
            }
            receipt_file = receipt_root / "sample.json"
            receipt_file.write_text(json.dumps(receipt), encoding="utf-8")
            measured = {
                "codec_name": "pcm_f32le",
                "sample_rate_hz": 32000,
                "channels": 1,
                "duration_s": 3.88,
                "mean_volume_db": -25.0,
                "max_volume_db": -6.0,
            }
            with (
                mock.patch.object(run_recipe, "FIXTURES_DIR", fixture_root),
                mock.patch.object(run_recipe, "AUDIO_RECEIPTS_DIR", receipt_root),
                mock.patch.object(run_recipe, "probe_audio_fixture", return_value=measured),
            ):
                self.assertEqual(
                    run_recipe.validate_audio_fixture_receipt("sample.wav"),
                    run_recipe.sha256_file(receipt_file),
                )
                measured["sample_rate_hz"] = 44100
                with self.assertRaises(ValueError):
                    run_recipe.validate_audio_fixture_receipt("sample.wav")

    def test_live_widget_gate_rejects_missing_required_and_bad_link_slots(self):
        object_info = {
            "Source": {
                "input": {"required": {"value": ["INT", {}]}, "optional": {}},
                "output": ["LATENT"],
            },
            "Sink": {
                "input": {"required": {"samples": ["LATENT", {}]}, "optional": {}},
                "output": [],
                "output_node": True,
            },
        }
        missing = {
            "prompt": {
                "1": {"class_type": "Source", "inputs": {}},
                "2": {"class_type": "Sink", "inputs": {"samples": ["1", 0]}},
            }
        }
        with self.assertRaises(run_recipe.PreflightError):
            run_recipe.check_widget_integrity(missing, object_info)

        bad_slot = {
            "prompt": {
                "1": {"class_type": "Source", "inputs": {"value": 1}},
                "2": {"class_type": "Sink", "inputs": {"samples": ["1", 1]}},
            }
        }
        with self.assertRaises(run_recipe.PreflightError):
            run_recipe.check_widget_integrity(bad_slot, object_info)

    def test_live_widget_gate_accepts_dynamic_combo_subinputs(self):
        object_info = {
            "Resize": {
                "input": {
                    "required": {
                        "image": ["IMAGE", {}],
                        "resize_type": ["COMFY_DYNAMICCOMBO_V3", {}],
                    },
                    "optional": {},
                },
                "output": ["IMAGE"],
            },
            "Source": {"input": {"required": {}, "optional": {}}, "output": ["IMAGE"]},
        }
        recipe = {
            "prompt": {
                "1": {"class_type": "Source", "inputs": {}},
                "2": {
                    "class_type": "Resize",
                    "inputs": {
                        "image": ["1", 0],
                        "resize_type.width": 832,
                        "resize_type.height": 480,
                        "resize_type.crop": "disabled",
                    },
                },
            }
        }
        run_recipe.check_widget_integrity(recipe, object_info)

    def test_final_provenance_failure_is_captured_for_invalid_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            recipe_path = Path(tmp) / "recipe.json"
            recipe_path.write_text('{"prompt": {}}', encoding="utf-8")
            with mock.patch.object(
                run_recipe, "audio_receipt_sha256s", side_effect=ValueError("receipt drift")
            ):
                snapshot = run_recipe.capture_provenance_snapshot(
                    recipe_path, {"prompt": {}}
                )
        self.assertFalse(snapshot["valid"])
        self.assertIn("receipt drift", snapshot["error"])

    def test_suite_lock_blocks_unrelated_runner_but_allows_owned_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite_lock = root / ".suite.lock"
            gpu_lock = root / ".gpu.lock"
            coordinator = root / ".coordinator.mutex"
            with run_h3_suite.SuiteLock(
                suite_lock, gpu_path=gpu_lock, coordinator_path=coordinator
            ) as owner:
                unrelated = run_recipe.LockManager(
                    gpu_lock,
                    suite_lock_path=suite_lock,
                    coordinator_path=coordinator,
                )
                with self.assertRaises(run_recipe.PreflightError):
                    unrelated.acquire()

                child_env = owner.child_environment({})
                child = run_recipe.LockManager(
                    gpu_lock,
                    suite_child=True,
                    suite_lock_path=suite_lock,
                    coordinator_path=coordinator,
                    environment=child_env,
                )
                with mock.patch.object(lab_locks.os, "getppid", return_value=os.getpid()):
                    child.acquire()
                self.assertTrue(gpu_lock.exists())
                child.release()
                self.assertTrue(gpu_lock.exists())

            self.assertFalse(suite_lock.exists())
            self.assertFalse(gpu_lock.exists())

    @staticmethod
    def _valid_suite_children():
        children = []
        sentinel_count = 0
        pair_counts = {"T": 0, "I": 0, "R": 0}
        identities = {
            "h3_i2v_suite_sentinel": "sentinel-id",
            "h3_t2v_best": "t-id",
            "h3_i2v_best": "i-id",
            "h3_r2v_best": "r-id",
        }
        for label, recipe, role in run_h3_suite.CANONICAL_SEQUENCE:
            if label.startswith(("W", "S")):
                sentinel_count += 1
                run_number = config_count = sentinel_count
            else:
                family = label[0]
                pair_counts[family] += 1
                run_number = config_count = pair_counts[family]
            children.append(
                {
                    "label": label,
                    "recipe": recipe,
                    "role": role,
                    "status": "PASS" if label in {"T1", "I1", "R1"} else "PASS (cold)",
                    "gate_pass": True,
                    "warm_pass": label in {"T1", "I1", "R1", "S0", "S1", "S2", "S3"},
                    "run_number": run_number,
                    "config_run_count": config_count,
                    "run_identity_sha256": identities[recipe],
                    "lab_locks_sha256": "a" * 64,
                    "server_instance": {"serving_pid": 10, "process_create_time": 1.0},
                    "peak_vram_gib": 10.0,
                    "baseline_vram_gib": 3.0,
                    "net_peak_vram_gib": 7.0,
                    "pre_settle_samples_gib": [3.0, 3.0],
                    "pre_settle_median_gib": 3.0,
                    "post_settle_samples_gib": [3.0, 3.0],
                    "post_settle_median_gib": 3.0,
                    "settled_delta_gib": 0.0,
                    "output_path": f"{label}.mp4",
                    "queued_prompt_sha256": "e" * 64,
                    "execution_cache_control": {
                        "mode": "pinned-undeclared-randomnoise-input",
                        "nonce": f"run:{label}",
                        "recipe_noise_seed": 42,
                        "fresh_execution_proved": True,
                        "cached_fresh_node_ids": [],
                        "sampler_node_ids": ["8"],
                        "stable_node_ids": ["1", "2"],
                        "cached_node_ids": ["1", "2"],
                    },
                }
            )
        return children

    def test_h3_suite_evaluation_requires_warm_pairs_and_no_creep(self):
        children = self._valid_suite_children()
        self.assertEqual(run_h3_suite.evaluate_suite(children, 0.25), [])
        for invalid_tolerance in (True, "0.25", float("nan"), float("inf")):
            self.assertTrue(
                run_h3_suite.evaluate_suite(children, invalid_tolerance),
                invalid_tolerance,
            )
        warm = next(child for child in children if child["label"] == "T1")
        warm["peak_vram_gib"] = 10.251
        warm["net_peak_vram_gib"] = 7.251
        failures = run_h3_suite.evaluate_suite(children, 0.25)
        self.assertTrue(any("T1 peak_vram_gib rose" in failure for failure in failures))
        self.assertTrue(run_h3_suite.vram_creep_failures(failures))
        self.assertEqual(
            run_h3_suite.vram_creep_failures(["T1 is not a passing second consecutive identity"]),
            [],
        )

    def test_h3_suite_ignores_baseline_confounded_net_peak_deltas(self):
        children = self._valid_suite_children()
        by_label = {child["label"]: child for child in children}
        for label in ("S0", "T0", "I0", "R0"):
            by_label[label]["baseline_vram_gib"] = 5.0
            by_label[label]["net_peak_vram_gib"] = 5.0
        for label in ("S1", "S2", "S3", "T1", "I1", "R1"):
            by_label[label]["baseline_vram_gib"] = 3.0
            by_label[label]["net_peak_vram_gib"] = 7.0

        failures = run_h3_suite.evaluate_suite(children, 0.25)
        self.assertEqual(failures, [])
        self.assertFalse(
            any("net_peak_vram_gib" in failure for failure in failures), failures
        )

    def test_h3_suite_rejects_recomputed_post_settle_creep(self):
        children = self._valid_suite_children()
        warm = next(child for child in children if child["label"] == "T1")
        warm["post_settle_samples_gib"] = [3.251, 3.251]
        warm["post_settle_median_gib"] = 3.251
        warm["settled_delta_gib"] = 0.251

        failures = run_h3_suite.evaluate_suite(children, 0.25)
        self.assertTrue(
            any(
                "T1 post_settle_median_gib rose 0.251" in failure
                for failure in failures
            ),
            failures,
        )

    def test_suite_settle_samples_are_required_and_recomputed(self):
        child = {
            "label": "T0",
            "run_number": 1,
            "config_run_count": 1,
            "peak_vram_gib": 8.0,
            "net_peak_vram_gib": 5.0,
            "pre_settle_samples_gib": [3.0, 3.2],
            "pre_settle_median_gib": 3.1,
            "post_settle_samples_gib": [3.2, 3.4],
            "post_settle_median_gib": 3.3,
            "settled_delta_gib": 0.2,
        }
        self.assertEqual(run_h3_suite.suite_numeric_failures(child), [])
        self.assertEqual(validate_recipes._suite_summary_numeric_errors(child), [])

        for invalid_net in (True, float("nan"), float("inf")):
            with self.subTest(invalid_net=invalid_net):
                invalid = dict(child)
                invalid["net_peak_vram_gib"] = invalid_net
                self.assertTrue(
                    any(
                        "net_peak_vram_gib" in error
                        for error in run_h3_suite.suite_numeric_failures(invalid)
                    )
                )
                self.assertTrue(
                    any(
                        "net_peak_vram_gib" in error
                        for error in validate_recipes._suite_summary_numeric_errors(invalid)
                    )
                )

        missing = dict(child)
        missing.pop("pre_settle_samples_gib")
        self.assertTrue(
            any(
                "pre_settle_samples_gib" in error
                for error in run_h3_suite.suite_numeric_failures(missing)
            )
        )

        for field, bad_value in (
            ("pre_settle_median_gib", 3.0),
            ("post_settle_median_gib", 3.2),
            ("settled_delta_gib", 0.1),
        ):
            tampered = dict(child)
            tampered[field] = bad_value
            runner_errors = run_h3_suite.suite_numeric_failures(tampered)
            validator_errors = validate_recipes._suite_summary_numeric_errors(tampered)
            self.assertTrue(any(field in error for error in runner_errors), runner_errors)
            self.assertTrue(any(field in error for error in validator_errors), validator_errors)

    def test_suite_lane_receipt_and_child_args_derive_from_manifest(self):
        reserve, disable, label, args = run_h3_suite.suite_lane(
            {
                "boot_lane": {
                    "reserve_vram_gib": 8.5,
                    "disable_pinned_memory": False,
                    "cache_mode": "classic",
                }
            }
        )
        self.assertEqual(reserve, 8.5)
        self.assertFalse(disable)
        self.assertEqual(label, "lab-8199, sage-free, cache-classic, reserve-8.5gb")
        self.assertEqual(args, [])

    def test_suite_manifest_rejects_substitution_reordering_and_role_drift(self):
        base = {
            "sequence": [
                {"label": label, "recipe": recipe, "role": role}
                for label, recipe, role in run_h3_suite.CANONICAL_SEQUENCE
            ]
        }
        for mutation in ("substitute", "reorder", "role"):
            manifest = json.loads(json.dumps(base))
            if mutation == "substitute":
                manifest["sequence"][2]["recipe"] = "h3_i2v_low"
            elif mutation == "reorder":
                manifest["sequence"][2], manifest["sequence"][3] = (
                    manifest["sequence"][3], manifest["sequence"][2]
                )
            else:
                manifest["sequence"][2]["role"] = "sentinel"
            with self.assertRaisesRegex(run_h3_suite.SuiteFailure, "canonical ordered"):
                run_h3_suite.preflight_manifest(manifest)

    def test_suite_evaluation_rejects_identity_counter_and_server_discontinuity(self):
        children = []
        sentinel_count = 0
        pair_counts = {"T": 0, "I": 0, "R": 0}
        for label, recipe, role in run_h3_suite.CANONICAL_SEQUENCE:
            if label.startswith(("W", "S")):
                sentinel_count += 1
                count = sentinel_count
                identity = "sentinel"
            else:
                pair_counts[label[0]] += 1
                count = pair_counts[label[0]]
                identity = label[0]
            children.append(
                {
                    "label": label,
                    "recipe": recipe,
                    "role": role,
                    "status": "PASS",
                    "gate_pass": True,
                    "warm_pass": label != "W0",
                    "run_number": count,
                    "config_run_count": count,
                    "run_identity_sha256": identity,
                    "lab_locks_sha256": "a" * 64,
                    "server_instance": {"serving_pid": 1, "process_create_time": 1.0},
                    "peak_vram_gib": 8.0,
                    "net_peak_vram_gib": 5.0,
                    "pre_settle_samples_gib": [3.0, 3.0],
                    "pre_settle_median_gib": 3.0,
                    "post_settle_samples_gib": [3.0, 3.0],
                    "post_settle_median_gib": 3.0,
                    "settled_delta_gib": 0.0,
                    "output_path": f"{label}.mp4",
                    "queued_prompt_sha256": "e" * 64,
                    "execution_cache_control": {
                        "mode": "pinned-undeclared-randomnoise-input",
                        "nonce": f"run:{label}",
                        "recipe_noise_seed": 42,
                        "fresh_execution_proved": True,
                        "cached_fresh_node_ids": [],
                        "sampler_node_ids": ["8"],
                        "stable_node_ids": ["1", "2"],
                        "cached_node_ids": ["1", "2"],
                    },
                }
            )
        next(child for child in children if child["label"] == "T1")["run_identity_sha256"] = "other"
        next(child for child in children if child["label"] == "I1")["config_run_count"] = 9
        next(child for child in children if child["label"] == "S2")["server_instance"] = {
            "serving_pid": 2,
            "process_create_time": 2.0,
        }
        next(child for child in children if child["label"] == "R1")[
            "lab_locks_sha256"
        ] = "b" * 64
        failures = run_h3_suite.evaluate_suite(children, 0.25)
        self.assertTrue(any("T0/T1" in failure for failure in failures))
        self.assertTrue(any("I1 config count" in failure for failure in failures))
        self.assertTrue(any("server instance" in failure for failure in failures))
        self.assertTrue(any("lab_locks.py hash" in failure for failure in failures))

    def test_suite_receipts_use_unique_ids_and_atomic_byte_parity(self):
        first = run_h3_suite.suite_run_id()
        second = run_h3_suite.suite_run_id()
        self.assertNotEqual(first, second)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "suite-archive.json"
            alias = root / "suite-current.json"
            with mock.patch.object(run_h3_suite, "SUITE_RESULT", alias):
                encoded = run_h3_suite.write_receipt(
                    {"suite": "sample", "status": "RUNNING"},
                    archive,
                    create_archive=True,
                )
                self.assertEqual(archive.read_bytes(), encoded)
                self.assertEqual(alias.read_bytes(), encoded)
                with self.assertRaises(FileExistsError):
                    run_h3_suite.write_receipt(
                        {"suite": "sample"}, archive, create_archive=True
                    )

    def test_release_failure_overwrites_provisional_pass_in_archive_and_alias(self):
        class FailingReleaseLock:
            def release(self, checkpoint=None):
                self.assert_checkpoint(checkpoint)
                checkpoint(())
                checkpoint(("forced coordinator unlock failure",))
                raise run_h3_suite.SuiteFailure("forced coordinator unlock failure")

            @staticmethod
            def assert_checkpoint(checkpoint):
                if checkpoint is None:
                    raise AssertionError("release checkpoint is required")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "h3_best_suite_run.json"
            alias = root / "h3_best_suite.json"
            payload = {
                "suite": "h3_best_suite",
                "status": "MACHINE SUITE FINALIZING",
                "machine_pass": False,
                "promotion_ready": False,
                "failures": [],
                "lease_release": {"success": False, "reason": "pending"},
            }
            with mock.patch.object(run_h3_suite, "SUITE_RESULT", alias):
                run_h3_suite.write_receipt(payload, archive, create_archive=True)
                failure = run_h3_suite.release_suite_with_evidence(
                    FailingReleaseLock(),
                    payload,
                    archive,
                    provisional_machine_pass=True,
                )

            self.assertIsInstance(failure, run_h3_suite.SuiteFailure)
            self.assertEqual(archive.read_bytes(), alias.read_bytes())
            durable = json.loads(alias.read_text(encoding="utf-8"))
            self.assertFalse(durable["machine_pass"])
            self.assertEqual(durable["status"], "MACHINE SUITE FAIL")
            self.assertFalse(durable["lease_release"]["success"])
            self.assertTrue(
                any("coordinator unlock failure" in item for item in durable["failures"]),
                durable["failures"],
            )

    def test_torn_release_pass_cannot_leave_a_passing_archive(self):
        class TornReleaseLock:
            def release(self, checkpoint=None):
                if checkpoint is None:
                    raise AssertionError("release checkpoint is required")
                try:
                    checkpoint(())
                except Exception as exc:
                    try:
                        checkpoint((f"checkpoint failed: {exc}",))
                    except Exception:
                        pass
                    raise run_h3_suite.SuiteFailure("forced torn publish") from exc

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "h3_best_suite_run.json"
            alias = root / "h3_best_suite.json"
            payload = {
                "suite": "h3_best_suite",
                "status": "MACHINE SUITE FINALIZING",
                "machine_pass": False,
                "promotion_ready": False,
                "failures": [],
                "lease_release": {"success": False, "reason": "pending"},
            }
            with mock.patch.object(run_h3_suite, "SUITE_RESULT", alias):
                run_h3_suite.write_receipt(payload, archive, create_archive=True)

                def torn_replace(path, encoded, *, exclusive=False):
                    if path == alias and json.loads(encoded)["machine_pass"] is True:
                        path.write_bytes(encoded)
                        return
                    raise OSError("forced publication failure")

                with mock.patch.object(
                    run_h3_suite, "_atomic_replace", side_effect=torn_replace
                ):
                    failure = run_h3_suite.release_suite_with_evidence(
                        TornReleaseLock(),
                        payload,
                        archive,
                        provisional_machine_pass=True,
                    )

            self.assertIsInstance(failure, run_h3_suite.SuiteFailure)
            archived = json.loads(archive.read_text(encoding="utf-8"))
            current = json.loads(alias.read_text(encoding="utf-8"))
            self.assertFalse(archived["machine_pass"])
            self.assertTrue(current["machine_pass"])
            self.assertNotEqual(archive.read_bytes(), alias.read_bytes())

    def test_fresh_start_cleanup_failure_replaces_stale_pass_with_unique_fail(self):
        class CheckpointSuiteLock:
            def __init__(self):
                self.child_environment_called = False

            def acquire(self):
                return None

            def child_environment(self, _env):
                self.child_environment_called = True
                raise AssertionError("fresh-start failure must not launch a child")

            def release(self, checkpoint=None):
                if checkpoint is None:
                    raise AssertionError("release checkpoint is required")
                checkpoint(())

        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            alias = results / "h3_best_suite.json"
            alias.write_text(
                json.dumps({"machine_pass": True, "status": "STALE PASS"}),
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "name": "h3_best_suite",
                "sequence": [
                    {"label": label, "recipe": recipe, "role": role}
                    for label, recipe, role in run_h3_suite.CANONICAL_SEQUENCE
                ],
                "creep_tolerance_gib": 0.25,
            }
            recipe_hashes = {
                recipe: "pinned-hash"
                for _, recipe, _ in run_h3_suite.CANONICAL_SEQUENCE
            }
            suite_lock = CheckpointSuiteLock()
            failed_cleanup = {
                "success": False,
                "reason": "forced fresh-start cleanup failure",
            }
            with (
                mock.patch.object(run_h3_suite, "SUITE_RESULT", alias),
                mock.patch.object(run_h3_suite.run_recipe, "RESULTS_DIR", results),
                mock.patch.object(run_h3_suite, "load_manifest", return_value=(manifest, b"{}")),
                mock.patch.object(run_h3_suite, "preflight_manifest", return_value=recipe_hashes),
                mock.patch.object(
                    run_h3_suite,
                    "suite_lane",
                    return_value=(8.5, False, "lab-8199, sage-free, reserve-8.5gb", []),
                ),
                mock.patch.object(run_h3_suite, "SuiteLock", return_value=suite_lock),
                mock.patch.object(run_h3_suite, "suite_run_id", return_value="fresh-fail"),
                mock.patch.object(run_h3_suite.run_recipe, "enforce_lab_port"),
                mock.patch.object(
                    run_h3_suite.run_recipe,
                    "shutdown_lab_server",
                    return_value=failed_cleanup,
                ) as cleanup,
                mock.patch.object(
                    run_h3_suite.run_recipe, "sha256_file", return_value="pinned-hash"
                ),
                mock.patch.object(
                    run_h3_suite.run_recipe,
                    "suite_cache_runtime_sha256s",
                    return_value=run_recipe.SUITE_CACHE_RUNTIME_SOURCES,
                ),
                mock.patch.object(run_h3_suite.sys, "argv", ["run_h3_suite.py"]),
            ):
                self.assertEqual(run_h3_suite.main(), 1)

            archive = results / "h3_best_suite_fresh-fail.json"
            self.assertTrue(archive.is_file())
            self.assertEqual(archive.read_bytes(), alias.read_bytes())
            durable = json.loads(alias.read_text(encoding="utf-8"))
            self.assertEqual(durable["suite_run_id"], "fresh-fail")
            self.assertFalse(durable["machine_pass"])
            self.assertEqual(durable["status"], "MACHINE SUITE FAIL")
            self.assertEqual(durable["fresh_start_cleanup"], failed_cleanup)
            self.assertEqual(durable["children"], [])
            self.assertTrue(durable["lease_release"]["success"])
            self.assertFalse(suite_lock.child_environment_called)
            cleanup.assert_called_once_with()

    def test_final_settle_sampling_rejects_server_restart_after_last_sample(self):
        manifest = {
            "settle_before_sampling_s": 0.001,
            "settle_sample_duration_s": 0.001,
            "settle_sample_interval_s": 0.001,
        }
        expected = {"serving_pid": 100, "process_create_time": 1.0}
        restarted = {"serving_pid": 101, "process_create_time": 2.0}
        with (
            mock.patch.object(run_h3_suite.time, "sleep"),
            mock.patch.object(
                run_h3_suite.run_recipe, "query_gpu_vram_mb", return_value=3072.0
            ) as query_vram,
            mock.patch.object(
                run_h3_suite.run_recipe,
                "verified_server_instance",
                side_effect=[expected, expected, expected, expected, expected, restarted],
            ),
        ):
            with self.assertRaisesRegex(
                run_h3_suite.SuiteFailure,
                "after S3 post-render sample 2/2",
            ):
                run_h3_suite.settle_samples(
                    manifest, expected, "S3 post-render"
                )
        self.assertEqual(query_vram.call_count, 2)

    def test_suite_interrupt_writes_durable_fail_then_re_raises_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            manifest = {
                "schema_version": 1,
                "name": "h3_best_suite",
                "sequence": [
                    {"label": label, "recipe": recipe, "role": role}
                    for label, recipe, role in run_h3_suite.CANONICAL_SEQUENCE
                ],
                "creep_tolerance_gib": 0.25,
            }
            recipe_hashes = {
                recipe: "pinned-hash"
                for _, recipe, _ in run_h3_suite.CANONICAL_SEQUENCE
            }
            suite_lock = mock.Mock()
            suite_lock.child_environment.return_value = {}
            cleanup = mock.Mock(return_value={"success": True, "reason": "mocked clean"})

            with (
                mock.patch.object(run_h3_suite, "SUITE_RESULT", results / "h3_best_suite.json"),
                mock.patch.object(run_h3_suite.run_recipe, "RESULTS_DIR", results),
                mock.patch.object(run_h3_suite, "load_manifest", return_value=(manifest, b"{}")),
                mock.patch.object(run_h3_suite, "preflight_manifest", return_value=recipe_hashes),
                mock.patch.object(
                    run_h3_suite,
                    "suite_lane",
                    return_value=(
                        8.5,
                        False,
                        "lab-8199, sage-free, reserve-8.5gb",
                        [],
                    ),
                ),
                mock.patch.object(run_h3_suite, "SuiteLock", return_value=suite_lock),
                mock.patch.object(run_h3_suite.run_recipe, "enforce_lab_port"),
                mock.patch.object(run_h3_suite.run_recipe, "shutdown_lab_server", cleanup),
                mock.patch.object(
                    run_h3_suite.run_recipe, "sha256_file", return_value="pinned-hash"
                ),
                mock.patch.object(
                    run_h3_suite.run_recipe,
                    "suite_cache_runtime_sha256s",
                    return_value=run_recipe.SUITE_CACHE_RUNTIME_SOURCES,
                ),
                mock.patch.object(
                    run_h3_suite.run_recipe,
                    "audit_run_history",
                    return_value={"max_run_number": 0},
                ),
                mock.patch.object(
                    run_h3_suite,
                    "settle_samples",
                    side_effect=KeyboardInterrupt("ctrl-c"),
                ),
                mock.patch.object(
                    run_h3_suite,
                    "establish_suite_server",
                    return_value={"serving_pid": 1, "process_create_time": 1.0},
                ),
                mock.patch.object(run_h3_suite.sys, "argv", ["run_h3_suite.py"]),
            ):
                with self.assertRaisesRegex(KeyboardInterrupt, "ctrl-c"):
                    run_h3_suite.main()

            receipt_path = results / "h3_best_suite.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertFalse(receipt["machine_pass"])
            self.assertEqual(receipt["status"], "MACHINE SUITE FAIL")
            self.assertFalse(receipt["canonical_sequence_completed"])
            self.assertFalse(receipt["suite_evaluation_completed"])
            self.assertEqual(receipt["children"], [])
            self.assertTrue(
                any("KeyboardInterrupt: ctrl-c" in failure for failure in receipt["failures"]),
                receipt["failures"],
            )
            self.assertTrue(receipt["cleanup"]["success"])
            self.assertEqual(cleanup.call_count, 2)
            suite_lock.release.assert_called_once()

    def test_suite_lock_loser_writes_no_shared_receipt(self):
        manifest = {
            "name": "h3_best_suite",
            "creep_tolerance_gib": 0.25,
            "boot_lane": {
                "reserve_vram_gib": 12.0,
                "disable_pinned_memory": True,
                "cache_mode": "classic",
            },
            "sequence": [
                {"label": label, "recipe": recipe, "role": role}
                for label, recipe, role in run_h3_suite.CANONICAL_SEQUENCE
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            with (
                mock.patch.object(run_h3_suite, "load_manifest", return_value=(manifest, b"{}")),
                mock.patch.object(run_h3_suite, "preflight_manifest", return_value={}),
                mock.patch.object(run_recipe, "RESULTS_DIR", results),
                mock.patch.object(run_h3_suite, "SUITE_RESULT", results / "h3_best_suite.json"),
                mock.patch.object(
                    run_h3_suite.SuiteLock,
                    "acquire",
                    side_effect=run_h3_suite.SuiteFailure("held"),
                ),
                mock.patch.object(run_h3_suite.sys, "argv", ["run_h3_suite.py"]),
            ):
                self.assertEqual(run_h3_suite.main(), 1)
            self.assertEqual(list(results.glob("*.json")), [])

    def test_suite_loads_exact_next_archive_and_rejects_alias_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            before = run_recipe.audit_run_history(results, "sample")
            payload = {"recipe": "sample", "run_number": 1, "gate_pass": True}
            run_recipe.write_run_receipts_atomic(
                payload, results / "sample_run1.json", results / "sample.json"
            )
            with mock.patch.object(run_recipe, "RESULTS_DIR", results):
                receipt, path, raw = run_h3_suite.load_new_child_receipt("sample", before)
                self.assertEqual(receipt["run_number"], 1)
                self.assertEqual(path.name, "sample_run1.json")
                self.assertEqual(raw, (results / "sample.json").read_bytes())
                (results / "sample.json").write_text(
                    json.dumps({**payload, "note": "drift"}), encoding="utf-8"
                )
                with self.assertRaisesRegex(run_h3_suite.SuiteFailure, "disagrees"):
                    run_h3_suite.load_new_child_receipt("sample", before)

    def test_validator_accepts_suite_receipt_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suites = root / "suites"
            results = root / "results"
            suites.mkdir()
            results.mkdir()
            manifest = suites / "sample.json"
            manifest.write_text(
                '{"schema_version":1,"creep_tolerance_gib":0.25}', encoding="utf-8"
            )
            lock_helper = root / "lab_locks.py"
            lock_helper.write_bytes(b"lock helper")
            receipt_file = results / "sample_suite.json"
            receipt = {
                "suite_schema_version": 1,
                "suite_run_id": "run-id",
                "suite": "sample_suite",
                "status": "RUNNING",
                "machine_pass": False,
                "manifest": "suites/sample.json",
                "manifest_sha256": run_recipe.sha256_file(manifest),
                "runner_sha256": "a",
                "lab_locks_sha256": run_recipe.sha256_file(lock_helper),
                "suite_runner_sha256": "b",
                "suite_integrity_sha256": "c" * 64,
                "recipe_sha256s": {},
                "boot_lane": "lab-8199, sage-free, reserve-12gb",
                "creep_tolerance_gib": 0.25,
                "vram_creep": False,
                "children": [],
                "failures": [],
                "cleanup": {"success": False, "reason": "running"},
            }
            archival = results / "sample_suite_run-id.json"
            encoded = json.dumps(receipt).encode("utf-8")
            receipt_file.write_bytes(encoded)
            archival.write_bytes(encoded)
            self.assertEqual(
                validate_recipes.suite_receipt_errors(receipt, receipt_file, root), []
            )
            lock_helper.write_bytes(b"changed lock helper")
            errors = validate_recipes.suite_receipt_errors(receipt, receipt_file, root)
            self.assertTrue(any("lab_locks.py SHA-256 mismatch" in error for error in errors))

    def test_suite_validator_rejects_summary_that_disagrees_with_hashed_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "suites").mkdir()
            (root / "results").mkdir()
            manifest = {
                "schema_version": 1,
                "sequence": [{"label": "X", "recipe": "sample", "role": "candidate"}],
            }
            manifest_path = root / "suites" / "sample.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            child_payload = {
                "receipt_schema_version": run_recipe.RECEIPT_SCHEMA_VERSION,
                "recipe": "sample",
                "run_number": 1,
                "config_run_count": 1,
                "run_identity_sha256": "id",
                "status": "FAIL",
                "gate_pass": False,
                "warm_pass": False,
                "output_path": "x.mp4",
                "artifact_sha256": "a",
                "recipe_sha256": "r",
                "lab_locks_sha256": "b" * 64,
                "server_instance": {"serving_pid": 1, "process_create_time": 1.0},
                "peak_vram_gb": 99.0,
                "baseline_vram_gb": 1.0,
                "peak_host_ram_gb": 2.0,
                "duration_s": 3.0,
                "provenance_unchanged": True,
                "server_instance_unchanged": True,
            }
            child_path = root / "results" / "sample_run1.json"
            child_path.write_text(json.dumps(child_payload), encoding="utf-8")
            child_summary = {
                "label": "X",
                "recipe": "sample",
                "role": "candidate",
                **child_payload,
                "status": "PASS",
                "gate_pass": True,
                "warm_pass": True,
                "peak_vram_gib": 1.0,
                "baseline_vram_gib": 1.0,
                "net_peak_vram_gib": 0.0,
                "peak_host_ram_gib": 2.0,
                "receipt": "results/sample_run1.json",
                "receipt_sha256": run_recipe.sha256_file(child_path),
            }
            suite = {
                "suite_schema_version": 1,
                "suite_run_id": "id",
                "suite": "sample_suite",
                "status": "RUNNING",
                "machine_pass": False,
                "manifest": "suites/sample.json",
                "manifest_sha256": run_recipe.sha256_file(manifest_path),
                "runner_sha256": "a",
                "lab_locks_sha256": "a" * 64,
                "suite_runner_sha256": "b",
                "suite_integrity_sha256": "c" * 64,
                "recipe_sha256s": {"sample": "r"},
                "boot_lane": "lab-8199, sage-free",
                "creep_tolerance_gib": 0.25,
                "vram_creep": False,
                "children": [child_summary],
                "failures": [],
                "cleanup": {"success": False},
            }
            errors = validate_recipes.suite_receipt_errors(
                suite, root / "results" / "sample_suite_id.json", root
            )
            self.assertTrue(any("status" in error for error in errors))
            self.assertTrue(any("peak_vram_gib" in error for error in errors))
            self.assertTrue(any("lab_locks.py hash" in error for error in errors))

    def test_suite_validator_rejects_nan_summary_over_real_vram_creep(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            suites = root / "suites"
            results.mkdir()
            suites.mkdir()
            manifest = {
                "schema_version": 1,
                "creep_tolerance_gib": 0.25,
                "sequence": [
                    {"label": label, "recipe": recipe, "role": role}
                    for label, recipe, role in run_h3_suite.CANONICAL_SEQUENCE
                ],
            }
            manifest_path = suites / "h3_best_suite.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            children = []
            sentinel_count = 0
            pair_counts = {"T": 0, "I": 0, "R": 0}
            identities = {
                "h3_i2v_suite_sentinel": "sentinel",
                "h3_t2v_best": "t",
                "h3_i2v_best": "i",
                "h3_r2v_best": "r",
            }
            for label, recipe, role in run_h3_suite.CANONICAL_SEQUENCE:
                if label.startswith(("W", "S")):
                    sentinel_count += 1
                    run_number = config_count = sentinel_count
                    warm = label != "W0"
                else:
                    pair_counts[label[0]] += 1
                    run_number = config_count = pair_counts[label[0]]
                    warm = config_count == 2
                peak = 9.0 if label in {"T1", "I1", "R1"} else 8.0
                child_payload = {
                    "receipt_schema_version": run_recipe.RECEIPT_SCHEMA_VERSION,
                    "recipe": recipe,
                    "run_number": run_number,
                    "config_run_count": config_count,
                    "run_identity_sha256": identities[recipe],
                    "status": "PASS" if warm else "PASS (cold)",
                    "gate_pass": True,
                    "warm_pass": warm,
                    "output_path": f"{label}.mp4",
                    "artifact_sha256": f"artifact-{label}",
                    "recipe_sha256": f"recipe-{recipe}",
                    "lab_locks_sha256": "a" * 64,
                    "server_instance": {"serving_pid": 1, "process_create_time": 1.0},
                    "server_instance_unchanged": True,
                    "provenance_unchanged": True,
                    "peak_vram_gb": peak,
                    "baseline_vram_gb": 3.0,
                    "peak_host_ram_gb": 10.0,
                    "duration_s": 1.0,
                }
                child_path = results / f"{recipe}_run{run_number}.json"
                child_raw = (json.dumps(child_payload) + "\n").encode("utf-8")
                child_path.write_bytes(child_raw)
                children.append(
                    {
                        "label": label,
                        "recipe": recipe,
                        "role": role,
                        "run_number": run_number,
                        "config_run_count": config_count,
                        "run_identity_sha256": identities[recipe],
                        "status": child_payload["status"],
                        "gate_pass": True,
                        "warm_pass": warm,
                        "output_path": child_payload["output_path"],
                        "artifact_sha256": child_payload["artifact_sha256"],
                        "recipe_sha256": child_payload["recipe_sha256"],
                        "lab_locks_sha256": child_payload["lab_locks_sha256"],
                        "server_instance": child_payload["server_instance"],
                        "peak_vram_gib": float("nan"),
                        "baseline_vram_gib": 3.0,
                        "net_peak_vram_gib": float("nan"),
                        "peak_host_ram_gib": 10.0,
                        "duration_s": 1.0,
                        "pre_settle_samples_gib": [3.0, 3.0],
                        "pre_settle_median_gib": 3.0,
                        "post_settle_samples_gib": [3.0, 3.0],
                        "post_settle_median_gib": float("nan"),
                        "settled_delta_gib": 0.0,
                        "receipt": str(child_path.relative_to(root)).replace("\\", "/"),
                        "receipt_sha256": run_recipe.sha256_bytes(child_raw),
                    }
                )

            suite = {
                "suite_schema_version": 1,
                "suite_run_id": "id",
                "suite": "h3_best_suite",
                "status": "MACHINE SUITE PASS (human video/audio pending)",
                "machine_pass": True,
                "manifest": "suites/h3_best_suite.json",
                "manifest_sha256": run_recipe.sha256_file(manifest_path),
                "runner_sha256": "runner",
                "lab_locks_sha256": "a" * 64,
                "suite_runner_sha256": "suite-runner",
                "suite_integrity_sha256": "c" * 64,
                "recipe_sha256s": {},
                "boot_lane": "lab-8199, sage-free",
                "creep_tolerance_gib": 0.25,
                "vram_creep": False,
                "children": children,
                "failures": [],
                "cleanup": {"success": True},
                "canonical_sequence_completed": True,
                "suite_evaluation_completed": True,
                "finished_at": "2026-08-08T00:00:00Z",
            }
            receipt_file = results / "h3_best_suite_id.json"
            receipt_file.write_text(json.dumps(suite), encoding="utf-8")

            errors = validate_recipes.suite_receipt_errors(suite, receipt_file, root)

            self.assertTrue(any("finite numeric field" in error for error in errors), errors)
            self.assertTrue(any("peak_vram_gib" in error for error in errors), errors)
            self.assertTrue(
                run_h3_suite.evaluate_suite(children, float("nan")),
                "NaN tolerance must fail closed",
            )

    def test_topology_contract_rejects_dead_nodes_and_socket_drift(self):
        recipe = {
            "topology_contract": {
                "required_connections": {"2.samples": ["1", 0]},
                "required_class_types": ["Source", "Sink"],
                "forbidden_class_types": ["LegacySampler"],
                "require_all_nodes_reachable": True,
            },
            "prompt": {
                "1": {"class_type": "Source", "inputs": {}},
                "2": {"class_type": "SaveVideo", "inputs": {"samples": ["1", 1]}},
                "3": {"class_type": "LegacySampler", "inputs": {}},
            },
        }
        errors = validate_recipes.topology_contract_errors(recipe, recipe["prompt"])
        self.assertTrue(any("socket 2.samples" in error for error in errors))
        self.assertTrue(any("forbidden" in error for error in errors))
        self.assertTrue(any("disconnected" in error for error in errors))

    def test_h3_contracts_pin_exact_nodes_and_mode_specific_absent_inputs(self):
        expected_absent = {
            "t2v": ["7.first_frame", "7.last_frame"],
            "i2v": ["7.last_frame"],
            "r2v": [
                "7.ref_images",
                "7.ref_videos",
                "7.ref_video_audios",
                "7.ref_audios",
                *(f"7.ref_images.ref_image_{index}" for index in range(1, 9)),
                *(f"7.ref_videos.ref_video_{index}" for index in range(3)),
                *(
                    f"7.ref_video_audios.ref_video_audio_{index}"
                    for index in range(3)
                ),
                *(f"7.ref_audios.ref_audio_{index}" for index in range(3)),
            ],
        }
        for mode, absent_inputs in expected_absent.items():
            with self.subTest(mode=mode):
                topology = build_clean_h3_recipes.make_topology_contract(mode)
                self.assertIs(topology["exact_node_set"], True)
                self.assertEqual(topology["required_absent_inputs"], absent_inputs)
                self.assertEqual(
                    topology["installed_schema"],
                    {
                        "comfyui_version": build_clean_h3_recipes.COMFYUI_SCHEMA_VERSION,
                        "git_commit": build_clean_h3_recipes.COMFYUI_SCHEMA_COMMIT,
                    },
                )
                recipe = json.loads(
                    (run_recipe.REPO_ROOT / "recipes" / f"h3_{mode}_best.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(recipe["topology_contract"], topology)

        mime = build_clean_h3_recipes.make_mime_topology_contract()
        self.assertIs(mime["exact_node_set"], True)
        self.assertEqual(mime["required_absent_inputs"], ["7.last_frame"])
        self.assertIn(
            {"node": "2", "input": "device", "equals": "default"},
            mime["required_input_values"],
        )

    def test_h3_contracts_reject_mode_changing_optional_inputs(self):
        cases = (
            ("t2v", "first_frame", ["16", 0]),
            ("i2v", "last_frame", ["11", 0]),
            ("r2v", "ref_videos.ref_video_0", ["11", 0]),
        )
        for mode, input_name, value in cases:
            with self.subTest(mode=mode, input_name=input_name):
                prompt = build_clean_h3_recipes.make_h3_prompt(
                    mode, 1344, 768, 124, is_best=True
                )
                if mode == "t2v":
                    prompt["16"] = {
                        "class_type": "LoadImage",
                        "inputs": {"image": "scene_still.png"},
                    }
                prompt["7"]["inputs"][input_name] = value
                recipe = {
                    "topology_contract": build_clean_h3_recipes.make_topology_contract(mode),
                    "prompt": prompt,
                }
                errors = validate_recipes.topology_contract_errors(recipe, prompt)
                self.assertTrue(
                    any(f"7.{input_name} must be absent" in error for error in errors),
                    errors,
                )
                if mode == "t2v":
                    self.assertTrue(
                        any("exact_node_set contains unexpected nodes" in error for error in errors),
                        errors,
                    )

    def test_live_topology_gate_enforces_exact_nodes_and_absent_inputs(self):
        recipe = {
            "topology_contract": {
                "required_nodes": {"1": "Source", "2": "SaveVideo"},
                "exact_node_set": True,
                "required_absent_inputs": ["1.optional_mode"],
            },
            "prompt": {
                "1": {
                    "class_type": "Source",
                    "inputs": {"optional_mode": "mode-changing"},
                },
                "2": {
                    "class_type": "SaveVideo",
                    "inputs": {"samples": ["1", 0]},
                },
                "3": {"class_type": "Extra", "inputs": {}},
            },
        }
        object_info = {
            "Source": {
                "input": {
                    "required": {},
                    "optional": {"optional_mode": ["STRING", {}]},
                },
                "output": ["IMAGE"],
            },
            "SaveVideo": {
                "input": {"required": {"samples": ["IMAGE", {}]}, "optional": {}},
                "output": [],
                "output_node": True,
            },
            "Extra": {"input": {"required": {}, "optional": {}}, "output": []},
        }
        with self.assertRaises(run_recipe.PreflightError) as raised:
            run_recipe.check_widget_integrity(recipe, object_info)
        self.assertIn("exact_node_set contains unexpected nodes", str(raised.exception))
        self.assertIn("1.optional_mode must be absent", str(raised.exception))

    def test_live_topology_gate_freezes_comfyui_version_and_commit(self):
        expected_version = build_clean_h3_recipes.COMFYUI_SCHEMA_VERSION
        expected_commit = build_clean_h3_recipes.COMFYUI_SCHEMA_COMMIT
        recipe = {
            "topology_contract": {
                "installed_schema": {
                    "comfyui_version": expected_version,
                    "git_commit": expected_commit,
                }
            }
        }
        matching_stats = {"system": {"comfyui_version": expected_version}}
        with mock.patch.object(run_recipe, "git_commit", return_value=expected_commit):
            run_recipe.check_installed_schema_contract(recipe, matching_stats)

        with mock.patch.object(run_recipe, "git_commit", return_value=expected_commit):
            with self.assertRaisesRegex(run_recipe.PreflightError, "live server reports"):
                run_recipe.check_installed_schema_contract(
                    recipe, {"system": {"comfyui_version": "0.30.3"}}
                )

        with mock.patch.object(run_recipe, "git_commit", return_value="f" * 40):
            with self.assertRaisesRegex(run_recipe.PreflightError, "installed checkout"):
                run_recipe.check_installed_schema_contract(recipe, matching_stats)

    def test_live_topology_gate_hashes_root_contained_node_source_bytes(self):
        expected_version = build_clean_h3_recipes.COMFYUI_SCHEMA_VERSION
        expected_commit = build_clean_h3_recipes.COMFYUI_SCHEMA_COMMIT
        matching_stats = {"system": {"comfyui_version": expected_version}}
        with tempfile.TemporaryDirectory() as tmp:
            comfy_root = Path(tmp) / "ComfyUI"
            source = comfy_root / "comfy_extras" / "nodes_minimax_h3.py"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"frozen installed node source")
            recipe = {
                "topology_contract": {
                    "installed_schema": {
                        "comfyui_version": expected_version,
                        "git_commit": expected_commit,
                        "node_source": "comfy_extras/nodes_minimax_h3.py",
                        "node_source_sha256": run_recipe.sha256_file(source),
                    }
                }
            }

            with (
                mock.patch.object(run_recipe, "COMFYUI_ROOT", comfy_root),
                mock.patch.object(run_recipe, "git_commit", return_value=expected_commit),
            ):
                run_recipe.check_installed_schema_contract(recipe, matching_stats)

                source.write_bytes(b"dirty source at the same git commit")
                with self.assertRaisesRegex(
                    run_recipe.PreflightError, "node source SHA-256 changed"
                ):
                    run_recipe.check_installed_schema_contract(recipe, matching_stats)

                source.unlink()
                with self.assertRaisesRegex(
                    run_recipe.PreflightError, "node source is missing"
                ):
                    run_recipe.check_installed_schema_contract(recipe, matching_stats)

    def test_live_topology_gate_rejects_node_source_traversal_and_incomplete_pin(self):
        expected_version = build_clean_h3_recipes.COMFYUI_SCHEMA_VERSION
        expected_commit = build_clean_h3_recipes.COMFYUI_SCHEMA_COMMIT
        matching_stats = {"system": {"comfyui_version": expected_version}}
        with tempfile.TemporaryDirectory() as tmp:
            comfy_root = Path(tmp) / "ComfyUI"
            comfy_root.mkdir()
            outside = Path(tmp) / "outside.py"
            outside.write_bytes(b"outside source")
            base_schema = {
                "comfyui_version": expected_version,
                "git_commit": expected_commit,
            }
            traversal_recipe = {
                "topology_contract": {
                    "installed_schema": {
                        **base_schema,
                        "node_source": "../outside.py",
                        "node_source_sha256": run_recipe.sha256_file(outside),
                    }
                }
            }
            incomplete_recipe = {
                "topology_contract": {
                    "installed_schema": {
                        **base_schema,
                        "node_source": "comfy_extras/nodes_minimax_h3.py",
                    }
                }
            }

            with (
                mock.patch.object(run_recipe, "COMFYUI_ROOT", comfy_root),
                mock.patch.object(run_recipe, "git_commit", return_value=expected_commit),
            ):
                with self.assertRaisesRegex(run_recipe.PreflightError, "traversal-free"):
                    run_recipe.check_installed_schema_contract(
                        traversal_recipe, matching_stats
                    )
                with self.assertRaisesRegex(run_recipe.PreflightError, "declared together"):
                    run_recipe.check_installed_schema_contract(
                        incomplete_recipe, matching_stats
                    )

    def test_fixture_hash_contract_checks_visual_and_audio_subset_before_upload(self):
        scene = b"frozen visual fixture"
        style = b"un-pinned but provenance-bound visual"
        audio = b"frozen audio fixture"
        recipe = {
            "topology_contract": {
                "fixture_hashes": {
                    "scene.png": run_recipe.sha256_bytes(scene),
                    "sample.wav": run_recipe.sha256_bytes(audio),
                }
            },
            "prompt": {
                "1": {"class_type": "LoadImage", "inputs": {"image": "scene.png"}},
                "2": {"class_type": "LoadImage", "inputs": {"image": "style.png"}},
                "3": {"class_type": "LoadAudio", "inputs": {"audio": "sample.wav"}},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            fixture_root = Path(tmp)
            (fixture_root / "scene.png").write_bytes(scene)
            (fixture_root / "style.png").write_bytes(style)
            (fixture_root / "sample.wav").write_bytes(audio)
            with (
                mock.patch.object(run_recipe, "FIXTURES_DIR", fixture_root),
                mock.patch.object(
                    run_recipe, "validate_audio_fixture_receipt", return_value="receipt-hash"
                ) as receipt_gate,
                mock.patch.object(run_recipe, "upload_fixtures") as upload,
            ):
                fixture_hashes, receipt_hashes = run_recipe.check_fixtures_uploaded(recipe)

        self.assertEqual(
            fixture_hashes,
            {
                "sample.wav": run_recipe.sha256_bytes(audio),
                "scene.png": run_recipe.sha256_bytes(scene),
                "style.png": run_recipe.sha256_bytes(style),
            },
        )
        self.assertEqual(receipt_hashes, {"sample.wav": "receipt-hash"})
        receipt_gate.assert_called_once_with("sample.wav", audio)
        upload.assert_called_once()
        self.assertEqual(set(upload.call_args.args[0]), {"scene.png", "style.png", "sample.wav"})

    def test_fixture_hash_contract_fails_closed_before_receipt_or_upload(self):
        content = b"actual fixture bytes"
        valid_hash = run_recipe.sha256_bytes(content)
        base_recipe = {
            "prompt": {
                "1": {"class_type": "LoadImage", "inputs": {"image": "scene.png"}}
            }
        }
        cases = (
            (
                "hash drift",
                {"fixture_hashes": {"scene.png": "0" * 64}},
                "SHA-256 mismatch",
            ),
            (
                "extra unreferenced pin",
                {"fixture_hashes": {"scene.png": valid_hash, "ghost.png": valid_hash}},
                "unreferenced/extra",
            ),
            (
                "unsafe pin",
                {"fixture_hashes": {"../scene.png": valid_hash}},
                "must be a basename",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            fixture_root = Path(tmp)
            (fixture_root / "scene.png").write_bytes(content)
            for label, topology, message in cases:
                with self.subTest(case=label):
                    recipe = {**base_recipe, "topology_contract": topology}
                    with (
                        mock.patch.object(run_recipe, "FIXTURES_DIR", fixture_root),
                        mock.patch.object(
                            run_recipe, "validate_audio_fixture_receipt"
                        ) as receipt_gate,
                        mock.patch.object(run_recipe, "upload_fixtures") as upload,
                    ):
                        with self.assertRaisesRegex(run_recipe.PreflightError, message):
                            run_recipe.check_fixtures_uploaded(recipe)
                    receipt_gate.assert_not_called()
                    upload.assert_not_called()

            missing_recipe = {
                "topology_contract": {"fixture_hashes": {"missing.png": valid_hash}},
                "prompt": {
                    "1": {
                        "class_type": "LoadImage",
                        "inputs": {"image": "missing.png"},
                    }
                },
            }
            with mock.patch.object(run_recipe, "FIXTURES_DIR", fixture_root), mock.patch.object(
                run_recipe, "upload_fixtures"
            ) as upload:
                with self.assertRaisesRegex(run_recipe.PreflightError, "Fixture file missing"):
                    run_recipe.check_fixtures_uploaded(missing_recipe)
            upload.assert_not_called()

    def test_fixture_hash_contract_is_optional(self):
        recipe = {
            "prompt": {
                "1": {"class_type": "LoadImage", "inputs": {"image": "scene.png"}}
            }
        }
        run_recipe.validate_fixture_hash_contract(recipe, {"scene.png": b"legacy bytes"})

    def test_fixture_upload_forces_exact_name_and_verifies_readback_hash(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return self.payload

        content = b"frozen-fixture-bytes"
        upload_response = json.dumps(
            {"name": "scene.png", "subfolder": "", "type": "input"}
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            fixture_root = Path(tmp)
            with (
                mock.patch.object(run_recipe, "FIXTURES_DIR", fixture_root),
                mock.patch.object(
                    run_recipe.urllib.request,
                    "urlopen",
                    side_effect=[FakeResponse(upload_response), FakeResponse(content)],
                ) as mock_urlopen,
            ):
                run_recipe.upload_fixtures({"scene.png": content})

            upload_request = mock_urlopen.call_args_list[0].args[0]
            self.assertIn(b'name="overwrite"\r\n\r\ntrue', upload_request.data)
            self.assertIn(b'name="type"\r\n\r\ninput', upload_request.data)
            self.assertIn(b'filename="scene.png"', upload_request.data)
            view_request = mock_urlopen.call_args_list[1].args[0]
            self.assertIn("filename=scene.png", view_request.full_url)
            self.assertIn("type=input", view_request.full_url)

    def test_sha256_file_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_bytes(b"recipe")
            self.assertEqual(
                run_recipe.sha256_file(path),
                "e1d8e552330911f9f779f85b6f2c00a15e790dcc3fbb3b28f5da1d660a30c5b8",
            )

    def test_schema_v2_receipt_cannot_drop_runner_field_to_look_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_file = root / "sample.json"
            output_dir = root / "outputs"
            results_dir = root / "results"
            output_dir.mkdir()
            results_dir.mkdir()
            recipe_file.write_text('{"name":"sample"}', encoding="utf-8")
            output_file = output_dir / "sample.mp4"
            output_file.write_bytes(b"video")
            identity = {
                "recipe_sha256": run_recipe.sha256_file(recipe_file),
                "runner_sha256": "runner-hash",
                "fixture_sha256s": {},
                "boot_lane": "lab-8199, sage-free",
                "server_argv": ["main.py", "--port", "8199"],
                "comfyui_git_commit": "commit",
            }
            receipt = {
                "receipt_schema_version": 2,
                "recipe": "sample",
                "run_number": 2,
                "run_count": 2,
                **identity,
                "identity": identity,
                "run_identity_sha256": run_recipe.stable_identity(identity),
                "gate_pass": True,
                "warm_pass": True,
                "pass": True,
                "status": "PASS",
                "config_run_count": 2,
                "provenance_unchanged": True,
                "output_path": output_file.name,
                "artifact_sha256": run_recipe.sha256_file(output_file),
            }
            (results_dir / "sample_run2.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )

            self.assertEqual(
                validate_recipes.current_certification_errors(receipt, recipe_file, root),
                [],
            )
            receipt.update(
                {
                    "eyeball": "ok",
                    "eyeball_source": "human",
                    "eyeball_reviewed_at": "2026-08-08T00:00:00Z",
                    "human_video_description": "Coherent motion.",
                    "human_video_scope": "full artifact",
                }
            )
            self.assertEqual(
                validate_recipes.current_certification_errors(receipt, recipe_file, root),
                [],
            )
            receipt.pop("runner_sha256")
            errors = validate_recipes.current_certification_errors(receipt, recipe_file, root)
            self.assertTrue(any("runner_sha256" in error for error in errors))

    def test_legacy_manager_probe_identity_is_reproved_from_nested_receipt_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_file = root / "sample.json"
            output_dir = root / "outputs"
            results_dir = root / "results"
            output_dir.mkdir()
            results_dir.mkdir()
            recipe_file.write_text('{"name":"sample"}', encoding="utf-8")
            output_file = output_dir / "sample.mp4"
            output_file.write_bytes(b"video")
            manager_evidence = {
                "enabled": True,
                "recipe_scope": {"id": "historic-manager-lane"},
                "guard_source": {"path": "guard.py", "sha256": "g" * 64},
                "test_boot_source": {"path": "boot.cmd", "sha256": "b" * 64},
                "offline_environment": {"set_nonsecret": {"PIP_NO_INDEX": "1"}},
                "advisory_config": {
                    "snapshot": {"path": "config.ini", "sha256": "a" * 64}
                },
                "log_scan": {
                    "authoritative_server_reported_mode": {"resolved_mode": "offline"},
                    "source_proof": {
                        name: {"sha256": name[0] * 64}
                        for name in (
                            "manager_prestartup",
                            "manager_server",
                            "manager_core",
                            "comfy_folder_paths",
                            "manager_util",
                        )
                    },
                    "current_prestartup_state": {"state_sha256": "s" * 64},
                    "preboot_records": [{"record": {"record_sha256": "p" * 64}}],
                },
                "log_path": "attempt.log",
                "serving_pid": 123,
                "serving_process_create_time_ns": 456,
            }
            manager_identity = validate_recipes.manager_probe_identity_from_receipt(
                manager_evidence
            )
            self.assertIsNotNone(manager_identity)
            # `recipe_scope` was introduced after the receipts this validates;
            # historical identity is still fully re-proved for its own keys.
            manager_identity.pop("recipe_scope")
            identity = {
                "recipe_sha256": run_recipe.sha256_file(recipe_file),
                "runner_sha256": "runner-hash",
                "fixture_sha256s": {},
                "manager_offline_probe_identity": manager_identity,
            }
            receipt = {
                "receipt_schema_version": 2,
                "recipe": "sample",
                "run_number": 2,
                "run_count": 2,
                "recipe_sha256": identity["recipe_sha256"],
                "runner_sha256": identity["runner_sha256"],
                "fixture_sha256s": identity["fixture_sha256s"],
                "identity": identity,
                "run_identity_sha256": run_recipe.stable_identity(identity),
                "gate_pass": True,
                "warm_pass": True,
                "pass": True,
                "status": "PASS",
                "config_run_count": 2,
                "provenance_unchanged": True,
                "output_path": output_file.name,
                "artifact_sha256": run_recipe.sha256_file(output_file),
                "manager_offline_probe": {"pre_queue": manager_evidence},
            }
            archive = results_dir / "sample_run2.json"
            archive.write_text(json.dumps(receipt), encoding="utf-8")

            self.assertEqual(
                validate_recipes.current_certification_errors(receipt, recipe_file, root),
                [],
            )

            bad = json.loads(json.dumps(receipt))
            bad["manager_offline_probe"]["pre_queue"]["log_path"] = "tampered.log"
            archive.write_text(json.dumps(bad), encoding="utf-8")
            errors = validate_recipes.current_certification_errors(bad, recipe_file, root)
            self.assertTrue(
                any("manager_offline_probe.pre_queue disagrees" in error for error in errors),
                errors,
            )

    def test_current_certification_rejects_type_confused_machine_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            outputs = root / "outputs"
            results.mkdir()
            outputs.mkdir()
            recipe_file = root / "sample.json"
            recipe_file.write_text("{}", encoding="utf-8")
            artifact = outputs / "sample.mp4"
            artifact.write_bytes(b"video")
            identity = {
                "recipe_sha256": run_recipe.sha256_file(recipe_file),
                "runner_sha256": "runner",
                "fixture_sha256s": {},
            }
            valid = {
                "receipt_schema_version": 2,
                "recipe": "sample",
                "run_number": 2,
                "run_count": 2,
                **identity,
                "identity": identity,
                "run_identity_sha256": run_recipe.stable_identity(identity),
                "status": "PASS",
                "gate_pass": True,
                "warm_pass": True,
                "pass": True,
                "config_run_count": 2,
                "provenance_unchanged": True,
                "output_path": artifact.name,
                "artifact_sha256": run_recipe.sha256_file(artifact),
            }
            for field, value in (
                ("pass", "false"),
                ("gate_pass", "false"),
                ("warm_pass", 1),
                ("config_run_count", "2"),
                ("config_run_count", True),
                ("run_count", True),
                ("receipt_schema_version", True),
                ("status", "FAIL"),
            ):
                with self.subTest(field=field, value=value):
                    receipt = {**valid, field: value}
                    (results / "sample_run2.json").write_text(
                        json.dumps(receipt), encoding="utf-8"
                    )
                    errors = validate_recipes.current_certification_errors(
                        receipt, recipe_file, root
                    )
                    self.assertTrue(errors, (field, value))

    def test_current_certification_requires_contained_nonempty_regular_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            outputs = root / "outputs"
            results.mkdir()
            outputs.mkdir()
            recipe_file = root / "sample.json"
            recipe_file.write_text("{}", encoding="utf-8")
            safe = outputs / "safe.mp4"
            safe.write_bytes(b"video")
            outside = root / "outside.mp4"
            outside.write_bytes(b"outside")
            identity = {
                "recipe_sha256": run_recipe.sha256_file(recipe_file),
                "runner_sha256": "runner",
                "fixture_sha256s": {},
            }
            base = {
                "receipt_schema_version": 2,
                "recipe": "sample",
                "run_number": 2,
                **identity,
                "identity": identity,
                "run_identity_sha256": run_recipe.stable_identity(identity),
                "status": "PASS",
                "gate_pass": True,
                "warm_pass": True,
                "pass": True,
                "config_run_count": 2,
                "provenance_unchanged": True,
                "output_path": safe.name,
                "artifact_sha256": run_recipe.sha256_file(safe),
            }

            (results / "sample_run2.json").write_text(
                json.dumps(base), encoding="utf-8"
            )
            self.assertEqual(
                validate_recipes.current_certification_errors(base, recipe_file, root),
                [],
            )

            unsafe_cases = [
                ("../outside.mp4", run_recipe.sha256_file(outside)),
                (str(outside.resolve()), run_recipe.sha256_file(outside)),
            ]
            empty = outputs / "empty.mp4"
            empty.write_bytes(b"")
            unsafe_cases.append((empty.name, run_recipe.sha256_file(empty)))
            linked = outputs / "linked.mp4"
            try:
                linked.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"artifact symlinks are unavailable: {exc}")
            unsafe_cases.append((linked.name, run_recipe.sha256_file(outside)))

            for output_name, artifact_hash in unsafe_cases:
                with self.subTest(output_name=output_name):
                    receipt = {
                        **base,
                        "output_path": output_name,
                        "artifact_sha256": artifact_hash,
                    }
                    (results / "sample_run2.json").write_text(
                        json.dumps(receipt), encoding="utf-8"
                    )
                    errors = validate_recipes.current_certification_errors(
                        receipt, recipe_file, root
                    )
                    self.assertTrue(
                        any(
                            token in error
                            for error in errors
                            for token in ("contained", "empty", "symlink", "reparse")
                        ),
                        errors,
                    )

    def test_schema_v3_binds_lab_lock_helper_to_identity_and_current_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_file = root / "sample.json"
            lock_helper = root / "lab_locks.py"
            output_dir = root / "outputs"
            results_dir = root / "results"
            output_dir.mkdir()
            results_dir.mkdir()
            recipe_file.write_text('{"name":"sample"}', encoding="utf-8")
            lock_helper.write_bytes(b"lock helper v1")
            output_file = output_dir / "sample.mp4"
            output_file.write_bytes(b"video")
            identity = {
                "recipe_sha256": run_recipe.sha256_file(recipe_file),
                "runner_sha256": "runner-hash",
                "lab_locks_sha256": run_recipe.sha256_file(lock_helper),
                "fixture_sha256s": {},
            }
            receipt = {
                "receipt_schema_version": run_recipe.RECEIPT_SCHEMA_VERSION,
                "recipe": "sample",
                "run_number": 2,
                **identity,
                "identity": identity,
                "run_identity_sha256": run_recipe.stable_identity(identity),
                "gate_pass": True,
                "warm_pass": True,
                "pass": True,
                "status": "PASS",
                "config_run_count": 2,
                "provenance_unchanged": True,
                "output_path": output_file.name,
                "artifact_sha256": run_recipe.sha256_file(output_file),
            }
            archive = results_dir / "sample_run2.json"
            archive.write_text(json.dumps(receipt), encoding="utf-8")

            self.assertEqual(
                validate_recipes.current_certification_errors(receipt, recipe_file, root),
                [],
            )

            lock_helper.write_bytes(b"lock helper v2")
            errors = validate_recipes.current_certification_errors(
                receipt, recipe_file, root
            )
            self.assertTrue(any("lab_locks.py hash" in error for error in errors), errors)

            missing = dict(receipt)
            missing_identity = dict(identity)
            missing_identity.pop("lab_locks_sha256")
            missing.pop("lab_locks_sha256")
            missing["identity"] = missing_identity
            missing["run_identity_sha256"] = run_recipe.stable_identity(missing_identity)
            archive.write_text(json.dumps(missing), encoding="utf-8")
            errors = validate_recipes.current_certification_errors(
                missing, recipe_file, root
            )
            self.assertTrue(
                any("schema v3 field is missing or invalid" in error for error in errors),
                errors,
            )

    def test_modern_pass_without_immutable_archive_fails_certification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_file = root / "sample.json"
            output_dir = root / "outputs"
            output_dir.mkdir()
            (root / "results").mkdir()
            recipe_file.write_text('{"name":"sample"}', encoding="utf-8")
            output_file = output_dir / "sample.mp4"
            output_file.write_bytes(b"video")
            identity = {
                "recipe_sha256": run_recipe.sha256_file(recipe_file),
                "runner_sha256": "runner-hash",
                "fixture_sha256s": {},
            }
            receipt = {
                "receipt_schema_version": 2,
                "recipe": "sample",
                "run_number": 7,
                **identity,
                "identity": identity,
                "run_identity_sha256": run_recipe.stable_identity(identity),
                "gate_pass": True,
                "warm_pass": True,
                "pass": True,
                "config_run_count": 2,
                "provenance_unchanged": True,
                "output_path": output_file.name,
                "artifact_sha256": run_recipe.sha256_file(output_file),
            }

            errors = validate_recipes.current_certification_errors(receipt, recipe_file, root)

            self.assertTrue(
                any("requires matching immutable archive" in error for error in errors),
                errors,
            )

    def test_current_alias_cannot_promote_failed_cold_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_file = root / "sample.json"
            output_dir = root / "outputs"
            results_dir = root / "results"
            output_dir.mkdir()
            results_dir.mkdir()
            recipe_file.write_text('{"name":"sample"}', encoding="utf-8")
            output_file = output_dir / "sample.mp4"
            output_file.write_bytes(b"video")
            identity = {
                "recipe_sha256": run_recipe.sha256_file(recipe_file),
                "runner_sha256": "runner-hash",
                "fixture_sha256s": {},
            }
            archive = {
                "receipt_schema_version": 2,
                "recipe": "sample",
                "run_number": 3,
                "run_count": 3,
                **identity,
                "identity": identity,
                "run_identity_sha256": run_recipe.stable_identity(identity),
                "status": "FAIL",
                "gate_pass": False,
                "warm_pass": False,
                "pass": False,
                "config_run_count": 1,
                "provenance_unchanged": True,
                "output_path": output_file.name,
                "artifact_sha256": run_recipe.sha256_file(output_file),
            }
            (results_dir / "sample_run3.json").write_text(
                json.dumps(archive), encoding="utf-8"
            )
            receipt = {
                **archive,
                "status": "PASS",
                "gate_pass": True,
                "warm_pass": True,
                "pass": True,
                "config_run_count": 2,
            }

            errors = validate_recipes.current_certification_errors(receipt, recipe_file, root)

            for field in ("status", "gate_pass", "warm_pass", "pass", "config_run_count"):
                self.assertTrue(any(field in error for error in errors), (field, errors))

    def test_clamp_target_translates_to_reserve(self):
        self.assertAlmostEqual(run_recipe.reserve_for_target_gib(16.0, 12.0), 4.0)
        self.assertAlmostEqual(run_recipe.reserve_for_target_gib(16.0, 8.0), 8.0)

    def test_marginal_warm_pass_is_never_promotion_ready(self):
        self.assertFalse(run_recipe.promotion_ready_for_run(True, True, False))
        self.assertFalse(run_recipe.promotion_ready_for_run(True, False, True))
        self.assertTrue(run_recipe.promotion_ready_for_run(True, False, False))

        self.assertTrue(
            run_recipe.recipe_requires_human_eyeball(
                {"contract": {"requires_human_eyeball": True}}
            )
        )
        self.assertTrue(
            run_recipe.recipe_requires_human_eyeball(
                {"contract": {"engine": "minimax_h3"}}
            )
        )
        self.assertFalse(
            run_recipe.recipe_requires_human_eyeball(
                {"contract": {"requires_human_eyeball": False}}
            )
        )

        receipt = {
            "receipt_schema_version": 2,
            "pass": True,
            "status": "PASS (marginal)",
            "promotion_ready": True,
            "run_number": 1,
            "recipe": "sample",
            "config_run_count": 2,
            "gate_pass": True,
            "warm_pass": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            errors = validate_recipes.current_certification_errors(
                receipt, root / "sample.json", root
            )
        self.assertTrue(any("marginal pass cannot" in error for error in errors), errors)

    def test_clamp_rejects_impossible_target(self):
        with self.assertRaises(ValueError):
            run_recipe.reserve_for_target_gib(16.0, 17.0)
        with self.assertRaises(ValueError):
            run_recipe.reserve_for_target_gib(16.0, 0.0)
        with self.assertRaises(ValueError):
            run_recipe.reserve_for_target_gib(16.0, float("nan"))

    def test_direct_reserve_requires_finite_nonnegative_value_below_physical(self):
        self.assertEqual(run_recipe.validate_reserve_gib(12.0, 16.0), 12.0)
        for invalid in [-1.0, float("nan"), float("inf"), 16.0]:
            with self.assertRaises(ValueError):
                run_recipe.validate_reserve_gib(invalid, 16.0)

    def test_boot_lane_requires_exact_reserve_argv(self):
        offline_argv = [
            "main.py",
            "--disable-all-custom-nodes",
            "--whitelist-custom-nodes",
            "ComfyUI-GGUF",
            "ComfyUI-KJNodes",
        ]
        with mock.patch.dict(
            os.environ,
            {"LAB_RESERVE_VRAM_GB": "4", "LAB_DISABLE_PINNED": ""},
            clear=False,
        ):
            run_recipe.check_boot_lane(
                "recipe",
                {"system": {"argv": [*offline_argv, "--reserve-vram", "4"]}},
            )
            with self.assertRaises(run_recipe.PreflightError):
                run_recipe.check_boot_lane(
                    "recipe",
                    {"system": {"argv": [*offline_argv, "--reserve-vram", "12"]}},
                )

    def test_boot_lane_requires_exact_offline_custom_node_whitelist(self):
        valid = [
            "main.py",
            "--disable-all-custom-nodes",
            "--whitelist-custom-nodes",
            "ComfyUI-KJNodes",
            "ComfyUI-GGUF",
        ]
        with mock.patch.dict(
            os.environ,
            {"LAB_RESERVE_VRAM_GB": "", "LAB_DISABLE_PINNED": ""},
            clear=False,
        ):
            run_recipe.check_boot_lane("recipe", {"system": {"argv": valid}})

            cases = (
                (
                    "missing disable-all",
                    [value for value in valid if value != "--disable-all-custom-nodes"],
                    "disable-all-custom-nodes",
                ),
                (
                    "missing whitelist flag",
                    ["main.py", "--disable-all-custom-nodes"],
                    "whitelist-custom-nodes",
                ),
                (
                    "missing required pack",
                    [
                        "main.py",
                        "--disable-all-custom-nodes",
                        "--whitelist-custom-nodes",
                        "ComfyUI-GGUF",
                    ],
                    "must contain exactly",
                ),
                (
                    "extra pack",
                    [*valid, "ComfyUI-VideoHelperSuite"],
                    "must contain exactly",
                ),
                (
                    "duplicate pack",
                    [*valid, "ComfyUI-GGUF"],
                    "must contain exactly",
                ),
                (
                    "manager forbidden",
                    [*valid, "ComfyUI-Manager"],
                    "ComfyUI-Manager is forbidden",
                ),
            )
            for label, argv, message in cases:
                with self.subTest(case=label):
                    with self.assertRaisesRegex(run_recipe.PreflightError, message):
                        run_recipe.check_boot_lane("recipe", {"system": {"argv": argv}})

    def test_boot_lane_requires_exact_classic_cache_mode_for_suite(self):
        base = [
            "main.py",
            "--disable-all-custom-nodes",
            "--whitelist-custom-nodes",
            "ComfyUI-GGUF",
            "ComfyUI-KJNodes",
        ]
        with mock.patch.dict(
            os.environ,
            {
                "LAB_RESERVE_VRAM_GB": "",
                "LAB_DISABLE_PINNED": "",
                "LAB_CACHE_CLASSIC": "1",
            },
            clear=False,
        ):
            run_recipe.check_boot_lane(
                "recipe", {"system": {"argv": [*base, "--cache-classic"]}}
            )
            run_recipe.check_boot_lane(
                "recipe", {"system": {"argv": [*base, "--high-ram"]}}
            )
            with self.assertRaises(run_recipe.PreflightError):
                run_recipe.check_boot_lane("recipe", {"system": {"argv": base}})
            with self.assertRaises(run_recipe.PreflightError):
                run_recipe.check_boot_lane(
                    "recipe",
                    {"system": {"argv": [*base, "--cache-classic", "--cache-none"]}},
                )

    def test_live_schema_shutdown_delegates_to_verified_runner_cleanup(self):
        success = {"success": True, "reason": "verified shutdown"}
        with mock.patch.object(
            run_recipe, "shutdown_lab_server", return_value=success
        ) as shutdown:
            live_schema_check.shutdown_server()
        shutdown.assert_called_once_with()

        failure = {"success": False, "reason": "PID ownership mismatch"}
        with mock.patch.object(run_recipe, "shutdown_lab_server", return_value=failure):
            with self.assertRaisesRegex(RuntimeError, "PID ownership mismatch"):
                live_schema_check.shutdown_server()

    def test_expected_lab_pid_requires_main_port_and_output_directory(self):
        valid_argv = [
            "python.exe",
            str(run_recipe.COMFYUI_ROOT / "main.py"),
            "--port",
            str(run_recipe.LAB_PORT),
            "--output-directory",
            str(run_recipe.REPO_ROOT / "outputs"),
        ]
        process = mock.Mock()
        process.cmdline.return_value = valid_argv
        with mock.patch.object(run_recipe.psutil, "Process", return_value=process):
            self.assertTrue(run_recipe.is_expected_lab_server_pid(123))
            process.cmdline.return_value = [*valid_argv[:-1], "C:\\other\\outputs"]
            self.assertFalse(run_recipe.is_expected_lab_server_pid(123))

    def test_shutdown_retains_receipt_when_pid_identity_is_untrusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=True),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=False),
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(receipt.exists())
            terminate.assert_not_called()

    def test_shutdown_removes_receipt_only_after_verified_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            alive = {"value": True}

            def terminate(_pid):
                alive["value"] = False
                return True

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "terminate_owned_process_tree", side_effect=terminate),
                mock.patch.object(
                    run_recipe.psutil, "pid_exists", side_effect=lambda _pid: alive["value"]
                ),
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertTrue(result["success"])
            self.assertTrue(result["receipt_removed"])
            self.assertFalse(receipt.exists())

    def test_preflight_refuses_to_overwrite_live_orphan_receipt(self):
        with (
            mock.patch.object(run_recipe, "cleanup_stale_pid_receipt"),
            mock.patch.object(run_recipe, "query_server_stats", return_value=None),
            mock.patch.object(run_recipe, "get_recorded_pid", return_value=123),
            mock.patch.object(run_recipe, "check_gpu_idle") as check_idle,
            mock.patch.object(
                run_recipe,
                "boot_lab_server",
                side_effect=AssertionError("unit test must never boot the real lab server"),
            ) as boot,
        ):
            with self.assertRaises(run_recipe.PreflightError):
                run_recipe.check_server_up_and_ownership()
        check_idle.assert_not_called()
        boot.assert_not_called()

    def test_affordability_blocks_same_lane_net_clamp_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            (results / "sample.json").write_text(
                json.dumps(
                    {
                        "recipe_sha256": "same",
                        "boot_lane": "clamp-8gb (reserve-8gb)",
                        "peak_vram_gb": 12.0,
                        "gate_pass": False,
                        "status": "FAIL (net VRAM 9.00 GB > clamp 8.0 GB)",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(run_recipe, "RESULTS_DIR", results):
                with self.assertRaises(run_recipe.PreflightError):
                    run_recipe.check_affordability(
                        "sample", "same", "clamp-8gb (reserve-8gb)"
                    )

    def test_matrix_writer_matches_current_header_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            matrix = Path(tmp) / "matrix.md"
            matrix.write_text(
                "| recipe | tier | status | peak VRAM (GB) | wall clock (s) | gated | pass consecutive | boot lane | last run | notes |\n"
                "|---|---|---|---|---|---|---|---|---|---|\n",
                encoding="utf-8",
            )
            with mock.patch.object(run_recipe, "ENGINE_MATRIX_BETA", matrix):
                run_recipe.update_engine_matrix_beta(
                    "sample", "smoke", "PASS", 6.5, 200.0, "yes", "2/2", "lane", "note"
                )
            row = matrix.read_text(encoding="utf-8").splitlines()[-1]
            columns = [part.strip() for part in row.strip("|").split("|")]
            self.assertEqual(len(columns), 10)
            self.assertEqual(columns[4], "200.0")
            self.assertEqual(columns[6], "2/2")

    def test_media_gate_requires_frames_and_video_packets(self):
        valid_metrics = {
            "encoded_frame_count": 97,
            "video_stream_bytes": 1000,
            "encoded_width": 832,
            "encoded_height": 480,
            "encoded_fps": 25.0,
            "container_duration_s": 3.88,
            "video_duration_s": 3.88,
            "audio_present": True,
            "audio_stream_bytes": 500,
            "audio_duration_s": 3.88,
        }
        contract = {
            "frames": 97,
            "width": 832,
            "height": 480,
            "fps": 25.0,
            "duration_s": 3.88,
        }
        self.assertTrue(
            run_recipe.media_artifact_is_valid(valid_metrics, contract, requires_audio=True)
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {"encoded_frame_count": 0, "video_stream_bytes": 1000}
            )
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {
                    "encoded_frame_count": 97,
                    "video_stream_bytes": 1000,
                    "media_probe_error": "invalid data",
                }
            )
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {**valid_metrics, "encoded_frame_count": 1}, contract
            )
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {**valid_metrics, "encoded_width": 640}, contract
            )
        )
        self.assertFalse(
            run_recipe.media_artifact_is_valid(
                {**valid_metrics, "audio_present": False, "audio_stream_bytes": 0},
                contract,
                requires_audio=True,
            )
        )

    def test_media_gate_and_paper_validator_reject_invalid_numeric_contracts(self):
        contract = {
            "frames": 90,
            "width": 864,
            "height": 480,
            "fps": 24.0,
            "target_s": 3.75,
            "vram_ceiling_gb": 14.5,
        }
        metrics = {
            "encoded_frame_count": 90,
            "video_stream_bytes": 1000,
            "encoded_width": 864,
            "encoded_height": 480,
            "encoded_fps": 24.0,
            "container_duration_s": 3.75,
            "video_duration_s": 3.75,
        }
        self.assertTrue(run_recipe.media_artifact_is_valid(metrics, contract))

        invalid_contracts = (
            ("frames", True),
            ("frames", 0),
            ("width", False),
            ("width", -1),
            ("height", 0),
            ("fps", True),
            ("fps", 0.0),
            ("fps", -1.0),
            ("fps", float("nan")),
            ("fps", float("inf")),
            ("target_s", False),
            ("target_s", 0.0),
            ("target_s", -1.0),
            ("target_s", float("nan")),
            ("target_s", float("inf")),
        )
        for field, value in invalid_contracts:
            with self.subTest(contract_field=field, value=value):
                invalid = {**contract, field: value}
                self.assertFalse(run_recipe.media_artifact_is_valid(metrics, invalid))
                with tempfile.TemporaryDirectory() as tmp:
                    recipe_path = Path(tmp) / "video_numeric_contract.json"
                    recipe_path.write_text(
                        json.dumps(
                            {
                                "name": recipe_path.stem,
                                "contract": invalid,
                                "prompt": {
                                    "1": {"class_type": "SaveVideo", "inputs": {}}
                                },
                            }
                        ),
                        encoding="utf-8",
                    )
                    report = validate_recipes.validate_recipe_file(recipe_path)
                self.assertFalse(report["valid"], report)
                self.assertTrue(
                    any(field in error for error in report["errors"]), report["errors"]
                )

        for field in ("encoded_fps", "container_duration_s", "video_duration_s"):
            for value in (True, 0.0, -1.0, float("nan"), float("inf")):
                with self.subTest(measured_field=field, value=value):
                    self.assertFalse(
                        run_recipe.media_artifact_is_valid(
                            {**metrics, field: value}, contract
                        )
                    )

    def test_video_fingerprint_uses_frame_count_not_measured_audio_bitrate(self):
        left = {
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "encoded_width": 832,
            "encoded_height": 480,
            "encoded_fps": 25.0,
            "encoded_frame_count": 97,
            "audio_bitrate": 127000,
        }
        right = {**left, "audio_bitrate": 129000}
        self.assertEqual(run_recipe.media_fingerprint(left), run_recipe.media_fingerprint(right))
        right["encoded_frame_count"] = 121
        self.assertNotEqual(run_recipe.media_fingerprint(left), run_recipe.media_fingerprint(right))

    def test_bitrate_anomaly_is_strictly_over_twice_same_lane_clean_median(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            outputs = root / "outputs"
            results.mkdir()
            outputs.mkdir()
            base_metrics = {
                "video_codec": "h264",
                "pixel_format": "yuv420p",
                "encoded_width": 832,
                "encoded_height": 480,
                "encoded_fps": 25.0,
                "encoded_frame_count": 97,
            }
            for index, value in enumerate([90.0, 100.0, 110.0], start=1):
                output_name = f"clean{index}.mp4"
                output_file = outputs / output_name
                output_file.write_bytes(f"artifact-{index}".encode("ascii"))
                receipt = {
                    **base_metrics,
                    "video_stream_bytes_per_frame": value,
                    "boot_lane": "lane-a",
                    "eyeball": "ok",
                    "eyeball_source": "human",
                    "eyeball_reviewed_at": "2026-08-08T00:00:00Z",
                    "output_path": output_name,
                    "artifact_sha256": run_recipe.sha256_file(output_file),
                }
                (results / f"sample_run{index}.json").write_text(
                    json.dumps(receipt), encoding="utf-8"
                )

            with (
                mock.patch.object(run_recipe, "RESULTS_DIR", results),
                mock.patch.object(run_recipe, "REPO_ROOT", root),
            ):
                at_two = run_recipe.bitrate_anomaly_fields(
                    "sample", {**base_metrics, "video_stream_bytes_per_frame": 200.0}, "lane-a"
                )
                above_two = run_recipe.bitrate_anomaly_fields(
                    "sample", {**base_metrics, "video_stream_bytes_per_frame": 200.01}, "lane-a"
                )
                other_lane = run_recipe.bitrate_anomaly_fields(
                    "sample", {**base_metrics, "video_stream_bytes_per_frame": 300.0}, "lane-b"
                )

            self.assertFalse(at_two["bitrate_anomaly"])
            self.assertTrue(above_two["bitrate_anomaly"])
            self.assertEqual(other_lane["bitrate_baseline_status"], "provisional:0-of-3-clean-artifacts")


if __name__ == "__main__":
    unittest.main()
