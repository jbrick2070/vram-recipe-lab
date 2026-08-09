#!/usr/bin/env python3
"""Generate canonical MiniMax H3 lanes, Mini Mime variants, and the AV suite sentinel."""

import json
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
RECIPES_DIR = REPO_ROOT / "recipes"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from duration_match import duration_match

FROZEN_TEMPLATE_PROVENANCE = {
    "t2v": {
        "path": "research/comfy_templates/video_minimax_h3_t2v.json",
        "sha256": "31ab33fdb053a7834cc866bd7aa08b887518fc656e4a796c89779c6b5e1786e6",
    },
    "i2v": {
        "path": "research/comfy_templates/video_minimax_h3_i2v.json",
        "sha256": "bb71aecdd3c0b62e56eafe03acb14d1cfeabec7072eaed9cbdf473c2aaf73009",
    },
    "r2v": {
        "path": "research/comfy_templates/video_minimax_h3_r2v.json",
        "sha256": "099d24eda6263854818975c7209db6f29ebfd0339936c928f12293d5ab029ffb",
    },
}

COMFYUI_SCHEMA_VERSION = "0.31.1"
COMFYUI_SCHEMA_COMMIT = "fe4195f7f4275f2626cbafc703acc3ddde1e5490"
H3_NODE_SOURCE = "comfy_extras/nodes_minimax_h3.py"
H3_NODE_SOURCE_SHA256 = (
    "f767df4074b908efb345f5a87c2fd263ba82c12e65bcca932846207cc213e064"
)
SCENE_STILL_SHA256 = (
    "0476dbc87358d367d244c65e976f8013f9659aeb80f7a1c45b368cc1728a5596"
)
PORTRAIT_SHA256 = (
    "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
)
H3_R2V_LOW_BASE_SHA256 = (
    "3221fdbbdbaae4747584663849de0c8fa8a3d81eaca6980f06de4b5aedc48d93"
)
H3_I2V_SUITE_SENTINEL_NAME = "h3_i2v_suite_sentinel"
H3_I2V_SUITE_SENTINEL_PREFIX = "h3_i2v_suite_sentinel_out"
H3_MIME_R2V_NAME = "h3_mime_r2v"
H3_MIME_R2V_PREFIX = "h3_mime_r2v_out"
H3_DEFAULT_PROMPT = (
    "cinematic camera motion across vintage radio control room, warm analog glow, 8k"
)

MIME_PROMPT = (
    "A restrained cinematic moment inside the vintage radio control room from the "
    "first frame: warm analog console glow, subtle equipment motion, a slow stable "
    "camera drift, and physically coherent environmental movement. Generate ambient "
    "room tone and synchronized diegetic sound effects only: low electrical hum, "
    "quiet relay clicks, soft ventilation, and an occasional distant static crackle. "
    "No dialogue, no intelligible speech, no voices, no vocals, no humming, and no music."
)

MIME_R2V_PROMPT = (
    "<Picture 1> is the sole character identity and appearance reference. Preserve the "
    "person's recognizable face, hair, clothing, and body proportions. The person from "
    "<Picture 1> is alone in a vintage radio control room under warm analog lighting "
    "while the camera makes one slow, stable cinematic move and all motion remains "
    "physically coherent. Generate a coherent diegetic soundscape synchronized with the "
    "visual action: low electrical hum, quiet relay clicks, soft ventilation, and an "
    "occasional distant static crackle. No dialogue, no intelligible speech, no voices, "
    "no vocals, no humming, and no music."
)


