from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

import diffomatic
import diffomatic_fleet
import diffomatic_map


class _Wire(tuple):
    pass


class _StructuralEngine:
    name = "structural"
    render_canvas = (1024, 576)
    frame_contract = types.SimpleNamespace(discrete_frames=(97,))

    def _node_candidates(self):
        return {
            "source": ("EmptyLTXVLatentVideo",),
            "stage": ("LTXVLatentUpsampler",),
        }

    def _build_graph(self, plan, width, height, length):
        self.seen = (width, height, length, plan["target_frame_count"])
        return {
            "source": {"class": "source", "inputs": {
                "width": width, "height": height, "length": length,
            }},
            "stage": {"class": "stage", "inputs": {
                "samples": _Wire(("source", 0)),
            }},
        }


class DiffomaticDynamicTests(unittest.TestCase):
    def test_declared_canvas_drives_realistic_builder_fixture(self):
        engine = _StructuralEngine()
        graph, fixture = diffomatic._invoke_graph_builder(engine)

        self.assertEqual((1024, 576), (fixture["width"], fixture["height"]))
        self.assertEqual((1024, 576, 97, 97), engine.seen)
        self.assertEqual(2, len(graph))

    def test_node_candidates_are_authoritative_and_wiring_only_stage_survives(self):
        engine = _StructuralEngine()
        graph, _fixture = diffomatic._invoke_graph_builder(engine)
        loaded = diffomatic._normalise_dynamic_graph(engine, graph)

        self.assertEqual(2, loaded.total_nodes)
        self.assertEqual(
            ["EmptyLTXVLatentVideo", "LTXVLatentUpsampler"],
            [node[0] for node in loaded.nodes],
        )
        stage = next(node for node in loaded.nodes if node[0] == "LTXVLatentUpsampler")
        self.assertEqual({}, stage[1], "a wiring-only structural node must remain")

    def test_undeclared_logical_class_fails_closed(self):
        engine = _StructuralEngine()
        with self.assertRaisesRegex(
            diffomatic.UnsupportedGraphError, "absent from.*_node_candidates"
        ):
            diffomatic._normalise_dynamic_graph(
                engine, {"x": {"class": "invented", "inputs": {}}}
            )

    def test_unknown_required_builder_argument_fails_closed(self):
        class UnknownArgumentEngine(_StructuralEngine):
            def _build_graph(self, plan, width, height, mystery):
                raise AssertionError("builder must not be called")

        with self.assertRaisesRegex(
            diffomatic.UnsupportedGraphError, "unknown required arguments.*mystery"
        ):
            diffomatic._invoke_graph_builder(UnknownArgumentEngine())

    def test_concrete_engine_selection_uses_registry_and_rejects_ambiguity(self):
        module = types.SimpleNamespace(__name__="fake.adapters")
        class_one = type(
            "One", (), {"__module__": module.__name__, "name": "one",
                        "_build_graph": lambda self: {}}
        )
        class_two = type(
            "Two", (), {"__module__": module.__name__, "name": "two",
                        "_build_graph": lambda self: {}}
        )
        helper = type(
            "Helper", (), {"__module__": "fake.helper", "name": "helper",
                           "_build_graph": lambda self: {}}
        )

        self.assertIsInstance(
            diffomatic._select_concrete_engine(module, [class_one(), helper()]),
            class_one,
        )
        with self.assertRaisesRegex(diffomatic.UnsupportedGraphError, "multiple registered"):
            diffomatic._select_concrete_engine(module, [class_one(), class_two()])

        canonical_module = types.SimpleNamespace(__name__="fake.eng_humo")
        canonical = type(
            "Canonical", (), {"__module__": canonical_module.__name__, "name": "humo",
                              "_build_graph": lambda self: {}}
        )
        variant = type(
            "Variant", (), {"__module__": canonical_module.__name__, "name": "humo_14B",
                            "_build_graph": lambda self: {}}
        )
        self.assertIsInstance(
            diffomatic._select_concrete_engine(
                canonical_module, [variant(), canonical()]
            ),
            canonical,
        )

    def test_composed_node_candidate_methods_are_merged_without_alias_guessing(self):
        class ComposedEngine(_StructuralEngine):
            def _node_candidates_sampling(self):
                return {"selector": ("KSamplerSelect",)}

        mapping = diffomatic._candidate_map(ComposedEngine())
        self.assertEqual(("EmptyLTXVLatentVideo",), mapping["source"])
        self.assertEqual(("KSamplerSelect",), mapping["selector"])

    @unittest.skipUnless(os.path.isdir(diffomatic.OTR_ROOT), "OTR checkout absent")
    def test_real_ltx_av_uses_its_declared_1024x576_canvas(self):
        loaded = diffomatic._build_engine_graph("eng_ltx_av")
        base_latent = [params for class_type, params, _order in loaded.nodes
                       if class_type == "EmptyLTXVLatentVideo"]
        inplace = [params for class_type, params, _order in loaded.nodes
                   if class_type == "LTXVImgToVideoInplace"]
        self.assertTrue(base_latent)
        self.assertEqual(
            (512, 288),
            (base_latent[0]["width"], base_latent[0]["height"]),
            "the two-stage recipe must derive its half-size base from 1024x576",
        )
        self.assertEqual(2, len(inplace), "base and full-canvas refine anchors survive")


