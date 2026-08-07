# MiniMax-H3 ComfyUI Community Release Package & Multi-Tier Workflow Matrix

**Primary Author**: Jeffrey Brick / vram-recipe-lab  
**Target Audience**: Community Release for **Low VRAM (6GB–8GB)**, **Mid VRAM (12GB–16GB, RTX 5080 Lab Target)**, and **High VRAM (24GB+)** users.  
**Lab Hardware Invariant**: NVIDIA GeForce RTX 5080 Laptop GPU (16 GB Physical VRAM, 14.5 GB / 14,848 MiB Hard Gate Ceiling), 64 GB System Host RAM, Windows 11.

---

## Executive Summary & Community Shipping Matrix

To ensure maximum accessibility, this ComfyUI workflow package is structured into **three distinct tier presets** tailored for low, mid, and high VRAM hardware. Every user—from a 6GB RTX 3060 to a 24GB RTX 4090 / 5090—gets a fully functional, optimized MiniMax-H3 workflow.

### Multi-Tier Community Release Matrix

| Target Hardware Tier | Workflow Preset | Model Stack | Resolution & Frames | Measured Peak VRAM | Quality & Target Audience |
|---|---|---|---|---|---|
| **Low VRAM (6GB – 8GB)** | `MMH3_LOW_VRAM_6GB_PREVIEW` | GGUF Q3 DiT + Q2 Qwen3-VL | 864×480 / 960×544 (124 frames) | Peak Unmeasured (6GB card) | **Low / Portable Preview** (RTX 3060 6GB/8GB) |
| **Mid VRAM (12GB – 16GB)** | `MMH3_MID_VRAM_16GB_PRODUCTION` | Official INT8 DiT + NVFP4 Encoder | **864×480** (124 frames) | **7.4 – 7.6 GB** | **Certified Production Target** (RTX 4070 / 4080 / 5080 16GB) |
| **High VRAM (24GB+)** | `MMH3_HIGH_VRAM_24GB_NATIVE` | Official INT8 DiT + NVFP4 Encoder | **1344×768 (Native)** (124 frames) | **14.6 – 15.6 GB** | **Native High Fidelity** (RTX 3090 / 4090 / 5090 24GB+) |

---

## 1. Low VRAM Shipping Tier: `MMH3_LOW_VRAM_6GB_PREVIEW`

### Target Hardware
GPUs with 6GB to 8GB VRAM (e.g. NVIDIA GeForce RTX 3060 6GB/8GB, RTX 4050 Laptop).

