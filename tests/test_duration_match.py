import json
import math
import unittest
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from duration_match import (
    DurationMatchError,
    InvalidDurationError,
    UnrepresentableDurationError,
    duration_match,
)
from scratch.build_clean_h3_recipes import MIME_PROMPT, make_h3_mime_i2v_recipe
from validate_recipes import iter_prompt_links, topology_contract_errors, validate_recipe_file


REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "fixtures" / "ledger.json"


def timed_ledger_slots() -> list[tuple[str, Decimal]]:
    """Return every concrete beat/line clock slot plus scheduled music slots."""
    with LEDGER_PATH.open("r", encoding="utf-8") as handle:
        ledger = json.load(handle, parse_float=Decimal, parse_int=Decimal)

    slots: list[tuple[str, Decimal]] = []
    for collection in ("beats", "lines"):
        for entry in ledger.get(collection, []):
            duration = entry.get("dur_s")
            if duration is not None:
                identifier = entry.get("beat_id") or entry.get("line_id") or "unknown"
                slots.append((f"{collection}:{identifier}", duration))
    for entry in ledger.get("music", []):
        duration = entry.get("dur_s")
        if duration is not None:
            slots.append((f"music:{entry.get('cue_id', 'unknown')}", duration))
    return slots


class DurationMatchTests(unittest.TestCase):
    def assert_exact_plan(self, target: Decimal, mode: str) -> None:
        fps, step, offset = {
            "h3": (24, 17, 5),
            "ltx": (25, 8, 1),
        }[mode]
        plan = duration_match(target, mode)

        self.assertEqual(plan["target_seconds"], target)
        self.assertEqual(plan["delivered_s"], target)
        self.assertEqual(plan["delivery_quantization_error_s"], Decimal("0"))
        self.assertEqual((plan["frame_count"] - offset) % step, 0)
        self.assertGreaterEqual(plan["trim_frames"], 0)
        self.assertEqual(plan["rendered_s"], Fraction(plan["frame_count"], fps))

        kept_frames = plan["frame_count"] - plan["trim_frames"]
        kept_endpoint = Fraction(kept_frames, fps)
        target_fraction = Fraction(target)
        self.assertGreaterEqual(kept_endpoint, target_fraction)
        self.assertEqual(plan["tail_trim_s"], kept_endpoint - target_fraction)
        self.assertGreaterEqual(plan["tail_trim_s"], 0)
        self.assertLess(plan["tail_trim_s"], Fraction(1, fps))
        if kept_frames > 0:
            self.assertLess(Fraction(kept_frames - 1, fps), target_fraction)

    def test_h3_default_beat_is_exact_90_frame_grid_point(self):
        plan = duration_match(Decimal("3.750"), "h3")
        self.assertEqual(plan["frame_count"], 90)
        self.assertEqual(plan["trim_frames"], 0)
        self.assertEqual(plan["rendered_s"], Fraction(15, 4))
        self.assertEqual(plan["delivered_s"], Decimal("3.750"))
        self.assertEqual(plan["tail_trim_s"], 0)

    def test_h3_eight_seconds_is_exact_192_frame_grid_point(self):
        plan = duration_match(Decimal("8.000"), "h3")
        self.assertEqual(plan["frame_count"], 192)
        self.assertEqual(plan["delivered_frame_count"], 192)
        self.assertEqual(plan["trim_frames"], 0)
        self.assertEqual(plan["rendered_s"], Fraction(8, 1))
        self.assertEqual(plan["whole_frame_delivery_s"], Fraction(8, 1))
        self.assertEqual(plan["delivered_s"], Decimal("8.000"))
        self.assertEqual(plan["tail_trim_s"], 0)

    def test_ltx_default_beat_renders_97_then_uses_exact_endpoint(self):
        plan = duration_match(Decimal("3.750"), "ltx")
        self.assertEqual(plan["frame_count"], 97)
        self.assertEqual(plan["trim_frames"], 3)
        self.assertEqual(plan["rendered_s"], Fraction(97, 25))
        self.assertEqual(plan["tail_trim_s"], Fraction(1, 100))
        self.assertEqual(plan["delivered_s"], Decimal("3.750"))

    def test_every_real_ledger_slot_has_exact_h3_and_ltx_delivery_plan(self):
        slots = timed_ledger_slots()
        # Current fixture truth: three timed dialogue lines and three music cues.
        self.assertEqual(
            {name for name, _ in slots},
            {
                "lines:b002",
                "lines:b003",
                "lines:b004",
                "music:opening",
                "music:closing",
                "music:interstitial",
            },
        )
        for name, target in slots:
            for mode in ("h3", "ltx"):
                with self.subTest(slot=name, target=target, mode=mode):
                    self.assert_exact_plan(target, mode)

    def test_non_frame_aligned_ledger_value_exposes_subframe_tail(self):
        plan = duration_match(Decimal("12.72"), "h3")
        self.assertEqual(plan["frame_count"], 311)
        self.assertEqual(plan["trim_frames"], 5)
        self.assertEqual(plan["tail_trim_s"], Fraction(3, 100))
        self.assertEqual(plan["delivered_s"], Decimal("12.72"))

    def test_strict_whole_frame_mode_rejects_unrepresentable_target(self):
        with self.assertRaises(UnrepresentableDurationError):
            duration_match(Decimal("12.72"), "h3", strict_frame_aligned=True)
        aligned = duration_match(Decimal("3.75"), "h3", strict_frame_aligned=True)
        self.assertEqual(aligned["frame_count"], 90)

    def test_invalid_targets_and_modes_fail_explicitly(self):
        for invalid in (0, -1, "", "NaN", "Infinity", float("nan"), True, object()):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(InvalidDurationError):
                    duration_match(invalid)
        with self.assertRaises(DurationMatchError):
            duration_match(1, "unknown")

    def test_float_input_uses_human_decimal_spelling_not_binary_payload(self):
        plan = duration_match(12.72, "h3")
        self.assertEqual(plan["target_seconds"], Decimal("12.72"))
        self.assertTrue(math.isclose(float(plan["delivered_s"]), 12.72))


