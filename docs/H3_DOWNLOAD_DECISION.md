# MiniMax-H3 Weight Download Decision Brief

**Target Audience**: Internal Pipeline Decision for Jeffrey Brick  
**System Hardware**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB VRAM, 14.5 GB Hard Gate), 63.4 GB System RAM, Windows 11.  
**Current Lab Status**: **BLOCKED** across all H3 recipes (0 bytes of H3 weights on disk).

---

## Executive Overview

This decision brief contrasts **Path A (Official INT8 Stack)** and **Path B (GGUF Quantized Stack)** to provide an honest, unvarnished summary of storage requirements, operational costs, software dependencies, and unblocked recipe coverage.

---

## Option Comparison Matrix

| Option Property | Path A: Official INT8 Stack | Path B: GGUF Quantized Stack |
|---|---|---|
| **Primary Checkpoints** | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (20.97 GB)<br>`qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (15.69 GB)<br>`minimax_h3_video_vae_fp16.safetensors` (5.21 GB)<br>`minimax_h3_audio_vae_fp32.safetensors` (0.61 GB)<br>*(Optional R2V: `minimax_h3_ref2va_pruned_int8_convrot.safetensors`, 20.97 GB)* | `MiniMax-H3-FL2VA-Q3_K_M.gguf` (15.58 GB)<br>`qwen3vl-32B-MiniMax-H3-Q2_K.gguf` (8.49 GB)<br>`minimax_h3_video_vae_fp16.safetensors` (5.21 GB)<br>`minimax_h3_audio_vae_fp32.safetensors` (0.61 GB) |
| **Download Size (Disk Check)** | **42.48 GiB (~45.6 GB)** (FL2VA base stack)<br>*+20.97 GiB if adding R2V* | **29.89 GiB (~32.1 GB)** |
| **Unblocked Matrix Rows** | Unblocks `h3_t2v_low`, `h3_t2v_best`, `h3_i2v_low`, `h3_i2v_best`, `h3_r2v_low`, `h3_r2v_best` | Unblocks GGUF preview variants (`h3_t2v_gguf_preview`, `h3_i2v_gguf_preview`) |
| **Custom Node Dependencies** | Native ComfyUI 0.30.0+ nodes (`MiniMaxH3TextToVideo`, `MiniMaxH3ImageToVideo`, etc.) | Requires `ComfyUI-GGUF` (`UnetLoaderGGUF`), `ComfyUI-Spectrum-MiniMax-H3`, `ComfyUI-Easy-Use` |
| **NVMe Read Cost / Run** | **~268 GB NVMe reads** per generation (EXTERNAL-REPORTED by Tomiigo) from 32-block layerwise swapping | Lower (smaller Q3 DiT weights), exact read volume unreported |
| **VRAM Telemetry Source** | **7.4 – 7.6 GB peak** (EXTERNAL-REPORTED by Tomiigo Linux 8GB test @ 864x480) | Peak VRAM **unmeasured** (EXTERNAL-REPORTED on RTX 3060 6GB card) |
| **Licensing Status** | **Unread**: MiniMax community license contains US local weight usage restrictions | **Unknown**: Quantized GGUF license status unverified |

---

## Technical Dependencies & Custom Node Class Names

- **Path A (Official Stack)**: Uses standard ComfyUI loaders: `UNETLoader`, `CLIPLoader`, `VAELoader`, and native `MiniMaxH3*ToVideo` nodes.
- **Path B (GGUF Stack)**: Requires `ComfyUI-GGUF` custom nodes. `UnetLoaderGGUF` (already verified and present on server for the Wan 5B GGUF recipe lane) loads GGUF diffusion checkpoints.

---

## Key Operational Risks & Cost Drivers

1. **Laptop SSD Wear**: Layerwise DiT streaming reads **~268 GB from disk per 5-second video generation**. Heavy daily testing will cause substantial NVMe read wear and thermal throttling on a laptop SSD.
2. **Windows WDDM Memory Delta**: External low-VRAM benchmarks (7.4–7.6 GB) were conducted on Linux. Windows WDDM VRAM management adds OS overhead (~0.5–1.2 GB), which must be measured locally.
3. **Licensing Caution**: Both paths carry legal licensing caveats for US-based local execution that require legal review prior to public release.