### Models & Storage Requirements (~29.9 GB total)
- `MiniMax-H3-FL2VA-Q3_K_M.gguf` (15.58 GB) — GGUF Q3 DiT
- `qwen3vl-32B-MiniMax-H3-Q2_K.gguf` (8.49 GB) — GGUF Q2 Text Encoder
- `minimax_h3_video_vae_fp16.safetensors` (5.21 GB)
- `minimax_h3_audio_vae_fp32.safetensors` (0.61 GB)
- *Source Repo*: [`realrebelai/MiniMax-H3_GGUFs`](https://huggingface.co/realrebelai/MiniMax-H3_GGUFs/tree/main)

### Required Custom Nodes
- `ComfyUI-GGUF` (`city96/ComfyUI-GGUF`)
- `ComfyUI-Spectrum-MiniMax-H3` (`xmarre/ComfyUI-Spectrum-MiniMax-H3`)
- `ComfyUI-Easy-Use` (`yolain/Comfyui-Easy-Use`) cache-clearing nodes
- Native `MiniMaxH3SigmaShift`

### Preset Configuration
- **T2V**: 960×544, 124 frames (~5.17s @ 24 fps), 20 steps, Euler sampler, simple scheduler, Sigma Shift 12→3, Spectrum enabled (~20 min render).
- **FLF / I2V**: 864×480, 124 frames, 20 steps (~35 min render).
- **Community Reference**: Grounded in the [CG Pixel RTX 3060 6GB workflow](https://www.youtube.com/watch?v=Kr5SrY5bwJU) & [Civitai tutorial](https://civitai.com/articles/33517).

---

## 2. Mid VRAM Shipping Tier: `MMH3_MID_VRAM_16GB_PRODUCTION`

### Target Hardware & Lab Standard
GPUs with 12GB to 16GB VRAM (e.g. NVIDIA GeForce RTX 4070 / 4080 / RTX 5080 16GB). **This is our lab's certified production target.**

### Models & Storage Requirements (~42.5 GB total)
- `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (20.97 GB) — Official INT8 Image-to-Video / Text-to-Video DiT
- `minimax_h3_ref2va_pruned_int8_convrot.safetensors` (20.97 GB) — Official INT8 Reference-to-Video DiT
- `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (15.69 GB) — Official NVFP4 Text Encoder
- `minimax_h3_video_vae_fp16.safetensors` (5.21 GB)
- `minimax_h3_audio_vae_fp32.safetensors` (0.61 GB)
- *Source Repo*: [`Comfy-Org/MiniMax-H3`](https://huggingface.co/Comfy-Org/MiniMax-H3)

### Benchmark Telemetry ([`Tomiigo/minimax-h3-16gb`](https://github.com/Tomiigo/minimax-h3-16gb))
- **Resolution & Length**: **864×480**, **124 frames** (5.17s @ 24 fps), 20 steps.
- **Measured VRAM Peak**: **7.4 – 7.6 GB** across 5 consecutive runs (fits comfortably under the 14.5 GB gate line).
- **Measured Host RAM**: ~10 GB.
- **Wall Clock**: ~180 seconds.
- **Recommended Upscale Path**: Render at 864×480, completely unload H3 from VRAM, then run a separate LTX 2.3 ×2 upscale pass.

---

## 3. High VRAM Shipping Tier: `MMH3_HIGH_VRAM_24GB_NATIVE`

### Target Hardware
GPUs with 24GB+ VRAM (e.g. NVIDIA GeForce RTX 3090 / 4090 / RTX 5090 24GB+, RTX A6000).

### Preset Configuration
- **Model Stack**: Official INT8 DiT + NVFP4 / FP16 Text Encoder + VAEs.
- **Resolution & Length**: **1344×768 (Native)**, **124 frames** (5.17s @ 24 fps), 20 steps.
- **Measured Telemetry** ([`tnsor_works`](https://note.com/tnsor_works/n/n5405bf0154d9) & [`HF Discussion #6`](https://huggingface.co/Comfy-Org/MiniMax-H3/discussions/6)):
  - **Measured VRAM Peak**: **14.6 – 15.6 GB** (15,219 MiB text encoding peak, 15,633 MiB sampling peak).
  - **Measured Host RAM**: 29.8 – 30.7 GB.
  - **Wall Clock**: ~525 seconds.
- **Note for 16GB Cards**: Runs on a physical 16GB RTX 5080 card, but exceeds our strict 14.5 GB (14,848 MiB) lab gate ceiling. High VRAM users with 24GB+ can run this natively without layerwise swapping pressure.

---

## Standalone Windows Startup Command

For shipping the standalone Windows ComfyUI package, the recommended startup command is:

```powershell
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --reserve-vram 2 --fast-disk --preview-method none
```

### Critical Operating Guidelines
1. **Keep DynamicVRAM Enabled**: Do NOT pass `--disable-dynamic-vram`. DynamicVRAM handles block-by-block layerwise DiT swapping into host RAM.
2. **`--lowvram` Flag**: Ineffective while DynamicVRAM is active.
3. **System RAM Allocation**: Require at least 32GB system RAM (64GB recommended for optimal layerwise caching).

---

## Licensing Q&A Notice for Community Release

> [!CAUTION]
> The current [MiniMax-H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) does not grant local-weight execution within the United States. Per the official [Licensing Q&A](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/QA-about-License.md), US-based users must obtain separate MiniMax authorization before local execution or commercial distribution. The hosted API remains globally available.
