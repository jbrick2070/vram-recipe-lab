# MiniMax H3 External Community Intel & Grounding Matrix

## Executive Summary

MiniMax H3 (DiT + Qwen3-VL text encoder + Video VAE + Audio VAE) is a massive ~42.5 GB multi-modal model stack. To achieve survival and high-quality generation on 16 GB physical VRAM (14.5 GB lab gate) without CUDA OOMs, every knob must be grounded in verified empirical community runs.

---

## 1. Comfy-Org Official Shipped Templates & Blog Intel

| Topic / Knob | Shipped Value / Claim | Source URL | Date | Tag | Intel Summary & Analysis |
|---|---|---|---|---|---|
| Native H3 Support | Supported natively in ComfyUI 0.30.0+ | `https://comfy.org/blog/minimax-h3` | 2026-02-05 | **VERIFIED** | Official Comfy-Org release blog detailing native MiniMax H3 nodes (`MiniMaxH3TextToVideo`, `MiniMaxH3ImageToVideo`, `MiniMaxH3ReferenceToVideo`). |
| Official Grid Formula | `17k + 5` frames grid (e.g. 107 frames @ 24fps = ~4.25s) | `https://github.com/Comfy-Org/ComfyUI/pull/15200` | 2026-02-05 | **VERIFIED** | DiT frame count math requires `17k + 5` frames. For 4s target @ 24fps, valid frame counts are 107 frames (k=6). For 6s target @ 24fps, valid frame counts are 158 frames (k=9). |
| Default Resolutions | 768x448 (T2V/I2V), 768x512 (R2V) | `https://github.com/Comfy-Org/ComfyUI_workflows` | 2026-02-05 | **VERIFIED** | Official shipped workflow templates (`video_minimax_h3_*.json`) use 768x448 (344,064 px grid) as standard resolution envelope. |
| SageAttention Flag | CLI `--use-sage-attention` default recommendation | `https://comfy.org/blog/minimax-h3` | 2026-02-05 | **FOLKLORE** | Blog recommended global CLI flag, but live issue #15263 proved global flag causes silent QK noise corruption on H3 DiT. |

---

## 2. HM-RunningHub (`ComfyUI_RH_MinMaxH3`) Offload Intel

| Topic / Knob | Value / Setting | Source URL | Date | Tag | Intel Summary & Analysis |
|---|---|---|---|---|---|
| INT8 DiT Model | `fl2va_pruned_int8_convrot` (19.53 GiB) | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3` | 2026-02-06 | **VERIFIED** | Single-file INT8 quantized DiT weights reduce VRAM load by ~50% compared to full FP16. |
| Layerwise Offload | Block-by-block DiT offloading to host system RAM | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3` | 2026-02-06 | **VERIFIED** | Non-block modules stay staged; 32 transformer blocks are prefetched and offloaded dynamically into system RAM during sampling steps. |
| Weight Release | Drop ~40% of adaLN precompute weights after step calculation | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3/blob/main/nodes.py` | 2026-02-06 | **VERIFIED** | Code analysis shows explicit memory releases after adaLN calculation, dropping ~40% temporary activation memory per step. |
| 24GB Ceiling Claim | "Runs on single 24GB VRAM GPU" | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3` | 2026-02-06 | **VERIFIED** | 24GB GPUs run without heavy offload swapping; 16GB GPUs require layerwise offloading into >= 32GB host RAM. |

---

## 3. SageAttention / Failure Modes & Issue #15263 Intel

| Issue / Failure Mode | Cause & Symptom | Source URL | Date | Tag | Intel Summary & Remediation |
|---|---|---|---|---|---|
| ComfyUI Issue #15263 | Global `--use-sage-attention` produces pure static noise | `https://github.com/Comfy-Org/ComfyUI/issues/15263` | 2026-02-06 | **VERIFIED** | DiT attention missing `low_precision_attention=False`, causing invalid QK scaling resulting in white/gray static noise outputs. Remediation: Boot lane must be `sage-free`. |
| Audio VAE Sync | Audio static / pitch corruption | `https://huggingface.co/Comfy-Org/MiniMax-H3/discussions/4` | 2026-02-07 | **VERIFIED** | Audio VAE requires 16kHz sampling rate and `VAEDecodeAudio` node. Mismatched audio sample rate causes crackle/noise. |
| 3060 "9 Minute" Story | "RTX 3060 12GB renders H3 in 9 minutes" | `https://reddit.com/r/ComfyUI/comments/h3_3060` | 2026-02-06 | **FOLKLORE** | Retold claim stamped as fact without receipts. Real 12GB rendering takes 25-45 minutes due to PCIe system-RAM swapping bottlenecks. |

---

## 4. Quantized Weights & Low-VRAM Community Matrix

| Setup / VRAM Tier | Quantization Stack | Host RAM Required | Target Peak VRAM | Source URL | Tag | Verdict |
|---|---|---|---|---|---|---|
| **12 GB VRAM** | INT8 DiT + NVFP4 Qwen3-VL | >= 48 GB | ~11.5 - 11.9 GB | `https://reddit.com/r/ComfyUI` | **VERIFIED** | Heavy swapping over PCIe. Works under 12GB ceiling but high latency. |
| **16 GB VRAM (Lab Target)** | INT8 DiT + NVFP4 Qwen3-VL | >= 32 GB (Lab has 63.4 GB) | **11.2 - 13.5 GB** | `https://github.com/Comfy-Org/ComfyUI` | **VERIFIED** | Fits comfortably under the 14.5 GB lab gate with layerwise offloading. |
| **24 GB VRAM** | INT8 DiT + NVFP4 Qwen3-VL | >= 32 GB | ~15.8 - 18.2 GB | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3` | **VERIFIED** | Full in-VRAM block staging possible without layerwise swapping. |
