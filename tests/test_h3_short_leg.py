import importlib.util
import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scratch" / "run_h3_short_leg.py"
spec = importlib.util.spec_from_file_location("h3_short_leg_tested", SOURCE)
assert spec is not None and spec.loader is not None
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import run_recipe  # noqa: E402


class H3ShortLegTests(unittest.TestCase):
    def test_exact_jobd_plan_is_one_cold_shutdown_child(self) -> None:
        value = launcher.plan(launcher.JOBS["jobd"], "h3short-test-jobd-001")
        command = value["command"]
        self.assertEqual(command.count("--manager-offline-test"), 1)
        self.assertEqual(command[command.index("--manager-probe-phase") + 1], "cold")
        self.assertIn("--disable-pinned-memory", command)
        self.assertIn("--shutdown", command)
        self.assertNotIn("--suite", command)
        self.assertNotIn("--force", command)
        self.assertEqual(command[command.index("--completion-timeout-s") + 1], "3600")
        self.assertEqual(
            value["recipe_name"], "h3_jobd_lipsync_refaudio_seed43_f192"
        )

    def test_origin_primary_and_fallback_are_distinct(self) -> None:
        primary = launcher.plan(
            launcher.JOBS["origin-primary"], "h3short-test-origin-001"
        )
        fallback = launcher.plan(
            launcher.JOBS["origin-fallback"], "h3short-test-origin-fallback-001"
        )
        self.assertNotEqual(primary["recipe_name"], fallback["recipe_name"])
        self.assertNotEqual(primary["expected_artifact"], fallback["expected_artifact"])
        self.assertEqual(
            primary["command"][primary["command"].index("--completion-timeout-s") + 1],
            "2400",
        )

    def test_fallback_is_default_denied(self) -> None:
        with self.assertRaises(launcher.LaunchError):
            launcher.validate_fallback_evidence(None)

    def test_source_snapshots_match_frozen_jobd(self) -> None:
        snapshots = launcher.source_snapshots(launcher.JOBS["jobd"])
        self.assertEqual(snapshots["runner"]["sha256"], launcher.RUNNER_SHA256)
        self.assertEqual(
            snapshots["recipe"]["sha256"],
            launcher.JOBS["jobd"].recipe_sha256,
        )

    def test_offline_reserve_environment_is_exact(self) -> None:
        environment, evidence = launcher.child_environment(
            ROOT / "results" / "h3_short_jobs" / "server_logs" / "unit.log"
        )
        self.assertEqual(environment["LAB_RESERVE_VRAM_GB"], "12")
        self.assertEqual(environment["LAB_CACHE_CLASSIC"], "1")
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
        self.assertEqual(environment["TRANSFORMERS_OFFLINE"], "1")
        self.assertTrue(evidence["values_are_nonsecret"])
        self.assertEqual(evidence["set_nonsecret"]["HF_HUB_OFFLINE"], "1")

    def test_runner_scope_and_hard_idle_gate_are_bound(self) -> None:
        scope = run_recipe.manager_probe_recipe_scope(
            launcher.JOBS["jobd"].recipe_name
        )
        self.assertEqual(scope["scope"], "h3-short-jobs")
        origin_scope = run_recipe.manager_probe_recipe_scope(
            launcher.JOBS["origin-primary"].recipe_name
        )
        self.assertEqual(origin_scope["scope"], "h3-music-followup")
        idle = run_recipe.gpu_idle_gate_contract()["policy"]
        self.assertEqual(idle["maximum_vram_used_mib"], 3072.0)
        self.assertTrue(idle["vram_used_mib_threshold_gating"])
        self.assertTrue(
            run_recipe.operator_idle_policy_contract()[
                "preboot_baseline_threshold_gating"
            ]
        )

    def test_transport_has_no_forceful_process_surface(self) -> None:
        source = inspect.getsource(launcher).lower()
        for forbidden in (".terminate(", ".kill(", "taskkill", "--force"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("timeout=", source)


if __name__ == "__main__":
    unittest.main()