def write_recipe_if_changed(path: Path, recipe_data: dict) -> bool:
    """Write canonical UTF-8/LF JSON unless the existing graph is semantically identical."""
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            existing = None
        if existing == recipe_data:
            return False

    payload = (json.dumps(recipe_data, indent=2) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return True


def write_immutable_recipe(path: Path, recipe_data: dict) -> bool:
    """Create a canonical recipe once and reject any later byte drift."""
    payload = (json.dumps(recipe_data, indent=2) + "\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"Immutable generated recipe differs: {path}")
        return False
    path.write_bytes(payload)
    return True

def make_h3_prompt(mode: str, width: int, height: int, frames: int, is_best: bool = False):
    """
    Construct API prompt format dictionary for MiniMax H3.
    """
    # 1. UNETLoader
    unet_name = (
        "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
        if mode == "r2v"
        else "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    )
    # 2. CLIPLoader
    clip_name = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
    # 3. Video VAE
    video_vae_name = "minimax_h3_video_vae_fp16.safetensors"
    # 4. Audio VAE
    audio_vae_name = "minimax_h3_audio_vae_fp32.safetensors"

    prompt_nodes = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": unet_name,
                "weight_dtype": "default"
            }
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": clip_name,
                "type": "minimax",
                **({"device": "default"} if is_best else {}),
            }
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": video_vae_name
            }
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": audio_vae_name
            }
        }
    }

    use_official_sampler = mode != "t2v" or is_best
    include_native_audio = mode == "r2v" or is_best

    if not use_official_sampler:
        # Keep the already-approved low T2V legacy-control lane unchanged.
        prompt_nodes["5"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "cinematic camera motion across vintage radio control room, warm analog glow, 8k",
                "clip": ["2", 0]
            }
        }
        prompt_nodes["6"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "blurry, noise, artifacts, distorted, static, oversaturated",
                "clip": ["2", 0]
            }
        }
    else:
        # Frozen official H3 templates use explicit noise, basic guidance,
        # res_multistep sampling, and a model-derived simple schedule.
        prompt_nodes["5"] = {
            "class_type": "RandomNoise",
            "inputs": {
                "noise_seed": 42
            }
        }
        prompt_nodes["6"] = {
            "class_type": "BasicGuider",
            "inputs": {
                "model": ["1", 0],
                "conditioning": ["7", 0]
            }
        }

    if mode in ["t2v", "i2v"]:
        # Use MiniMaxH3ImageToVideo
        cond_inputs = {
            "clip": ["2", 0],
            "vae": ["3", 0],
                "prompt": H3_DEFAULT_PROMPT,
            "width": width,
            "height": height,
            "length": frames
        }
        if mode == "i2v":
            cond_inputs["first_frame"] = ["11", 0]
            prompt_nodes["11"] = {
                "class_type": "LoadImage",
                "inputs": {
                    "image": "scene_still.png"
                }
            }

        prompt_nodes["7"] = {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": cond_inputs
        }
    elif mode == "r2v":
        # Use MiniMaxH3ReferenceToVideo
        prompt_nodes["11"] = {
            "class_type": "LoadImage",
            "inputs": {
                "image": "portrait.png"
            }
        }
        prompt_nodes["7"] = {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "audio_vae": ["4", 0],
                "prompt": (
                    "Use <Picture 1> as the exact character identity and appearance reference. "
                    "Place that person in a vintage radio control room under warm analog lighting; "
                    "preserve their face, hair, clothing, and proportions while the camera makes a "
                    "slow cinematic move."
                ),
                "width": width,
                "height": height,
                "length": frames,
                "ref_image_size": "match",
                "ref_images.ref_image_0": ["11", 0]
            }
        }

    if not use_official_sampler:
        prompt_nodes["8"] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 6.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["7", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 1]
            }
        }
    else:
        prompt_nodes["8"] = {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["5", 0],
                "guider": ["6", 0],
                "sampler": ["13", 0],
                "sigmas": ["14", 0],
                "latent_image": ["7", 1]
            }
        }
        prompt_nodes["13"] = {
            "class_type": "KSamplerSelect",
            "inputs": {
                "sampler_name": "res_multistep"
            }
        }
        prompt_nodes["14"] = {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["1", 0],
                "scheduler": "simple",
                "steps": 20,
                "denoise": 1.0
            }
        }

    # VAEDecode (Video)
    prompt_nodes["9"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["8", 0],
            "vae": ["3", 0]
        }
    }

    if include_native_audio:
        prompt_nodes["15"] = {
            "class_type": "VAEDecodeAudio",
            "inputs": {
                "samples": ["8", 0],
                "vae": ["4", 0]
            }
        }

    # CreateVideo & SaveVideo
    create_video_inputs = {
        "images": ["9", 0],
        "fps": 24.0,
        **({"bit_depth": 8} if is_best else {}),
    }
    if include_native_audio:
        create_video_inputs["audio"] = ["15", 0]

    prompt_nodes["10"] = {
        "class_type": "CreateVideo",
        "inputs": create_video_inputs
    }

    recipe_name = f"h3_{mode}_{'low' if width == 864 else 'best'}"
    filename_prefix = (
        "h3_i2v_low_official_sampler_out"
        if recipe_name == "h3_i2v_low"
        else f"{recipe_name}_out"
    )
    prompt_nodes["12"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["10", 0],
            "filename_prefix": filename_prefix,
            "format": "auto",
            "codec": "auto"
        }
    }

    return prompt_nodes


