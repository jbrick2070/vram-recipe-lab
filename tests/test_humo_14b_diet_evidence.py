from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scratch" / "build_humo_14b_diet_evidence.py"
SPEC = importlib.util.spec_from_file_location("build_humo_14b_diet_evidence", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def all_pair_receipts_exist() -> bool:
    return all(
        (ROOT / evidence.run_receipt_path(spec, run)).is_file()
        for spec in evidence.RUN_SPECS.values()
        for run in (1, 2)
    )


class HuMo14BDietEvidenceTests(unittest.TestCase):
    def test_builder_is_utf8_without_bom(self):
        raw = MODULE_PATH.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        raw.decode("utf-8")

    def test_recipe_and_comparator_pins_are_explicit(self):
        self.assertEqual(
            evidence.RUN_SPECS["portrait"]["recipe_sha256"],
            "ed4db54cb792733c87a09eeb75fb55d19364422305694bd19768e2a5c11a69c9",
        )
        self.assertEqual(
            evidence.RUN_SPECS["landscape"]["recipe_sha256"],
            "af27ea377c55129ed2400ac63c1cfd6d92a0732e6226f53cb1858c3a8802d232",
        )
        self.assertEqual(evidence.EXPECTED_RESERVE_GIB, 2.921)
        self.assertEqual(evidence.GLOBAL_GATE_GIB, 14.5)
        self.assertRegex(evidence.PRODUCTION_RECEIPT_SHA256, r"^[0-9a-f]{64}$")
        self.assertRegex(evidence.PRODUCTION_ARTIFACT_SHA256, r"^[0-9a-f]{64}$")

    def test_ab_uses_one_shared_raw_tts_track_from_input_two(self):
        argv = evidence.ab_ffmpeg_argv(
            "humo_14b_diet_portrait_480x832_f97_out_00002_.mp4"
        )
        maps = [argv[index + 1] for index, token in enumerate(argv[:-1]) if token == "-map"]
        self.assertEqual(maps, ["[v]", "2:a:0"])
        self.assertNotIn("0:a:0", argv)
        self.assertNotIn("1:a:0", argv)
        self.assertEqual(argv[argv.index("-t") + 1], "3.88")
        self.assertEqual(argv[argv.index("-r") + 1], "25")
        self.assertEqual(argv[argv.index("-ac") + 1], "1")
        self.assertEqual(argv[argv.index("-ar") + 1], "44100")
        inputs = [argv[index + 1] for index, token in enumerate(argv[:-1]) if token == "-i"]
        self.assertEqual(inputs[2], str(evidence.TTS_FIXTURE))

    def test_preflight_reports_only_actual_missing_paths(self):
        report = evidence.prerequisite_report(ROOT)
        for relative in report["missing"]:
            self.assertFalse((ROOT / relative).is_file())
        portrait = evidence.RUN_SPECS["portrait"]
        ab_required = [
            evidence.PRODUCTION_RECEIPT,
            evidence.PRODUCTION_ARTIFACT,
            evidence.PORTRAIT_FIXTURE,
            evidence.TTS_FIXTURE,
            evidence.PORTRAIT_RUN2_RECOVERY,
            portrait["recipe_path"],
            evidence.run_receipt_path(portrait, 1),
            evidence.run_receipt_path(portrait, 2),
        ]
        expected_ab_ready = all((ROOT / path).is_file() for path in ab_required)
        self.assertEqual(report["ready_for_ab"], expected_ab_ready)
        self.assertEqual(report["ab_exists"], (ROOT / evidence.AB_OUTPUT).is_file())

    @unittest.skipUnless(
        (ROOT / evidence.run_receipt_path(evidence.RUN_SPECS["portrait"], 1)).is_file(),
        "portrait cold receipt not rendered yet",
    )
    def test_portrait_cold_receipt_and_artifact_bind(self):
        row, receipt = evidence.validate_run(ROOT, "portrait", 1)
        self.assertEqual(row["role"], "cold")
        self.assertEqual(row["metrics"]["peak_vram_gib"], receipt["peak_vram_gb"])
        self.assertEqual(row["media_probe"]["frame_count"], 97)
        self.assertEqual((row["media_probe"]["width"], row["media_probe"]["height"]), (480, 832))
        self.assertEqual(set(receipt["execution_cache_control"]["fresh_node_ids"]), {"13", "14", "15", "16"})

    @unittest.skipUnless(
        all(
            (ROOT / evidence.run_receipt_path(evidence.RUN_SPECS["portrait"], run)).is_file()
            for run in (1, 2)
        ),
        "portrait cold/warm pair not complete yet",
    )
    def test_portrait_pair_proves_same_server_and_warm_cache(self):
        pair, warm_receipt = evidence.validate_pair(ROOT, "portrait")
        cold, warm = pair["runs"]
        self.assertEqual(cold["server_instance"], warm["server_instance"])
        self.assertEqual(cold["run_identity_sha256"], warm["run_identity_sha256"])
        self.assertEqual(warm["role"], "warm")
        recovery = evidence.validate_portrait_run2_recovery(ROOT, warm_receipt)
        self.assertEqual(recovery["status"], "RECOVERED_SUCCESSFULLY")
        self.assertFalse(recovery["normal_runner_shutdown_proved"])
        self.assertTrue(recovery["measurement_remains_valid"])

    @unittest.skipUnless(
        all_pair_receipts_exist() and (ROOT / evidence.AB_OUTPUT).is_file(),
        "full Job A receipt set and A/B are not complete yet",
    )
    def test_full_build_is_deterministic_and_landscape_answer_is_receipt_derived(self):
        first = evidence.build(ROOT)
        second = evidence.build(ROOT)
        self.assertEqual(
            evidence.canonical_json_bytes(first), evidence.canonical_json_bytes(second)
        )
        verdict = first["diet_pairs"]["landscape"]["warm_vram_verdict"]
        peak = first["diet_pairs"]["landscape"]["runs"][1]["metrics"]["peak_vram_gib"]
        self.assertEqual(verdict["peak_vram_gib"], peak)
        self.assertEqual(verdict["fits_under_14p5"], peak <= 14.5)
        self.assertEqual(verdict["headroom_gib"], round(14.5 - peak, 6))
        self.assertEqual(
            first["portrait_production_vs_diet_ab"]["human_review"]["status"],
            "PENDING_HUMAN",
        )


if __name__ == "__main__":
    unittest.main()
