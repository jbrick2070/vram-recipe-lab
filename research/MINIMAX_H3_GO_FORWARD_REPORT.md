# MiniMax-H3 Internal Architecture & Options Matrix

**Internal Lab Reference**: `vram-recipe-lab`  
**Lab Hardware Ceiling**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB Physical VRAM, 14.5 GB / 14,848 MiB Hard Gate Ceiling), 64 GB System Host RAM, Windows 11.  
**Local Execution Status**: **BLOCKED** across all H3 recipes (zero H3 weights exist on disk; zero local runs executed).

---

## Executive Summary & Provenance Disclaimers

> [!IMPORTANT]
> **Provenance Invariant**: `vram-recipe-lab` has **NEVER** executed MiniMax-H3. No H3 model weights exist on disk in `C:\ComfyUI-Models`. All numbers, VRAM peaks, system RAM figures, and runtimes cited below are **EXTERNAL-REPORTED** claims from third-party benchmarks. They are not local measurements and do NOT constitute lab certification. All local H3 recipes remain **BLOCKED**.

---

## Internal Option Matrix

| Internal Option | Primary Target Setup | External Reported Source | External-Reported VRAM Peak | External-Reported Host RAM | Local Lab Gate Status |
|---|---|---|---|---|---|
| **Path A (`h3_*_low`)** | Official INT8/NVFP4 (864×480) | Tomiigo Linux/Blackwell Benchmark | **7.4 – 7.6 GB** (EXTERNAL-REPORTED by Tomiigo) | ~10 GB (EXTERNAL-REPORTED) | **BLOCKED** (Weights missing; gate target <= 14.5 GB) |
| **Path A (`h3_*_native_experimental`)** | Official INT8/NVFP4 (1344×768) | tnsor_works RTX 5080 Test | **14.6 – 15.3 GB** (EXTERNAL-REPORTED by tnsor_works) | ~30 GB (EXTERNAL-REPORTED) | **BLOCKED** (Predicts > 14.5 GB gate line) |
| **Path B (`h3_*_gguf_preview`)** | GGUF Q3 DiT / Q2 Encoder (864×480) | CG Pixel RTX 3060 Test | Peak Unmeasured (EXTERNAL-REPORTED on 6GB card) | Unreported | **BLOCKED** (Weights missing; requires GGUF nodes) |

---

## Option 1: Official INT8 Weight Stack (Path A)

### Model Footprint (~42.5 GB total on disk)
- `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (20.97 GB) — Official INT8 DiT (T2V/I2V)
- `minimax_h3_ref2va_pruned_int8_convrot.safetensors` (20.97 GB) — Official INT8 DiT (R2V)
- `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (15.69 GB) — Official NVFP4 Text Encoder
- `minimax_h3_video_vae_fp16.safetensors` (5.21 GB)
- `minimax_h3_audio_vae_fp32.safetensors` (0.61 GB)

### External-Reported Telemetry ([Tomiigo Benchmark](https://github.com/Tomiigo/minimax-h3-16gb/blob/cc3e8445d21f1909b62432e018e3d4fd390cccb9/README.md))
- **Source Environment**: Linux, PyTorch, CUDA, physical GPU VRAM restricted to 8,188 MiB, system RAM restricted to 32 GB.
- **Parameters**: 864×480, 124 frames (5.17s @ 24 fps), 20 steps.
- **EXTERNAL-REPORTED Metrics**: 7.4–7.6 GB VRAM peak, ~10 GB host RAM, ~180s wall clock, **~268 GB NVMe read traffic** per run from layerwise DiT block swapping.

---

## Option 2: GGUF Quantized Stack (Path B)

### Model Footprint (~29.9 GB total on disk)
- `MiniMax-H3-FL2VA-Q3_K_M.gguf` (15.58 GB) — Quantized Q3 DiT
- `qwen3vl-32B-MiniMax-H3-Q2_K.gguf` (8.49 GB) — Quantized Q2 Text Encoder
- `minimax_h3_video_vae_fp16.safetensors` (5.21 GB)
- `minimax_h3_audio_vae_fp32.safetensors` (0.61 GB)

### External-Reported Telemetry ([CG Pixel Test](https://www.youtube.com/watch?v=Kr5SrY5bwJU))
- **Source Environment**: Windows, RTX 3060 6GB card.
- **EXTERNAL-REPORTED Metrics**: Rendered 864×480 / 960×544 in ~35 mins. VRAM peak and host RAM were **unmeasured**. One FLF attempt OOMed before succeeding on requeue.

---

## Operational Costs & Unknowns

1. **NVMe Wear & Storage Strain**: Layerwise DiT swapping streams **~268 GB of reads from disk per generation**. On a laptop NVMe SSD, frequent generations accelerate drive wear and produce thermal/I-O latency.
2. **Linux vs. Windows Delta**: The Tomiigo 7.4–7.6 GB report was measured on Linux. Windows WDDM driver memory management adds OS VRAM overhead (~0.5–1.2 GB), which may push VRAM higher on Windows.
3. **Licensing Status**:
   - **Official Stack License**: MiniMax-H3 community license contains US usage restrictions; license text remains unread by this lab.
   - **GGUF Stack License**: Quantized GGUF license status is unknown.
