#!/usr/bin/env python3
"""
build_clean_h3_recipes.py — Generates clean API format JSON recipes for all six MiniMax H3 lanes.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
RECIPES_DIR = REPO_ROOT / "recipes"


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

def make_h3_prompt(mode: str, width: int, height: int, frames: int, is_gguf: bool = False):
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
                "type": "minimax"
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

    if mode == "t2v":
        # Keep the already-approved T2V lane unchanged.
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
            "prompt": "cinematic camera motion across vintage radio control room, warm analog glow, 8k",
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
                "ref_images": {
                    "ref_image_0": ["11", 0]
                }
            }
        }

    if mode == "t2v":
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

    if mode == "r2v":
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
        "fps": 24.0
    }
    if mode == "r2v":
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
            "prompt": make_h3_prompt(mode, w, h, f),
            "workflow": {
                "nodes": [],
                "links": []
            }
        })

        out_path = RECIPES_DIR / f"{name}.json"
        changed = write_recipe_if_changed(out_path, recipe_data)
        action = "Generated clean recipe" if changed else "Unchanged semantic recipe"
        print(f"{action}: {out_path.name}")

if __name__ == "__main__":
    build_all()