class MiniMimeRecipeTests(unittest.TestCase):
    def setUp(self):
        self.recipe_path = REPO_ROOT / "recipes" / "h3_mime_i2v.json"
        self.raw = self.recipe_path.read_bytes()
        self.recipe = json.loads(self.raw.decode("utf-8"))
        self.prompt = self.recipe["prompt"]

    def test_generator_is_byte_semantically_identical_to_recipe(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.raw.endswith(b"\n"))
        self.assertEqual(self.recipe, make_h3_mime_i2v_recipe())

    def test_recipe_uses_exact_default_plan_and_scene_still(self):
        self.assertEqual(self.recipe["contract"]["frames"], 90)
        self.assertEqual(self.recipe["contract"]["target_s"], 3.75)
        self.assertEqual(self.recipe["contract"]["trim_frames"], 0)
        self.assertEqual(self.recipe["contract"]["delivered_s"], 3.75)
        self.assertEqual(self.prompt["7"]["inputs"]["length"], 90)
        self.assertEqual(self.prompt["11"]["inputs"]["image"], "scene_still.png")
        self.assertEqual(self.prompt["2"]["inputs"]["device"], "default")

    def test_native_audio_is_the_only_delivered_soundtrack(self):
        self.assertEqual(self.prompt["15"]["class_type"], "VAEDecodeAudio")
        self.assertEqual(self.prompt["15"]["inputs"]["samples"], ["8", 0])
        self.assertEqual(self.prompt["10"]["inputs"]["audio"], ["15", 0])
        self.assertNotIn(
            "LoadAudio", {node["class_type"] for node in self.prompt.values()}
        )
        lowered = MIME_PROMPT.lower()
        for prohibition in ("no dialogue", "no voices", "no vocals", "no music"):
            self.assertIn(prohibition, lowered)

    def test_graph_is_certified_low_i2v_plus_only_mime_payload_changes(self):
        low = json.loads(
            (REPO_ROOT / "recipes" / "h3_i2v_low.json").read_text(encoding="utf-8")
        )["prompt"]
        expected = deepcopy(low)
        expected["2"]["inputs"]["device"] = "default"
        expected["7"]["inputs"]["prompt"] = MIME_PROMPT
        expected["7"]["inputs"]["length"] = 90
        expected["15"] = {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["8", 0], "vae": ["4", 0]},
        }
        expected["10"]["inputs"]["audio"] = ["15", 0]
        expected["12"]["inputs"]["filename_prefix"] = "h3_mime_i2v_out"
        self.assertEqual(self.prompt, expected)

    def test_topology_contract_and_dag_are_valid(self):
        self.assertEqual(topology_contract_errors(self.recipe, self.prompt), [])
        self.assertTrue(validate_recipe_file(self.recipe_path)["valid"])

        dependencies: dict[str, set[str]] = {node_id: set() for node_id in self.prompt}
        for node_id, node in self.prompt.items():
            for value in node.get("inputs", {}).values():
                for _, source_id, _ in iter_prompt_links(value):
                    self.assertIn(source_id, self.prompt)
                    dependencies[node_id].add(source_id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                self.fail(f"cycle found at node {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for source_id in dependencies[node_id]:
                visit(source_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in self.prompt:
            visit(node_id)
        self.assertEqual(visited, set(self.prompt))

    def test_receipt_contract_requires_duration_and_human_inverted_ear_gate(self):
        requirements = self.recipe["receipt_requirements"]
        timing_fields = set(requirements["timing"]["required_fields"])
        self.assertTrue({"target_s", "delivered_s", "duration_error_s"} <= timing_fields)
        self.assertTrue(requirements["timing"]["ffprobe_required"])
        self.assertEqual(
            requirements["timing"]["absolute_duration_error_lte_s"], 1 / 24
        )
        ear = requirements["inverted_ear_gate"]
        self.assertEqual(ear["status"], "pending_human")
        self.assertIn("soundscape_description", ear["required_fields"])


if __name__ == "__main__":
    unittest.main()
