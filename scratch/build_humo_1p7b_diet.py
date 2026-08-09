#!/usr/bin/env python3
"""Build the immutable HuMo 1.7B clamp-floor recipe.

This is an offline transcription of OTR's production HuMo17BEngine graph.  It
does not import OTR, query ComfyUI, inspect a live port, install anything, or
render.  The source files that justify every graph value are hash-pinned and
verified before the recipe is written.

The only nodes after the OTR graph are CreateVideo and SaveVideo.  CreateVideo
receives the same LoadAudio output used for conditioning so the lab review clip
has the exact source TTS.  OTR's native production artifact remains silent by
policy; this delivery tail is deliberately outside the generation graph.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = ROOT / "recipes" / "humo_1p7b_diet.json"
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
COMFY_ROOT = Path(r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI")

OTR_COMMIT = "15f23044a6f1224a61a39dc38e1e60875a894dd6"
COMFY_COMMIT = "fe4195f7f4275f2626cbafc703acc3ddde1e5490"
COMFY_VERSION = "0.31.1"

OTR_SOURCE_HASHES = {
    "nodes/_otr_video_engines/eng_humo.py": (
        "77562728f09595082012c91a57ebcd878f7dc9b2f80b17e7b16b77e412b6bd6c"
    ),
    "nodes/_otr_video_engines/render_driver.py": (
        "7d431a5877af678fbb88b0be1c57d98009eb7ffca1290d7ebbae97f44a98b564"
    ),
}

COMFY_SOURCE_HASHES = {
    "nodes.py": "aa7e2a87bb7c1b43273736eef9fcf4811cb55497c5bde2e201135b244b97431a",
    "comfy_extras/nodes_wan.py": (
        "dcd8b81d1225d84e8b0c6743675d59772449899018e9f50bb27267dbb8962002"
    ),
    "comfy_extras/nodes_audio_encoder.py": (
        "ad290791fe4dc79a59d511ace2ff1c8df732a7b3cf5a01c61cfe6579192872c2"
    ),
    "comfy_extras/nodes_audio.py": (
        "82bb9dcf191a84cb0695bc2533602f7956e29a81a1176965556350b02e1bd67e"
    ),
    "comfy_extras/nodes_model_advanced.py": (
        "ffa70c4bb3568537ba13b368092d2599b861db7c83b1bcfa41347058b40dcba7"
    ),
    "comfy_extras/nodes_video.py": (
        "727653159de9a6e9d5b37b1101d3ece5df7dce8fc6a5a3a1f27e260afcfa6c14"
    ),
}

FIXTURE_HASHES = {
    "portrait.png": "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad",
    "tts_dialogue.wav": (
        "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"
    ),
}

POSITIVE = (
    "a 1940s radio studio, on air sign illuminated, period broadcast set"
)
NEGATIVE = (
    "low quality, worst quality, blurry, jpeg artifacts, distorted, deformed, "
    "extra fingers, bad hands, bad face, static, watermark, text"
)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(raw)


def _git_head(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()


def verify_frozen_sources() -> None:
    """Refuse to relabel a changed implementation as the measured source."""
    identities = (
        (OTR_ROOT, OTR_COMMIT, OTR_SOURCE_HASHES, "OTR"),
        (COMFY_ROOT, COMFY_COMMIT, COMFY_SOURCE_HASHES, "ComfyUI"),
    )
    for repo, expected_commit, expected_hashes, label in identities:
        actual_commit = _git_head(repo)
        if actual_commit != expected_commit:
            raise RuntimeError(
                f"{label} commit changed: expected {expected_commit}, "
                f"found {actual_commit}"
            )
        for relative, expected_hash in expected_hashes.items():
            path = repo / Path(relative)
            if not path.is_file():
                raise RuntimeError(f"{label} source is missing: {relative}")
            actual_hash = sha256_file(path)
            if actual_hash != expected_hash:
                raise RuntimeError(
                    f"{label} source changed: {relative}: expected "
                    f"{expected_hash}, found {actual_hash}"
                )

    for name, expected_hash in FIXTURE_HASHES.items():
        path = ROOT / "fixtures" / name
        if not path.is_file():
            raise RuntimeError(f"fixture is missing: {name}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"fixture changed: {name}: expected {expected_hash}, "
                f"found {actual_hash}"
            )


def build_prompt() -> dict[str, dict[str, Any]]:
    """Concrete Comfy API graph specialized from HuMo17BEngine._build_graph."""
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "humo_1.7B_fp16.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default",
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": POSITIVE, "clip": ["2", 0]},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": NEGATIVE, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "wan_2.1_vae.safetensors"},
        },
        "6": {
            "class_type": "LoadAudio",
            "inputs": {"audio": "tts_dialogue.wav"},
        },
        "7": {
            "class_type": "AudioEncoderLoader",
            "inputs": {
                "audio_encoder_name": "whisper_large_v3_fp16.safetensors"
            },
        },
        "8": {
            "class_type": "AudioEncoderEncode",
            "inputs": {
                "audio_encoder": ["7", 0],
                "audio": ["6", 0],
            },
        },
        "9": {
            "class_type": "LoadImage",
            "inputs": {"image": "portrait.png"},
        },
        "10": {
            "class_type": "WanHuMoImageToVideo",
            "inputs": {
                "width": 480,
                "height": 832,
                "length": 129,
                "batch_size": 1,
                "positive": ["3", 0],
                "negative": ["4", 0],
                "vae": ["5", 0],
                "audio_encoder_output": ["8", 0],
                "ref_image": ["9", 0],
            },
        },
        "11": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"shift": 8.0, "model": ["1", 0]},
        },
        "12": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 7,
                "steps": 20,
                "cfg": 1.0,
                "sampler_name": "uni_pc",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["11", 0],
                "positive": ["10", 0],
                "negative": ["10", 1],
                "latent_image": ["10", 2],
            },
        },
        "13": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["12", 0], "vae": ["5", 0]},
        },
        # OTR encodes the native generation graph to a silent clip outside
        # _build_graph.  The lab appends exact source audio only for A/B review.
        "14": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["13", 0],
                "fps": 25.0,
                "bit_depth": 8,
                "audio": ["6", 0],
            },
        },
        "15": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["14", 0],
                "filename_prefix": "humo_1p7b_diet_out",
                "format": "auto",
                "codec": "auto",
            },
        },
    }


OTR_TO_LAB_NODE_MAP = {
    "unet": "1",
    "clip": "2",
    "pos": "3",
    "neg": "4",
    "vae": "5",
    "loadaudio": "6",
    "audioenc_loader": "7",
    "audioenc": "8",
    "loadimage": "9",
    "humo": "10",
    "modelsampling": "11",
    "ksampler": "12",
    "vaedecode": "13",
}


def source_graph_projection(prompt: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The graph portion with a one-to-one counterpart in OTR._build_graph."""
    return {
        source_id: prompt[lab_id]
        for source_id, lab_id in OTR_TO_LAB_NODE_MAP.items()
    }