class DiffomaticWidgetSchemaTests(unittest.TestCase):
    def test_dynamic_combo_consumes_selector_children_and_following_widget(self):
        schemas = {
            "ResizeImageMaskNode": [
                {"id": "input", "kind": "v3", "spec": {"optional": False}},
                {"id": "resize_type", "kind": "v3", "spec": {
                    "options": [
                        {"key": "scale longer dimension", "inputs": {
                            "required": {"longer_size": ("INT", {"default": 512})}
                        }},
                        {"key": "scale dimensions", "inputs": {
                            "required": {
                                "width": ("INT", {"default": 512}),
                                "height": ("INT", {"default": 512}),
                            }
                        }},
                    ]
                }},
                {"id": "scale_method", "kind": "v3", "spec": {
                    "default": "lanczos", "options": ["nearest", "lanczos"]
                }},
            ]
        }
        params = diffomatic._ui_params(
            "ResizeImageMaskNode",
            {"widgets_values": ["scale longer dimension", 1536, "lanczos"]},
            schemas,
        )
        self.assertEqual({
            "resize_type": "scale longer dimension",
            "resize_type.longer_size": 1536,
            "scale_method": "lanczos",
        }, params)
        self.assertNotIn("input", params)

    def test_seed_control_value_is_consumed_but_excluded_from_comparison(self):
        schemas = {"RandomNoise": [{
            "id": "noise_seed", "kind": "v3",
            "spec": {"default": 0, "control_after_generate": True},
        }]}
        params = diffomatic._ui_params(
            "RandomNoise", {"widgets_values": [42, "fixed"]}, schemas
        )
        self.assertEqual(42, params["noise_seed"])
        self.assertEqual("fixed", params["noise_seed.control_after_generate"])
        summary = diffomatic.summarise([("RandomNoise", params, 0)])
        self.assertEqual({"noise_seed": 42}, summary["RandomNoise"][0][1])

    def test_unknown_schema_and_widget_count_mismatch_fail_closed(self):
        with self.assertRaisesRegex(diffomatic.UnsupportedGraphError, "no resolvable schema"):
            diffomatic._ui_params("UnknownSampler", {"widgets_values": [1]}, {})
        with self.assertRaisesRegex(diffomatic.UnsupportedGraphError, "count mismatch"):
            diffomatic._ui_params(
                "RandomNoise",
                {"widgets_values": [42, "fixed", "extra"]},
                {"RandomNoise": [{
                    "id": "noise_seed", "kind": "v3",
                    "spec": {"default": 0, "control_after_generate": True},
                }]},
            )

    def test_load_image_upload_companion_is_exact_and_not_a_parameter(self):
        schemas = {"LoadImage": [{
            "id": "image", "kind": "legacy",
            "type": ["portrait.png"],
            "spec": {"image_upload": True},
        }]}
        params = diffomatic._ui_params(
            "LoadImage", {"widgets_values": ["portrait.png", "image"]}, schemas
        )
        self.assertEqual({"image": "portrait.png", "upload": "image"}, params)
        self.assertEqual(
            [(0, {})],
            diffomatic.summarise([("LoadImage", params, 0)])["LoadImage"],
        )
        with self.assertRaisesRegex(diffomatic.UnsupportedGraphError, "count mismatch"):
            diffomatic._ui_params(
                "LoadImage",
                {"widgets_values": ["portrait.png", "not-an-upload-marker"]},
                schemas,
            )

    def test_load_audio_preview_companions_are_exact_and_not_parameters(self):
        schemas = {"LoadAudio": [{
            "id": "audio", "kind": "v3",
            "spec": {"options": ["voice.wav"], "audio_upload": True},
        }]}
        params = diffomatic._ui_params(
            "LoadAudio", {"widgets_values": ["voice.wav", None, ""]}, schemas
        )
        self.assertEqual({"audio": "voice.wav", "upload": [None, ""]}, params)
        self.assertEqual(
            [(0, {"audio": "voice.wav"})],
            diffomatic.summarise([("LoadAudio", params, 0)])["LoadAudio"],
        )
        with self.assertRaisesRegex(diffomatic.UnsupportedGraphError, "count mismatch"):
            diffomatic._ui_params(
                "LoadAudio",
                {"widgets_values": ["voice.wav", "unexpected", None]},
                schemas,
            )

    def test_api_dynamic_dict_and_ui_dynamic_widgets_flatten_identically(self):
        ui = {"resize_type": "scale dimensions", "resize_type.width": 832,
              "resize_type.height": 480, "resize_type.crop": "center"}
        api = diffomatic._normalise_params({"resize_type": {
            "resize_type": "scale dimensions", "width": 832,
            "height": 480, "crop": "center",
        }})
        self.assertEqual(ui, api)

    def test_older_template_may_use_only_an_explicit_trailing_default(self):
        params = diffomatic._ui_params(
            "CreateVideo", {"widgets_values": [24]}, {
                "CreateVideo": [
                    {"id": "fps", "kind": "v3", "spec": {"default": 30}},
                    {"id": "bit_depth", "kind": "v3", "spec": {"default": 8}},
                ]
            },
        )
        self.assertEqual({"fps": 24, "bit_depth": 8}, params)


