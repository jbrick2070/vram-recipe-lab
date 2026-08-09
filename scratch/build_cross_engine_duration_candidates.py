#!/usr/bin/env python3
"""Build immutable, receipt-ready cross-engine duration candidates.

The graph shapes are grounded in frozen OTR production/bench sources, but the
three files emitted here are lab-owned experiments.  Nothing in this module
imports OTR or mutates its repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).parent.parent.resolve()
RECIPES_DIR = REPO_ROOT / "recipes"

COMFYUI_SCHEMA_VERSION = "0.31.1"
COMFYUI_SCHEMA_COMMIT = "fe4195f7f4275f2626cbafc703acc3ddde1e5490"
SCENE_STILL_SHA256 = (
    "0476dbc87358d367d244c65e976f8013f9659aeb80f7a1c45b368cc1728a5596"
)

OTR_HEAD = "bf9f7fb11157be56b9aa6fac1115b49be68221e1"
OTR_WAN_TI2V_SOURCE_BLOB = "8e77a1058cd653bd66242a8dc79cddf02007b576"
OTR_WAN_I2V_SOURCE_BLOB = "ad0ea4219cf56549075e0b1d4e4d77f4c053de83"
OTR_LTX8_SOURCE_BLOB = "2c7960af936b77c259390138f25ac4914c65fa40"
OTR_WAN_BENCH_BLOB = "7f9989a866ee527c129111eee7e6531a1b0e57f6"
OTR_LTX8_BENCH_BLOB = "c96b78f7e3973859626d7c2a9a93dd01ad54322c"

WAN_NODE_SOURCE = "comfy_extras/nodes_wan.py"
WAN_NODE_SOURCE_SHA256 = (
    "dcd8b81d1225d84e8b0c6743675d59772449899018e9f50bb27267dbb8962002"
)
LTX_NODE_SOURCE = "comfy_extras/nodes_lt.py"
LTX_NODE_SOURCE_SHA256 = (
    "9dc42e342a0c4242e5a7cc3a136b746afeee4349ea08c510b7c2c17002e4b6be"
)

COMPARE_WIDTH = 832
COMPARE_HEIGHT = 480
COMPARE_FRAMES = 193
COMPARE_FPS = 25.0
COMPARE_DURATION_S = 7.72
EXONERATION_FRAMES = 33
EXONERATION_DURATION_S = 1.32
SEED = 42

POSITIVE = "subtle natural motion, cinematic lighting, detailed"
NEGATIVE = "low quality, worst quality, blurry, distorted, watermark, text, static"

WAN_COMPARE_NAME = "wan_ti2v_5b_cmp_832x480_f193"
WAN_COMPARE_PREFIX = f"{WAN_COMPARE_NAME}_out"
LTX_COMPARE_NAME = "ltx_video_2b_distilled_cmp_832x480_f193"
LTX_COMPARE_PREFIX = f"{LTX_COMPARE_NAME}_out"
WAN14_EXONERATION_NAME = "wan_i2v_14b_exoneration_832x480_f33"
WAN14_EXONERATION_PREFIX = f"{WAN14_EXONERATION_NAME}_out"


def _is_link(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    )


def _topology_contract(
    prompt: dict[str, dict[str, Any]],
    *,
    intent: str,
    node_source: str,
    node_source_sha256: str,
    evidence: dict[str, Any],
    required_absent_inputs: list[str],
    intentional_divergences: list[str],
) -> dict[str, Any]:
    required_connections: dict[str, list[Any]] = {}
    required_input_values: list[dict[str, Any]] = []
    for node_id, node in prompt.items():
        for input_name, value in node["inputs"].items():
            if _is_link(value):
                required_connections[f"{node_id}.{input_name}"] = value
            else:
                required_input_values.append(
                    {"node": node_id, "input": input_name, "equals": value}
                )

    required_nodes = {
        node_id: node["class_type"] for node_id, node in prompt.items()
    }
    return {
        "schema_version": 1,
        "intent": intent,
        "installed_schema": {
            "comfyui_version": COMFYUI_SCHEMA_VERSION,
            "git_commit": COMFYUI_SCHEMA_COMMIT,
            "node_source": node_source,
            "node_source_sha256": node_source_sha256,
        },
        "evidence": evidence,
        "exact_node_set": True,
        "required_nodes": required_nodes,
        "required_class_types": list(dict.fromkeys(required_nodes.values())),
        "required_connections": required_connections,
        "required_input_values": required_input_values,
        "required_absent_inputs": required_absent_inputs,
        "forbidden_class_types": [
            "EmptyLatentImage",
            "VAEDecodeTiled",
            "LoadAudio",
        ],
        "terminal_node": "12",
        "require_all_nodes_reachable": True,
        "intentional_divergences": intentional_divergences,
        "fixture_hashes": {"scene_still.png": SCENE_STILL_SHA256},
    }


def _contract(engine: str, mode: str, frames: int, duration_s: float) -> dict[str, Any]:
    return {
        "engine": engine,
        "mode": mode,
        "width": COMPARE_WIDTH,
        "height": COMPARE_HEIGHT,
        "frames": frames,
        "fps": COMPARE_FPS,
        "target_s": duration_s,
        "duration_s": duration_s,
        "delivered_s": duration_s,
        "trim_frames": 0,
        "requires_audio": False,
        "required_boot_lane": "lab-8199, sage-free",
        "vram_ceiling_gb": 14.5,
    }


def _receipt_requirements(frames: int, duration_s: float) -> dict[str, Any]:
    return {
        "warm_gate": {
            "required_consecutive_runs": 2,
            "passing_run": "second consecutive run",
            "peak_vram_gb_lte": 14.5,
        },
        "timing": {
            "ffprobe_required": True,
            "expected_frame_count": frames,
            "expected_fps": COMPARE_FPS,
            "target_s": duration_s,
            "absolute_duration_error_lte_s": 1.0 / COMPARE_FPS,
        },
        "quality": {"human_eyeball_required": True},
    }


def make_wan_ti2v_prompt() -> dict[str, dict[str, Any]]:
    return {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": "Wan2.2-TI2V-5B-Q5_K_M.gguf"},
        },
        "2": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["1", 0], "shift": 5.0},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default",
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": POSITIVE, "clip": ["3", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": NEGATIVE, "clip": ["3", 0]},
        },
        "6": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "wan2.2_vae.safetensors"},
        },
        "7": {
            "class_type": "LoadImage",
            "inputs": {"image": "scene_still.png"},
        },
        "8": {
            "class_type": "Wan22ImageToVideoLatent",
            "inputs": {
                "width": COMPARE_WIDTH,
                "height": COMPARE_HEIGHT,
                "length": COMPARE_FRAMES,
                "batch_size": 1,
                "vae": ["6", 0],
                "start_image": ["7", 0],
            },
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": SEED,
                "steps": 30,
                "cfg": 5.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["8", 0],
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["6", 0]},
        },
        "11": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["10", 0], "fps": COMPARE_FPS, "bit_depth": 8},
        },
        "12": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["11", 0],
                "filename_prefix": WAN_COMPARE_PREFIX,
                "format": "auto",
                "codec": "auto",
            },
        },
    }


def make_ltx_2b_prompt() -> dict[str, dict[str, Any]]:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "ltxv-2b-0.9.8-distilled.safetensors"},
        },
        "2": {
            "class_type": "ModelSamplingLTXV",
            "inputs": {"model": ["1", 0], "max_shift": 2.05, "base_shift": 0.95},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "t5xxl_fp16.safetensors",
                "type": "ltxv",
                "device": "cpu",
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": POSITIVE, "clip": ["3", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": NEGATIVE, "clip": ["3", 0]},
        },
        "7": {
            "class_type": "LoadImage",
            "inputs": {"image": "scene_still.png"},
        },
        "8": {
            "class_type": "LTXVImgToVideo",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "vae": ["1", 2],
                "image": ["7", 0],
                "width": COMPARE_WIDTH,
                "height": COMPARE_HEIGHT,
                "length": COMPARE_FRAMES,
                "batch_size": 1,
                "strength": 1.0,
            },
        },
        "15": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["8", 0],
                "negative": ["8", 1],
                "frame_rate": COMPARE_FPS,
            },
        },
        "16": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": 8,
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
                "latent": ["8", 2],
            },
        },
        "17": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"},
        },
        "9": {
            "class_type": "SamplerCustom",
            "inputs": {
                "model": ["2", 0],
                "add_noise": True,
                "noise_seed": SEED,
                "cfg": 1.0,
                "positive": ["15", 0],
                "negative": ["15", 1],
                "sampler": ["17", 0],
                "sigmas": ["16", 0],
                "latent_image": ["8", 2],
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["1", 2]},
        },
        "11": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["10", 0], "fps": COMPARE_FPS, "bit_depth": 8},
        },
        "12": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["11", 0],
                "filename_prefix": LTX_COMPARE_PREFIX,
                "format": "auto",
                "codec": "auto",
            },
        },
    }


def make_wan14_prompt() -> dict[str, dict[str, Any]]:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["1", 0], "shift": 8.0},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default",
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": POSITIVE, "clip": ["3", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": NEGATIVE, "clip": ["3", 0]},
        },
        "6": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "wan_2.1_vae.safetensors"},
        },
        "7": {
            "class_type": "LoadImage",
            "inputs": {"image": "scene_still.png"},
        },
        "8": {
            "class_type": "WanImageToVideo",
            "inputs": {
                "width": COMPARE_WIDTH,
                "height": COMPARE_HEIGHT,
                "length": EXONERATION_FRAMES,
                "batch_size": 1,
                "positive": ["4", 0],
                "negative": ["5", 0],
                "vae": ["6", 0],
                "start_image": ["7", 0],
            },
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": SEED,
                "steps": 20,
                "cfg": 3.5,
                "sampler_name": "uni_pc",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["8", 0],
                "negative": ["8", 1],
                "latent_image": ["8", 2],
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["6", 0]},
        },
        "11": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["10", 0], "fps": COMPARE_FPS, "bit_depth": 8},
        },
        "12": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["11", 0],
                "filename_prefix": WAN14_EXONERATION_PREFIX,
                "format": "auto",
                "codec": "auto",
            },
        },
    }


def make_wan_ti2v_recipe() -> dict[str, Any]:
    prompt = make_wan_ti2v_prompt()
    return {
        "name": WAN_COMPARE_NAME,
        "tier": "comparison",
        "blocked": False,
        "experiment": {
            "campaign": "cross_engine_same_canvas_duration_v1",
            "variant": "wan_ti2v_5b",
            "comparison_controls": [
                "scene_still.png",
                POSITIVE,
                NEGATIVE,
                f"seed={SEED}",
                "832x480",
                "193 frames",
                "25 fps",
                "plain VAEDecode",
            ],
            "grid": "4n+1 (n=48)",
        },
        "contract": _contract("wan_ti2v_5b", "i2v", COMPARE_FRAMES, COMPARE_DURATION_S),
        "receipt_requirements": _receipt_requirements(COMPARE_FRAMES, COMPARE_DURATION_S),
        "topology_contract": _topology_contract(
            prompt,
            intent="Wan 2.2 TI2V-5B same-canvas 193-frame comparison candidate",
            node_source=WAN_NODE_SOURCE,
            node_source_sha256=WAN_NODE_SOURCE_SHA256,
            evidence={
                "otr_commit": OTR_HEAD,
                "engine_source": "nodes/_otr_video_engines/eng_wan_ti2v.py",
                "engine_source_git_blob_sha1": OTR_WAN_TI2V_SOURCE_BLOB,
                "bench_graph": "scripts/bench_graphs/arm_b_partial_wan_ti2v_gguf_unet_st_clip.json",
                "bench_graph_git_blob_sha1": OTR_WAN_BENCH_BLOB,
                "use": "read-only topology and frozen sampling evidence",
            },
            required_absent_inputs=[],
            intentional_divergences=[
                "Lab fixture scene_still.png replaces the OTR bench still",
                "Length moves from the OTR capped bench ladder to the core-node-legal 193-frame 4n+1 rung",
                "CreateVideo uses the native 25 fps conditioning clock for exact 7.72-second delivery",
                "Plain VAEDecode follows the lab production-canvas no-tiling rule",
                "OTR-only VRAM reset/probe nodes are omitted because run_recipe owns telemetry",
            ],
        ),
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }


def make_ltx_2b_recipe() -> dict[str, Any]:
    prompt = make_ltx_2b_prompt()
    return {
        "name": LTX_COMPARE_NAME,
        "tier": "comparison",
        "blocked": False,
        "experiment": {
            "campaign": "cross_engine_same_canvas_duration_v1",
            "variant": "ltx_video_2b_distilled",
            "comparison_controls": [
                "scene_still.png",
                POSITIVE,
                NEGATIVE,
                f"seed={SEED}",
                "832x480",
                "193 frames",
                "25 fps",
                "plain VAEDecode",
            ],
            "grid": "8n+1 (n=24)",
        },
        "contract": _contract(
            "ltx_video_2b_distilled", "i2v", COMPARE_FRAMES, COMPARE_DURATION_S
        ),
        "receipt_requirements": _receipt_requirements(COMPARE_FRAMES, COMPARE_DURATION_S),
        "topology_contract": _topology_contract(
            prompt,
            intent="LTX-Video 0.9.8 distilled 2B same-canvas 193-frame comparison candidate",
            node_source=LTX_NODE_SOURCE,
            node_source_sha256=LTX_NODE_SOURCE_SHA256,
            evidence={
                "otr_commit": OTR_HEAD,
                "engine_source": "nodes/_otr_video_engines/eng_ltx_8gb.py",
                "engine_source_git_blob_sha1": OTR_LTX8_SOURCE_BLOB,
                "bench_graph": "scripts/bench_graphs/arm_d_ltx_8gb.json",
                "bench_graph_git_blob_sha1": OTR_LTX8_BENCH_BLOB,
                "use": "read-only topology and measured v2 sampling evidence",
            },
            required_absent_inputs=["2.latent"],
            intentional_divergences=[
                "Lab fixture scene_still.png replaces the OTR bench still",
                "Canvas moves from the OTR 8GB tier's 512x288 to the requested shared 832x480 comparison canvas",
                "Length moves past the OTR adapter cap to the core-node-legal 193-frame 8n+1 rung",
                "CreateVideo uses the native 25 fps conditioning clock for exact 7.72-second delivery",
                "Plain VAEDecode follows the lab production-canvas no-tiling rule",
                "OTR-only VRAM reset/probe nodes are omitted because run_recipe owns telemetry",
            ],
        ),
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }


def make_wan14_exoneration_recipe() -> dict[str, Any]:
    prompt = make_wan14_prompt()
    contract = _contract(
        "wan_i2v_14b", "i2v", EXONERATION_FRAMES, EXONERATION_DURATION_S
    )
    contract.update(
        {
            "required_boot_lane": (
                "lab-8199, sage-free, no-pinned, clamp-12gb "
                "(reserve computed from physical VRAM)"
            ),
            "target_card_budget_gb": 12.0,
            "requires_disable_pinned_memory": True,
            "clamp_peak_minus_baseline_gb_lte": 12.0,
        }
    )
    receipts = _receipt_requirements(EXONERATION_FRAMES, EXONERATION_DURATION_S)
    receipts["warm_gate"].update(
        {
            "required_lane": "--clamp 12 --disable-pinned-memory",
            "peak_minus_baseline_gb_lte": 12.0,
        }
    )
    return {
        "name": WAN14_EXONERATION_NAME,
        "tier": "exoneration",
        "blocked": False,
        "experiment": {
            "campaign": "wan_i2v_14b_clamp12_exoneration_v1",
            "variant": "short_33f_no_pinned",
            "grid": "4n+1 (n=8)",
            "weights_verified": "models_manifest.md and read-only on-disk check",
        },
        "contract": contract,
        "receipt_requirements": receipts,
        "topology_contract": _topology_contract(
            prompt,
            intent="Wan 2.2 I2V-14B short-rung clamp-12 no-pinned exoneration candidate",
            node_source=WAN_NODE_SOURCE,
            node_source_sha256=WAN_NODE_SOURCE_SHA256,
            evidence={
                "otr_commit": OTR_HEAD,
                "engine_source": "nodes/_otr_video_engines/eng_wan_i2v.py",
                "engine_source_git_blob_sha1": OTR_WAN_I2V_SOURCE_BLOB,
                "use": "read-only frozen single-pass 14B topology and sampling evidence",
            },
            required_absent_inputs=["8.clip_vision_output"],
            intentional_divergences=[
                "Lab fixture scene_still.png supplies the required start image",
                "The exoneration rung is fixed at 33 legal 4n+1 frames",
                "The clamp-12 and no-pinned requirements are execution-lane controls recorded in receipts, not graph nodes",
            ],
        ),
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }


def recipes() -> dict[str, dict[str, Any]]:
    return {
        WAN_COMPARE_NAME: make_wan_ti2v_recipe(),
        LTX_COMPARE_NAME: make_ltx_2b_recipe(),
        WAN14_EXONERATION_NAME: make_wan14_exoneration_recipe(),
    }


def write_immutable_recipes(output_dir: Path = RECIPES_DIR) -> list[Path]:
    """Create canonical UTF-8/LF JSON once; reject any subsequent byte drift."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, recipe in recipes().items():
        path = output_dir / f"{name}.json"
        payload = (json.dumps(recipe, indent=2) + "\n").encode("utf-8")
        if path.exists():
            if path.read_bytes() != payload:
                raise RuntimeError(f"Immutable generated recipe differs: {path}")
            continue
        path.write_bytes(payload)
        written.append(path)
    return written


if __name__ == "__main__":
    for generated in write_immutable_recipes():
        print(generated.relative_to(REPO_ROOT).as_posix())