def required_input_values(prompt: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Freeze every scalar input; links are frozen separately."""
    assertions: list[dict[str, Any]] = []
    for node_id, node in prompt.items():
        for input_name, value in node["inputs"].items():
            if not (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
            ):
                assertions.append(
                    {"node": node_id, "input": input_name, "equals": value}
                )
    return assertions


def required_connections(prompt: dict[str, dict[str, Any]]) -> dict[str, list[Any]]:
    connections: dict[str, list[Any]] = {}
    for node_id, node in prompt.items():
        for input_name, value in node["inputs"].items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
            ):
                connections[f"{node_id}.{input_name}"] = value
    return connections


def build_recipe() -> dict[str, Any]:
    prompt = build_prompt()
    production_projection = source_graph_projection(prompt)
    source_pairs = {
        source_id: {
            "lab_node": lab_id,
            "class_type": prompt[lab_id]["class_type"],
            "comparison": "exact class and inputs after symbolic Wire links are concretized",
        }
        for source_id, lab_id in OTR_TO_LAB_NODE_MAP.items()
    }
    return {
        "name": "humo_1p7b_diet",
        "tier": "experiment",
        "blocked": False,
        "experiment": {
            "campaign": "humo_vram_diet_v1",
            "variant": "production_graph_zero_change_clamp_floor",
            "independent_variable": "boot_lane_target_card_budget_gb",
            "single_variable_order": [13.0, 12.0],
            "execution_order": [
                {"target_card_budget_gb": 13.0, "same_server_consecutive_runs": 2},
                {"target_card_budget_gb": 12.0, "same_server_consecutive_runs": 2},
            ],
            "graph_change_count": 0,
            "generation_graph_policy": (
                "Immutable within and across two independent warm pairs: "
                "clamp-13 twice on one server, then clamp-12 twice on a fresh "
                "server; only reserve pressure changes between pairs"
            ),
            "production_comparator": (
                "results/otr_side/humo_1_7b_bakeoff_take1.json"
            ),
            "production_comparator_clip": "outputs/humo_1_7b_bakeoff_take1.mp4",
            "required_human_gate": (
                "Jeffrey judges lip sync, identity, motion, and visual quality "
                "parity against the production bakeoff clip"
            ),
            "render_status": "unrendered",
            "behavioral_claim_status": "unrendered and unproven",
        },
        "contract": {
            "engine": "humo_1p7b",
            "mode": "audio_driven_face",
            "width": 480,
            "height": 832,
            "frames": 129,
            "fps": 25.0,
            "target_s": 5.16,
            "duration_s": 5.16,
            "requires_audio": True,
            "requires_human_eyeball": True,
            "vram_ceiling_gb": 14.5,
            "diet_target_peak_vram_gb": 13.5,
            "warm_runs_required": 2,
            "requires_disable_pinned_memory": True,
            "clamp_experiment": {
                "semantics": (
                    "target-card budget; runner computes reserve as physical "
                    "VRAM minus target"
                ),
                "ordered_target_card_budgets_gb": [13.0, 12.0],
                "consecutive_runs_per_budget": 2,
                "fresh_server_between_budgets": True,
                "peak_minus_baseline_must_lte_target_card_budget": True,
                "absolute_peak_must_lte_gb": 13.5,
            },
            "required_boot_lanes": [
                "lab-8199, sage-free, no-pinned, clamp-13gb (two consecutive runs on one server)",
                "lab-8199, sage-free, no-pinned, clamp-12gb (two consecutive runs on a fresh server)",
            ],
        },
        "receipt_requirements": {
            "warm_certification": {
                "consecutive_same_recipe_runs": 2,
                "same_boot_lane": True,
            },
            "vram": {
                "absolute_peak_vram_gb_lte": 13.5,
                "global_lab_ceiling_gb_lte": 14.5,
                "record_baseline_and_peak": True,
            },
            "phase_timeline": {
                "sample_interval_s": 0.2,
                "correlate_with_server_log": True,
                "name_peak_phase_and_memory_hog": True,
            },
            "human_quality_parity": {
                "status": "PENDING_HUMAN",
                "comparator": "outputs/humo_1_7b_bakeoff_take1.mp4",
            },
        },
        "topology_contract": {
            "schema_version": 1,
            "profile": "otr_humo_1p7b_production_graph_clamp_floor_v1",
            "intent": (
                "Exact OTR HuMo17BEngine generation graph with a lab-only "
                "exact-source-audio review delivery tail"
            ),
            "origin": {
                "builder": "scratch/build_humo_1p7b_diet.py",
                "seed_rule": (
                    "OTR eng_humo.HuMo17BEngine._build_graph specialized with "
                    "render_driver.render_single/build_request defaults; never "
                    "a vendor template"
                ),
                "original_implementation": True,
                "third_party_workflow_json_copied": False,
                "custom_node_pack_required": False,
                "node_origin": (
                    "ComfyUI core v0.31.1: WanHuMoImageToVideo and audio "
                    "encoder classes are in comfy_extras"
                ),
            },
            "source_graph_evidence": {
                "otr_commit": OTR_COMMIT,
                "engine_source": "nodes/_otr_video_engines/eng_humo.py",
                "engine_source_sha256": OTR_SOURCE_HASHES[
                    "nodes/_otr_video_engines/eng_humo.py"
                ],
                "request_source": "nodes/_otr_video_engines/render_driver.py",
                "request_source_sha256": OTR_SOURCE_HASHES[
                    "nodes/_otr_video_engines/render_driver.py"
                ],
                "source_method": "HuMoEngine._build_graph",
                "source_specialization": "HuMo17BEngine defaults plus render_single request",
                "source_to_lab_node_pairs": source_pairs,
                "source_graph_projection_sha256": canonical_sha256(
                    production_projection
                ),
                "source_graph_node_count": len(production_projection),
                "lora": {
                    "source_value": "none",
                    "node_present": False,
                    "reason": "HuMo17BEngine skips incompatible 14B-shaped LoRA",
                },
                "lab_only_delivery_nodes": {
                    "14": "CreateVideo",
                    "15": "SaveVideo",
                },
                "intentional_transcription_differences": [
                    "OTR wrapper_bridge symbolic class aliases and Wire objects are concretized as Comfy API class_type/link values",
                    "OTR staged fixture paths are represented by hash-identical lab fixture basenames",
                    "OTR emits a native silent clip outside _build_graph; the lab appends CreateVideo/SaveVideo and delivers exact source TTS for A/B review",
                ],
            },
            "installed_schema": {
                "comfyui_version": COMFY_VERSION,
                "git_commit": COMFY_COMMIT,
                "node_sources_sha256": COMFY_SOURCE_HASHES,
                "manifest_gate": (
                    "run_recipe preflight remains authoritative; this builder "
                    "does not edit models_manifest.md"
                ),
            },
            "fixture_hashes": FIXTURE_HASHES,
            "exact_node_set": True,
            "required_nodes": {
                node_id: node["class_type"] for node_id, node in prompt.items()
            },
            "required_class_types": sorted(
                {node["class_type"] for node in prompt.values()}
            ),
            "required_connections": required_connections(prompt),
            "required_input_values": required_input_values(prompt),
            "required_absent_inputs": [
                "10.start_image",
                "10.clip_vision_output",
            ],
            "forbidden_class_types": [
                "LoraLoaderModelOnly",
                "VAEDecodeTiled",
                "WanImageToVideo",
                "EmptyLatentImage",
            ],
            "audio_path_contract": {
                "conditioning": (
                    "6.LoadAudio -> 8.AudioEncoderEncode.audio; "
                    "7.AudioEncoderLoader -> 8.audio_encoder -> "
                    "10.WanHuMoImageToVideo.audio_encoder_output"
                ),
                "delivery": "6.LoadAudio -> 14.CreateVideo.audio",
                "same_source_node_for_conditioning_and_delivery": True,
                "production_native_output": "silent by OTR policy",
                "lab_review_output": "exact source TTS delivered for parity review",
                "delivery_tail_changes_generation": False,
            },
            "terminal_node": "15",
            "require_all_nodes_reachable": True,
            "intentional_divergences": [
                "Lab fixture basenames replace hash-identical OTR staging filenames",
                "CreateVideo and SaveVideo are appended after the exact OTR generation graph",
                "Source TTS is delivered on the lab review artifact; OTR production native clips remain silent",
                "Clamp and no-pinned controls are boot-lane variables, never graph nodes",
            ],
        },
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }


def serialized_recipe(recipe: dict[str, Any]) -> bytes:
    return (json.dumps(recipe, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> int:
    verify_frozen_sources()
    raw = serialized_recipe(build_recipe())
    RECIPE_PATH.write_bytes(raw)
    print(f"wrote {RECIPE_PATH}")
    print(f"recipe_sha256={sha256_bytes(raw)}")
    print(
        "source_graph_projection_sha256="
        + build_recipe()["topology_contract"]["source_graph_evidence"][
            "source_graph_projection_sha256"
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