class DiffomaticTopologyTests(unittest.TestCase):
    def _api(self, mapping):
        return diffomatic._normalise_api_graph("memory.json", mapping, "api_flat", "abc")

    def test_api_node_renumbering_is_digest_stable_but_rewiring_is_not(self):
        left = self._api({
            "1": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
            "2": {"class_type": "RandomNoise", "inputs": {"noise_seed": 43}},
            "3": {"class_type": "SamplerCustomAdvanced", "inputs": {
                "noise": ["1", 0], "guider": ["2", 0]
            }},
        })
        renumbered = self._api({
            "a": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
            "b": {"class_type": "RandomNoise", "inputs": {"noise_seed": 43}},
            "c": {"class_type": "SamplerCustomAdvanced", "inputs": {
                "noise": ["a", 0], "guider": ["b", 0]
            }},
        })
        rewired = self._api({
            "a": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
            "b": {"class_type": "RandomNoise", "inputs": {"noise_seed": 43}},
            "c": {"class_type": "SamplerCustomAdvanced", "inputs": {
                "noise": ["b", 0], "guider": ["a", 0]
            }},
        })
        self.assertEqual(left.counts()["topology_digest"],
                         renumbered.counts()["topology_digest"])
        self.assertNotEqual(left.counts()["topology_digest"],
                            rewired.counts()["topology_digest"])

    def test_unknown_source_pair_stays_a_literal(self):
        loaded = self._api({
            "1": {"class_type": "RandomNoise", "inputs": {
                "noise_seed": ["not-a-node", 0]
            }}
        })
        self.assertEqual(0, len(loaded.edges))
        self.assertEqual(["not-a-node", 0], loaded.nodes[0][1]["noise_seed"])

    def test_api_prompt_scope_ignores_nested_metadata_nodes(self):
        data = {
            "prompt": {"1": {"class_type": "RandomNoise", "inputs": {
                "noise_seed": 42
            }}},
            "extra": {"fake": {"class_type": "SamplerCustomAdvanced",
                                 "inputs": {}}},
        }
        mapping, kind = diffomatic._api_node_mapping(data)
        loaded = diffomatic._normalise_api_graph("api.json", mapping, kind, "abc")
        self.assertEqual(1, loaded.total_nodes)
        self.assertEqual("RandomNoise", loaded.nodes[0][0])

    def test_single_invoked_ui_subgraph_is_selected_without_root_duplication(self):
        subgraph = {
            "id": "sub-one", "name": "actual", "nodes": [{
                "id": 2, "type": "RandomNoise", "order": 0, "mode": 0,
                "inputs": [], "outputs": [],
                "widgets_values_named": {"noise_seed": 42},
            }], "links": [],
        }
        data = {
            "nodes": [{"id": 1, "type": "sub-one", "mode": 0}], "links": [],
            "definitions": {"subgraphs": [subgraph]},
        }
        loaded = diffomatic._normalise_ui_graph("ui.json", data, {}, "abc")
        self.assertEqual("subgraph:actual", loaded.scope)
        self.assertEqual(1, loaded.total_nodes)
        self.assertEqual("RandomNoise", loaded.nodes[0][0])

    def test_ui_link_metadata_mismatch_fails_closed(self):
        data = {
            "nodes": [
                {"id": 1, "type": "RandomNoise", "mode": 0,
                 "inputs": [], "outputs": [{"links": [7]}]},
                {"id": 2, "type": "SamplerCustomAdvanced", "mode": 0,
                 "inputs": [{"name": "noise", "link": 99}], "outputs": []},
            ],
            "links": [{"id": 7, "origin_id": 1, "origin_slot": 0,
                       "target_id": 2, "target_slot": 0}],
        }
        with self.assertRaisesRegex(diffomatic.UnsupportedGraphError, "contradicts"):
            diffomatic._normalise_ui_graph("ui.json", data, {}, "abc")

    def test_inactive_source_and_edge_are_excluded_not_executed(self):
        data = {
            "nodes": [
                {"id": 1, "type": "LoadImage", "mode": 4,
                 "inputs": [], "outputs": [{"links": [7]}]},
                {"id": 2, "type": "SamplerCustomAdvanced", "mode": 0,
                 "inputs": [{"name": "optional_image", "link": 7}],
                 "outputs": []},
            ],
            "links": [{"id": 7, "origin_id": 1, "origin_slot": 0,
                       "target_id": 2, "target_slot": 0}],
        }
        loaded = diffomatic._normalise_ui_graph("ui.json", data, {}, "abc")
        self.assertEqual(1, loaded.total_nodes)
        self.assertEqual(0, len(loaded.edges))

    def test_live_link_removes_dormant_serialized_widget_fallback(self):
        data = {
            "nodes": [
                {"id": 1, "type": "PrimitiveInt", "mode": 0,
                 "inputs": [], "outputs": [{"links": [7]}]},
                {"id": 2, "type": "EmptyLTXVLatentVideo", "mode": 0,
                 "inputs": [{"name": "width", "widget": {"name": "width"},
                             "link": 7}], "outputs": [],
                 "widgets_values_named": {
                     "width": 768, "height": 512, "length": 97,
                     "batch_size": 1,
                 }},
            ],
            "links": [{"id": 7, "origin_id": 1, "origin_slot": 0,
                       "target_id": 2, "target_slot": 0}],
        }
        loaded = diffomatic._normalise_ui_graph("ui.json", data, {}, "abc")
        latent = next(params for node, params, _order in loaded.nodes
                      if node == "EmptyLTXVLatentVideo")
        self.assertNotIn("width", latent)
        self.assertEqual(512, latent["height"])
        self.assertEqual(97, latent["length"])

    def test_quality_loader_and_sampling_widgets_are_not_omitted(self):
        data = {"nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple", "mode": 0,
             "inputs": [], "outputs": [],
             "widgets_values_named": {"ckpt_name": "model.safetensors"}},
            {"id": 2, "type": "LoraLoaderModelOnly", "mode": 0,
             "inputs": [], "outputs": [], "widgets_values_named": {
                 "lora_name": "detail.safetensors", "strength_model": 0.5,
             }},
            {"id": 3, "type": "ModelSamplingSD3", "mode": 0,
             "inputs": [], "outputs": [],
             "widgets_values_named": {"shift": 8.0}},
            {"id": 4, "type": "ComfyMathExpression", "mode": 0,
             "inputs": [], "outputs": [],
             "widgets_values_named": {"expression": "a * 2"}},
        ], "links": []}
        loaded = diffomatic._normalise_ui_graph("ui.json", data, {}, "abc")
        summary = diffomatic.summarise(loaded.nodes)
        self.assertEqual("model.safetensors",
                         summary["CheckpointLoaderSimple"][0][1]["ckpt_name"])
        self.assertEqual(0.5,
                         summary["LoraLoaderModelOnly"][0][1]["strength_model"])
        self.assertEqual(8.0, summary["ModelSamplingSD3"][0][1]["shift"])
        self.assertEqual("a * 2",
                         summary["ComfyMathExpression"][0][1]["expression"])

    def test_multiple_uninvoked_ui_subgraphs_are_ambiguous(self):
        graph = lambda name: {
            "id": name, "name": name,
            "nodes": [{"id": 1, "type": "RandomNoise", "mode": 0,
                       "inputs": [], "outputs": []}], "links": [],
        }
        data = {"nodes": [], "links": [], "definitions": {
            "subgraphs": [graph("one"), graph("two")]
        }}
        with self.assertRaisesRegex(diffomatic.UnsupportedGraphError, "2 possible"):
            diffomatic._normalise_ui_graph("ui.json", data, {}, "abc")

    @unittest.skipUnless(
        os.path.isfile(os.path.join(diffomatic_map.TEMPLATES,
                                    "video_ltx2_3_ia2v.json")),
        "official LTX 2.3 template absent",
    )
    def test_official_ltx_templates_drop_live_fallbacks_and_keep_quality_loaders(self):
        ltx25 = diffomatic.load_nodes(os.path.join(
            diffomatic_map.TEMPLATES, "video_ltx2_5_i2v.json"
        ))
        ltx25_summary = diffomatic.summarise(ltx25.nodes)
        latent = ltx25_summary["EmptyLTXVLatentVideo"][0][1]
        self.assertNotIn("width", latent)
        self.assertNotIn("height", latent)
        self.assertNotIn("length", latent)

        audio = diffomatic.load_nodes(os.path.join(
            diffomatic_map.TEMPLATES, "video_ltx2_3_ia2v.json"
        ))
        audio_summary = diffomatic.summarise(audio.nodes)
        checkpoint = audio_summary["CheckpointLoaderSimple"][0][1]
        distilled = audio_summary["LoraLoaderModelOnly"][0][1]
        style = audio_summary["LoraLoader"][0][1]
        self.assertEqual("ltx-2.3-22b-dev-fp8.safetensors",
                         checkpoint["ckpt_name"])
        self.assertEqual(0.5, distilled["strength_model"])
        self.assertEqual(1, style["strength_model"])
        self.assertEqual(1, style["strength_clip"])


