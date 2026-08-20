# Models Manifest — Available Local Models

Query timestamp: 2026-08-09T17:17:38Z (Verified from the owned live lab ComfyUI via `GET /object_info` and `GET /models/audio_encoders` at `http://127.0.0.1:8199`; no prompt submitted; verified shutdown receipt: `results/humo_diet/phase0_lane_feasibility.json`)

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

### UNET / Diffusion Models (`UNETLoader` & `UnetLoaderGGUF`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `diffusion_models/` | MiniMax H3 FL2VA Pruned INT8 ConvRot diffusion model |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `diffusion_models/` | MiniMax H3 Ref2VA Pruned INT8 ConvRot diffusion model |
| `z_image_turbo_nvfp4.safetensors` | `diffusion_models/` | Z-Image Turbo NVFP4 image diffusion model |
| `Wan2_1-HuMo-14B_fp8_e4m3fn_scaled_KJ.safetensors` | `diffusion_models/` | Wan 2.1 HuMo 14B FP8 video model |
| `humo_1.7B_fp16.safetensors` | `diffusion_models/` | HuMo 1.7B FP16 video model |
| `humo_17B_fp8_e4m3fn.safetensors` | `diffusion_models/` | HuMo 17B FP8 video model |
| `ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors` | `diffusion_models/` | LTX Video 2.3 22B Transformer FP8 |
| `lumina_2_model_bf16.safetensors` | `diffusion_models/` | Lumina 2 BF16 diffusion model |
| `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | `diffusion_models/` | Wan 2.2 I2V 14B FP8 model |
| `Wan2.2-TI2V-5B-Q5_K_M.gguf` | `diffusion_models/` | Wan 2.2 TI2V 5B Q5_K_M GGUF model (`UnetLoaderGGUF`) |
| `ltx-2.3-22b-dev-Q3_K_M.gguf` | `unet/` | LTX Video 2.3 22B Q3_K_M GGUF model (`UnetLoaderGGUF`) |
| `distilled-1.1/ltx-2.3-22b-distilled-1.1-Q3_K_M.gguf` | `unet/` | LTX Video 2.3 22B Distilled Q3_K_M GGUF model (`UnetLoaderGGUF`) |
| `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | `latent_upscale_models/` | LTX Video 2.3 Spatial Upscaler x2 model |
| `LTX-2.5-Distilled-Q3_K_M.gguf` | `diffusion_models/` | LTX Video 2.5 Distilled Q3_K_M GGUF model (`UnetLoaderGGUF`) |

### Text Encoders / CLIP (`CLIPLoader`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `text_encoders/` | Qwen3-VL 32B MiniMax H3 NVFP4 AWQ text encoder |
| `qwen_3_4b_fp8_mixed.safetensors` | `text_encoders/` | Qwen 3.4B FP8 text encoder |
| `qwen_3_4b.safetensors` | `text_encoders/` | Qwen 3.4B text encoder |
| `gemma_2_2b_fp16.safetensors` | `text_encoders/` | Gemma 2 2B FP16 text encoder |
| `gemma_3_12B_it_fp4_mixed.safetensors` | `text_encoders/` | Gemma 3 12B FP4 text encoder |
| `mistral_3_small_flux2_fp4_mixed.safetensors` | `text_encoders/` | Mistral 3 Small text encoder |
| `t5xxl_fp16.safetensors` | `text_encoders/` | T5-XXL FP16 text encoder |
| `t5-base.safetensors` | `text_encoders/` | T5 Base text encoder |
| `t5gemma_b_b_ul2.safetensors` | `text_encoders/` | T5 Gemma UL2 text encoder |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `text_encoders/` | UMT5 XXL FP8 text encoder |
| `ltx-2.3-22b-dev_embeddings_connectors.safetensors` | `text_encoders/` | LTX Video 2.3 22B CLIP connectors |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | `text_encoders/` | Gemma 4 12B LTX 2.5 INT8 text encoder |
| `gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf` | `text_encoders/` | Gemma 4 12B LTX 2.5 Q5_K_M GGUF text encoder |

### Audio Encoders (`AudioEncoderLoader`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `whisper_large_v3_fp16.safetensors` | `audio_encoders/` | HuMo Whisper Large V3 FP16 audio encoder |

### VAEs (`VAELoader`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `minimax_h3_audio_vae_fp32.safetensors` | `vae/` | MiniMax H3 Audio VAE FP32 |
| `minimax_h3_video_vae_fp16.safetensors` | `vae/` | MiniMax H3 Video VAE FP16 |
| `ae.safetensors` | `vae/` | Standard Autoencoder VAE |
| `flux2-vae.safetensors` | `vae/` | Flux 2 VAE |
| `lumina2_ae.safetensors` | `vae/` | Lumina 2 VAE |
| `ltx-2.3-22b-dev_video_vae.safetensors` | `vae/` | LTX Video VAE |
| `ltx-2.3-22b-dev_audio_vae.safetensors` | `vae/` | LTX Audio VAE |
| `wan2.2_vae.safetensors` | `vae/` | Wan 2.2 VAE |
| `wan_2.1_vae.safetensors` | `vae/` | Wan 2.1 VAE |
| `ltx-2.5-video-vae-bf16.safetensors` | `vae/` | LTX Video 2.5 Video VAE BF16 |
| `ltx-2.5-audio-vae-bf16.safetensors` | `vae/` | LTX Video 2.5 Audio VAE BF16 |

### LoRAs (`LoraLoader` & `LoraLoaderModelOnly`)
| Model Filename | Path / Store | Notes |
|---|---|---|
| `ltxv\ltx2\ltx-2.3-22b-distilled-lora-384-1.1.safetensors` | `loras/` | LTX Video 2.3 22B Distilled LoRA 1.1 |
| `ltxv\ltx2\ltx-2.3-22b-distilled-lora-384.safetensors` | `loras/` | LTX Video 2.3 22B Distilled LoRA 1.0 |
| `Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors` | `loras/` | Wan 2.2 5B Fast Full Attention LoRA |
| `lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors` | `loras/` | LightX2V I2V 14B 480p LoRA |

## Verified Active Models
All MiniMax H3 weight files verified byte-exact on disk in `C:\ComfyUI-Models` under license grant at `docs/H3_LICENSE_GRANT.md`.
| `LTX-2.5-Distilled-Q5_K_M.gguf` | `quarantine/diffusion_models/` | LTX Video 2.5 Distilled Q5_K_M GGUF model (`UnetLoaderGGUF`) |