def make_topology_contract(mode: str) -> dict:
    """Describe the frozen official H3 best-lane DAG in machine-checkable form."""
    conditioning_class = (
        "MiniMaxH3ReferenceToVideo" if mode == "r2v" else "MiniMaxH3ImageToVideo"
    )
    required_nodes = {
        "1": "UNETLoader",
        "2": "CLIPLoader",
        "3": "VAELoader",
        "4": "VAELoader",
        "5": "RandomNoise",
        "6": "BasicGuider",
        "7": conditioning_class,
        "8": "SamplerCustomAdvanced",
        "9": "VAEDecode",
        "10": "CreateVideo",
        "12": "SaveVideo",
        "13": "KSamplerSelect",
        "14": "BasicScheduler",
        "15": "VAEDecodeAudio",
    }
    if mode in {"i2v", "r2v"}:
        required_nodes["11"] = "LoadImage"

    required_connections = {
        "6.model": ["1", 0],
        "14.model": ["1", 0],
        "7.clip": ["2", 0],
        "7.vae": ["3", 0],
        "6.conditioning": ["7", 0],
        "8.noise": ["5", 0],
        "8.guider": ["6", 0],
        "8.sampler": ["13", 0],
        "8.sigmas": ["14", 0],
        "8.latent_image": ["7", 1],
        "9.samples": ["8", 0],
        "9.vae": ["3", 0],
        "15.samples": ["8", 0],
        "15.vae": ["4", 0],
        "10.images": ["9", 0],
        "10.audio": ["15", 0],
        "12.video": ["10", 0],
    }
    if mode == "i2v":
        required_connections["7.first_frame"] = ["11", 0]
    elif mode == "r2v":
        required_connections["7.audio_vae"] = ["4", 0]
        required_connections["7.ref_images.ref_image_0"] = ["11", 0]

    mode_divergences = {
        "t2v": [
            "first_frame and last_frame are intentionally absent for text-only generation",
        ],
        "i2v": [
            "scene_still.png replaces the template example image and is connected only as first_frame",
            "last_frame is intentionally absent",
        ],
        "r2v": [
            "portrait.png is the sole reference image and the prompt assigns it exactly as <Picture 1>",
            "optional reference videos and reference audios are intentionally absent",
        ],
    }
    required_absent_inputs = {
        "t2v": ["7.first_frame", "7.last_frame"],
        "i2v": ["7.last_frame"],
        "r2v": [
            "7.ref_images",
            "7.ref_videos",
            "7.ref_video_audios",
            "7.ref_audios",
            *(f"7.ref_images.ref_image_{index}" for index in range(1, 9)),
            *(f"7.ref_videos.ref_video_{index}" for index in range(3)),
            *(
                f"7.ref_video_audios.ref_video_audio_{index}"
                for index in range(3)
            ),
            *(f"7.ref_audios.ref_audio_{index}" for index in range(3)),
        ],
    }

    return {
        "schema_version": 1,
        "intent": "Frozen official MiniMax H3 sampler and native joint video/audio output topology",
        "frozen_template": FROZEN_TEMPLATE_PROVENANCE[mode],
        "installed_schema": {
            "comfyui_version": COMFYUI_SCHEMA_VERSION,
            "git_commit": COMFYUI_SCHEMA_COMMIT,
        },
        "exact_node_set": True,
        "required_nodes": required_nodes,
        "required_class_types": list(dict.fromkeys(required_nodes.values())),
        "required_connections": required_connections,
        "required_absent_inputs": required_absent_inputs[mode],
        "required_input_values": [
            {"node": "2", "input": "device", "equals": "default"},
            {"node": "13", "input": "sampler_name", "equals": "res_multistep"},
            {"node": "14", "input": "scheduler", "equals": "simple"},
            {"node": "14", "input": "steps", "equals": 20},
            {"node": "14", "input": "denoise", "equals": 1.0},
            {"node": "10", "input": "fps", "equals": 24.0},
            {"node": "10", "input": "bit_depth", "equals": 8},
        ],
        "forbidden_class_types": ["KSampler", "CLIPTextEncode"],
        "terminal_node": "12",
        "require_all_nodes_reachable": True,
        "intentional_divergences": [
            "The template subgraph is flattened to native API prompt nodes; UI-only notes, selectors, and duration helpers are omitted",
            "The OTR prompt and deterministic seed 42 replace template demonstration content and randomized seeds",
            "The best lane fixes the canvas at 1344x768 and length at 124 frames",
            "The output filename prefix is lab-local",
            *mode_divergences[mode],
        ],
    }


