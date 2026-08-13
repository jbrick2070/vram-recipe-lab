#!/usr/bin/env python3
"""Build the two immutable HuMo 14B Job-A diet recipes, entirely offline.

The graph is transcribed from the exact OTR source pinned by the production
bakeoff receipt.  The current OTR worktree is read-only and its unrelated HEAD
movement is deliberately not recipe identity: both the historical blob and the
current source file must match the bakeoff SHA-256.

No live port is queried.  Model availability is proved from the lab manifest
and local file metadata; node availability is proved from hash-pinned ComfyUI
source.  Live /object_info and model-enum validation remain run_recipe.py's
authoritative preflight immediately before a render.
"""

from __future__ import annotations

import ast
import copy
import configparser
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OTR_ROOT = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio"
)
COMFY_ROOT = Path(r"C:\Users\jeffr\ComfyUI-Installs\ComfyUI\ComfyUI")
MODEL_ROOT = Path(r"C:\ComfyUI-Models")
MANIFEST_PATH = ROOT / "models_manifest.md"
MANAGER_CONFIG = Path(
    r"C:\Users\jeffr\Documents\ComfyUI\user\__manager\config.ini"
)

PORTRAIT_RECIPE = ROOT / "recipes" / "humo_14b_diet_portrait_480x832_f97.json"
LANDSCAPE_RECIPE = ROOT / "recipes" / "humo_14b_diet_landscape_832x480_f97.json"

# This is the source identity carried by humo_14b_fp8_bakeoff_take1.json.
OTR_BAKEOFF_COMMIT = "15f23044a6f1224a61a39dc38e1e60875a894dd6"
OTR_SOURCE_HASHES = {
    "nodes/_otr_video_engines/eng_humo.py": (
        "77562728f09595082012c91a57ebcd878f7dc9b2f80b17e7b16b77e412b6bd6c"
    ),
    "nodes/_otr_video_engines/render_driver.py": (
        "7d431a5877af678fbb88b0be1c57d98009eb7ffca1290d7ebbae97f44a98b564"
    ),
    "nodes/_otr_shared/aspect.py": (
        "2815d3e6d07f46a6e6e115690fb1319d91f2f1087bfe0c39b8c401ec6da07caf"
    ),
}

COMFY_COMMIT = "fe4195f7f4275f2626cbafc703acc3ddde1e5490"
COMFY_VERSION = "0.31.1"
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

CLASS_SOURCES = {
    "UNETLoader": "nodes.py",
    "LoraLoaderModelOnly": "nodes.py",
    "CLIPLoader": "nodes.py",
    "CLIPTextEncode": "nodes.py",
    "VAELoader": "nodes.py",
    "LoadAudio": "comfy_extras/nodes_audio.py",
    "AudioEncoderLoader": "comfy_extras/nodes_audio_encoder.py",
    "AudioEncoderEncode": "comfy_extras/nodes_audio_encoder.py",
    "LoadImage": "nodes.py",
    "WanHuMoImageToVideo": "comfy_extras/nodes_wan.py",
    "ModelSamplingSD3": "comfy_extras/nodes_model_advanced.py",
    "KSampler": "nodes.py",
    "VAEDecode": "nodes.py",
    "CreateVideo": "comfy_extras/nodes_video.py",
    "SaveVideo": "comfy_extras/nodes_video.py",
}

MANIFEST_SHA256 = "a0124883545b7f693ced351d6e110bc210c46114f2eed32cb3c8846980e4208d"
MODEL_ASSETS = {
    "Wan2_1-HuMo-14B_fp8_e4m3fn_scaled_KJ.safetensors": {
        "folder": "diffusion_models",
        "bytes": 17_892_294_098,
        "loader": "UNETLoader",
    },
    "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors": {
        "folder": "loras",
        "bytes": 738_005_744,
        "loader": "LoraLoaderModelOnly",
    },
    "umt5_xxl_fp8_e4m3fn_scaled.safetensors": {
        "folder": "text_encoders",
        "bytes": 6_735_906_897,
        "loader": "CLIPLoader",
    },
    "wan_2.1_vae.safetensors": {
        "folder": "vae",
        "bytes": 253_815_318,
        "loader": "VAELoader",
    },
    "whisper_large_v3_fp16.safetensors": {
        "folder": "audio_encoders",
        "bytes": 3_087_130_976,
        "loader": "AudioEncoderLoader",
    },
}

