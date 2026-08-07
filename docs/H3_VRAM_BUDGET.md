# MiniMax H3 VRAM & Operational Budget Analysis

## Hardware & Operating System Invariants
- **Target System**: NVIDIA GeForce RTX 5080 Laptop GPU (16.0 GB VRAM, 14.5 GB / 14,848 MiB Hard Gate Ceiling)
- **Host System RAM**: 63.4 GB total RAM
- **Platform**: Windows 11, PyTorch 2.10.0+cu130, CUDA 13.0
- **Boot Lane**: `lab-8199, sage-free` (SageAttention causes silent QK noise corruption on H3 DiT)
- **Lab Execution Status**: **BLOCKED** across all H3 recipes (zero H3 weights on disk; zero local runs executed).

---

## Provenance Disclaimer
All VRAM peaks, host RAM figures, wall clock times, and NVMe throughput metrics below are **EXTERNAL-REPORTED** claims from third-party sources (Tomiigo Linux benchmark, tnsor_works RTX 5080 test, CG Pixel RTX 3060 test). No numbers have been measured locally by `run_recipe.py` on this system.

---

## Operational Costs & System Impact

1. **NVMe Disk Read Overhead**: Layerwise DiT offloading streams **~268 GB of reads from disk per 5-second generation** (EXTERNAL-REPORTED by Tomiigo). On a laptop NVMe SSD, continuous layerwise streaming increases drive read wear and introduces I-O throughput bottlenecks.
2. **Linux vs. Windows Memory Management Delta**: Third-party low-VRAM benchmarks (7.4–7.6 GB peak) were executed on Linux. Windows 11 WDDM driver allocation adds OS background VRAM overhead (~0.5–1.2 GB), which may raise local Windows VRAM peaks.
3. **Boot-Lane Flag Options**:
   - The Tomiigo external benchmark used `--disable-pinned-memory` and `--reserve-vram 1.5`.
   - **Boot Lane Handling**: These flags are proposed boot-lane options for `boot_lab_server.cmd` if a dedicated H3 server lane is booted. They must NOT be edited silently into the standard `boot_lab_server.cmd`.
4. **Licensing Status**:
   - **Official INT8 Stack**: MiniMax-H3 community license contains US local weight usage restrictions; text remains unread by this lab.
   - **GGUF Stack**: GGUF quantization license status is unknown.

---

## Model Weight Footprint & Total Active Stack

| Component | Model Checkpoint File | Weight Size (GiB) | Offload & Residency Strategy |
|---|---|---|---|
| **DiT Backbone (T2V/I2V)** | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 20.97 GiB | **Layerwise Offload**. Swaps 32 transformer blocks into host system RAM (~268 GB NVMe read traffic). |
| **DiT Backbone (R2V)** | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 20.97 GiB | Replaces FL2VA backbone for multimodal reference conditioning. |
| **Text Encoder** | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15.69 GiB | **Encode-Then-Unload**. Purged from VRAM before DiT sampling initialization. |
| **Video VAE** | `minimax_h3_video_vae_fp16.safetensors` | 5.21 GiB | Tiled temporal & spatial video decode. Loaded during VAE decode. |
| **Audio VAE** | `minimax_h3_audio_vae_fp32.safetensors` | 0.61 GiB | Audio latent decode. Resident during audio synthesis phase. |
| **Total Active Stack** | FL2VA + Qwen3-VL + Video VAE + Audio VAE | **42.48 GiB (~45.6 GB)** | Fits in 63.4 GB system RAM with >18 GB OS headroom. |

---

## Internal Recipe Options & External-Reported Telemetry

### 1. `h3_*_low` (Official INT8 Stack @ 864×480)
- **Resolution & Length**: 864×480, 124 frames (5.17s @ 24 fps, `17k+5` grid k=7), 20 steps.
- **EXTERNAL-REPORTED Metrics**: 7.4 – 7.6 GB VRAM peak, ~10 GB Host RAM, 180s wall clock (Tomiigo Linux 8GB benchmark).
- **Local Lab Status**: **BLOCKED** (Weights missing).

### 2. `h3_*_native_experimental` (Official INT8 Stack @ 1344×768)
- **Resolution & Length**: 1344×768, 124 frames (5.17s @ 24 fps), 20 steps.
- **EXTERNAL-REPORTED Metrics**: 14.6 – 15.3 GB VRAM peak, ~30 GB Host RAM, 525s wall clock (tnsor_works RTX 5080 test).
- **Local Lab Status**: **BLOCKED** (Predicts > 14.5 GB gate line).

### 3. `h3_*_gguf_preview` (GGUF Stack @ 864×480)
- **Model Stack**: `MiniMax-H3-FL2VA-Q3_K_M.gguf` (15.58 GB) + `qwen3vl-32B-MiniMax-H3-Q2_K.gguf` (8.49 GB).
- **EXTERNAL-REPORTED Metrics**: VRAM peak unmeasured (CG Pixel RTX 3060 6GB test).
- **Local Lab Status**: **BLOCKED** (Weights missing; requires GGUF custom nodes).
