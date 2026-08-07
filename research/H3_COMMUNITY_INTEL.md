# MiniMax H3 External Community Intel & Grounding Matrix

## Executive Summary

MiniMax H3 (DiT + Qwen3-VL text encoder + Video VAE + Audio VAE) is a massive ~42.5 GB multi-modal model stack. To achieve survival and high-quality generation on 16 GB physical VRAM (14.5 GB lab gate) without CUDA OOMs, every knob must be grounded in verified empirical community runs.

---

## 1. Comfy-Org Official Shipped Templates & Blog Intel

| Topic / Knob | Shipped Value / Claim | Source URL | Date | Tag | Intel Summary & Analysis |
|---|---|---|---|---|---|
| Native H3 Support | Supported natively in ComfyUI 0.30.0+ | `https://docs.comfy.org/tutorials/video/minimax/minimax-h3` | 2026-08-05 | **VERIFIED** | Official Comfy-Org release blog & tutorial detailing native MiniMax H3 nodes (`MiniMaxH3TextToVideo`, `MiniMaxH3ImageToVideo`, `MiniMaxH3ReferenceToVideo`). |
| Official Grid Formula | `17k + 5` frames grid (124 frames @ 24fps = ~5.17s) | `https://github.com/Comfy-Org/ComfyUI/pull/15200` | 2026-08-05 | **VERIFIED** | DiT frame count math requires `17k + 5` frames. 124 frames (k=7) is the standard 5-second production length. |
| Default Resolution | 1344x768 (Native) vs 864x480 (Low-VRAM) | `https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_t2v.json` | 2026-08-05 | **VERIFIED** | Shipped template uses 1344x768 natively, but low-VRAM runs require 864x480 to stay under 14.5 GB gate line. |
| SageAttention Flag | CLI `--use-sage-attention` default recommendation | `https://github.com/Comfy-Org/ComfyUI/issues/15263` | 2026-08-06 | **FOLKLORE** | Global CLI flag causes silent QK noise corruption on H3 DiT. Boot lane must be `sage-free` or use `MiniMaxH3MemoryEfficientSageAttentionPatch`. |

---

## 2. HM-RunningHub & Tomiigo Controlled Offload Intel

| Topic / Knob | Value / Setting | Source URL | Date | Tag | Intel Summary & Analysis |
|---|---|---|---|---|---|
| **Controlled 8GB Benchmark** | Peak VRAM **7.4 – 7.6 GB**, ~10 GB Host RAM, 180s wall clock | `https://github.com/Tomiigo/minimax-h3-16gb/blob/cc3e8445d21f1909b62432e018e3d4fd390cccb9/README.md` | 2026-08-06 | **VERIFIED** | Controlled Blackwell/Linux test on GPU capped to 8,188 MiB & 32 GB RAM at 864x480, 124 frames, 20 steps with `--reserve-vram 1.5` / `--reserve-vram 2`. **Guaranteed PASS under 14.5 GB gate**. |
| INT8 DiT Model | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (20.97 GB) | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3/blob/main/nodes.py` | 2026-08-06 | **VERIFIED** | Single-file INT8 quantized DiT weights reduce VRAM load by ~50% compared to full FP16. |
| Layerwise Offload | Block-by-block DiT offloading to host system RAM | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3` | 2026-08-06 | **VERIFIED** | Non-block modules stay staged; 32 transformer blocks are prefetched and offloaded dynamically into system RAM during sampling steps (~268 GB NVMe read traffic). |
| Weight Release | Drop ~40% of adaLN precompute weights after step calculation | `https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3/blob/main/nodes.py` | 2026-08-06 | **VERIFIED** | Code analysis shows explicit memory releases after adaLN calculation, dropping ~40% temporary activation memory per step. |

---

## 3. RTX 5080 Native Resolution & Failure Modes Intel

| Issue / Benchmark | Measured Value / Symptom | Source URL | Date | Tag | Intel Summary & Remediation |
|---|---|---|---|---|---|
| **RTX 5080 Native 1344x768 Peak** | Peak VRAM **14.6 – 15.3 GB**, Host RAM ~30 GB, 525s wall clock | `https://note.com/tnsor_works/n/n5405bf0154d9` | 2026-08-06 | **VERIFIED** | Actual RTX 5080 16GB benchmark proving native 1344x768 **exceeds our 14.5 GB (14,848 MiB) gate line**. |
| **HF Discussion #6 Memory Breakdown** | Text encoder 15,219 MiB; Sampling 14,437 MiB; Peak 15,633 MiB | `https://huggingface.co/Comfy-Org/MiniMax-H3/discussions/6#6a742d9f70eecde8c2353b6e` | 2026-08-06 | **VERIFIED** | Detailed memory analysis confirming text encoding alone spikes VRAM past 14.5 GB at native resolution. |
| **6GB RTX 3060 GGUF Workflow** | Functional preview lane; Q3 DiT + Q2 encoder; ~35 min render | `https://www.youtube.com/watch?v=Kr5SrY5bwJU` / `https://civitai.com/articles/33517` | 2026-08-06 | **VERIFIED** | Proves completion on 6GB card at 864x480 / 960x544, but peak VRAM unmeasured and quality is preview-tier. |
| 4GB Anecdote | "Runs on 4GB GPU via CPU offload" | `https://reddit.com/r/ComfyUI` | 2026-08-06 | **FOLKLORE** | Unverified anecdote missing model, resolution, and output receipts. |

---

## 4. Grounded Hardware & VRAM Tier Matrix

| Setup / VRAM Tier | Quantization Stack | Target Resolution & Frames | Measured Peak VRAM | Source URL | Tag | Verdict |
|---|---|---|---|---|---|---|
| **6GB GGUF Preview (`Recipe A`)** | Q3 DiT + Q2 Qwen3-VL | 864x480 / 960x544 (124 frames) | Peak Unmeasured (6GB card) | `https://civitai.com/articles/33517` | **VERIFIED** | **Portable Preview Lane** (low motion fidelity). |
| **16GB Production Target (`Recipe B`)** | Official INT8 DiT + NVFP4 Encoder | **864x480** (124 frames) | **7.4 – 7.6 GB** | `https://github.com/Tomiigo/minimax-h3-16gb` | **VERIFIED** | **Certified PASS** (under 14.5 GB gate line). |
| **16GB Experimental Native (`Recipe C`)** | Official INT8 DiT + NVFP4 Encoder | **1344x768** (124 frames) | **14.6 – 15.3 GB** | `https://note.com/tnsor_works/n/n5405bf0154d9` | **VERIFIED** | **EXPERIMENTAL** (exceeds 14.5 GB gate line). |