class DiffomaticReceiptTests(unittest.TestCase):
    def _write_json(self, folder: Path, name: str, payload) -> Path:
        path = folder / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_empty_parse_is_nonzero_and_writes_named_error_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            empty = self._write_json(folder, "empty.json", {"nodes": []})
            valid = self._write_json(folder, "valid.json", {
                "1": {"class_type": "KSamplerSelect", "inputs": {
                    "sampler_name": "euler"
                }}
            })
            receipt = folder / "receipt.json"
            with contextlib.redirect_stderr(io.StringIO()):
                code = diffomatic.main([
                    "--template", str(empty), "--ours", str(valid),
                    "--json", str(receipt),
                ])

            self.assertNotEqual(0, code)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual("error", payload["status"])
            self.assertEqual("EMPTY_GRAPH", payload["error"]["code"])
            self.assertEqual(0, payload["node_counts"]["failed_source"]["total"])

    def test_equal_wiring_only_graphs_are_proven_by_nonzero_node_counts(self):
        graph = {
            "1": {"class_type": "LTXVLatentUpsampler", "inputs": {
                "samples": ["0", 0], "upscale_model": ["2", 0], "vae": ["3", 0]
            }}
        }
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            left = self._write_json(folder, "left.json", graph)
            right = self._write_json(folder, "right.json", graph)
            receipt = folder / "receipt.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = diffomatic.main([
                    "--template", str(left), "--ours", str(right),
                    "--json", str(receipt),
                ])

            self.assertEqual(0, code)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual("ok", payload["status"])
            self.assertEqual(1, payload["node_counts"]["reference"]["significant"])
            self.assertEqual(1, payload["node_counts"]["ours"]["significant"])
            self.assertIn("node counts above prove both graphs were parsed", stdout.getvalue())

    def test_unsupported_engine_is_nonzero_with_both_side_counts(self):
        graph = {
            "1": {"class_type": "KSamplerSelect", "inputs": {
                "sampler_name": "euler"
            }}
        }
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            reference = self._write_json(folder, "reference.json", graph)
            receipt = folder / "receipt.json"
            with contextlib.redirect_stderr(io.StringIO()):
                code = diffomatic.main([
                    "--template", str(reference),
                    "--ours", "eng_definitely_not_registered",
                    "--json", str(receipt),
                ])

            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(diffomatic.UnsupportedGraphError.exit_code, code)
            self.assertEqual("UNSUPPORTED_GRAPH", payload["error"]["code"])
            self.assertEqual(1, payload["node_counts"]["reference"]["total"])
            self.assertEqual(0, payload["node_counts"]["ours"]["total"])

    def test_unexpected_loader_exception_writes_internal_error_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            receipt = Path(raw) / "receipt.json"
            with mock.patch.object(diffomatic, "load_nodes", side_effect=ValueError("boom")):
                with contextlib.redirect_stderr(io.StringIO()):
                    code = diffomatic.main([
                        "--template", "left.json", "--ours", "right.json",
                        "--json", str(receipt),
                    ])
            self.assertEqual(diffomatic.InternalDiffomaticError.exit_code, code)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual("INTERNAL_ERROR", payload["error"]["code"])
            self.assertIn("ValueError", payload["error"]["message"])

    @unittest.skipUnless(
        os.path.isfile(os.path.join(diffomatic_map.TEMPLATES,
                                    "video_ltx2_3_ia2v.json")),
        "official LTX 2.3 template absent",
    )
    def test_only_side_receipt_keeps_complete_official_lora_settings(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            ours = self._write_json(folder, "ours.json", {
                "1": {"class_type": "KSamplerSelect", "inputs": {
                    "sampler_name": "euler"
                }}
            })
            receipt = folder / "receipt.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = diffomatic.main([
                    "--template", os.path.join(
                        diffomatic_map.TEMPLATES, "video_ltx2_3_ia2v.json"
                    ),
                    "--ours", str(ours),
                    "--json", str(receipt),
                ])

            self.assertEqual(0, code)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            lora = next(
                row for row in payload["only_in_reference"]
                if row["node"] == "LoraLoader"
            )
            self.assertEqual(1, lora["instance_count"])
            self.assertEqual(48, lora["instances"][0]["order"])
            self.assertEqual({
                "lora_name": (
                    "gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors"
                ),
                "strength_model": 1,
                "strength_clip": 1,
            }, lora["instances"][0]["params"])
            self.assertIn('"strength_clip": 1', stdout.getvalue())


