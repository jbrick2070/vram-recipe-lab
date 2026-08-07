# Models Manifest — Available Local Models

Query timestamp: 2026-08-07

This manifest lists models available via the local ComfyUI instance (`http://127.0.0.1:8188`) or registered on disk for recipe validation. Recipes in `recipes/` must ONLY reference models listed in this manifest.

## Available Models

| Category | Model Filename | Path / Store | Notes |
|---|---|---|---|
| Checkpoint / UNET | `v1-5-pruned-emaonly.safetensors` | `checkpoints/` | SD 1.5 standard base model for t2i seed pair |
| Checkpoint / UNET | `Wan2.2-TI2V-5B-Q5_K_M.gguf` | `unet/` | Wan 2.2 TI2V 5B GGUF base model |
| LoRA | `Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors` | `loras/` | FastWan 5B distillation LoRA |
| Text Encoder | `umt5-xxl-encoder-Q5_K_M.gguf` | `text_encoders/` | uMT5 XXL encoder for Wan recipes |
| VAE | `wan2.2_vae.safetensors` | `vae/` | Wan 2.2 VAE |

## Missing / Unloaded Models (BLOCKED)

| Model Set | Required Files | Status | Reason |
|---|---|---|---|
| MiniMax H3 | `fl2va_pruned_int8_convrot`, `qwen3vl_32b_nvfp4_awq`, video VAE, audio VAE | **BLOCKED** | 42.5 GB weight set not present on disk. |
