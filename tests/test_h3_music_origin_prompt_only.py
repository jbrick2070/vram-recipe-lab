from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))

import build_h3_music_origin_prompt_only as builder
import run_recipe


class H3MusicOriginPromptOnlyTests(unittest.TestCase):
    def test_source_pin_and_prompts_are_exact(self) -> None:
        source = builder.load_source()
        source_prompt = source["prompt"]["7"]["inputs"]["prompt"]
        self.assertEqual(source_prompt, builder.ORIGIN_PROMPT)
        self.assertEqual(
            builder.FALLBACK_PROMPT,
            builder.ORIGIN_PROMPT[len(builder.PICTURE_SENTENCE) :],
        )
        self.assertEqual(
            hashlib.sha256(builder.SOURCE.read_bytes()).hexdigest(),
            builder.SOURCE_SHA256,
        )

    def test_both_recipes_are_prompt_only_ref2va_with_native_audio(self) -> None:
        generated = builder.build_all()
        for variant in builder.variants():
            recipe = generated[variant.name]
            graph = recipe["prompt"]
            inputs = graph["7"]["inputs"]
            self.assertNotIn("11", graph)
            self.assertNotIn("LoadImage", [row["class_type"] for row in graph.values()])
            self.assertEqual(
                graph["7"]["class_type"], "MiniMaxH3ReferenceToVideo"
            )
            self.assertFalse(
                any(
                    key == "ref_images" or key.startswith("ref_images.")
                    for key in inputs
                )
            )
            self.assertFalse(
                any(
                    key.startswith("ref_audios")
                    or key.startswith("ref_videos")
                    or key.startswith("ref_video_audios")
                    for key in inputs
                )
            )
            self.assertEqual(
                (inputs["width"], inputs["height"], inputs["length"]),
                (832, 480, 124),
            )
            self.assertEqual(graph["5"]["inputs"]["noise_seed"], 42)
            self.assertEqual(
                graph["15"]["inputs"], {"samples": ["8", 0], "vae": ["4", 0]}
            )
            self.assertEqual(graph["10"]["inputs"]["audio"], ["15", 0])
            self.assertFalse(recipe["origin_test"]["external_mux"])
            self.assertEqual(
                recipe["origin_test"]["quality_judgment"], "PENDING_HUMAN"
            )
            self.assertEqual(
                run_recipe.minimax_h3_autogrow_input_errors(graph), []
            )
            self.assertEqual(builder._local_topology_errors(recipe), [])

    def test_variants_differ_only_in_prompt_and_output_prefix(self) -> None:
        generated = builder.build_all()
        primary = generated[builder.PRIMARY_NAME]
        fallback = generated[builder.FALLBACK_NAME]
        self.assertEqual(
            primary["prompt"]["7"]["inputs"]["prompt"], builder.ORIGIN_PROMPT
        )
        self.assertEqual(
            fallback["prompt"]["7"]["inputs"]["prompt"], builder.FALLBACK_PROMPT
        )
        left = copy.deepcopy(primary["prompt"])
        right = copy.deepcopy(fallback["prompt"])
        for graph in (left, right):
            graph["7"]["inputs"]["prompt"] = "<variant-prompt>"
            graph["12"]["inputs"]["filename_prefix"] = "<evidence-prefix>"
        self.assertEqual(left, right)

    def test_current_runner_hard_idle_and_manager_contracts_are_bound(self) -> None:
        contracts = builder.current_runner_contracts()
        self.assertEqual(
            contracts["runner"]["sha256"], builder.sha256_file(builder.RUNNER)
        )
        preboot = contracts["preboot_gpu_idle_gate_contract"]
        policy = preboot["policy"]
        self.assertEqual(policy["maximum_vram_used_mib"], 3072.0)
        self.assertTrue(policy["vram_used_mib_threshold_gating"])
        operator = contracts["operator_idle_policy"]
        self.assertEqual(operator["preboot_baseline_maximum_mib"], 3072.0)
        self.assertTrue(operator["preboot_baseline_threshold_gating"])
        self.assertEqual(operator["elevated_baseline_threshold_mib"], 2048.0)
        self.assertEqual(
            operator["elevated_baseline_stamp"], builder.ELEVATED_BASELINE_STAMP
        )
        self.assertTrue(operator["known_render_compute_processes_block"])
        self.assertEqual(
            operator["net_peak_formula"], "peak_vram_gb - baseline_vram_gb"
        )
        self.assertEqual(
            preboot["collector"]["sha256"], contracts["runner"]["sha256"]
        )
        for recipe in builder.build_all().values():
            origin = recipe["origin_test"]
            self.assertEqual(origin["runner_contracts"], contracts)
            manager = origin["manager_offline_gate"]
            self.assertTrue(manager["required"])
            self.assertEqual(
                manager["required_server_log_substring"], "network_mode: offline"
            )
            self.assertTrue(manager["must_be_observed_before_prompt_post"])
            boot = origin["boot_requirements"]
            self.assertFalse(boot["sage_attention_allowed"])
            self.assertTrue(boot["disable_pinned_memory_required"])
            self.assertEqual(boot["cache_mode"], "classic")
            self.assertEqual(boot["reserve_vram_gib"], 12)
            scope = run_recipe.manager_probe_recipe_scope(recipe["name"])
            self.assertEqual(scope["scope"], "h3-music-followup")
            self.assertEqual(scope["match_type"], "prefix")

    def test_fallback_is_fail_closed_and_specific(self) -> None:
        valid = {
            "primary_recipe": builder.PRIMARY_NAME,
            "primary_prompt_submission_attempted": True,
            "primary_artifact_absent": True,
            "error_stage": "prompt_validation",
            "error_node_id": "7",
            "error_class_type": "MiniMaxH3ReferenceToVideo",
            "error_text": "Node 7 rejected <Picture 1> because no reference image was supplied",
        }
        self.assertTrue(builder.fallback_is_authorized(valid))
        for field, value in (
            ("primary_recipe", "different"),
            ("primary_prompt_submission_attempted", False),
            ("primary_artifact_absent", False),
            ("error_stage", "preboot"),
            ("error_node_id", "8"),
            ("error_class_type", "SamplerCustomAdvanced"),
            ("error_text", "generic runtime error"),
        ):
            with self.subTest(field=field):
                tampered = dict(valid)
                tampered[field] = value
                self.assertFalse(builder.fallback_is_authorized(tampered))
        fallback = builder.build_all()[builder.FALLBACK_NAME]["origin_test"]
        self.assertFalse(fallback["authorization"]["default_authorized"])
        self.assertTrue(fallback["authorization"]["conditional_only"])
        self.assertIn("OOM or VRAM ceiling failure", fallback["authorization"]["does_not_authorize"])

    def test_materialized_json_is_canonical_utf8_and_matches_builder(self) -> None:
        generated = builder.build_all()
        for variant in builder.variants():
            self.assertTrue(variant.path.is_file())
            raw = variant.path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(raw, builder.canonical_json(generated[variant.name]))
            self.assertEqual(json.loads(raw.decode("utf-8")), generated[variant.name])

    def test_builder_has_no_render_or_live_query_surface(self) -> None:
        source = Path(builder.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "subprocess.",
            "urlopen(",
            "requests.",
            "127.0.0.1:8199/",
            "nvidia-smi",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