class DiffomaticDocumentationTests(unittest.TestCase):
    def test_reason_is_tied_to_referenced_constant_and_exact_line(self):
        source = (
            "# unrelated prose\n"
            "OTHER = 9\n"
            "\n"
            "# Three steps are the measured refine schedule.\n"
            "LOCKED_STEPS = 3\n"
            "GRAPH = {\"steps\": LOCKED_STEPS}\n"
        )
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "recipe.py"
            path.write_text(source, encoding="utf-8")
            reason = diffomatic.find_documentation_for_param(
                "steps", 3, [str(path)]
            )

        self.assertIn(f"[{os.path.abspath(path)}:5]", reason)
        self.assertIn("measured refine schedule", reason)
        self.assertNotIn("unrelated prose", reason)

    def test_unrelated_node_comment_does_not_document_an_arbitrary_param(self):
        source = (
            "# LTXVImgToVideoInplace exists for another decision.\n"
            "ANCHOR = 1.0\n"
            "GRAPH = {\"passes\": 2}\n"
        )
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "recipe.py"
            path.write_text(source, encoding="utf-8")
            reason = diffomatic.find_documentation_for_param(
                "passes", 2, [str(path)]
            )
        self.assertEqual("", reason)

    def test_duplicate_parameter_names_require_unique_value_evidence(self):
        source = (
            "# Base pass, not the requested value.\n"
            "BASE = {\"steps\": 8}\n"
            "# Refine pass selected by its exact static value.\n"
            "REFINE = {\"steps\": 3}\n"
        )
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "recipe.py"
            path.write_text(source, encoding="utf-8")
            selected = diffomatic.find_documentation_for_param(
                "steps", 3, [str(path)]
            )
            ambiguous_path = Path(raw) / "ambiguous.py"
            ambiguous_path.write_text(
                "# First.\nA = {\"steps\": 3}\n"
                "# Second.\nB = {\"steps\": 3}\n",
                encoding="utf-8",
            )
            ambiguous = diffomatic.find_documentation_for_param(
                "steps", 3, [str(ambiguous_path)]
            )
        self.assertIn("Refine pass", selected)
        self.assertNotIn("Base pass", selected)
        self.assertEqual("", ambiguous)


