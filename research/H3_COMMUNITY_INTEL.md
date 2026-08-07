# MiniMax H3 External Community Intel & Grounding Matrix

## Executive Summary & Provenance Warning

> [!IMPORTANT]
> **PROVENANCE NOTICE**: `vram-recipe-lab` has **NEVER** executed MiniMax-H3. Zero H3 model weights exist on disk in `C:\ComfyUI-Models`. The tags below distinguish third-party claims reported with code/receipts (**EXTERNAL-REPORTED**) from unverified stories (**FOLKLORE**). No row represents local lab certification. Local recipe status is **BLOCKED**.

---

## 1. Upstream Comfy-Org Documentation & Specifications

| Topic / Knob | Value / Claim | External Source URL | Date | Provenance Tag | Intel Summary & Analysis |
|---|---|---|---|---|---|
| Native H3 Support | Supported natively in ComfyUI 0.30.0+ | `https://docs.comfy.org/tutorials/video/minimax/minimax-h3` | 2026-08-05 | **EXTERNAL-REPORTED (Comfy-Org)** | Official Comfy-Org tutorial detailing native MiniMax H3 nodes (`MiniMaxH3TextToVideo`, `MiniMaxH3ImageToVideo`, `MiniMaxH3ReferenceToVideo`). |
| Frame Grid Formula | `17k + 5` frames grid (124 frames @ 24fps = ~5.17s) | `https://github.com/Comfy-Org/ComfyUI/pull/15200` | 2026-08-05 | **EXTERNAL-REPORTED (Comfy-Org PR #15200)** | DiT frame count math requires `17k + 5` frames. 124 frames (k=7) is the standard 5-second production length. |
| Default Resolution | 1344x768 (Native) vs 864x480 (Low-VRAM) | `https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_t2v.json` | 2026-08-05 | **EXTERNAL-REPORTED (Comfy-Org Template)** | Shipped template uses 1344x768 natively, but low-VRAM runs require 864x480 to stay under 14.5 GB gate line. |
| SageAttention Flag | CLI `--use-sage-attention` default recommendation | `https://github.com/Comfy-Org/ComfyUI/issues/15263` | 2026-08-06 | **FOLKLORE** | Global CLI flag causes silent QK noise corruption on H3 DiT. Boot lane must be `sage-free` or use `MiniMaxH3MemoryEfficientSageAttentionPatch`. |

---

## 2. External Third-Party Benchmarks

| Benchmark Topic | External Value / Setting | External Source URL | Date | Provenance Tag | External Intel Summary |
|---|---|---|---|---|---|
| **Low-VRAM 8GB Benchmark** | Peak VRAM **7.4 – 7.6 GB**, ~10 GB Host RAM, 180s wall clock | `https://github.com/Tomiigo/minimax-h3-16gb/blob/cc3e8445d21f1909b62432e018e3d4fd390cccb9/README.md` | 2026-08-06 | **EXTERNAL-REPORTED (Tomiigo Linux/Blackwell Test)** | Controlled Linux test on GPU capped to 8,188 MiB & 32 GB RAM at 864x480, 124 frames, 20 steps with `--reserve-vram 1.5` / `--reserve-vram 2`. Unverified on Windows. |
| INT8 DiT Model | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (20.97 GB) | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3/blob/main/nodes.py` | 2026-08-06 | **EXTERNAL-REPORTED (HM-RunningHub)** | Single-file INT8 quantized DiT weights reduce VRAM load by ~50% compared to full FP16. |
| Layerwise Offload | Block-by-block DiT offloading to host system RAM | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3` | 2026-08-06 | **EXTERNAL-REPORTED (HM-RunningHub)** | Non-block modules stay staged; 32 transformer blocks are prefetched and offloaded dynamically into system RAM during sampling steps (~268 GB NVMe read traffic). |
| **RTX 5080 Native 1344x768 Peak** | Peak VRAM **14.6 – 15.3 GB**, Host RAM ~30 GB, 525s wall clock | `https://note.com/tnsor_works/n/n5405bf0154d9` | 2026-08-06 | **EXTERNAL-REPORTED (tnsor_works RTX 5080 Test)** | Third-party RTX 5080 16GB benchmark reporting native 1344x768 exceeds 14.5 GB (14,848 MiB) gate line. |
| **HF Discussion #6 Memory** | Text encoder 15,219 MiB; Sampling 14,437 MiB; Peak 15,633 MiB | `https://huggingface.co/Comfy-Org/MiniMax-H3/discussions/6#6a742d9f70eecde8c2353b6e` | 2026-08-06 | **EXTERNAL-REPORTED (HF Discussion #6)** | Third-party memory analysis confirming text encoding alone spikes VRAM past 14.5 GB at native resolution. |
| **6GB RTX 3060 GGUF Workflow** | Functional preview lane; Q3 DiT + Q2 encoder; ~35 min render | `https://www.youtube.com/watch?v=Kr5SrY5bwJU` / `https://civitai.com/articles/33517` | 2026-08-06 | **EXTERNAL-REPORTED (CG Pixel RTX 3060 Test)** | Proves completion on 6GB card at 864x480 / 960x544, but peak VRAM unmeasured. |
| 4GB Anecdote | "Runs on 4GB GPU via CPU offload" | `https://reddit.com/r/ComfyUI` | 2026-08-06 | **FOLKLORE** | Unverified anecdote missing model, resolution, and output receipts. |