def make_mime_topology_contract() -> dict:
    """Pin Mini Mime to the certified low I2V graph plus native audio decode."""
    topology = make_topology_contract("i2v")
    topology["intent"] = (
        "Certified low MiniMax H3 I2V sampler topology with the model-native joint "
        "audio latent decoded and delivered directly"
    )
    topology["required_input_values"] = [
        assertion
        for assertion in topology["required_input_values"]
        if (assertion["node"], assertion["input"]) != ("10", "bit_depth")
    ]
    topology["required_input_values"].extend(
        [
            {"node": "7", "input": "prompt", "equals": MIME_PROMPT},
            {"node": "7", "input": "length", "equals": 90},
            {"node": "11", "input": "image", "equals": "scene_still.png"},
        ]
    )
    topology["forbidden_class_types"] = [
        *topology["forbidden_class_types"],
        "LoadAudio",
        "AudioAdjustVolume",
        "TrimAudioDuration",
    ]
    topology["intentional_divergences"] = [
        "The template subgraph is flattened to native API prompt nodes",
        "The certified low I2V 864x480 canvas and deterministic seed 42 are retained",
        "Length is the 90-frame H3 grid point for the 3.750-second lab beat",
        "scene_still.png is connected only as first_frame; last_frame is absent",
        "The generated joint-audio latent is decoded by VAEDecodeAudio and connected directly to CreateVideo.audio",
        "No external audio loader, conditioning track, replacement mux, dialogue, vocals, or music is permitted",
    ]
    return topology


def make_mime_r2v_topology_contract() -> dict:
    """Pin portrait-only Mini Mime to the corrected low Ref2VA graph."""
    topology = make_topology_contract("r2v")
    topology["profile"] = "minimax_h3_mime_r2v_portrait_only_v1"
    topology["intent"] = (
        "Corrected current low MiniMax H3 Ref2VA topology with one flat-V3 portrait "
        "reference and model-native joint audio decoded and delivered directly"
    )
    topology["origin"] = {
        "builder": "scratch/build_clean_h3_recipes.py",
        "base_recipe": "recipes/h3_r2v_low.json",
        "base_recipe_sha256": H3_R2V_LOW_BASE_SHA256,
        "original_implementation": True,
    }
    topology["installed_schema"] = {
        "comfyui_version": COMFYUI_SCHEMA_VERSION,
        "git_commit": COMFYUI_SCHEMA_COMMIT,
        "node_source": H3_NODE_SOURCE,
        "node_source_sha256": H3_NODE_SOURCE_SHA256,
    }
    topology["fixture_hashes"] = {"portrait.png": PORTRAIT_SHA256}
    topology["required_input_values"] = [
        assertion
        for assertion in topology["required_input_values"]
        if (assertion["node"], assertion["input"])
        not in {("2", "device"), ("10", "bit_depth")}
    ]
    topology["required_input_values"].extend(
        [
            {
                "node": "1",
                "input": "unet_name",
                "equals": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
            },
            {"node": "1", "input": "weight_dtype", "equals": "default"},
            {
                "node": "2",
                "input": "clip_name",
                "equals": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            },
            {"node": "2", "input": "type", "equals": "minimax"},
            {
                "node": "3",
                "input": "vae_name",
                "equals": "minimax_h3_video_vae_fp16.safetensors",
            },
            {
                "node": "4",
                "input": "vae_name",
                "equals": "minimax_h3_audio_vae_fp32.safetensors",
            },
            {"node": "5", "input": "noise_seed", "equals": 42},
            {"node": "7", "input": "prompt", "equals": MIME_R2V_PROMPT},
            {"node": "7", "input": "width", "equals": 864},
            {"node": "7", "input": "height", "equals": 480},
            {"node": "7", "input": "length", "equals": 90},
            {"node": "7", "input": "ref_image_size", "equals": "match"},
            {"node": "11", "input": "image", "equals": "portrait.png"},
            {
                "node": "12",
                "input": "filename_prefix",
                "equals": H3_MIME_R2V_PREFIX,
            },
            {"node": "12", "input": "format", "equals": "auto"},
            {"node": "12", "input": "codec", "equals": "auto"},
        ]
    )
    topology["required_absent_inputs"] = [
        *topology["required_absent_inputs"],
        "7.first_frame",
        "7.last_frame",
        "2.device",
        "10.bit_depth",
    ]
    topology["forbidden_class_types"] = [
        *topology["forbidden_class_types"],
        "LoadAudio",
        "AudioAdjustVolume",
        "TrimAudioDuration",
        "VHS_LoadAudio",
        "H3ReferenceAudio",
        "MiniMaxH3NativeAudioLock",
        "VRGDG_MiniMaxH3AudioDrive",
    ]
    topology["audio_path_contract"] = {
        "sampled_target": "7.LATENT -> 8.SamplerCustomAdvanced -> 15.VAEDecodeAudio",
        "delivery": "15.AUDIO -> 10.CreateVideo.audio",
        "create_video_audio_required": ["15", 0],
        "external_audio_conditioning": False,
        "external_source_mux": False,
    }
    topology["intentional_divergences"] = [
        "The current official R2V template subgraph is flattened to native API prompt nodes; UI-only notes and helpers are omitted",
        "The corrected low Ref2VA 864x480 canvas and deterministic seed 42 are retained",
        "Length is the 90-frame H3 grid point for the 3.750-second Mini Mime beat",
        "portrait.png is hash-pinned as the sole visual reference and connects only through flat socket ref_images.ref_image_0",
        "All optional reference images, videos, paired video audio, and reference audio sockets are absent",
        "The sampled target latent feeds both VAEDecode and VAEDecodeAudio, and only decoded target audio feeds CreateVideo.audio",
        "No external audio loader, conditioning track, replacement mux, dialogue, speech, voices, vocals, humming, or music is permitted",
        "The output filename prefix is unique to the portrait-only R2V Mini Mime experiment",
    ]
    return topology


