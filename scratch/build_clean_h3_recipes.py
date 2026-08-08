#!/usr/bin/env python3
"""
build_clean_h3_recipes.py — Generates clean API format JSON recipes for all six MiniMax H3 lanes.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
RECIPES_DIR = REPO_ROOT / "recipes"

def make_h3_prompt(mode: str, width: int, height: int, frames: int, is_gguf: bool = False):
    """
    Construct API prompt format dictionary for MiniMax H3.
    """
    # 1. UNETLoader
    unet_name = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
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
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "cinematic camera motion across vintage radio control room, warm analog glow, 8k",
                "clip": ["2", 0]
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "blurry, noise, artifacts, distorted, static, oversaturated",
                "clip": ["2", 0]
            }
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
                "prompt": "cinematic portrait, vintage radio control room, warm lighting",
                "width": width,
                "height": height,
                "length": frames,
                "ref_image_size": "match",
                "ref_images": {
                    "ref_image_0": ["11", 0]
                }
            }
        }

    # KSampler
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

    # VAEDecode (Video)
    prompt_nodes["9"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["8", 0],
            "vae": ["3", 0]
        }
    }

    # CreateVideo & SaveVideo
    prompt_nodes["10"] = {
        "class_type": "CreateVideo",
        "inputs": {
            "images": ["9", 0],
            "fps": 24.0
        }
    }

    recipe_name = f"h3_{mode}_{'low' if width == 864 else 'best'}"
    prompt_nodes["12"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["10", 0],
            "filename_prefix": f"{recipe_name}_out",
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
            "blocked": False,
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
        }

        out_path = RECIPES_DIR / f"{name}.json"
        out_path.write_text(json.dumps(recipe_data, indent=2), encoding="utf-8")
        print(f"Generated clean recipe: {out_path.name}")

if __name__ == "__main__":
    build_all()
