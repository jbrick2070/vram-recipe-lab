# H3 Turbo Larry v4 profile manifest

This is the immutable model manifest for the `h3-turbo-larry-v4` Front Office profile. It is intentionally separate from the legacy root manifest so admission of this new candidate cannot rewrite historic recipe identities or receipts.

## Required base H3 assets

| Filename | Managed path family | Role |
|---|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `C:\ComfyUI-Models\diffusion_models\` | FL2VA pruned INT8 diffusion model |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `C:\ComfyUI-Models\text_encoders\` | H3 text encoder |
| `minimax_h3_video_vae_fp16.safetensors` | `C:\ComfyUI-Models\vae\` | Native video decoder |
| `minimax_h3_audio_vae_fp32.safetensors` | `C:\ComfyUI-Models\vae\` | Native audio decoder |

## Explicitly admitted Turbo candidate

| Filename | Managed path | Source | Declared license | Bytes | SHA-256 |
|---|---|---|---|---:|---|
| `minimax_h3_turbo_v4_step600_ema.safetensors` | `C:\ComfyUI-Models\loras\h3-turbo-larry-v4\minimax_h3_turbo_v4_step600_ema.safetensors` | `larryvrh/MiniMax-H3-Turbo-Lora` at `43a74557ac3f6539db8e0f2a959d03feb7a81480` | Apache-2.0, as declared by the upstream model card during the authorized retrieval | 779849816 | `5f3a626cd72c93a8b9318d6760c510bc5092d2ab13aaba1f932c5bab07a416d3` |

## Pinned node support asset

| Filename | Managed path | Role | Bytes | SHA-256 |
|---|---|---|---:|---|
| `h3_silu_temb_grid.safetensors` | `C:\ComfyUI-Models\custom_node_assets\ComfyUI-MiniMax-H3-Turbo\h3_silu_temb_grid.safetensors` | Required support grid for the pinned Turbo node at `546b5028f4934f5129eb6c7142c2f3e461dfddbf`; the source checkout consumes the same bytes through a no-copy hard link | 5510600 | `30eb3c2cc7fb6b470d9717ff840d359313ac27cd64b705e32da1baa10f72d6a8` |

No other model is admitted by this profile. Live discovery through its Sage-free, exact-whitelist server and `/object_info` remains required before queuing the one declared recipe.