def make_h3_i2v_suite_sentinel_topology_contract() -> dict:
    """Pin the current official 864x480 I2V graph through native AV delivery."""
    topology = make_topology_contract("i2v")
    topology["intent"] = (
        "Current-official MiniMax H3 FL2VA I2V suite sentinel with the sampled joint "
        "video/audio latent decoded and delivered through the native AV output path"
    )
    topology["installed_schema"] = {
        "comfyui_version": COMFYUI_SCHEMA_VERSION,
        "git_commit": COMFYUI_SCHEMA_COMMIT,
        "node_source": H3_NODE_SOURCE,
        "node_source_sha256": H3_NODE_SOURCE_SHA256,
    }
    topology["fixture_hashes"] = {"scene_still.png": SCENE_STILL_SHA256}
    topology["required_input_values"].extend(
        [
            {
                "node": "1",
                "input": "unet_name",
                "equals": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            },
            {"node": "1", "input": "weight_dtype", "equals": "default"},
            {
                "node": "2",
                "input": "clip_name",
                "equals": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            },
            {"node": "2", "input": "type", "equals": "minimax"},
            {
                "node": "3",
                "input": "vae_name",
                "equals": "minimax_h3_video_vae_fp16.safetensors",
            },
            {
                "node": "4",
                "input": "vae_name",
                "equals": "minimax_h3_audio_vae_fp32.safetensors",
            },
            {"node": "5", "input": "noise_seed", "equals": 42},
            {"node": "7", "input": "prompt", "equals": H3_DEFAULT_PROMPT},
            {"node": "7", "input": "width", "equals": 864},
            {"node": "7", "input": "height", "equals": 480},
            {"node": "7", "input": "length", "equals": 124},
            {"node": "11", "input": "image", "equals": "scene_still.png"},
            {
                "node": "12",
                "input": "filename_prefix",
                "equals": H3_I2V_SUITE_SENTINEL_PREFIX,
            },
            {"node": "12", "input": "format", "equals": "auto"},
            {"node": "12", "input": "codec", "equals": "auto"},
        ]
    )
    topology["forbidden_class_types"] = [
        *topology["forbidden_class_types"],
        "MiniMaxH3SigmaShift",
        "LoadAudio",
    ]
    topology["intentional_divergences"] = [
        "The current official I2V template subgraph is flattened to native API prompt nodes; UI-only notes and helpers are omitted",
        "The official 16:9, 0.4-megapixel, multiple-of-32 selector result is pinned at 864x480",
        "The official five-second duration-helper result is pinned at 124 H3 frames",
        "The randomized template seed is pinned at 42 so the cache nonce remains execution-only",
        "scene_still.png is hash-pinned and connected only as first_frame; last_frame is absent",
        "The sampled target latent feeds both VAEDecode and VAEDecodeAudio, and only decoded target audio feeds CreateVideo.audio",
        "No optional MiniMaxH3SigmaShift override is inserted; current ModelSamplingAV defaults remain model-native",
        "The output filename prefix is unique to the AV-complete suite sentinel",
    ]
    return topology


