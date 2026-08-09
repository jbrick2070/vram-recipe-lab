import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from duration_match import duration_match
from scratch import build_clean_h3_recipes as builder
from validate_recipes import topology_contract_errors, validate_recipe_file


ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = ROOT / "recipes" / "h3_mime_i2v_ledger_music_closing_8s.json"
BASE_RECIPE_PATH = ROOT / "recipes" / "h3_mime_i2v.json"
COMFY_ROOT = Path.home() / "ComfyUI-Installs" / "ComfyUI" / "ComfyUI"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class H3MimeI2VLedgerMusicClosing8sTests(unittest.TestCase):
    def setUp(self):
        self.raw = RECIPE_PATH.read_bytes()
        self.recipe = json.loads(self.raw.decode("utf-8"))
        self.prompt = self.recipe["prompt"]

    def test_real_ledger_closing_binding_and_exact_grid_math(self):
        raw = builder.LEDGER_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), builder.LEDGER_SHA256)
        ledger = json.loads(raw.decode("utf-8"), parse_float=Decimal)
        row = ledger["music"][1]
        self.assertEqual(row["cue_id"], "closing")
        self.assertEqual(row["description"], "1940s old time radio closing sting")
        self.assertEqual(row["tts_engine"], "musicgen")
        self.assertEqual(row["dur_s"], Decimal("8.0"))
        self.assertEqual(row["generated_dur_s"], Decimal("8.1"))
        self.assertEqual(row["audio_sample_hash"], "ec1d7904")

        plan = duration_match(row["dur_s"], "h3")
        self.assertEqual(plan["frame_count"], 192)
        self.assertEqual(plan["frame_count"], 17 * 11 + 5)
        self.assertEqual(plan["delivered_frame_count"], 192)
        self.assertEqual(plan["trim_frames"], 0)
        self.assertEqual(plan["rendered_s"], Fraction(8, 1))
        self.assertEqual(plan["whole_frame_delivery_s"], Fraction(8, 1))
        self.assertEqual(plan["delivered_s"], Decimal("8.0"))
        self.assertEqual(plan["tail_trim_s"], 0)

    def test_closing_is_the_shortest_positive_exact_h3_grid_ledger_duration(self):
        ledger = json.loads(
            builder.LEDGER_PATH.read_text(encoding="utf-8"), parse_float=Decimal
        )
        timed_rows = [
            (collection, index, row)
            for collection in ("lines", "sfx", "music")
            for index, row in enumerate(ledger.get(collection, []))
            if isinstance(row.get("dur_s"), Decimal) and row["dur_s"] > 0
        ]
        exact_grid_rows = []
        for collection, index, row in timed_rows:
            plan = duration_match(row["dur_s"], "h3")
            if (
                plan["trim_frames"] == 0
                and plan["rendered_s"] == Fraction(row["dur_s"])
            ):
                exact_grid_rows.append((row["dur_s"], collection, index, row))
        self.assertTrue(exact_grid_rows)
        duration, collection, index, row = min(exact_grid_rows, key=lambda item: item[0])
        self.assertEqual((duration, collection, index, row["cue_id"]), (Decimal("8.0"), "music", 1, "closing"))

    def test_generator_matches_canonical_immutable_recipe(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(self.raw.endswith(b"\n"))
        self.assertNotIn(b"\r\n", self.raw)
        self.assertEqual(
            self.recipe, builder.make_h3_mime_i2v_ledger_closing_recipe()
        )

    def test_writer_is_idempotent_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertTrue(builder.write_h3_mime_i2v_ledger_closing(output))
            path = output / f"{builder.H3_MIME_I2V_LEDGER_CLOSING_NAME}.json"
            first = path.read_bytes()
            self.assertFalse(builder.write_h3_mime_i2v_ledger_closing(output))
            self.assertEqual(path.read_bytes(), first)
            path.write_bytes(b"{}\n")
            with self.assertRaisesRegex(RuntimeError, "Immutable generated recipe differs"):
                builder.write_h3_mime_i2v_ledger_closing(output)

    def test_graph_is_current_unconditioned_mime_i2v_at_192_frames(self):
        base = json.loads(BASE_RECIPE_PATH.read_text(encoding="utf-8"))["prompt"]
        expected = deepcopy(base)
        expected["7"]["inputs"]["length"] = 192
        expected["12"]["inputs"][
            "filename_prefix"
        ] = builder.H3_MIME_I2V_LEDGER_CLOSING_PREFIX
        expected = dict(sorted(expected.items(), key=lambda item: int(item[0])))
        self.assertEqual(self.prompt, expected)

    def test_native_audio_is_delivered_directly_without_trim_or_conditioning(self):
        classes = {node["class_type"] for node in self.prompt.values()}
        self.assertNotIn("Video Slice", classes)
        self.assertNotIn("LoadAudio", classes)
        self.assertEqual(self.prompt["11"]["inputs"]["image"], "scene_still.png")
        self.assertEqual(self.prompt["7"]["inputs"]["first_frame"], ["11", 0])
        self.assertNotIn("last_frame", self.prompt["7"]["inputs"])
        self.assertEqual(
            self.prompt["15"]["inputs"], {"samples": ["8", 0], "vae": ["4", 0]}
        )
        self.assertEqual(self.prompt["10"]["inputs"]["audio"], ["15", 0])
        self.assertEqual(self.prompt["12"]["inputs"]["video"], ["10", 0])

    def test_existing_runner_media_contract_is_satisfied_without_changes(self):
        self.assertFalse(self.recipe["blocked"])
        contract = self.recipe["contract"]
        self.assertEqual(contract["render_frames"], 192)
        self.assertEqual(contract["frames"], 192)
        self.assertEqual(contract["fps"], 24.0)
        self.assertEqual(contract["target_s"], 8.0)
        self.assertEqual(contract["duration_s"], 8.0)
        self.assertEqual(contract["delivered_s"], 8.0)
        self.assertEqual(contract["trim_frames"], 0)
        delivery = self.recipe["topology_contract"]["delivery_contract"]
        self.assertFalse(delivery["runner_changes_required"])
        self.assertFalse(delivery["video_slice_required"])
        self.assertTrue(delivery["native_audio_retained"])
        self.assertFalse(delivery["external_audio_mux"])
        self.assertEqual(
            self.recipe["experiment"]["runner_support"]["status"],
            "supported_by_existing_media_contract",
        )

    def test_topology_ledger_fixture_and_h3_source_hashes_are_pinned(self):
        topology = self.recipe["topology_contract"]
        self.assertEqual(
            topology, builder.make_mime_i2v_ledger_closing_topology_contract()
        )
        self.assertEqual(topology["ledger_contract"]["json_pointer"], "/music/1")
        self.assertEqual(
            topology["fixture_hashes"],
            {"scene_still.png": builder.SCENE_STILL_SHA256},
        )
        self.assertEqual(
            sha256(ROOT / "fixtures" / "scene_still.png"),
            builder.SCENE_STILL_SHA256,
        )
        h3_source = COMFY_ROOT / builder.H3_NODE_SOURCE
        self.assertEqual(sha256(h3_source), builder.H3_NODE_SOURCE_SHA256)
        self.assertEqual(topology_contract_errors(self.recipe, self.prompt), [])
        report = validate_recipe_file(RECIPE_PATH)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["warnings"], [])


if __name__ == "__main__":
    unittest.main()