class DiffomaticMapTests(unittest.TestCase):
    def test_engine_scan_contains_only_supplied_registered_objects(self):
        fake_class = type(
            "Registered", (), {
                "__module__": __name__,
                "name": "registered_only",
                "family": "image_to_video",
                "required_inputs": ("text_prompt", "init_image"),
            }
        )
        engines = diffomatic_map.scan_engines([("video", fake_class())])
        self.assertEqual(["video:registered_only"], list(engines))
        self.assertEqual("i2v", engines["video:registered_only"]["role"])

    def test_one_family_token_is_a_no_match_but_versioned_pair_is_strong(self):
        weak, _why = diffomatic_map.score(
            {"weights": {"ltx-special.gguf"}},
            {"weights": {"ltx-unrelated.safetensors"}},
        )
        strong, why = diffomatic_map.score(
            {"weights": {"ltx-2.5-q3.gguf"}},
            {"weights": {"ltx-2.5-fp8.safetensors"}},
        )
        self.assertEqual(0.0, weak)
        self.assertGreater(strong, 0.0)
        self.assertIn("strong family", why)

    def test_i2v_t2v_ambiguity_is_explicit_and_never_alphabetical(self):
        ranked = [
            {"template": "video_ltx_t2v.json", "score": 30.0,
             "why": "same model", "role": "t2v"},
            {"template": "video_ltx_i2v.json", "score": 30.0,
             "why": "same model", "role": "i2v"},
        ]
        engine = {
            "engine": "ltx25_video", "kind": "video", "module": "eng_ltx25",
            "role": "i2v", "no_reference_reason": "",
        }
        selected = diffomatic_map.choose_mapping(engine, ranked)
        self.assertEqual("role_disambiguated", selected["status"])
        self.assertEqual("video_ltx_i2v.json", selected["template"])
        self.assertEqual(2, len(selected["candidates"]))
        self.assertIn("video_ltx_t2v.json", selected["why"])

        engine["role"] = "unknown"
        ambiguous = diffomatic_map.choose_mapping(engine, ranked)
        self.assertEqual("ambiguous_role", ambiguous["status"])
        self.assertIsNone(ambiguous["template"])

    def test_zero_evidence_never_becomes_a_mapping_at_zero_threshold(self):
        engines = {"video:x": {
            "engine": "x", "kind": "video", "module": "eng_x",
            "role": "unknown", "weights": {"ltx-special.gguf"},
            "no_reference_reason": "",
        }}
        templates = {"unrelated.json": {
            "weights": {"wan-unrelated.safetensors"}, "role": "unknown",
        }}
        rows = diffomatic_map.build_rows(engines, templates, 0.0)
        self.assertEqual("no_match", rows[0]["status"])
        self.assertIsNone(rows[0]["template"])

    def test_cli_rejects_nonpositive_or_nonfinite_threshold(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    diffomatic_map.main(["--min-score", value])


class DiffomaticFleetTests(unittest.TestCase):
    def test_declared_fleet_partition_is_complete_and_unique(self):
        compared = [case.engine for case in diffomatic_fleet.CASES]
        self.assertEqual(len(compared), len(set(compared)))
        self.assertEqual(13, len(compared))
        self.assertEqual(11, sum(case.relation == "exact"
                                 for case in diffomatic_fleet.CASES))
        self.assertEqual(2, sum(case.relation == "qualified"
                                for case in diffomatic_fleet.CASES))
        self.assertEqual(17, len(diffomatic_fleet.NO_REFERENCE))
        self.assertFalse(set(compared) & diffomatic_fleet.NO_REFERENCE)

    def test_recipe_override_environment_is_cleared_and_audited(self):
        with mock.patch.dict(os.environ, {
            "OTR_WAN_I2V_CLIP_NAME": "developer-override.safetensors",
            "HF_HOME": "C:/developer/cache",
        }, clear=False):
            audit = diffomatic_fleet._sanitize_environment()
            self.assertNotIn("OTR_WAN_I2V_CLIP_NAME", os.environ)
            self.assertNotIn("HF_HOME", os.environ)
            self.assertEqual("1", os.environ["OTR_TEST_MODE"])
            self.assertEqual("", os.environ["CUDA_VISIBLE_DEVICES"])
        self.assertIn("OTR_WAN_I2V_CLIP_NAME", audit["cleared_present_keys"])
        self.assertIn("HF_HOME", audit["cleared_present_keys"])

    @unittest.skipUnless(os.path.isdir(diffomatic.OTR_ROOT), "OTR checkout absent")
    def test_live_registered_video_roster_matches_the_30_row_contract(self):
        _scanned, errors = diffomatic_fleet._validate_roster()
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