FIXTURE_HASHES = {
    "portrait.png": "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad",
    "tts_dialogue.wav": (
        "30c51f3ffa7a422d8cdda6e1ad3fb50b9380c0c5128117d083de9f02e4748ae1"
    ),
}

POSITIVE = "a 1940s radio studio, on air sign illuminated, period broadcast set"
NEGATIVE = (
    "low quality, worst quality, blurry, jpeg artifacts, distorted, deformed, "
    "extra fingers, bad hands, bad face, static, watermark, text"
)

RESERVE_VRAM_GIB = 2.921
DIET_BOOT_ARGS = ["--reserve-vram", "2.921", "--disable-pinned-memory"]


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(raw)


def _git_blob(repo: Path, commit: str, relative: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{commit}:{relative}"]
    )


def _top_level_classes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))
    }


def verify_static_inventory() -> dict[str, Any]:
    """Verify every static prerequisite without booting or querying ComfyUI."""
    for relative, expected_hash in OTR_SOURCE_HASHES.items():
        historical = _git_blob(OTR_ROOT, OTR_BAKEOFF_COMMIT, relative)
        historical_hash = sha256_bytes(historical)
        if historical_hash != expected_hash:
            raise RuntimeError(
                f"OTR bakeoff blob changed for {relative}: expected {expected_hash}, "
                f"found {historical_hash}"
            )
        current = OTR_ROOT / Path(relative)
        if not current.is_file() or sha256_file(current) != expected_hash:
            raise RuntimeError(
                f"Current OTR source no longer matches bakeoff bytes: {relative}"
            )

    comfy_head = subprocess.check_output(
        ["git", "-C", str(COMFY_ROOT), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()
    if comfy_head != COMFY_COMMIT:
        raise RuntimeError(
            f"ComfyUI commit changed: expected {COMFY_COMMIT}, found {comfy_head}"
        )
    classes_by_source: dict[str, set[str]] = {}
    for relative, expected_hash in COMFY_SOURCE_HASHES.items():
        path = COMFY_ROOT / Path(relative)
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise RuntimeError(f"Pinned ComfyUI source changed: {relative}")
        classes_by_source[relative] = _top_level_classes(path)
    for class_name, relative in CLASS_SOURCES.items():
        if class_name not in classes_by_source[relative]:
            raise RuntimeError(
                f"Required class {class_name} is absent from pinned {relative}"
            )

    manifest_hash = sha256_file(MANIFEST_PATH)
    if manifest_hash != MANIFEST_SHA256:
        raise RuntimeError(
            f"models_manifest.md changed: expected {MANIFEST_SHA256}, found {manifest_hash}"
        )
    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    inventory: dict[str, Any] = {}
    for name, metadata in MODEL_ASSETS.items():
        if f"`{name}`" not in manifest:
            raise RuntimeError(f"Required model is absent from models_manifest.md: {name}")
        path = MODEL_ROOT / metadata["folder"] / name
        if not path.is_file():
            raise RuntimeError(f"Manifest-present model is absent on disk: {path}")
        actual_bytes = path.stat().st_size
        if actual_bytes != metadata["bytes"]:
            raise RuntimeError(
                f"Model size changed for {name}: expected {metadata['bytes']}, "
                f"found {actual_bytes}"
            )
        inventory[name] = {
            "manifest_present": True,
            "disk_present": True,
            "model_store": metadata["folder"],
            "filename": name,
            "bytes": actual_bytes,
            "loader": metadata["loader"],
        }

    for name, expected_hash in FIXTURE_HASHES.items():
        path = ROOT / "fixtures" / name
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise RuntimeError(f"Fixture is missing or changed: {name}")

    manager = configparser.ConfigParser()
    if not MANAGER_CONFIG.is_file():
        raise RuntimeError(f"ComfyUI-Manager config is missing: {MANAGER_CONFIG}")
    manager.read(MANAGER_CONFIG, encoding="utf-8")
    network_mode = manager.get("default", "network_mode", fallback="").strip().lower()
    if network_mode != "offline":
        raise RuntimeError(
            f"ComfyUI-Manager network_mode must be offline before boot, found {network_mode!r}"
        )

    return {
        "models_manifest_sha256": manifest_hash,
        "models": inventory,
        "required_classes": sorted(CLASS_SOURCES),
        "class_sources": CLASS_SOURCES,
        "manager_config": str(MANAGER_CONFIG),
        "manager_network_mode": network_mode,
    }


def build_prompt(*, width: int, height: int, filename_prefix: str) -> dict[str, Any]:
    """Concrete API graph specialized from OTR HuMoEngine._build_graph."""
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "Wan2_1-HuMo-14B_fp8_e4m3fn_scaled_KJ.safetensors",
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
            "inputs": {"audio_encoder": ["7", 0], "audio": ["6", 0]},
        },
        "9": {
            "class_type": "LoadImage",
            "inputs": {"image": "portrait.png"},
        },
        "10": {
            "class_type": "WanHuMoImageToVideo",
            "inputs": {
                "width": width,
                "height": height,
                "length": 97,
                "batch_size": 1,
                "positive": ["3", 0],
                "negative": ["4", 0],
                "vae": ["5", 0],
                "audio_encoder_output": ["8", 0],
                "ref_image": ["9", 0],
            },
        },
        "11": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "lora_name": (
                    "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
                ),
                "strength_model": 1.0,
                "model": ["1", 0],
            },
        },
        "12": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"shift": 8.0, "model": ["11", 0]},
        },
        "13": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 7,
                "steps": 6,
                "cfg": 1.0,
                "sampler_name": "uni_pc",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["12", 0],
                "positive": ["10", 0],
                "negative": ["10", 1],
                "latent_image": ["10", 2],
            },
        },
        "14": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["13", 0], "vae": ["5", 0]},
        },
        "15": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["14", 0],
                "fps": 25.0,
                "bit_depth": 8,
                "audio": ["6", 0],
            },
        },
        "16": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["15", 0],
                "filename_prefix": filename_prefix,
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
    "lora": "11",
    "modelsampling": "12",
    "ksampler": "13",
    "vaedecode": "14",
}