def make_h3_i2v_suite_sentinel_recipe() -> dict:
    """Build the immutable current-official 864x480/124 AV suite sentinel."""
    prompt = make_h3_prompt("i2v", 864, 480, 124, is_best=True)
    prompt["12"]["inputs"]["filename_prefix"] = H3_I2V_SUITE_SENTINEL_PREFIX
    return {
        "name": H3_I2V_SUITE_SENTINEL_NAME,
        "tier": "suite",
        "blocked": False,
        "experiment": {
            "campaign": "h3_best_suite",
            "variant": "i2v_av_complete_sentinel",
            "measurement_role": "warmup and between-pair VRAM-creep sentinel",
            "scope": "suite measurement control; not an independent quality promotion lane",
        },
        "contract": {
            "engine": "minimax_h3",
            "mode": "i2v",
            "width": 864,
            "height": 480,
            "frames": 124,
            "fps": 24.0,
            "duration_s": round(124 / 24.0, 2),
            "requires_audio": True,
            "required_boot_lane": "lab-8199, sage-free",
            "vram_ceiling_gb": 14.5,
        },
        "topology_contract": make_h3_i2v_suite_sentinel_topology_contract(),
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }


def write_h3_i2v_suite_sentinel(output_dir: Path = RECIPES_DIR) -> bool:
    """Write the sentinel once, accepting only byte-identical repeat builds."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return write_immutable_recipe(
        output_dir / f"{H3_I2V_SUITE_SENTINEL_NAME}.json",
        make_h3_i2v_suite_sentinel_recipe(),
    )


def make_h3_mime_i2v_recipe() -> dict:
    """Build the immutable 3.750-second Mini Mime lab proof recipe."""
    timing = duration_match(Decimal("3.750"), "h3")
    if timing["frame_count"] != 90 or timing["trim_frames"] != 0:
        raise AssertionError("Mini Mime default timing must be 90 untrimmed H3 frames")

    # This starts with the certified low I2V graph.  Native audio decode is the
    # only structural addition; it is required because generated audio is the
    # payload in this experiment rather than a diagnostic or replaced mux.
    prompt = make_h3_prompt("i2v", 864, 480, timing["frame_count"], is_best=False)
    prompt["2"]["inputs"]["device"] = "default"
    prompt["7"]["inputs"]["prompt"] = MIME_PROMPT
    prompt["15"] = {
        "class_type": "VAEDecodeAudio",
        "inputs": {
            "samples": ["8", 0],
            "vae": ["4", 0],
        },
    }
    prompt["10"]["inputs"]["audio"] = ["15", 0]
    prompt["12"]["inputs"]["filename_prefix"] = "h3_mime_i2v_out"

    one_frame_s = 1 / 24
    return {
        "name": "h3_mime_i2v",
        "tier": "experiment",
        "blocked": False,
        "experiment": {
            "campaign": "mini_mime",
            "variant": "i2v_scene_still_native_audio",
            "scope": "lab-scale proof only",
            "otr_integration": "explicitly deferred",
            "timing_plan": {
                "planner": "duration_match.duration_match",
                "mode": "h3_17k_plus_5_at_24fps",
                "ledger": "fixtures/ledger.json",
                "target_source": "documented OTR default beat requested for this lab proof",
                "ledger_caveat": (
                    "The frozen ledger has total_beats=0 and no explicit 3.750-second row; "
                    "its concrete timed line/music slots are covered by unit tests"
                ),
                "target_decimal": "3.750",
                "target_s": float(timing["target_seconds"]),
                "frame_count": timing["frame_count"],
                "trim_frames": timing["trim_frames"],
                "rendered_s": float(timing["rendered_s"]),
                "delivered_s": float(timing["delivered_s"]),
                "tail_trim_s": float(timing["tail_trim_s"]),
            },
            "soundtrack_policy": {
                "source": "MiniMax H3 jointly generated audio only",
                "external_mux": False,
                "allowed": "ambient/environmental room tone and synchronized diegetic SFX",
                "forbidden": [
                    "dialogue",
                    "intelligible speech",
                    "voices",
                    "vocals",
                    "humming",
                    "music",
                ],
            },
            "human_gate": {
                "status": "pending",
                "kind": "inverted ear gate",
                "pass_requires": [
                    "no intelligible speech-like or vocal-like content",
                    "coherent diegetic synchronization",
                    "one-line human soundscape description in the receipt",
                ],
            },
        },
        "contract": {
            "engine": "minimax_h3",
            "mode": "i2v_mime",
            "width": 864,
            "height": 480,
            "frames": timing["frame_count"],
            "fps": 24.0,
            "duration_s": float(timing["rendered_s"]),
            "target_s": float(timing["target_seconds"]),
            "trim_frames": timing["trim_frames"],
            "delivered_s": float(timing["delivered_s"]),
            "requires_audio": True,
            "vram_ceiling_gb": 14.5,
        },
        "receipt_requirements": {
            "schema_version": 1,
            "timing": {
                "required_fields": [
                    "target_s",
                    "frame_count",
                    "trim_frames",
                    "rendered_s",
                    "delivered_s",
                    "duration_error_s",
                    "duration_tolerance_s",
                ],
                "target_s": float(timing["target_seconds"]),
                "ffprobe_required": True,
                "absolute_duration_error_lte_s": one_frame_s,
                "note": (
                    "The plan retains the exact Decimal target; the encoded artifact "
                    "passes when ffprobe absolute error is no more than one 24-fps frame"
                ),
            },
            "inverted_ear_gate": {
                "status": "pending_human",
                "required_fields": [
                    "audio_ear",
                    "audio_ear_source",
                    "audio_ear_reviewed_at",
                    "soundscape_description",
                    "speech_or_vocal_like_content",
                    "diegetic_sync",
                ],
                "pass_values": {
                    "audio_ear": "ok",
                    "audio_ear_source": "human",
                    "speech_or_vocal_like_content": "none_intelligible",
                    "diegetic_sync": "coherent",
                },
            },
        },
        "topology_contract": make_mime_topology_contract(),
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }


def make_h3_mime_r2v_recipe() -> dict:
    """Build the immutable portrait-only 3.750-second R2V Mini Mime recipe."""
    timing = duration_match(Decimal("3.750"), "h3")
    if timing["frame_count"] != 90 or timing["trim_frames"] != 0:
        raise AssertionError("R2V Mini Mime timing must be 90 untrimmed H3 frames")

    # Start from the corrected current low Ref2VA graph. The prompt, H3-grid
    # length, and unique output prefix are the only prompt-graph differences.
    prompt = make_h3_prompt("r2v", 864, 480, timing["frame_count"], is_best=False)
    prompt["7"]["inputs"]["prompt"] = MIME_R2V_PROMPT
    prompt["12"]["inputs"]["filename_prefix"] = H3_MIME_R2V_PREFIX

    one_frame_s = 1 / 24
    return {
        "name": H3_MIME_R2V_NAME,
        "tier": "experiment",
        "blocked": False,
        "experiment": {
            "campaign": "mini_mime",
            "variant": "r2v_portrait_only_native_audio",
            "scope": "lab-scale proof only",
            "otr_integration": "explicitly deferred",
            "reference_policy": {
                "source": "portrait.png",
                "socket": "ref_images.ref_image_0",
                "prompt_tag": "<Picture 1>",
                "visual_reference_count": 1,
                "external_audio_conditioning": False,
            },
            "timing_plan": {
                "planner": "duration_match.duration_match",
                "mode": "h3_17k_plus_5_at_24fps",
                "ledger": "fixtures/ledger.json",
                "target_source": "documented OTR default beat requested for this lab proof",
                "ledger_caveat": (
                    "The frozen ledger has total_beats=0 and no explicit 3.750-second row; "
                    "its concrete timed line/music slots are covered by unit tests"
                ),
                "target_decimal": "3.750",
                "target_s": float(timing["target_seconds"]),
                "frame_count": timing["frame_count"],
                "trim_frames": timing["trim_frames"],
                "rendered_s": float(timing["rendered_s"]),
                "delivered_s": float(timing["delivered_s"]),
                "tail_trim_s": float(timing["tail_trim_s"]),
            },
            "soundtrack_policy": {
                "source": "MiniMax H3 jointly generated audio only",
                "external_mux": False,
                "allowed": "coherent ambient/environmental room tone and synchronized diegetic SFX",
                "forbidden": [
                    "dialogue",
                    "intelligible speech",
                    "voices",
                    "vocals",
                    "humming",
                    "music",
                ],
            },
            "human_gate": {
                "status": "pending",
                "kind": "inverted ear gate",
                "pass_requires": [
                    "no intelligible speech-like or vocal-like content",
                    "coherent diegetic synchronization",
                    "one-line human soundscape description in the receipt",
                ],
            },
        },
        "contract": {
            "engine": "minimax_h3",
            "mode": "r2v_mime",
            "width": 864,
            "height": 480,
            "frames": timing["frame_count"],
            "fps": 24.0,
            "duration_s": float(timing["rendered_s"]),
            "target_s": float(timing["target_seconds"]),
            "trim_frames": timing["trim_frames"],
            "delivered_s": float(timing["delivered_s"]),
            "requires_audio": True,
            "required_boot_lane": "lab-8199, sage-free",
            "vram_ceiling_gb": 14.5,
        },
        "receipt_requirements": {
            "schema_version": 1,
            "timing": {
                "required_fields": [
                    "target_s",
                    "frame_count",
                    "trim_frames",
                    "rendered_s",
                    "delivered_s",
                    "duration_error_s",
                    "duration_tolerance_s",
                ],
                "target_s": float(timing["target_seconds"]),
                "ffprobe_required": True,
                "absolute_duration_error_lte_s": one_frame_s,
                "note": (
                    "The plan retains the exact Decimal target; the encoded artifact "
                    "passes when ffprobe absolute error is no more than one 24-fps frame"
                ),
            },
            "inverted_ear_gate": {
                "status": "pending_human",
                "required_fields": [
                    "audio_ear",
                    "audio_ear_source",
                    "audio_ear_reviewed_at",
                    "soundscape_description",
                    "speech_or_vocal_like_content",
                    "diegetic_sync",
                ],
                "pass_values": {
                    "audio_ear": "ok",
                    "audio_ear_source": "human",
                    "speech_or_vocal_like_content": "none_intelligible",
                    "diegetic_sync": "coherent",
                },
            },
        },
        "topology_contract": make_mime_r2v_topology_contract(),
        "prompt": prompt,
        "workflow": {"nodes": [], "links": []},
    }


def write_h3_mime_r2v(output_dir: Path = RECIPES_DIR) -> bool:
    """Create R2V Mini Mime once and reject any later generated byte drift."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return write_immutable_recipe(
        output_dir / f"{H3_MIME_R2V_NAME}.json",
        make_h3_mime_r2v_recipe(),
    )


