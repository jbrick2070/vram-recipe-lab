# Models Manifest — Available Local Models

Query timestamp: 2026-08-07 (Verified from live lab ComfyUI `GET /object_info` at `http://127.0.0.1:8199`)

This manifest lists all models available on the local lab server (`http://127.0.0.1:8199`). Recipes in `recipes/` must ONLY reference models listed in this manifest.

## Available Local Models

### Checkpoints (`CheckpointLoaderSimple`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `flux1-dev-fp8.safetensors` | `checkpoints/` | Flux.1 Dev FP8 image checkpoint |
| `hunyuan3d-dit-v2-mv.safetensors` | `checkpoints/` | Hunyuan 3D DiT V2 model |
| `ltx-2.3-22b-dev.safetensors` | `checkpoints/` | LTX Video 2.3 22B base checkpoint |
| `ltx-video-2b-v0.9.safetensors` | `checkpoints/` | LTX Video 2B base checkpoint (no text encoder) |
| `ltxv-2b-0.9.8-distilled.safetensors` | `checkpoints/` | LTX Video 2B distilled checkpoint |
| `stable-audio-open-1.0.safetensors` | `checkpoints/` | Stable Audio Open 1.0 audio model |
| `stable_audio_3_small_music.safetensors` | `checkpoints/` | Stable Audio 3 Small Music model |

### UNET / Diffusion Models (`UNETLoader`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `z_image_turbo_nvfp4.safetensors` | `diffusion_models/` | Z-Image Turbo NVFP4 image diffusion model |
| `Wan2_1-HuMo-14B_fp8_e4m3fn_scaled_KJ.safetensors` | `diffusion_models/` | Wan 2.1 HuMo 14B FP8 video model |
| `humo_1.7B_fp16.safetensors` | `diffusion_models/` | HuMo 1.7B FP16 video model |
| `humo_17B_fp8_e4m3fn.safetensors` | `diffusion_models/` | HuMo 17B FP8 video model |
| `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` | `diffusion_models/` | LTX Video 2.3 22B Transformer FP8 |
| `lumina_2_model_bf16.safetensors` | `diffusion_models/` | Lumina 2 BF16 diffusion model |
| `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | `diffusion_models/` | Wan 2.2 I2V 14B FP8 model |
| `Wan2.2-TI2V-5B-Q5_K_M.gguf` | `diffusion_models/` | Wan 2.2 TI2V 5B Q5_K_M GGUF model |

### Text Encoders / CLIP (`CLIPLoader`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `qwen_3_4b_fp8_mixed.safetensors` | `text_encoders/` | Qwen 3.4B FP8 text encoder (used for `qwen_image` / `z_image`) |
| `qwen_3_4b.safetensors` | `text_encoders/` | Qwen 3.4B text encoder |
| `gemma_2_2b_fp16.safetensors` | `text_encoders/` | Gemma 2 2B FP16 text encoder |
| `gemma_3_12B_it_fp4_mixed.safetensors` | `text_encoders/` | Gemma 3 12B FP4 text encoder |
| `mistral_3_small_flux2_fp4_mixed.safetensors` | `text_encoders/` | Mistral 3 Small text encoder |
| `t5xxl_fp16.safetensors` | `text_encoders/` | T5-XXL FP16 text encoder |
| `t5-base.safetensors` | `text_encoders/` | T5 Base text encoder |
| `t5gemma_b_b_ul2.safetensors` | `text_encoders/` | T5 Gemma UL2 text encoder |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `text_encoders/` | UMT5 XXL FP8 text encoder |
| `ltx-2.3-22b-dev_embeddings_connectors.safetensors` | `text_encoders/` | LTX Video 2.3 22B CLIP connectors |

### VAEs (`VAELoader`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `ae.safetensors` | `vae/` | Standard Autoencoder VAE (used for `z_image` / Flux / SD) |
| `flux2-vae.safetensors` | `vae/` | Flux 2 VAE |
| `lumina2_ae.safetensors` | `vae/` | Lumina 2 VAE |
| `ltx-2.3-22b-dev_video_vae.safetensors` | `vae/` | LTX Video VAE |
| `ltx-2.3-22b-dev_audio_vae.safetensors` | `vae/` | LTX Audio VAE |
| `wan2.2_vae.safetensors` | `vae/` | Wan 2.2 VAE |
| `wan_2.1_vae.safetensors` | `vae/` | Wan 2.1 VAE |

## Missing / Unloaded Models (BLOCKED)

| Model Set | Required Files | Status | Reason |
|---|---|---|---|
| MiniMax H3 | `fl2va_pruned_int8_convrot`, `qwen3vl_32b_nvfp4_awq`, video VAE, audio VAE | **BLOCKED** | 42.5 GB weight set not present on disk. |