def source_graph_projection(prompt: dict[str, Any]) -> dict[str, Any]:
    return {
        source_id: prompt[lab_id]
        for source_id, lab_id in OTR_TO_LAB_NODE_MAP.items()
    }


def required_input_values(prompt: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for node_id, node in prompt.items():
        for input_name, value in node["inputs"].items():
            is_link = (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
            )
            if not is_link:
                values.append({"node": node_id, "input": input_name, "equals": value})
    return values


def required_connections(prompt: dict[str, Any]) -> dict[str, list[Any]]:
    links: dict[str, list[Any]] = {}
    for node_id, node in prompt.items():
        for input_name, value in node["inputs"].items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
            ):
                links[f"{node_id}.{input_name}"] = value
    return links


def _execution_plan(recipe_name: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "cold",
            "recipe": f"recipes/{recipe_name}.json",
            "fresh_server": True,
            "same_server_as_previous": False,
            "executor_cache_nonce": f"job-a-{recipe_name}-cold",
        },
        {
            "role": "warm",
            "recipe": f"recipes/{recipe_name}.json",
            "fresh_server": False,
            "same_server_as_previous": True,
            "executor_cache_nonce": f"job-a-{recipe_name}-warm",
        },
    ]


def build_recipe(*, orientation: str) -> dict[str, Any]:
    if orientation == "portrait":
        name = "humo_14b_diet_portrait_480x832_f97"
        engine_id = "humo"
        width, height = 480, 832
        comparator = "outputs/humo_14b_fp8_bakeoff_take1.mp4"
    elif orientation == "landscape":
        name = "humo_14b_diet_landscape_832x480_f97"
        engine_id = "humo_14B_169"
        width, height = 832, 480
        comparator = None
    else:
        raise ValueError(f"unsupported orientation: {orientation}")

    prompt = build_prompt(
        width=width, height=height, filename_prefix=f"{name}_out"
    )
    projection = source_graph_projection(prompt)
    inventory = {
        model: {
            "manifest_present": True,
            "disk_present": True,
            "model_store": meta["folder"],
            "filename": model,
            "bytes": meta["bytes"],
            "loader": meta["loader"],
        }
        for model, meta in MODEL_ASSETS.items()
    }
    source_pairs = {
        source_id: {
            "lab_node": lab_id,
            "class_type": prompt[lab_id]["class_type"],
            "comparison": "exact class and inputs after symbolic Wire links are concretized",
        }
        for source_id, lab_id in OTR_TO_LAB_NODE_MAP.items()
    }
    return {
        "name": name,
        "tier": "experiment",
        "blocked": False,
        "experiment": {
            "campaign": "envelope_ladders_job_a_v1",
            "job": "A",
            "variant": orientation,
            "conceptual_pair_variable": "render_orientation",
            "graph_pair_difference": [
                "10.width",
                "10.height",
                "16.filename_prefix (delivery identity only)",
            ],
            "generation_graph_change_vs_production": "none",
            "production_comparator_receipt": (
                "results/otr_side/humo_14b_fp8_bakeoff_take1.json"
            ),
            "production_comparator_clip": comparator,
            "render_status": "unrendered",
            "behavioral_claim_status": "unmeasured",
        },
        "contract": {
            "engine_id": engine_id,
            "mode": "audio_driven_face",
            "orientation": orientation,
            "width": width,
            "height": height,
            "frames": 97,
            "fps": 25.0,
            "duration_s": 3.88,
            "seed": 7,
            "requires_audio": True,
            "requires_human_eyeball": True,
            "vram_ceiling_gb": 14.5,
            "warm_runs_required": 2,
            "diet_boot": {
                "semantics": "direct ComfyUI reserve/offload pressure; not clamp target-card emulation",
                "reserve_vram_gib": RESERVE_VRAM_GIB,
                "disable_pinned_memory": True,
                "comfyui_argv_delta": DIET_BOOT_ARGS,
                "runner_environment": {"LAB_RESERVE_VRAM_GB": "2.921"},
                "runner_argument": "--disable-pinned-memory",
                "expected_lane": "lab-8199, sage-free, no-pinned, reserve-2.921gb",
                "manager_network_mode_before_boot": "offline",
                "default_boot_unchanged": True,
            },
            "execution_plan": _execution_plan(name),
            "fresh_server_per_orientation": True,
            "same_server_consecutive_runs": 2,
            "unique_executor_cache_nonce_per_run": True,
            "shutdown_after_warm": True,
        },
        "receipt_requirements": {
            "cold_and_warm": True,
            "warm_definition": "second consecutive run of byte-identical recipe on the same owned server",
            "record": [
                "baseline_vram_gb",
                "peak_vram_gb",
                "peak_host_ram_gb",
                "duration_s",
                "boot_lane",
                "server_argv",
                "cache_evidence",
                "artifact_sha256",
                "fixture_sha256s",
            ],
            "quality_gate": {
                "status": "PENDING_HUMAN",
                "portrait_comparator": "outputs/humo_14b_fp8_bakeoff_take1.mp4",
                "review_audio": "exact fixtures/tts_dialogue.wav from t=0",
            },
        },
        "topology_contract": {
            "schema_version": 1,
            "profile": f"otr_{engine_id}_production_graph_diet_reserve_2p921_v1",
            "intent": (
                "Exact OTR HuMo 14B generation graph plus lab-only exact-source-audio review delivery"
            ),
            "origin": {
                "builder": "scratch/build_humo_14b_diet.py",
                "seed_rule": (
                    "OTR HuMoEngine._build_graph specialized with render_driver single_0000 request seed 7"
                ),
                "third_party_workflow_json_copied": False,
                "custom_node_pack_required": False,
            },
            "source_graph_evidence": {
                "otr_bakeoff_commit": OTR_BAKEOFF_COMMIT,
                "identity_policy": (
                    "Pinned bakeoff blobs and current source bytes must match; unrelated OTR HEAD movement is excluded"
                ),
                "engine_source": "nodes/_otr_video_engines/eng_humo.py",
                "engine_source_sha256": OTR_SOURCE_HASHES[
                    "nodes/_otr_video_engines/eng_humo.py"
                ],
                "request_source": "nodes/_otr_video_engines/render_driver.py",
                "request_source_sha256": OTR_SOURCE_HASHES[
                    "nodes/_otr_video_engines/render_driver.py"
                ],
                "dimension_source": "nodes/_otr_shared/aspect.py",
                "dimension_source_sha256": OTR_SOURCE_HASHES[
                    "nodes/_otr_shared/aspect.py"
                ],
                "source_method": "HuMoEngine._build_graph",
                "source_specialization": engine_id,
                "source_to_lab_node_pairs": source_pairs,
                "source_graph_projection_sha256": canonical_sha256(projection),
                "source_graph_node_count": len(projection),
                "lora": {
                    "source_value": (
                        "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
                    ),
                    "node_present": True,
                    "strength_model": 1.0,
                },
                "lab_only_delivery_nodes": {
                    "15": "CreateVideo",
                    "16": "SaveVideo",
                },
            },
            "installed_schema": {
                "verification_mode": "offline static; live runner preflight remains authoritative",
                "comfyui_version": COMFY_VERSION,
                "git_commit": COMFY_COMMIT,
                "node_sources_sha256": COMFY_SOURCE_HASHES,
                "class_sources": CLASS_SOURCES,
                "models_manifest_sha256": MANIFEST_SHA256,
                "model_inventory": inventory,
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
                "VAEDecodeTiled",
                "WanImageToVideo",
                "EmptyLatentImage",
            ],
            "audio_path_contract": {
                "conditioning": (
                    "6.LoadAudio -> 8.AudioEncoderEncode.audio; 7.AudioEncoderLoader -> "
                    "8.audio_encoder -> 10.WanHuMoImageToVideo.audio_encoder_output"
                ),
                "delivery": "6.LoadAudio -> 15.CreateVideo.audio",
                "same_source_node_for_conditioning_and_delivery": True,
                "production_native_output": "silent by OTR policy",
                "lab_review_output": "exact source TTS delivered from t=0",
                "delivery_tail_changes_generation": False,
            },
            "terminal_node": "16",
            "require_all_nodes_reachable": True,
            "intentional_divergences": [
                "Lab fixture basenames replace hash-identical OTR staging filenames",
                "CreateVideo and SaveVideo are appended after the exact OTR generation graph",
                "Source TTS is delivered on the lab review artifact; OTR native clips remain silent",
                "Reserve and no-pinned settings are boot controls, never graph nodes",
            ],
        },
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }


def serialized_recipe(recipe: dict[str, Any]) -> bytes:
    return (json.dumps(recipe, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_all() -> dict[Path, bytes]:
    return {
        PORTRAIT_RECIPE: serialized_recipe(build_recipe(orientation="portrait")),
        LANDSCAPE_RECIPE: serialized_recipe(build_recipe(orientation="landscape")),
    }


def normalized_pair_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
    """Normalize the declared orientation and delivery identity for pair comparison."""
    value = copy.deepcopy(prompt)
    value["10"]["inputs"]["width"] = "<orientation-width>"
    value["10"]["inputs"]["height"] = "<orientation-height>"
    value["16"]["inputs"]["filename_prefix"] = "<delivery-prefix>"
    return value


def main() -> int:
    inventory = verify_static_inventory()
    print(
        "static_inventory_sha256="
        + canonical_sha256(inventory)
    )
    for path, raw in build_all().items():
        path.write_bytes(raw)
        print(f"wrote {path}")
        print(f"recipe_sha256={sha256_bytes(raw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