def build_all():
    matrix = [
        ("t2v", "low", 864, 480, 124),
        ("t2v", "best", 1344, 768, 124),
        ("i2v", "low", 864, 480, 124),
        ("i2v", "best", 1344, 768, 124),
        ("r2v", "low", 864, 480, 124),
        ("r2v", "best", 1344, 768, 124),
    ]

    for mode, tier, w, h, f in matrix:
        name = f"h3_{mode}_{tier}"
        tier_type = "smoke" if tier == "low" else "suite"
        recipe_data = {
            "name": name,
            "tier": tier_type,
            "blocked": False
        }

        if name == "h3_i2v_low":
            recipe_data["experiment"] = {
                "campaign": "official_sampler_alignment",
                "variant": "i2v_official_sampler",
                "independent_variable": "sampler_and_guidance_bundle"
            }

        recipe_data.update({
            "contract": {
                "engine": "minimax_h3",
                "mode": mode,
                "width": w,
                "height": h,
                "frames": f,
                "fps": 24.0,
                "duration_s": round(f / 24.0, 2),
                "vram_ceiling_gb": 14.5
            },
            **({"topology_contract": make_topology_contract(mode)} if tier == "best" else {}),
            "prompt": make_h3_prompt(mode, w, h, f, is_best=(tier == "best")),
            "workflow": {
                "nodes": [],
                "links": []
            }
        })

        out_path = RECIPES_DIR / f"{name}.json"
        changed = write_recipe_if_changed(out_path, recipe_data)
        action = "Generated clean recipe" if changed else "Unchanged semantic recipe"
        print(f"{action}: {out_path.name}")

    mime_path = RECIPES_DIR / "h3_mime_i2v.json"
    mime_changed = write_recipe_if_changed(mime_path, make_h3_mime_i2v_recipe())
    mime_action = "Generated experiment recipe" if mime_changed else "Unchanged experiment recipe"
    print(f"{mime_action}: {mime_path.name}")

    mime_r2v_changed = write_h3_mime_r2v()
    mime_r2v_action = (
        "Generated immutable experiment recipe"
        if mime_r2v_changed
        else "Unchanged immutable experiment recipe"
    )
    print(f"{mime_r2v_action}: {H3_MIME_R2V_NAME}.json")

    sentinel_changed = write_h3_i2v_suite_sentinel()
    sentinel_action = (
        "Generated immutable suite sentinel"
        if sentinel_changed
        else "Unchanged immutable suite sentinel"
    )
    print(f"{sentinel_action}: {H3_I2V_SUITE_SENTINEL_NAME}.json")

if __name__ == "__main__":
    build_all()
