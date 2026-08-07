# Models Manifest — Available Local Models

Query timestamp: 2026-08-07 (Verified from live ComfyUI `GET /object_info`)

This manifest lists models available via the local ComfyUI instance (`http://127.0.0.1:8188`). Recipes in `recipes/` must ONLY reference models listed in this manifest.

## Available Local Models

| Category | Model Filename | Path / Store | Notes |
|---|---|---|---|
| Checkpoint | `ltx-video-2b-v0.9.safetensors` | `checkpoints/` | LTX Video 2B base model |
| Checkpoint | `ltx-2.3-22b-dev.safetensors` | `checkpoints/` | LTX Video 2.3 22B model |
| Checkpoint | `ltxv-2b-0.9.8-distilled.safetensors` | `checkpoints/` | LTX Video 2B distilled model |
| UNET / Diffusion | `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | `diffusion_models/` | Wan 2.2 I2V 14B FP8 model |
| UNET / Diffusion | `humo_1.7B_fp16.safetensors` | `diffusion_models/` | HuMo 1.7B FP16 model |
| UNET / Diffusion | `Wan2_1-HuMo-14B_fp8_e4m3fn_scaled_KJ.safetensors` | `diffusion_models/` | HuMo 14B FP8 model |
| VAE | `ltx-2.3-22b-dev_video_vae.safetensors` | `vae/` | LTX Video VAE |
| VAE | `ltx-2.3-22b-dev_audio_vae.safetensors` | `vae/` | LTX Audio VAE |
| VAE | `wan2.2_vae.safetensors` | `vae/` | Wan 2.2 Video VAE |

## Missing / Unloaded Models (BLOCKED)

| Model Set | Required Files | Status | Reason |
|---|---|---|---|
| MiniMax H3 | `fl2va_pruned_int8_convrot`, `qwen3vl_32b_nvfp4_awq`, video VAE, audio VAE | **BLOCKED** | 42.5 GB weight set not present on disk. |
