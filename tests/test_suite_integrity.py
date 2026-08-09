import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run_recipe
import suite_integrity
import validate_recipes


class SuiteStorageIntegrityTests(unittest.TestCase):
    def _fixture(self, root: Path):
        recipes = root / "recipes"
        outputs = root / "outputs"
        results = root / "results"
        recipes.mkdir()
        outputs.mkdir()
        results.mkdir()
        recipe = recipes / "sample.json"
        artifact = outputs / "sample.mp4"
        recipe.write_bytes(b'{"name":"sample"}\n')
        artifact.write_bytes(b"video-bytes")
        recipe_hash = hashlib.sha256(recipe.read_bytes()).hexdigest()
        artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        server_instance = {"serving_pid": 123, "process_create_time": 1.0}
        receipt = {
            "receipt_schema_version": 3,
            "recipe": "sample",
            "run_number": 1,
            "config_run_count": 1,
            "run_identity_sha256": "identity",
            "status": "PASS (cold)",
            "gate_pass": True,
            "warm_pass": False,
            "output_path": "sample.mp4",
            "artifact_sha256": artifact_hash,
            "recipe_sha256": recipe_hash,
            "lab_locks_sha256": "d" * 64,
            "server_instance": server_instance,
            "queued_prompt_sha256": "e" * 64,
            "execution_cache_control": {
                "mode": "pinned-undeclared-randomnoise-input",
                "nonce": "suite:S1",
                "recipe_noise_seed": 42,
                "fresh_execution_proved": True,
                "cached_fresh_node_ids": [],
                "sampler_node_ids": ["8"],
                "stable_node_ids": ["1"],
                "cached_node_ids": ["1"],
            },
            "suite_cache_runtime_sha256s": run_recipe.SUITE_CACHE_RUNTIME_SOURCES,
            "final_suite_cache_runtime_sha256s": run_recipe.SUITE_CACHE_RUNTIME_SOURCES,
            "peak_vram_gb": 8.0,
            "baseline_vram_gb": 3.0,
            "peak_host_ram_gb": 10.0,
            "duration_s": 1.0,
            "provenance_unchanged": True,
            "server_instance_unchanged": True,
        }
        receipt_raw = (json.dumps(receipt, sort_keys=True) + "\n").encode("utf-8")
        (results / "sample_run1.json").write_bytes(receipt_raw)
        (results / "sample.json").write_bytes(receipt_raw)
        children = [
            {
                "label": "S1",
                "role": "candidate",
                **{
                    field: receipt[field]
                    for field in suite_integrity._CHILD_RECEIPT_FIELDS
                },
                "peak_vram_gib": 8.0,
                "baseline_vram_gib": 3.0,
                "net_peak_vram_gib": 5.0,
                "peak_host_ram_gib": 10.0,
                "duration_s": 1.0,
                "receipt": "results/sample_run1.json",
                "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            }
        ]
        return recipe, artifact, {"sample": recipe_hash}, children

    def _cache_fixture(self, root: Path):
        recipes = root / "recipes"
        recipes.mkdir()
        prompt = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "model"}},
            "5": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
            "6": {
                "class_type": "BasicGuider",
                "inputs": {"model": ["1", 0]},
            },
            "8": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["5", 0], "guider": ["6", 0]},
            },
            "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0]}},
            "12": {"class_type": "SaveVideo", "inputs": {"video": ["9", 0]}},
            "99": {"class_type": "VAELoader", "inputs": {"vae_name": "dead"}},
        }
        recipe_path = recipes / "sample.json"
        recipe_path.write_text(
            json.dumps({"name": "sample", "prompt": prompt}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pin = run_recipe.sha256_file(recipe_path)
        suite_run_id = "suite-run"
        sequence = [
            {"label": "S0", "recipe": "sample", "role": "sentinel_reference"}
        ]
        queued, static_control = run_recipe.apply_suite_cache_nonce(
            prompt, f"{suite_run_id}:S0"
        )
        control = run_recipe.execution_cache_evidence(
            [["execution_cached", {"nodes": static_control["stable_node_ids"]}]],
            static_control,
        )
        runtime_hashes = dict(run_recipe.SUITE_CACHE_RUNTIME_SOURCES)
        child = {
            "label": "S0",
            "recipe": "sample",
            "role": "sentinel_reference",
            "recipe_sha256": pin,
            "queued_prompt_sha256": run_recipe.stable_identity(queued),
            "execution_cache_control": control,
            "suite_cache_runtime_sha256s": runtime_hashes,
            "final_suite_cache_runtime_sha256s": runtime_hashes,
        }
        return suite_run_id, sequence, {"sample": pin}, [child], runtime_hashes

    def _cache_errors(
        self,
        root: Path,
        fixture,
        *,
        children=None,
        suite_runtime_hashes=None,
        current_runtime_hashes=None,
    ):
        suite_run_id, sequence, pins, fixture_children, runtime_hashes = fixture
        return suite_integrity.suite_cache_evidence_errors(
            root,
            suite_run_id,
            sequence,
            pins,
            fixture_children if children is None else children,
            runtime_hashes if suite_runtime_hashes is None else suite_runtime_hashes,
            runtime_hashes if current_runtime_hashes is None else current_runtime_hashes,
        )

    def test_cache_verifier_recomputes_nonce_prompt_hash_and_graph_closures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._cache_fixture(root)
            self.assertEqual(self._cache_errors(root, fixture), [])

            for field, replacement, expected_error in (
                ("nonce", "forged:S0", "nonce mismatch"),
                ("fresh_node_ids", ["5", "8"], "fresh_node_ids mismatch"),
                ("stable_node_ids", ["1"], "stable_node_ids mismatch"),
                ("reachable_node_ids", ["1", "5"], "reachable_node_ids mismatch"),
                ("sampler_node_ids", ["999"], "sampler_node_ids mismatch"),
            ):
                with self.subTest(field=field):
                    children = json.loads(json.dumps(fixture[3]))
                    children[0]["execution_cache_control"][field] = replacement
                    errors = self._cache_errors(root, fixture, children=children)
                    self.assertTrue(any(expected_error in error for error in errors), errors)

            children = json.loads(json.dumps(fixture[3]))
            children[0]["queued_prompt_sha256"] = "f" * 64
            errors = self._cache_errors(root, fixture, children=children)
            self.assertTrue(any("queued prompt SHA-256 mismatch" in e for e in errors), errors)

    def test_cache_verifier_rejects_forged_dynamic_and_warm_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._cache_fixture(root)

            children = json.loads(json.dumps(fixture[3]))
            control = children[0]["execution_cache_control"]
            control["cached_node_ids"] = ["1", "5", "6"]
            control["cached_fresh_node_ids"] = []
            control["fresh_execution_proved"] = True
            errors = self._cache_errors(root, fixture, children=children)
            self.assertTrue(any("cached_fresh_node_ids mismatch" in e for e in errors), errors)
            self.assertTrue(any("reused nonce-controlled" in e for e in errors), errors)

            children = json.loads(json.dumps(fixture[3]))
            children[0]["execution_cache_control"]["cached_node_ids"] = ["1"]
            errors = self._cache_errors(root, fixture, children=children)
            self.assertTrue(any("recomputed warm cache hit" in e for e in errors), errors)

            children = json.loads(json.dumps(fixture[3]))
            control = children[0]["execution_cache_control"]
            control["cache_event_found"] = False
            control["fresh_execution_proved"] = True
            errors = self._cache_errors(root, fixture, children=children)
            self.assertTrue(any("execution_cached event" in e for e in errors), errors)
            self.assertTrue(any("did not prove fresh execution" in e for e in errors), errors)

            children = json.loads(json.dumps(fixture[3]))
            children[0]["execution_cache_control"]["cached_node_ids"] = ["1", "1"]
            errors = self._cache_errors(root, fixture, children=children)
            self.assertTrue(any("not canonical" in e for e in errors), errors)

    def test_cache_verifier_binds_queue_final_and_current_runtime_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._cache_fixture(root)
            for field in (
                "suite_cache_runtime_sha256s",
                "final_suite_cache_runtime_sha256s",
            ):
                with self.subTest(field=field):
                    children = json.loads(json.dumps(fixture[3]))
                    children[0][field]["execution.py"] = "0" * 64
                    errors = self._cache_errors(root, fixture, children=children)
                    self.assertTrue(
                        any("disagree with suite/current pins" in e for e in errors),
                        errors,
                    )

            current_hashes = dict(fixture[4])
            current_hashes["execution.py"] = "0" * 64
            errors = self._cache_errors(
                root, fixture, current_runtime_hashes=current_hashes
            )
            self.assertTrue(any("do not match current source" in e for e in errors), errors)

    def test_runner_shared_cache_verifier_fails_closed(self):
        import run_h3_suite

        runtime_hashes = dict(run_recipe.SUITE_CACHE_RUNTIME_SOURCES)
        with (
            mock.patch.object(
                run_h3_suite.run_recipe,
                "suite_cache_runtime_sha256s",
                return_value=runtime_hashes,
            ),
            mock.patch.object(
                suite_integrity,
                "suite_cache_evidence_errors",
                return_value=["forged cache evidence"],
            ) as verifier,
        ):
            with self.assertRaisesRegex(
                run_h3_suite.SuiteFailure, "forged cache evidence"
            ):
                run_h3_suite.require_suite_cache_evidence(
                    "run-id",
                    [{"label": "S0", "recipe": "sample", "role": "sentinel_reference"}],
                    {"sample": "a" * 64},
                    [{"label": "S0", "recipe": "sample", "role": "sentinel_reference"}],
                    runtime_hashes,
                )
        verifier.assert_called_once()

    def test_accepts_current_pinned_recipe_and_nonempty_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, pins, children = self._fixture(root)

            self.assertEqual(
                suite_integrity.suite_storage_errors(
                    root, pins, children, expected_recipes=["sample"]
                ),
                [],
            )

    def test_rejects_recipe_mutation_and_pin_omission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe, _, pins, children = self._fixture(root)
            recipe.write_bytes(b'{"name":"mutated"}\n')

            errors = suite_integrity.suite_storage_errors(
                root, pins, children, expected_recipes=["sample"]
            )
            self.assertTrue(any("recipe SHA-256 mismatch" in item for item in errors))

            errors = suite_integrity.suite_storage_errors(
                root, {}, children, expected_recipes=["sample"]
            )
            self.assertTrue(any("pin set" in item for item in errors))

    def test_rejects_artifact_mutation_deletion_and_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, artifact, pins, children = self._fixture(root)

            artifact.write_bytes(b"changed")
            errors = suite_integrity.suite_storage_errors(
                root, pins, children, expected_recipes=["sample"]
            )
            self.assertTrue(any("artifact SHA-256 mismatch" in item for item in errors))

            artifact.unlink()
            errors = suite_integrity.suite_storage_errors(
                root, pins, children, expected_recipes=["sample"]
            )
            self.assertTrue(any("artifact is missing" in item for item in errors))

            artifact.write_bytes(b"")
            errors = suite_integrity.suite_storage_errors(
                root, pins, children, expected_recipes=["sample"]
            )
            self.assertTrue(any("artifact is empty" in item for item in errors))

    def test_rejects_relative_and_absolute_output_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, outside, pins, children = self._fixture(root)
            outside = root / "outside.mp4"
            outside.write_bytes(b"outside")
            escaped = {
                **children[0],
                "output_path": "../outside.mp4",
                "artifact_sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
            }

            errors = suite_integrity.suite_storage_errors(
                root, pins, [escaped], expected_recipes=["sample"]
            )
            self.assertTrue(any("escapes" in item for item in errors))

            escaped["output_path"] = "../missing-outside.mp4"
            errors = suite_integrity.suite_storage_errors(
                root, pins, [escaped], expected_recipes=["sample"]
            )
            self.assertTrue(any("escapes" in item for item in errors))

            escaped["output_path"] = str(outside.resolve())
            errors = suite_integrity.suite_storage_errors(
                root, pins, [escaped], expected_recipes=["sample"]
            )
            self.assertTrue(any("escapes" in item for item in errors))

    def test_machine_pass_validator_rechecks_current_recipe_and_artifact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe, artifact, pins, children = self._fixture(root)
            suites = root / "suites"
            results = root / "results"
            suites.mkdir()
            results.mkdir(exist_ok=True)
            manifest = {
                "schema_version": 1,
                "creep_tolerance_gib": 0.25,
                "sequence": [
                    {"label": "S1", "recipe": "sample", "role": "candidate"}
                ],
            }
            manifest_path = suites / "sample_suite.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            helper_path = root / "suite_integrity.py"
            helper_path.write_bytes(b"helper-v1")
            receipt_file = results / "sample_suite.json"
            suite = {
                "suite_schema_version": 1,
                "suite_run_id": "run-id",
                "suite": "sample_suite",
                "status": "MACHINE SUITE PASS (human video/audio pending)",
                "machine_pass": True,
                "manifest": "suites/sample_suite.json",
                "manifest_sha256": run_recipe.sha256_file(manifest_path),
                "runner_sha256": "a" * 64,
                "lab_locks_sha256": "b" * 64,
                "suite_runner_sha256": "c" * 64,
                "suite_integrity_sha256": run_recipe.sha256_file(helper_path),
                "recipe_sha256s": pins,
                "boot_lane": "lab-8199, sage-free",
                "creep_tolerance_gib": 0.25,
                "vram_creep": False,
                "children": children,
                "failures": [],
                "cleanup": {"success": True},
                "lease_release": {"success": True},
                "finished_at": "2026-08-08T00:00:00Z",
            }
            encoded = (json.dumps(suite, sort_keys=True) + "\n").encode("utf-8")
            receipt_file.write_bytes(encoded)
            (results / "sample_suite_run-id.json").write_bytes(encoded)

            def storage_errors():
                return [
                    error
                    for error in validate_recipes.suite_receipt_errors(
                        suite, receipt_file, root
                    )
                    if "storage verification failed" in error
                ]

            self.assertEqual(storage_errors(), [])

            with mock.patch.object(
                suite_integrity,
                "suite_cache_evidence_errors",
                return_value=["forced shared cache-verifier failure"],
            ) as verifier:
                errors = validate_recipes.suite_receipt_errors(
                    suite, receipt_file, root
                )
            self.assertTrue(
                any("forced shared cache-verifier failure" in error for error in errors),
                errors,
            )
            verifier.assert_called_once()

            recipe.write_bytes(b'{"name":"mutated"}\n')
            self.assertTrue(any("recipe SHA-256 mismatch" in e for e in storage_errors()))
            recipe.write_bytes(b'{"name":"sample"}\n')

            artifact.unlink()
            self.assertTrue(any("artifact is missing" in e for e in storage_errors()))
            artifact.write_bytes(b"video-bytes")

            outside = root / "outside.mp4"
            outside.write_bytes(b"video-bytes")
            children[0]["output_path"] = "../outside.mp4"
            self.assertTrue(any("escapes" in e for e in storage_errors()))

            helper_path.write_bytes(b"helper-v2")
            errors = validate_recipes.suite_receipt_errors(suite, receipt_file, root)
            self.assertTrue(
                any("suite_integrity.py SHA-256 mismatch" in error for error in errors),
                errors,
            )

    def test_runner_rejects_mid_suite_integrity_helper_mutation(self):
        import run_h3_suite

        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "suite_integrity.py"
            helper.write_bytes(b"helper-v1")
            expected = run_recipe.sha256_file(helper)
            with mock.patch.object(
                run_h3_suite, "SUITE_INTEGRITY_SOURCE_PATH", helper
            ):
                run_h3_suite.require_suite_integrity_source(expected)
                helper.write_bytes(b"helper-v2")
                with self.assertRaisesRegex(
                    run_h3_suite.SuiteFailure, "changed during suite"
                ):
                    run_h3_suite.require_suite_integrity_source(expected)

    def test_final_boundary_reopens_all_archives_and_only_latest_recipe_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, pins, children = self._fixture(root)
            results = root / "results"
            archive1 = results / "sample_run1.json"
            raw1 = archive1.read_bytes()
            receipt2 = json.loads(raw1.decode("utf-8"))
            receipt2.update(
                {
                    "run_number": 2,
                    "config_run_count": 2,
                    "status": "PASS",
                    "warm_pass": True,
                }
            )
            raw2 = (json.dumps(receipt2, sort_keys=True) + "\n").encode("utf-8")
            (results / "sample_run2.json").write_bytes(raw2)
            (results / "sample.json").write_bytes(raw2)
            child2 = {
                **children[0],
                "label": "S2",
                "run_number": 2,
                "config_run_count": 2,
                "status": "PASS",
                "warm_pass": True,
                "receipt": "results/sample_run2.json",
                "receipt_sha256": hashlib.sha256(raw2).hexdigest(),
            }
            both = [children[0], child2]

            self.assertEqual(
                suite_integrity.suite_storage_errors(
                    root, pins, both, expected_recipes=["sample"]
                ),
                [],
            )

            archive1.write_bytes(raw1.replace(b"PASS (cold)", b"FAIL       "))
            errors = suite_integrity.suite_storage_errors(
                root, pins, both, expected_recipes=["sample"]
            )
            self.assertTrue(any("receipt SHA-256 mismatch" in e for e in errors), errors)
            archive1.write_bytes(raw1)

            (results / "sample.json").write_bytes(b"mutated latest alias")
            errors = suite_integrity.suite_storage_errors(
                root, pins, both, expected_recipes=["sample"]
            )
            self.assertTrue(any("latest current alias bytes" in e for e in errors), errors)

    def test_rejects_linked_repository_recipe_output_and_nested_roots(self):
        with self.subTest(root="repository"):
            with tempfile.TemporaryDirectory() as tmp:
                parent = Path(tmp)
                actual = parent / "actual"
                actual.mkdir()
                _, _, pins, children = self._fixture(actual)
                linked = parent / "linked"
                try:
                    linked.symlink_to(actual, target_is_directory=True)
                except OSError as exc:
                    self.skipTest(f"directory symlinks are unavailable: {exc}")
                errors = suite_integrity.suite_storage_errors(
                    linked, pins, children, expected_recipes=["sample"]
                )
                self.assertTrue(any("repository root" in e and "symlink" in e for e in errors))

        for root_name in ("recipes", "outputs"):
            with self.subTest(root=root_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _, _, pins, children = self._fixture(root)
                lexical = root / root_name
                actual = root / f"actual-{root_name}"
                lexical.rename(actual)
                lexical.symlink_to(actual, target_is_directory=True)
                errors = suite_integrity.suite_storage_errors(
                    root, pins, children, expected_recipes=["sample"]
                )
                self.assertTrue(
                    any(root_name in e and "symlink" in e for e in errors), errors
                )

        with self.subTest(root="nested output component"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _, _, pins, children = self._fixture(root)
                actual = root / "actual-nested"
                actual.mkdir()
                (actual / "sample.mp4").write_bytes(b"video-bytes")
                linked = root / "outputs" / "linked"
                linked.symlink_to(actual, target_is_directory=True)
                children[0]["output_path"] = "linked/sample.mp4"
                errors = suite_integrity.suite_storage_errors(
                    root, pins, children, expected_recipes=["sample"]
                )
                self.assertTrue(any("output artifact contains" in e for e in errors), errors)

    def test_malformed_child_recipe_label_and_mapping_values_never_raise(self):
        malformed_values = ([], {}, None, True)
        for field in ("recipe", "label"):
            for value in malformed_values:
                with self.subTest(field=field, value=repr(value)):
                    with tempfile.TemporaryDirectory() as tmp:
                        root = Path(tmp)
                        _, _, pins, children = self._fixture(root)
                        children[0][field] = value
                        errors = suite_integrity.suite_storage_errors(
                            root, pins, children, expected_recipes=["sample"]
                        )
                        self.assertTrue(errors)
                        self.assertTrue(any(field in error for error in errors), errors)

        for child in ([], None, True, {}):
            with self.subTest(child=repr(child)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _, _, pins, _ = self._fixture(root)
                errors = suite_integrity.suite_storage_errors(
                    root, pins, [child], expected_recipes=["sample"]
                )
                self.assertTrue(errors)

    def test_suite_validator_rejects_unhashable_labels_without_crashing(self):
        for value in ([], {}, None, True):
            with self.subTest(label=repr(value)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _, _, _, children = self._fixture(root)
                suites = root / "suites"
                suites.mkdir()
                manifest = suites / "sample.json"
                manifest.write_text(
                    json.dumps({"schema_version": 1, "creep_tolerance_gib": 0.25}),
                    encoding="utf-8",
                )
                children[0]["label"] = value
                suite = {
                    "suite_schema_version": 1,
                    "suite_run_id": "id",
                    "suite": "sample_suite",
                    "status": "RUNNING",
                    "machine_pass": False,
                    "manifest": "suites/sample.json",
                    "manifest_sha256": run_recipe.sha256_file(manifest),
                    "runner_sha256": "a" * 64,
                    "lab_locks_sha256": "b" * 64,
                    "suite_runner_sha256": "c" * 64,
                    "suite_integrity_sha256": "d" * 64,
                    "recipe_sha256s": {},
                    "boot_lane": "lab-8199, sage-free",
                    "creep_tolerance_gib": 0.25,
                    "vram_creep": False,
                    "children": children,
                    "failures": [],
                    "cleanup": {"success": False},
                }
                errors = validate_recipes.suite_receipt_errors(
                    suite, root / "results" / "sample_suite_id.json", root
                )
                self.assertTrue(any("labels are" in error for error in errors), errors)

    def test_child_receipt_path_accepts_only_regular_derived_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            archive = results / "sample_run1.json"
            archive.write_bytes(b"archive")

            self.assertEqual(
                validate_recipes.immutable_child_receipt_path(
                    root, "sample", 1, "results/sample_run1.json"
                ),
                archive,
            )
            for declared in (
                "results/sample.json",
                "results/../sample_run1.json",
                "results\\sample_run1.json",
                str(archive.resolve()),
            ):
                with self.subTest(declared=declared):
                    with self.assertRaisesRegex(ValueError, "exact immutable archive"):
                        validate_recipes.immutable_child_receipt_path(
                            root, "sample", 1, declared
                        )

    def test_child_receipt_path_rejects_symlink_to_mutable_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            alias = results / "sample.json"
            alias.write_bytes(b"mutable alias")
            archive = results / "sample_run1.json"
            try:
                archive.symlink_to(alias.name)
            except OSError as exc:
                self.skipTest(f"symlinks are unavailable: {exc}")

            with self.assertRaisesRegex(ValueError, "symlink.*reparse point"):
                validate_recipes.immutable_child_receipt_path(
                    root, "sample", 1, "results/sample_run1.json"
                )

    def test_child_receipt_path_rejects_reparse_results_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual_results = root / "actual-results"
            actual_results.mkdir()
            (actual_results / "sample_run1.json").write_bytes(b"archive")
            results = root / "results"
            try:
                results.symlink_to(actual_results, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")

            with self.assertRaisesRegex(ValueError, "symlink.*reparse point"):
                validate_recipes.immutable_child_receipt_path(
                    root, "sample", 1, "results/sample_run1.json"
                )

    def test_child_receipt_path_rejects_hardlink_to_mutable_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            results.mkdir()
            alias = results / "sample.json"
            alias.write_bytes(b"mutable alias")
            archive = results / "sample_run1.json"
            try:
                os.link(alias, archive)
            except OSError as exc:
                self.skipTest(f"hardlinks are unavailable: {exc}")

            self.assertTrue(os.path.samefile(alias, archive))
            with self.assertRaisesRegex(ValueError, "same file as the mutable current alias"):
                validate_recipes.immutable_child_receipt_path(
                    root, "sample", 1, "results/sample_run1.json"
                )


if __name__ == "__main__":
    unittest.main()
